# Threat Model

Git History Sanitize processes repositories that may contain sensitive history.
This document defines the temporary-workspace trust boundary; the source and
published-artifact contracts remain described in the README and `PLAN.md`.

## Protected assets

- The source repository, which the sanitizer must never mutate.
- The full unsanitized temporary clone and its derived objects.
- A private cutoff receipt before publication.
- A verified output after its native no-replace publication rename.

The local OS user, kernel, Git executable, `git-filter-repo`, Python runtime, and
the filesystem implementing the selected parent directories are trusted. Other
local users are outside the trust boundary. Root and a process running as the
same UID can inspect or alter workspace data and are not contained by this tool.

## Workspace controls

The sanitizer creates an exact-name direct child of the resolved output parent
with mode `0700` before cloning. This keeps staging on the publication
filesystem and prevents normal access by other users. A bounded `0600` manifest
contains only a version, opaque ID, UID/GID, diagnostic PID and creation time,
lifecycle state, role, and parent/workspace device-inode bindings. It excludes
paths, repository or policy identity, Git object IDs, command arguments, and
content. A non-inherited exclusive advisory lock is authoritative for activity;
PID values are never used to decide whether deletion is safe.

Receipt staging uses the same ID in a private workspace under the receipt parent
when necessary. Publication moves only the staged receipt or verified bare
repository out of workspace ownership. A successful no-replace rename is the
ownership-transfer boundary: later cleanup never deletes or rolls back that
published entry, including when parent-directory synchronization fails.

Discovery examines only immediate entries matching the exact name grammar.
Cleanup accepts only an absolute parent plus one exact opaque ID. It opens every
parent component, the workspace root, and metadata with no-follow semantics;
checks ownership, type, mode, link count, schema, device and inode bindings;
acquires the lock; revalidates the root; and removes content descriptor-relative.
Nested symlinks are unlinked and never followed. Invalid or unverifiable entries
are `ambiguous` and are retained.

## Interruption behavior

SIGINT and SIGTERM become controlled exceptions. The active child starts in a
separate process group and receives TERM, a bounded wait, KILL if needed, and a
final reap before Python unwinds. Workspace metadata is marked `interrupted`,
the lock is released, and staging is deliberately retained for explicit cleanup.
A second signal restores immediate default termination rather than recursively
inspecting or deleting files.

SIGKILL, kernel failure, host restart, and power loss cannot execute handlers or
state transitions. File-descriptor closure releases the advisory lock, so a
valid unlocked `active` manifest is reported as `stale`. A crash between private
directory creation and durable manifest creation may instead leave an ambiguous
entry; the sanitizer does not claim ownership or delete it automatically.

## Residual risks

- Advisory locks coordinate cooperating processes only. Root or the same UID can
  read, replace, lock, or mutate staging and can defeat these controls.
- Network and unusual filesystems may not provide reliable POSIX locks,
  no-follow descriptor operations, atomic rename, or directory durability. The
  tool fails closed when required primitives are unavailable; operators must not
  infer stronger guarantees from a filesystem that violates them.
- Cleanup is deletion, not secure erasure. Journals, copy-on-write snapshots,
  backups, swap, crash dumps, SSD remanence, and storage-controller behavior may
  retain source data after files disappear.
- Manifest ownership is operational identification, not cryptographic
  authentication. Ambiguous metadata always requires independent manual review.
- Repository and receipt publication are separate renames. Receipt-first order
  prevents output without evidence, but an orphan published receipt may remain
  when repository publication fails.
- The tool does not sandbox Git, isolate the network, protect against a malicious
  kernel/runtime, or resume an interrupted clone.

## Recovery policy

Use `workspace list --parent ABSOLUTE_PARENT` and then `workspace clean --parent
ABSOLUTE_PARENT --id OPAQUE_ID`. Clean each output and receipt parent separately
when both contain the ID. Never pass an arbitrary path, expand a glob, delete all
prefix matches, or treat a PID as proof of staleness. For `ambiguous` entries,
stop sanitizer processes and use an administrator-controlled inspection and
deletion procedure only after independently excluding published and unrelated
data. After cleanup, rerun sanitization from the immutable source.
