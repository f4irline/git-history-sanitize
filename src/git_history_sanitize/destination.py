"""Descriptor-safe placement checks and stable, inherited destination reservations."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import unicodedata
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator

from .errors import DestinationError
from .git import hold_process_lock

RESERVATION_PREFIX = ".ghs-destination-lock-"


def reservation_name(basename: str) -> str:
    normalized = unicodedata.normalize("NFC", basename).casefold()
    return RESERVATION_PREFIX + hashlib.sha256(b"v1\0" + os.fsencode(normalized)).hexdigest()


def _parent(path: Path) -> int:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def validate(path: str | Path, protected: tuple[Path, ...], label: str = "Destination") -> Path:
    del label
    original = os.fspath(path)
    candidate = Path(original)
    if not candidate.is_absolute() or any(part in {"", ".", ".."} for part in original.split("/")[1:]) or candidate.name.startswith(RESERVATION_PREFIX):
        raise DestinationError()
    try:
        descriptor = _parent(candidate)
        try:
            try:
                os.stat(candidate.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise DestinationError()
        finally:
            os.close(descriptor)
        if any(candidate == root or root in candidate.parents for root in protected):
            raise DestinationError()
        return candidate
    except (OSError, ValueError) as error:
        raise DestinationError() from error


def _validate_lock(parent: int, name: str, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (
        not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_size != 0
        or opened.st_uid != os.getuid() or opened.st_gid != os.getgid()
        or stat.S_IMODE(opened.st_mode) != 0o600
        or (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)
    ):
        raise DestinationError(reason="reservation_unsafe")


@contextmanager
def reserve(paths: tuple[Path, ...], protected: tuple[Path, ...]) -> Iterator[None]:
    """Never unlink or explicitly unlock: inherited children own the same flock."""
    for index, path in enumerate(paths):
        validate(path, protected)
        if any(path == other or path in other.parents or other in path.parents for other in paths[:index]):
            raise DestinationError()
    with ExitStack() as stack:
        entries: list[tuple[int, int, str, int, Path]] = []
        try:
            for path in paths:
                parent = _parent(path)
                stack.callback(os.close, parent)
                identity = os.fstat(parent)
                entries.append((identity.st_dev, identity.st_ino, reservation_name(path.name), parent, path))
            keys = [(device, inode, name) for device, inode, name, _, _ in entries]
            if len(set(keys)) != len(keys):
                raise DestinationError()
            for _, _, name, parent, _ in sorted(entries):
                flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
                try:
                    descriptor = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
                    stack.callback(os.close, descriptor)
                    os.fchmod(descriptor, 0o600)
                except FileExistsError:
                    descriptor = os.open(name, flags, dir_fd=parent)
                    stack.callback(os.close, descriptor)
                _validate_lock(parent, name, descriptor)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise DestinationError(reason="busy") from error
                _validate_lock(parent, name, descriptor)
                stack.enter_context(hold_process_lock(descriptor))
            for path in paths:
                validate(path, protected)
        except (OSError, ValueError) as error:
            raise DestinationError(reason="reservation_unsafe") from error
        yield
