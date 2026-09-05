# Git History Sanitize House Rules

**Version:** 1.0.0  
**Ratified:** 2026-09-05

## Core Principles

### 1. Security First

Never weaken isolation, sanitization, or verification to simplify implementation.

### 2. Predictable CLI

Use clear commands, safe defaults, actionable errors, and stable output formats.

### 3. Minimal Dependencies

Add dependencies only when they provide substantial value and can be reviewed and pinned.

### 4. Focused Scope

Handle Git-history rewriting and verification; leave runtime sandboxing and unrelated concerns elsewhere.

### 5. Deterministic Results

The same repository, policy, and supported toolchain should produce the same result.

## Governance

All PRs and reviews must verify compliance with these rules. Amendments require documentation and team approval.
