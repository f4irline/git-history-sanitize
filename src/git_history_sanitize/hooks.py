"""Safe discovery, installation, and scanning of trusted Git hooks."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import SanitizeError
from .git import Repository


class HookError(SanitizeError):
    """Raised for unsupported or unsafe hook metadata."""


@dataclass(frozen=True)
class Hook:
    name: str
    content: bytes
    mode: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class HookInventory:
    hooks: tuple[Hook, ...]
    custom_path: bool

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(hook.name for hook in self.hooks)

    @property
    def warning_categories(self) -> dict[str, tuple[str, ...]]:
        categories: dict[str, list[str]] = {}
        for hook in self.hooks:
            for warning in hook.warnings:
                categories.setdefault(warning, []).append(hook.name)
        return {warning: tuple(names) for warning, names in sorted(categories.items())}


_ABSOLUTE_PATH = re.compile(rb"(?<![A-Za-z0-9_./~-])/[A-Za-z0-9_./~-]+")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_directory(path: Path, roots: tuple[Path, ...]) -> Path:
    candidate = Path(os.path.abspath(path))
    if not any(_inside(candidate, root) for root in roots):
        raise HookError("repository-local core.hooksPath must remain inside the repository")
    current = candidate
    while True:
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise HookError("repository hooks directory must be a real directory")
        if current in roots:
            return candidate
        current = current.parent


def _local_path(repository: Repository) -> tuple[Path, bool]:
    configured = repository.run("config", "--local", "--get", "core.hooksPath", check=False).rstrip(b"\n")
    if not configured:
        return repository.git_dir / "hooks", False
    try:
        value = os.fsdecode(configured)
    except UnicodeError as error:
        raise HookError("repository-local core.hooksPath is invalid") from error
    worktree = repository.worktree_root()
    roots = tuple(root for root in (repository.git_dir, worktree) if root is not None)
    if not roots:
        raise HookError("repository-local core.hooksPath is unavailable")
    candidates = (Path(value),) if os.path.isabs(value) else tuple(root / value for root in roots)
    existing = tuple(candidate for candidate in candidates if candidate.exists())
    if len(existing) != 1:
        raise HookError("repository-local core.hooksPath must name one existing directory")
    return _safe_directory(existing[0], roots), True


def _warnings(content: bytes) -> tuple[str, ...]:
    warnings: list[str] = []
    if content.startswith(b"#!/"):
        warnings.append("absolute-shebang")
    if _ABSOLUTE_PATH.search(content):
        warnings.append("absolute-path")
    return tuple(warnings)


def discover(repository: Repository) -> HookInventory:
    directory, custom_path = _local_path(repository)
    if not custom_path and not directory.exists():
        return HookInventory((), False)
    worktree = repository.worktree_root()
    directory = _safe_directory(
        directory, (repository.git_dir, *(() if worktree is None else (worktree,)))
    )
    hooks: list[Hook] = []
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if entry.name.endswith(".sample"):
                    continue
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                    raise HookError("repository hooks must be regular non-symlink files")
                hook_descriptor = os.open(
                    entry.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor
                )
                with os.fdopen(hook_descriptor, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise HookError("repository hooks must be regular non-symlink files")
                    content = handle.read()
                hooks.append(Hook(entry.name, content, stat.S_IMODE(mode), _warnings(content)))
    finally:
        os.close(descriptor)
    return HookInventory(tuple(sorted(hooks, key=lambda hook: hook.name)), custom_path)


def install(repository: Repository, inventory: HookInventory) -> None:
    if not inventory.hooks and not inventory.custom_path:
        return
    directory = repository.git_dir / "hooks"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise HookError("sanitized hooks directory is unsafe")
    for hook in inventory.hooks:
        destination = directory / hook.name
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(hook.content)
            handle.flush()
            os.fsync(handle.fileno())
        destination.chmod(0o600 | (hook.mode & 0o111))
    if inventory.custom_path:
        repository.run("config", "--local", "core.hooksPath", "hooks")
