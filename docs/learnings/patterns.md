# Patterns

How we do things around here. Follow these for consistency.

---

## Hermetic Git integration fixtures
**Ticket:** BBQ-22
**Date:** 2026-09-05

Use `tests.support.git_fixture.GitFixture` for Git/CLI integration tests. It
creates fixture-owned HOME, XDG, global config, template, and hooks locations;
uses an allowlisted environment; and provides deterministic history builders plus
source/output snapshots that compare refs, reachable objects, and physical objects.

---
