"""Private, ownership-marked temporary workspaces and explicit stale cleanup."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal

from .errors import InterruptionError, UsageError, WorkspaceError


PREFIX = ".git-history-sanitize-"
MANIFEST_NAME = "ownership.json"
LOCK_NAME = "lock"
MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 4096
_ID = re.compile(r"[0-9a-f]{32}\Z")
_NAME = re.compile(re.escape(PREFIX) + r"([0-9a-f]{32})\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
WorkspaceState = Literal["active", "interrupted", "stale", "ambiguous"]


@dataclass(frozen=True)
class WorkspaceRecord:
    id: str
    state: WorkspaceState
    role: str | None = None


def _parent(path: str | Path) -> tuple[Path, int, os.stat_result]:
    candidate = Path(path)
    if not candidate.is_absolute() or any(part in {".", ".."} for part in candidate.parts):
        raise UsageError("Workspace parent must be an absolute path without aliases")
    descriptor = None
    try:
        descriptor = os.open("/", _DIRECTORY_FLAGS)
        for part in candidate.parts[1:]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        details = os.fstat(descriptor)
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise WorkspaceError("Workspace parent is unavailable") from error
    if not stat.S_ISDIR(details.st_mode):
        os.close(descriptor)
        raise WorkspaceError("Workspace parent is not a directory")
    return candidate, descriptor, details


def _write_file(directory_fd: int, name: str, content: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        os.fchmod(descriptor, 0o600)
        written = 0
        while written < len(content):
            count = os.write(descriptor, content[written:])
            if count == 0:
                raise WorkspaceError("Workspace metadata write did not complete")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    content = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(content) > MAX_MANIFEST_BYTES:
        raise WorkspaceError("Workspace ownership metadata is too large")
    return content


def _read_regular_file(directory_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_uid != os.getuid()
            or details.st_gid != os.getgid()
        ):
            raise WorkspaceError("Workspace metadata is not privately owned")
        content = os.read(descriptor, MAX_MANIFEST_BYTES + 1)
        if len(content) > MAX_MANIFEST_BYTES:
            raise WorkspaceError("Workspace metadata exceeds its size limit")
        return content, details
    finally:
        os.close(descriptor)


def _load_manifest(
    root_fd: int,
    workspace_id: str,
    parent_details: os.stat_result,
    root_details: os.stat_result,
) -> dict[str, object]:
    content, _ = _read_regular_file(root_fd, MANIFEST_NAME)
    try:
        manifest = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("Workspace ownership metadata is invalid") from error
    required = {
        "version", "id", "uid", "gid", "pid", "created_ns", "state", "role",
        "parent_dev", "parent_ino", "workspace_dev", "workspace_ino",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise WorkspaceError("Workspace ownership metadata has an invalid schema")
    integers = (
        "version", "uid", "gid", "pid", "created_ns", "parent_dev", "parent_ino",
        "workspace_dev", "workspace_ino",
    )
    if any(type(manifest[key]) is not int for key in integers):
        raise WorkspaceError("Workspace ownership metadata has invalid values")
    if (
        manifest["version"] != MANIFEST_VERSION
        or manifest["id"] != workspace_id
        or manifest["uid"] != os.getuid()
        or manifest["gid"] != os.getgid()
        or manifest["state"] not in {"active", "interrupted"}
        or manifest["role"] not in {"rewrite", "receipt"}
        or manifest["parent_dev"] != parent_details.st_dev
        or manifest["parent_ino"] != parent_details.st_ino
        or manifest["workspace_dev"] != root_details.st_dev
        or manifest["workspace_ino"] != root_details.st_ino
    ):
        raise WorkspaceError("Workspace ownership metadata does not match its directory")
    return manifest


def _lock(root_fd: int) -> tuple[int, bool]:
    descriptor = os.open(LOCK_NAME, os.O_RDWR | os.O_NOFOLLOW, dir_fd=root_fd)
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_uid != os.getuid()
        or details.st_gid != os.getgid()
    ):
        os.close(descriptor)
        raise WorkspaceError("Workspace lock is not privately owned")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return descriptor, False
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, True


def _open_owned(
    parent_fd: int,
    parent_details: os.stat_result,
    name: str,
    workspace_id: str,
) -> tuple[int, os.stat_result, dict[str, object], int, bool]:
    root_details = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISDIR(root_details.st_mode)
        or stat.S_IMODE(root_details.st_mode) != 0o700
        or root_details.st_uid != os.getuid()
        or root_details.st_gid != os.getgid()
        or root_details.st_dev != parent_details.st_dev
    ):
        raise WorkspaceError("Workspace directory is not privately owned")
    root_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    try:
        opened = os.fstat(root_fd)
        if (opened.st_dev, opened.st_ino) != (root_details.st_dev, root_details.st_ino):
            raise WorkspaceError("Workspace directory was replaced")
        manifest = _load_manifest(root_fd, workspace_id, parent_details, opened)
        lock_fd, acquired = _lock(root_fd)
        return root_fd, opened, manifest, lock_fd, acquired
    except BaseException:
        os.close(root_fd)
        raise


def _remove_contents(directory_fd: int) -> None:
    with os.scandir(directory_fd) as entries:
        names = [entry.name for entry in entries]
    for name in names:
        details = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(details.st_mode):
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (details.st_dev, details.st_ino):
                    raise WorkspaceError("Workspace content was replaced")
                _remove_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def _remove_root(
    parent_fd: int,
    name: str,
    root_fd: int,
    root_details: os.stat_result,
) -> None:
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (root_details.st_dev, root_details.st_ino):
        raise WorkspaceError("Workspace directory was replaced")
    _remove_contents(root_fd)
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (root_details.st_dev, root_details.st_ino):
        raise WorkspaceError("Workspace directory was replaced")
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _record(
    parent_fd: int,
    parent_details: os.stat_result,
    name: str,
    workspace_id: str,
) -> WorkspaceRecord:
    root_fd = lock_fd = None
    try:
        root_fd, _, manifest, lock_fd, acquired = _open_owned(
            parent_fd, parent_details, name, workspace_id
        )
        state: WorkspaceState
        if not acquired:
            state = "active"
        elif manifest["state"] == "interrupted":
            state = "interrupted"
        else:
            state = "stale"
        return WorkspaceRecord(workspace_id, state, str(manifest["role"]))
    except (OSError, WorkspaceError, ValueError, TypeError):
        return WorkspaceRecord(workspace_id, "ambiguous")
    finally:
        if lock_fd is not None:
            if lock_fd >= 0:
                os.close(lock_fd)
        if root_fd is not None:
            os.close(root_fd)


class Workspace:
    """One locked sanitizer-owned directory on a publication filesystem."""

    def __init__(
        self,
        parent: Path,
        parent_fd: int,
        parent_details: os.stat_result,
        path: Path,
        root_fd: int,
        root_details: os.stat_result,
        lock_fd: int,
        workspace_id: str,
        role: str,
        manifest: dict[str, object],
    ):
        self.parent = parent
        self._parent_fd = parent_fd
        self._parent_details = parent_details
        self.path = path
        self._root_fd = root_fd
        self._root_details = root_details
        self._lock_fd = lock_fd
        self.id = workspace_id
        self.role = role
        self._manifest = manifest
        self._closed = False

    @classmethod
    def create(
        cls,
        parent: str | Path,
        *,
        workspace_id: str | None = None,
        role: Literal["rewrite", "receipt"] = "rewrite",
    ) -> "Workspace":
        parent_path, parent_fd, parent_details = _parent(parent)
        workspace_id = workspace_id or secrets.token_hex(16)
        if _ID.fullmatch(workspace_id) is None:
            os.close(parent_fd)
            raise WorkspaceError("Workspace ID is invalid")
        name = PREFIX + workspace_id
        root_fd = lock_fd = None
        created = False
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            created = True
            root_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            os.fchmod(root_fd, 0o700)
            root_details = os.fstat(root_fd)
            if root_details.st_dev != parent_details.st_dev:
                raise WorkspaceError("Workspace is not on its parent filesystem")
            lock_fd = os.open(
                LOCK_NAME,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root_fd,
            )
            os.fchmod(lock_fd, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            manifest: dict[str, object] = {
                "version": MANIFEST_VERSION,
                "id": workspace_id,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "pid": os.getpid(),
                "created_ns": time.time_ns(),
                "state": "active",
                "role": role,
                "parent_dev": parent_details.st_dev,
                "parent_ino": parent_details.st_ino,
                "workspace_dev": root_details.st_dev,
                "workspace_ino": root_details.st_ino,
            }
            _write_file(root_fd, MANIFEST_NAME, _manifest_bytes(manifest))
            os.fsync(root_fd)
            os.fsync(parent_fd)
            return cls(
                parent_path,
                parent_fd,
                parent_details,
                parent_path / name,
                root_fd,
                root_details,
                lock_fd,
                workspace_id,
                role,
                manifest,
            )
        except BaseException as error:
            if created and root_fd is not None:
                try:
                    _remove_root(parent_fd, name, root_fd, os.fstat(root_fd))
                except BaseException:
                    pass
            if lock_fd is not None:
                os.close(lock_fd)
            if root_fd is not None:
                os.close(root_fd)
            os.close(parent_fd)
            if isinstance(error, (InterruptionError, WorkspaceError)):
                raise
            raise WorkspaceError("Workspace creation failed") from error

    def create_file(self, name: str) -> tuple[int, Path]:
        if not name or "/" in name or name in {".", "..", MANIFEST_NAME, LOCK_NAME}:
            raise WorkspaceError("Workspace file name is invalid")
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=self._root_fd,
            )
            os.fchmod(descriptor, 0o600)
        except OSError as error:
            raise WorkspaceError("Workspace file creation failed") from error
        return descriptor, self.path / name

    @property
    def lock_descriptor(self) -> int:
        return self._lock_fd

    def _mark_interrupted(self) -> None:
        self._manifest["state"] = "interrupted"
        content = _manifest_bytes(self._manifest)
        descriptor = os.open(MANIFEST_NAME, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=self._root_fd)
        try:
            written = 0
            while written < len(content):
                count = os.write(descriptor, content[written:])
                if count == 0:
                    raise WorkspaceError("Workspace metadata write did not complete")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(self._root_fd)

    def close(self, *, interrupted: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        cleanup_error: BaseException | None = None
        try:
            if interrupted:
                try:
                    self._mark_interrupted()
                except OSError:
                    pass
            else:
                _remove_root(
                    self._parent_fd,
                    self.path.name,
                    self._root_fd,
                    self._root_details,
                )
        except BaseException as error:
            cleanup_error = error
        finally:
            os.close(self._lock_fd)
            os.close(self._root_fd)
            os.close(self._parent_fd)
        if cleanup_error is not None:
            raise WorkspaceError("Workspace cleanup failed") from cleanup_error

    def __enter__(self) -> "Workspace":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.close(interrupted=isinstance(exception, InterruptionError))
        return False


def list_workspaces(parent: str | Path) -> tuple[WorkspaceRecord, ...]:
    """List exact immediate sanitizer entries without exposing their paths."""
    _, parent_fd, parent_details = _parent(parent)
    try:
        records: list[WorkspaceRecord] = []
        with os.scandir(parent_fd) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            match = _NAME.fullmatch(name)
            if match is not None:
                records.append(_record(parent_fd, parent_details, name, match.group(1)))
        return tuple(records)
    finally:
        os.close(parent_fd)


def clean_workspace(parent: str | Path, workspace_id: str) -> WorkspaceRecord:
    """Delete one exact, valid, unlocked sanitizer workspace."""
    if _ID.fullmatch(workspace_id) is None:
        raise UsageError("Workspace ID must be an exact opaque ID")
    _, parent_fd, parent_details = _parent(parent)
    name = PREFIX + workspace_id
    root_fd = lock_fd = None
    try:
        root_fd, root_details, manifest, lock_fd, acquired = _open_owned(
            parent_fd, parent_details, name, workspace_id
        )
        if not acquired:
            raise WorkspaceError("Active workspaces cannot be cleaned")
        state: WorkspaceState = "interrupted" if manifest["state"] == "interrupted" else "stale"
        _remove_root(parent_fd, name, root_fd, root_details)
        return WorkspaceRecord(workspace_id, state, str(manifest["role"]))
    except FileNotFoundError as error:
        raise WorkspaceError("Workspace does not exist") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise WorkspaceError("Symlinked workspaces cannot be cleaned") from error
        raise WorkspaceError("Workspace cleanup was refused") from error
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent_fd)
