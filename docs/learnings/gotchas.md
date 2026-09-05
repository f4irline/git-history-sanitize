# Gotchas

Things that might bite you. Check here before you get bitten.

---

## Verify git-filter-repo fingerprints from the pinned source
**Ticket:** BBQ-44
**Date:** 2026-09-05

Do not assume the planned git-filter-repo fingerprint matches a package label or
source tag. The pinned upstream source in BBQ-44 emits `a40bce548d2c`; this
corrects the approved pin from `bc98e38e057b`. Keep the checker fail-closed on
any output other than the verified fingerprint.

---
