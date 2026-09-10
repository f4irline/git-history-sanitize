# Patterns

How we do things around here. Follow these for consistency.

---

## Validate snapshot scope before inherited history
**Ticket:** BBQ-10
**Date:** 2026-09-10

Snapshot sanitization must construct its synthetic root directly from `HEAD` and
validate only the `HEAD` tree closure. Walking inherited commits first both
misstates scope counts and incorrectly rejects valid snapshot sources with merge
history or unavailable historical objects.

---

## Stream sensitive CLI input through fixture containers
**Ticket:** BBQ-9
**Date:** 2026-09-09

When a CLI accepts a private file or stdin, `GitFixture._container_cli` must
mount the file at a translated path and add `docker run -i` for stdin. Assert
the constructed mount and argv so container tests preserve both input delivery
and host-path redaction.

---

## Hermetic Git integration fixtures
**Ticket:** BBQ-22
**Date:** 2026-09-05

Use `tests.support.git_fixture.GitFixture` for Git/CLI integration tests. It
creates fixture-owned HOME, XDG, global config, template, and hooks locations;
uses an allowlisted environment; and provides deterministic history builders plus
source/output snapshots that compare refs, reachable objects, and physical objects.

---
