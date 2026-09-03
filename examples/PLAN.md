# Examples implementation plan

## Goal

Create a small set of runnable examples that show how teams can use Git
History Sanitize without making the project responsible for the surrounding
sandbox, CI platform, or container runtime.

The examples should progress from a local command-line walkthrough to realistic
integration patterns. Each one must use the standalone implementation from the
repository root rather than copying the sanitization logic used by `proto/`.

## Shared conventions

Every example must:

- contain its own README and policy file;
- use generated fixture repositories and obviously fake sentinel values;
- keep the source repository read-only during sanitization;
- run `plan`, `rewrite`, and/or `verify` as appropriate;
- demonstrate the timestamp or commit cutoff explicitly;
- include a mixed commit whose allowed changes survive with a `[sanitized]`
  message;
- include a sensitive-only commit that disappears;
- prove that configured paths and forbidden sentinel values are absent from
  reachable history and unreachable objects;
- explain which environment is trusted and which output may be exposed;
- fail closed when a required dependency, policy, or verification step fails;
- avoid checking generated repositories, archives, or build output into Git.

Examples may wrap the tool for orchestration, but must not reimplement history
rewriting or verification. They should remain independent of `proto/`.

## Directory layout

```text
examples/
├── README.md
├── PLAN.md
├── basic-cli/
│   ├── README.md
│   ├── policy.yml
│   └── run.sh
├── docker-buildkit/
│   ├── README.md
│   ├── Containerfile
│   ├── Containerfile.dockerignore
│   ├── policy.yml
│   └── test.sh
├── github-actions/
│   ├── README.md
│   ├── policy.yml
│   ├── workflow.yml
│   └── consume-sanitized-history.sh
└── devcontainer/
    ├── README.md
    ├── policy.yml
    ├── .devcontainer/
    │   ├── devcontainer.json
    │   ├── docker-compose.yml
    │   ├── Containerfile
    │   └── install-sanitized-git.sh
    └── workspace/
        └── README.md
```

Exact helper filenames may change during implementation, but each example
should retain a single obvious entry point.

## Example 1: basic CLI

### Purpose

Provide the shortest complete demonstration of the tool's behavior. A reader
should be able to run it locally and inspect both the original and sanitized
histories in a few minutes.

### Scenario

Generate a temporary linear repository containing:

1. two commits before the configured cutoff;
2. one allowed-only commit after the cutoff;
3. one mixed commit changing an allowed file and `secret.json`;
4. one sensitive-only commit;
5. one final allowed commit.

The script installs the local package in an isolated environment, previews the
rewrite, creates a bare sanitized repository, verifies it, and prints a compact
before-and-after log.

### Acceptance criteria

- The source repository's refs and object database remain unchanged.
- The sanitized history starts with one synthetic `[sanitized]` root.
- The mixed commit's allowed change remains under a `[sanitized]` message.
- The sensitive-only commit and `secret.json` are absent.
- Re-running the example replaces only its disposable output.
- The example works on supported Linux and macOS environments with Python,
  Git, and `git-filter-repo` installed.

## Example 2: Docker BuildKit

### Purpose

Show how to perform sanitization inside a trusted image build without adding a
global `.dockerignore` or copying the original Git object database into an
image layer.

### Scenario

Pass a source `.git` directory as a read-only named BuildKit context. Run Git
History Sanitize in a dedicated stage, verify the result, and export only the
sanitized bare repository from the build.

Use a Dockerfile-specific ignore file so this example does not affect unrelated
container builds. Document that BuildKit and the builder are inside the trusted
boundary.

### Acceptance criteria

- The regular build context excludes `.git`.
- The named Git context is mounted read-only for the sanitization step.
- No stage copied into the final/exported result contains the original `.git`.
- The exported repository passes `git-history-sanitize verify` independently.
- A layer and object scan cannot find the fake sensitive sentinel.
- The README explains cache invalidation and rebuilding after source commits or
  policy changes.

## Example 3: GitHub Actions

### Purpose

Demonstrate a trusted CI job producing a sanitized artifact for a downstream
job that must not receive the original history.

### Scenario

Provide a workflow template that:

1. checks out full history in a trusted producer job;
2. installs the project from a pinned release or immutable revision;
3. runs `plan`, `rewrite`, and `verify`;
4. archives only the sanitized bare repository;
5. uploads it as an artifact;
6. downloads and verifies it again in a consumer job that never checks out the
   source repository.

Because GitHub only executes workflows from `.github/workflows/`, keep the
template under this example and document how to copy it into a consuming
repository.

### Acceptance criteria

- The consumer job has no checkout step and receives only the sanitized
  artifact.
- Actions and the sanitizer version are pinned to immutable revisions in the
  production-oriented template.
- Artifact names, retention, and permissions are explicit.
- Logs and reports contain no removed commit messages or source-to-output commit
  mapping.
- Verification failure prevents artifact publication and consumer execution.
- The trust-boundary warning is prominent: the producer runner still sees the
  full repository.

## Example 4: devcontainer

### Purpose

Show how a sandbox owner can consume the standalone tool when constructing a
development container, while keeping filesystem and network isolation outside
the tool's scope.

### Scenario

Build a small workspace image using a sanitized bare repository produced by
Git History Sanitize. At container startup, initialize `/workspace/.git` from
the verified sanitized database while the host repository's real `.git` is
masked by a separate tmpfs mount.

The example should remain intentionally smaller than `proto/`: it demonstrates
the integration boundary, not a complete agent sandbox.

### Acceptance criteria

- The host `.git` is available only to the trusted build/sanitization phase.
- Runtime Git commands use the sanitized history from `/workspace/.git`.
- `git status`, `git log`, `git diff`, `git show`, and `git blame` work against
  the example workspace.
- The runtime container cannot read the original Git database.
- Rebuilding after a new source commit produces an updated sanitized HEAD.
- The README clearly separates guarantees provided by Git History Sanitize from
  guarantees provided by Compose, mounts, and network configuration.

## Examples index

Add `examples/README.md` when implementing the first example. It should include
a one-paragraph description of each sample, its prerequisites, expected runtime,
and a recommendation to start with `basic-cli/`.

It should also distinguish the examples from `proto/`:

- `proto/` preserves the original hand-built proof of concept.
- `examples/` demonstrates integrations that consume the reusable tool.

## Implementation order

1. Implement `basic-cli/` and establish fixture/output conventions.
2. Implement `docker-buildkit/` using the same policy and behavioral assertions.
3. Implement `github-actions/` and validate its commands locally where possible.
4. Implement `devcontainer/`, reusing the supported integration pattern rather
   than the prototype's sanitizer scripts.
5. Add the examples index and run all examples from a clean checkout.

## Repository-level validation

Add an examples smoke-test entry point that runs every example that is
available in the current environment. Container-dependent tests may be skipped
with an explicit reason when Docker is unavailable; the basic CLI example must
always run in CI.

Completion requires:

- all existing package tests still pass;
- all example smoke tests pass from a clean checkout;
- documentation commands are copied into tests or exercised directly;
- no example output contains the fake sensitive sentinel;
- no example depends on files from `proto/`;
- generated artifacts leave the working tree clean.

## Non-goals

These examples will not claim to provide a complete security boundary. They do
not replace hardening for CI runners, container daemons, filesystems, networks,
credentials, logs, caches, or artifact storage. Their purpose is to show where
sanitized Git history fits into those systems and how to verify the boundary it
does provide.
