"""Small, binary-safe wrappers around the Git command line."""

from __future__ import annotations

import os
import platform
import re
import selectors
import signal
import stat
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Iterable, Iterator, Literal

from .errors import DependencyCheck, DependencyError, SourceError
from .oci_toolchain import ToolchainManifestError, load_required_manifest


OCI_MANIFEST_SENTINEL = Path("/usr/local/etc/git-history-sanitize/oci-manifest-required")
GIT_MINIMUM = (2, 36, 0)
FILTER_REPO_FINGERPRINT = "a40bce548d2c"
FILTER_REPO_COMMAND = "filter-repo"
_GIT_VERSION = re.compile(
    r"git version ([0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4})"
    r"(?:\.windows\.[0-9]{1,4}| \(Apple Git-[0-9]{1,4}\))?"
)
_DEPENDENCY_TIMEOUT = 10.0
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
    # Git handles -C before helper lookup. Freeze relative search entries before
    # that repository-scoped chdir so doctor and rewrite cannot choose differently.
    env["PATH"] = os.pathsep.join(os.path.abspath(path) for path in env.get("PATH", os.defpath).split(os.pathsep))
    if env.get("GIT_EXEC_PATH"):
        env["GIT_EXEC_PATH"] = os.path.abspath(env["GIT_EXEC_PATH"])
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def _resolve_executable(name: str, search_path: str) -> str:
    """Match executable search order, retaining only resolver-owned provenance."""
    inaccessible: str | None = None
    for directory in search_path.split(os.pathsep):
        candidate = os.path.abspath(os.path.join(directory, name))
        try:
            mode = os.stat(candidate).st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue
        except (OSError, ValueError) as error:
            raise DependencyError(reason="startup_failed", executable_path=candidate) from error
        if stat.S_ISREG(mode) and os.access(candidate, os.X_OK):
            return candidate
        inaccessible = inaccessible or candidate
    raise DependencyError(
        reason="not_executable" if inaccessible else "missing", executable_path=inaccessible,
    )


def git_command(arguments: Iterable[str], environment: dict[str, str]) -> list[str]:
    """Use the same absolute Git invocation for inspection and rewrite."""
    return [_resolve_executable("git", environment.get("PATH", os.defpath)), *arguments]


@contextmanager
def hold_process_lock(descriptor: int) -> Iterator[None]:
    """Keep a workspace active while rewrite-owned descendants can still run."""
    previous = getattr(_PROCESS_CONTEXT, "lock_descriptors", ())
    _PROCESS_CONTEXT.lock_descriptors = (*previous, descriptor)
    try:
        yield
    finally:
        _PROCESS_CONTEXT.lock_descriptors = previous


def start_process(
    arguments: list[str], *, cwd: str | None = None,
    stdin: int | IO[bytes] | None = None, stdout: int | IO[bytes] | None = None,
    stderr: int | IO[bytes] | None = None, env: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.Popen[bytes]:
    """Start and register an isolated child process group."""
    inherited = tuple(getattr(_PROCESS_CONTEXT, "lock_descriptors", ()))
    process = subprocess.Popen(
        arguments,
        start_new_session=True,
        pass_fds=tuple(dict.fromkeys((*pass_fds, *inherited))),
        cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr, env=env,
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
    env = git_environment(environment)
    command = git_command(arguments, env)
    if cwd is not None:
        try:
            if not cwd.is_dir():
                raise GitError("Git working directory is unavailable")
        except OSError as error:
            raise GitError("Git working directory is unavailable") from error
    try:
        process = start_process(
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise DependencyError(reason="startup_failed") from error
    try:
        stdout, _ = process.communicate(input=input_bytes)
    except (OSError, subprocess.SubprocessError) as error:
        try:
            terminate_process(process)
        finally:
            raise GitError("Git operation could not complete") from error
    except BaseException:
        try:
            terminate_process(process)
        except (OSError, subprocess.SubprocessError) as error:
            raise GitError("Git operation could not stop") from error
        raise
    finally:
        finish_process(process)
    if check and process.returncode:
        raise GitError("Git operation failed")
    return stdout


def _dependency_output(command: list[str], env: dict[str, str], *, limit: int = 256) -> str:
    """Read a bounded version record with a deadline; discard stderr entirely."""
    try:
        process = start_process(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise DependencyError(reason="startup_failed") from error
    try:
        assert process.stdout is not None
        output = bytearray()
        deadline = time.monotonic() + _DEPENDENCY_TIMEOUT
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise DependencyError(reason="execution_failed")
                chunk = os.read(process.stdout.fileno(), limit + 1 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > limit:
                    raise DependencyError(reason="invalid_output")
        if process.wait(timeout=max(0.001, deadline - time.monotonic())):
            raise DependencyError(reason="execution_failed")
        return output.decode("utf-8").removesuffix("\n")
    except UnicodeError as error:
        raise DependencyError(reason="invalid_output") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise DependencyError(reason="execution_failed") from error
    finally:
        try:
            terminate_process(process)
            if process.stdout is not None:
                process.stdout.close()
        except (OSError, subprocess.SubprocessError) as error:
            raise DependencyError(reason="execution_failed") from error


def ensure_dependencies(environment: dict[str, str] | None = None) -> dict[str, object]:
    env = git_environment(environment)
    checks: list[DependencyCheck] = []
    failures: list[DependencyError] = []
    result: dict[str, object] = {}
    git_executable: str | None = None
    for name, requirement in (("git", ">=2.36"), ("git-filter-repo", f"{FILTER_REPO_FINGERPRINT} (2.47.0)")):
        executable: str | None = None
        detected: str | None = None
        status: Literal["pass", "fail"]
        try:
            if git_executable is None:
                git_executable = git_command([], env)[0]
            if name == "git":
                executable = git_executable
                version = _dependency_output([git_executable, "--version"], env)
                match = _GIT_VERSION.fullmatch(version)
                if match is None:
                    raise DependencyError(reason="invalid_output")
                detected = match[1]
                if tuple(map(int, detected.split("."))) < GIT_MINIMUM:
                    raise DependencyError(reason="unsupported")
                result["git"] = version
            else:
                # Git setup_path() prepends only its exec path to PATH.
                exec_path = _dependency_output([git_executable, "--exec-path"], env, limit=4096)
                if not exec_path or "\n" in exec_path or "\0" in exec_path:
                    raise DependencyError(reason="invalid_output")
                search_path = os.pathsep.join((exec_path, env.get("PATH", os.defpath)))
                executable = _resolve_executable("git-filter-repo", search_path)
                version = _dependency_output([git_executable, FILTER_REPO_COMMAND, "--version"], env)
                if re.fullmatch(r"[0-9a-f]{12}", version) is None:
                    raise DependencyError(reason="invalid_output")
                detected = version
                if detected != FILTER_REPO_FINGERPRINT:
                    raise DependencyError(reason="unsupported")
                result["git_filter_repo"] = version
        except DependencyError as error:
            if name == "git" or git_executable is not None:
                executable = executable or error.executable_path
            failures.append(error)
            status = "fail"
        else:
            status = "pass"
        checks.append(DependencyCheck(name, executable, detected, requirement, status))
    result["checks"] = [asdict(check) for check in checks]
    if failures:
        failures[0].checks = tuple(checks)
        raise failures[0]
    try:
        # stat() must not silently turn inaccessible or malformed sentinels into
        # a non-OCI success path. Only a genuinely absent sentinel is optional.
        try:
            OCI_MANIFEST_SENTINEL.lstat()
        except FileNotFoundError:
            return result
        manifest = load_required_manifest(OCI_MANIFEST_SENTINEL)
    except (OSError, ToolchainManifestError) as error:
        raise DependencyError(reason="oci_mismatch", checks=tuple(checks)) from error
    if (
        manifest["git"] != result["git"]
        or manifest["git_filter_repo"] != result["git_filter_repo"]
        or manifest["python"] != platform.python_version()
    ):
        raise DependencyError(reason="oci_mismatch", checks=tuple(checks))
    return result | {
        "python": str(manifest["python"]),
        "manifest_sha256": str(manifest["lock_sha256"]),
        "package_version": str(manifest["package_version"]),
        "source_revision": str(manifest["source_revision"]),
    }


class Repository:
    def __init__(self, path: str | Path):
        try:
            self.path = Path(path).resolve()
        except (OSError, ValueError) as error:
            raise SourceError("Cannot resolve source repository") from error
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
        except (OSError, UnicodeError, ValueError) as error:
            raise SourceError("Cannot inspect source repository") from error

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
            git_command([], git_environment())[0],
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
            refs[name] = (fields[1].decode("ascii"), fields[2].decode("ascii"), fields[3].decode("ascii"))

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
