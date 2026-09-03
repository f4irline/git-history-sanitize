# Sandbox testing

This repository contains a small Express application and a Docker
Compose/devcontainer sandbox for running AI development agents with restricted
network, working-tree, and Git-history access.

## Run the application

```bash
npm install
npm start
```

The server listens on port 3000 and responds to `GET /` with a greeting.

## Run the sandbox

```bash
docker compose -f .devcontainer/docker-compose.yml \
  up -d --build --force-recreate
```

The project working tree is bind-mounted at `/workspace`. The sandbox masks
`secret.json`, the `infra/` directory, and the host repository's real
`.git`. An internal Docker network also prevents external network access.

The sanitized Git database is created while the image is built:

1. The real `.git` is exposed only to one trusted BuildKit instruction.
2. Commits before the configured cutoff are collapsed into a parentless
   `[sanitized]` root commit.
3. Sensitive paths are removed from the shortened history with
   `git filter-repo`.
4. Mixed commits retain their allowed changes but receive the
   `[sanitized]` message. Sensitive-only commits disappear.
5. Extra refs, remotes, reflogs, temporary metadata, and unreachable objects
   are removed.
6. At runtime, the sanitized database is copied into a tmpfs mounted at
   `/workspace/.git`.

Configure the cutoff in
`.devcontainer/git-history-cutoff.txt`. Configure sensitive files and
directories in `.devcontainer/git-history-filter.txt`; directory entries end
with `/`. Rebuild the image after changing either configuration or after
creating new host commits.

## Verification

Run the isolated history fixture:

```bash
docker buildx build \
  --target git-history-test \
  --build-context trusted_git=.git \
  -f .devcontainer/Dockerfile.devcontainer .
```

Verify a running sandbox:

```bash
docker compose -f .devcontainer/docker-compose.yml run --rm devcontainer \
  /usr/local/bin/verify-git-history-sanitization \
  /workspace \
  /workspace/.devcontainer/git-history-filter.txt \
  /workspace/.devcontainer/git-history-cutoff.txt
```

The fixture and end-to-end sandbox checks verify that pre-cutoff messages and
sensitive paths are absent, mixed commits preserve allowed changes,
sensitive-only commits vanish, cleanup leaves no unreachable objects, and
normal commands such as `git status`, `git log`, `git diff`, `git show`,
and `git blame` continue to work.

Cutoff compaction currently requires a linear branch with monotonically
advancing committer timestamps. The build fails closed if it encounters a
merge or timestamps that cross the cutoff more than once.
