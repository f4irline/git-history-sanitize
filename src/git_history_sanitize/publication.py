"""Atomic no-replace publication and durability primitives."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
from pathlib import Path

from .errors import SanitizeError

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 4
_UNSUPPORTED_DIRECTORY_SYNC_ERRORS = {errno.EINVAL, errno.ENOTSUP}
if hasattr(errno, "EOPNOTSUPP"):
    _UNSUPPORTED_DIRECTORY_SYNC_ERRORS.add(errno.EOPNOTSUPP)


def publication_error(native_errno: int) -> SanitizeError:
    """Return a stable, path-redacted publication error for a native failure."""
    if native_errno == errno.EEXIST:
        return SanitizeError("Publication destination already exists")
    if native_errno in {errno.EACCES, errno.EPERM}:
        return SanitizeError("Publication failed: permission denied")
    if native_errno in {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}:
        return SanitizeError("Publication failed: insufficient storage")
    if native_errno in {errno.ENOTDIR, errno.EISDIR, errno.EINVAL}:
        return SanitizeError("Publication failed: destination or parent has an incompatible type")
    if native_errno == errno.EXDEV:
        return SanitizeError("Publication failed: source and destination must share a filesystem")
    return SanitizeError("Atomic publication failed")


def publish(source: Path, destination: Path) -> None:
    """Atomically publish a new entry without ever replacing a destination."""
    system = platform.system()
    if system == "Darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameatx_np
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        result = rename(_AT_FDCWD, os.fsencode(source), _AT_FDCWD, os.fsencode(destination), _RENAME_EXCL)
    elif system == "Linux":
        numbers = {"aarch64": 276, "arm64": 276, "x86_64": 316}
        number = numbers.get(platform.machine())
        if number is None:
            raise SanitizeError("Atomic no-replace publication is unsupported on this Linux architecture")
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.syscall(number, _AT_FDCWD, os.fsencode(source), _AT_FDCWD, os.fsencode(destination), _RENAME_NOREPLACE)
    else:
        raise SanitizeError("Atomic no-replace publication is unsupported on this platform")
    if result:
        raise publication_error(ctypes.get_errno())


def set_private_mode(path: Path, mode: int) -> None:
    """Set a deterministic private mode independent of the caller's umask."""
    try:
        os.chmod(path, mode)
    except OSError as error:
        raise SanitizeError("Unable to set private output permissions") from error


def _sync_required(path: Path, failure: str) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as error:
        raise SanitizeError(failure) from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise SanitizeError(failure) from error
    finally:
        os.close(descriptor)


def sync_staged_tree(root: Path) -> None:
    """Persist a verified staged repository before its publication point."""
    paths: list[Path] = []
    for directory, directories, files in os.walk(root, topdown=False):
        directory_path = Path(directory)
        paths.extend(directory_path / name for name in sorted(files))
        paths.append(directory_path)
    for path in paths:
        _sync_required(path, "Staged output synchronization failed before publication")


def sync_staged_file(path: Path) -> None:
    """Persist a staged private receipt before its publication point."""
    _sync_required(path, "Staged receipt synchronization failed before publication")


def sync_staged_directory(path: Path) -> None:
    """Persist the staging root after all staged contents are durable."""
    _sync_required(path, "Staged output synchronization failed before publication")


def sync_published_parent(parent: Path) -> bool:
    """Persist a newly published directory entry when the platform supports it.

    Returns false for documented unsupported directory synchronization. Other
    failures happen after the no-replace rename and must report the published
    output rather than attempt an unsafe rollback.
    """
    try:
        descriptor = os.open(parent, os.O_RDONLY)
    except OSError as error:
        if error.errno in _UNSUPPORTED_DIRECTORY_SYNC_ERRORS:
            return False
        raise SanitizeError(
            "Output was published but parent-directory durability could not be confirmed"
        ) from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno in _UNSUPPORTED_DIRECTORY_SYNC_ERRORS:
            return False
        raise SanitizeError(
            "Output was published but parent-directory durability could not be confirmed"
        ) from error
    finally:
        os.close(descriptor)
    return True
