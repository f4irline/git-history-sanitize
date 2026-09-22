"""Small, binary-safe wrappers around the Git command line."""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .errors import DependencyError, SourceError
from .oci_toolchain import ToolchainManifestError, load_required_manifest


OCI_MANIFEST_SENTINEL = Path("/usr/local/etc/git-history-sanitize/oci-manifest-required")
_SIGNATURE_MARKERS = (
    b"-----BEGIN PGP SIGNATURE-----",
    b"-----BEGIN SSH SIGNATURE-----",
    b"-----BEGIN CMS-----",
    b"-----BEGIN SIGNATURE-----",
    b"-----BEGIN SIGNED MESSAGE-----",
    b"-----BEGIN PKCS7 SIGNATURE-----",
)
_PROCESS_STOP_TIMEOUT = 1.0
_ACTIVE_PROCESSES: set[subprocess.Popen[bytes]] = set()
_ACTIVE_LOCK = threading.Lock()
_PROCESS_CONTEXT = threading.local()


class GitError(SourceError):
    """Raised when Git rejects an operation."""


def _is_signed_tag(annotation: bytes) -> bool:
    return any(marker in annotation for marker in _SIGNATURE_MARKERS)


@dataclass(frozen=True)
class RetainedRef:
    """A selected direct ref and its commit target, kept out of public reports."""

    name: str
    kind: str
    target: str
    annotation: bytes | None = None


def git_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Prevent Git from resolving replacements or fetching promised objects."""
    env = os.environ.copy()
    if environment:
        env.update(environment)
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


@contextmanager
def hold_process_lock(descriptor: int) -> Iterator[None]:
    """Keep a workspace active while rewrite-owned descendants can still run."""
    previous = getattr(_PROCESS_CONTEXT, "lock_descriptors", ())
    _PROCESS_CONTEXT.lock_descriptors = (*previous, descriptor)
    try:
        yield
    finally:
        _PROCESS_CONTEXT.lock_descriptors = previous


def start_process(arguments: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
    """Start and register an isolated child process group."""
    inherited = tuple(getattr(_PROCESS_CONTEXT, "lock_descriptors", ()))
    requested = tuple(kwargs.pop("pass_fds", ()))
    process = subprocess.Popen(  # type: ignore[arg-type]
        arguments,
        start_new_session=True,
        pass_fds=tuple(dict.fromkeys((*requested, *inherited))),
        **kwargs,
    )
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESSES.add(process)
    return process


def finish_process(process: subprocess.Popen[bytes]) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESSES.discard(process)


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Bound child shutdown to TERM, one wait interval, KILL, and reap."""
    if process.poll() is not None:
        finish_process(process)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=_PROCESS_STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        process.wait()
    finally:
        finish_process(process)


def cancel_active_processes() -> None:
    with _ACTIVE_LOCK:
        processes = tuple(_ACTIVE_PROCESSES)
    for process in processes:
        terminate_process(process)


def run(
    arguments: Iterable[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> bytes:
    command = ["git", *arguments]
    env = git_environment(environment)
    try:
        process = start_process(
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as error:
        raise DependencyError("Git executable is unavailable") from error
    try:
        stdout, stderr = process.communicate(input=input_bytes)
    except BaseException:
        terminate_process(process)
        raise
    finally:
        finish_process(process)
    if check and process.returncode:
        detail = stderr.decode("utf-8", "replace").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise GitError(f"Git command failed ({' '.join(command[:2])}){suffix}")
    return stdout


def ensure_dependencies() -> dict[str, str]:
    git_version = run(["--version"]).decode().strip()
    if shutil.which("git-filter-repo") is None:
        try:
            filter_repo_version = run(["filter-repo", "--version"]).decode().strip()
        except GitError as error:
            raise DependencyError("git-filter-repo is required on PATH") from error
    else:
        try:
            process = start_process(
                ["git-filter-repo", "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            try:
                stdout, _ = process.communicate()
            except BaseException:
                terminate_process(process)
                raise
            finally:
                finish_process(process)
            if process.returncode:
                raise subprocess.SubprocessError("git-filter-repo failed")
            filter_repo_version = stdout.decode().strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise DependencyError("git-filter-repo is unavailable") from error
    result = {"git": git_version, "git_filter_repo": filter_repo_version}
    if not OCI_MANIFEST_SENTINEL.is_file():
        return result
    try:
        manifest = load_required_manifest(OCI_MANIFEST_SENTINEL)
    except ToolchainManifestError as error:
        raise DependencyError("required OCI toolchain manifest is unavailable") from error
    if (
        manifest["git"] != git_version
        or manifest["git_filter_repo"] != filter_repo_version
        or manifest["python"] != platform.python_version()
    ):
        raise DependencyError("required OCI toolchain does not match its declaration")
    return result | {
        "python": str(manifest["python"]),
        "manifest_sha256": str(manifest["lock_sha256"]),
        "package_version": str(manifest["package_version"]),
        "source_revision": str(manifest["source_revision"]),
    }


class Repository:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._bare = False
        try:
            self.git_dir = Path(
                run(["-C", str(self.path), "rev-parse", "--absolute-git-dir"]).decode().strip()
            ).resolve()
            self._bare = run(
                ["-C", str(self.path), "rev-parse", "--is-bare-repository"]
            ).decode().strip() == "true"
        except GitError as error:
            if (self.path / "config").is_file() and (self.path / "objects").is_dir():
                self.git_dir = self.path
                self._bare = True
            else:
                raise SourceError(f"Not a Git repository: {self.path}") from error

    def run(
        self,
        *arguments: str,
        input_bytes: bytes | None = None,
        environment: dict[str, str] | None = None,
        check: bool = True,
    ) -> bytes:
        return run(
            [f"--git-dir={self.git_dir}", *arguments] if self._bare else ["-C", str(self.path), *arguments],
            input_bytes=input_bytes,
            environment=environment,
            check=check,
        )

    def command(self, *arguments: str) -> list[str]:
        """Return a Git command scoped to this repository."""
        return [
            "git",
            f"--git-dir={self.git_dir}" if self._bare else "-C",
            *(() if self._bare else (str(self.path),)),
            *arguments,
        ]

    def text(self, *arguments: str) -> str:
        return self.run(*arguments).decode("utf-8", "surrogateescape").strip()

    def head_ref(self) -> str:
        ref = self.run("symbolic-ref", "-q", "HEAD", check=False).decode("utf-8", "surrogateescape").strip()
        if not ref:
            raise SourceError("The retained repository must have a symbolic HEAD")
        return ref

    def object_format(self) -> str:
        value = self.text("rev-parse", "--show-object-format=storage")
        if value not in {"sha1", "sha256"}:
            raise SourceError("Unsupported Git object format")
        return value

    def head_identity(self) -> tuple[str, bytes, str]:
        ref = self.run("symbolic-ref", "-q", "HEAD", check=False).rstrip(b"\n")
        return ("symref", ref, self.text("rev-parse", "HEAD")) if ref else ("detached", b"", self.text("rev-parse", "HEAD"))

    def direct_refs(self) -> tuple[tuple[bytes, str], ...]:
        records = self.run("for-each-ref", "--sort=refname", "--format=%(refname)%00%(objectname)%00").splitlines()
        result: list[tuple[bytes, str]] = []
        for record in records:
            fields = record.split(b"\0")
            if len(fields) != 3 or fields[-1]:
                raise SourceError("Cannot read source references")
            result.append((fields[0], fields[1].decode("ascii")))
        return tuple(result)

    def retained_refs(self, selectors: tuple[str, ...]) -> tuple[RetainedRef, ...]:
        """Resolve the policy's direct branch/tag selectors without revision parsing."""
        head = self.head_ref()
        records = self.run(
            "for-each-ref",
            "--sort=refname",
            "--format=%(refname)%00%(objecttype)%00%(objectname)%00%(*objecttype)%00",
        ).splitlines()
        refs: dict[str, tuple[str, str, str]] = {}
        for record in records:
            fields = record.split(b"\0")
            if len(fields) != 5 or fields[-1]:
                raise SourceError("Cannot inspect retained references")
            name = fields[0].decode("utf-8", "surrogateescape")
            refs[name] = tuple(field.decode("ascii") for field in fields[1:4])

        selected: list[RetainedRef] = []
        for selector in selectors:
            name = head if selector == "HEAD" else selector
            if any(ref.name == name for ref in selected):
                raise SourceError("refs.keep selects the symbolic HEAD branch more than once")
            try:
                object_type, object_id, peeled_type = refs[name]
            except KeyError as error:
                raise SourceError("A selected reference does not exist") from error
            if name.startswith("refs/heads/"):
                if object_type != "commit":
                    raise SourceError("A selected branch must point directly to a commit")
                selected.append(RetainedRef(name, "branch", object_id))
                continue
            if not name.startswith("refs/tags/"):
                raise SourceError("A selected reference uses an unsupported namespace")
            if object_type == "commit":
                selected.append(RetainedRef(name, "lightweight-tag", object_id))
                continue
            if object_type != "tag" or peeled_type != "commit":
                raise SourceError("A selected tag must directly target a commit")
            annotation = self.run("cat-file", "tag", object_id)
            headers = annotation.split(b"\n\n", 1)[0].splitlines()
            if _is_signed_tag(annotation):
                raise SourceError("Signed annotated tags are not supported")
            if not any(header == b"type commit" for header in headers):
                raise SourceError("Selected tag chains and non-commit tag targets are not supported")
            target = self.text("rev-parse", "--verify", "--end-of-options", f"{name}^{{commit}}")
            selected.append(RetainedRef(name, "annotated-tag", target, annotation))
        if not any(ref.name == head for ref in selected):
            raise SourceError("refs.keep must select the symbolic HEAD branch")
        return tuple(selected)

    def resolve_cutoff_commit(self, value: str) -> str:
        object_format = self.object_format()
        width = 40 if object_format == "sha1" else 64
        if len(value) != width or any(character not in "0123456789abcdef" for character in value):
            raise SourceError("history.cutoffCommit must be a full lowercase storage-format object ID")
        if self.run("cat-file", "-t", "--", value, check=False).decode().strip() != "commit":
            raise SourceError("history.cutoffCommit must resolve to a commit")
        result = self.run("rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}", check=False).decode().strip()
        if len(result) != width:
            raise SourceError("history.cutoffCommit must resolve to a commit")
        return result

    def commit_tree(self, commit: str) -> str:
        return self.text("rev-parse", "--verify", "--end-of-options", f"{commit}^{{tree}}")

    def worktree_root(self) -> Path | None:
        result = self.run("rev-parse", "--show-toplevel", check=False).decode().strip()
        if result:
            return Path(result).resolve()
        if not self._bare and self.path == self.git_dir:
            marker = self.git_dir.parent / ".git"
            if marker.exists() and marker.resolve() == self.git_dir:
                return self.git_dir.parent
        return None

    def clone_to(
        self, destination: Path, *, bare: bool = False, template_directory: Path | None = None,
    ) -> "Repository":
        arguments = ["clone", "--no-checkout", "--no-local"]
        if template_directory is not None:
            arguments.extend(["--template", str(template_directory)])
        if bare:
            arguments.append("--bare")
        arguments.extend([str(self.path), str(destination)])
        run(arguments)
        return Repository(destination)
