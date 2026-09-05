# Project Agent Instructions

## Mandatory House Rules

The House Rules in `.opencode/HOUSE_RULES.md` in the checkout that launched the
workflow are binding for every project workflow. Use that file as the single
source of truth.

For an explicit repository path, use the Read tool directly. Never use Glob,
Grep, or directory listing to determine whether that known path exists. A
search returning no matches does not prove that a file is absent.

Capture the launching checkout as `workflow_root` before doing repository work.
Set `worktree_path` to `workflow_root` by default. If the workflow creates or
resolves a dedicated worktree, replace `worktree_path` with that checkout's
absolute path. This gives every workflow one active code path regardless of
whether it uses a dedicated worktree or works directly in the root checkout.

Read House Rules from `{workflow_root}/.opencode/HOUSE_RULES.md` and keep using
those loaded rules throughout the workflow. Do not require or load a House
Rules copy from a dedicated worktree. If the direct read fails, stop the
workflow and report the read error.
