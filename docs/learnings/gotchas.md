# Gotchas

Things that might bite you. Check here before you get bitten.

---

## Mount a worktree, not its metadata directory, in OCI contracts
**Ticket:** BBQ-44
**Date:** 2026-09-05

Git 2.47 rejected a read-only standalone worktree `.git` directory mounted as
the repository root in the OCI fixture. Mount the read-only worktree and pass
its `/input/.git` path instead. Keep the translation covered by
`tests/test_git_fixture.py`.

---

## Verify git-filter-repo fingerprints from the pinned source
**Ticket:** BBQ-44
**Date:** 2026-09-05

Do not assume the planned git-filter-repo fingerprint matches a package label or
source tag. The pinned upstream source in BBQ-44 emits `a40bce548d2c`; this
corrects the approved pin from `bc98e38e057b`. Keep the checker fail-closed on
any output other than the verified fingerprint.

---
