"""Native atomic no-replace publication primitives."""

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


def publish(source: Path, destination: Path) -> None:
    """Atomically publish a new filesystem entry without replacing an existing one."""
    system = platform.system()
    libc = ctypes.CDLL(None, use_errno=True)
    if system == "Darwin":
        rename = libc.renameatx_np
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        result = rename(_AT_FDCWD, os.fsencode(source), _AT_FDCWD, os.fsencode(destination), _RENAME_EXCL)
    elif system == "Linux":
        number = 276 if platform.machine() in {"aarch64", "arm64"} else 316
        result = libc.syscall(number, _AT_FDCWD, os.fsencode(source), _AT_FDCWD, os.fsencode(destination), _RENAME_NOREPLACE)
    else:
        raise SanitizeError("Atomic no-replace publication is unsupported on this platform")
    if result:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise SanitizeError("Publication destination already exists")
        raise SanitizeError("Atomic publication failed")


def fsync_path(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
