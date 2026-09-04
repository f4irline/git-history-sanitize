# Basic CLI integration

This is an illustrative invoice-reminder service. `src/` and `config/` are
shareable project material; the deliberately fake `secret.json` shows a path a
team would exclude. Review [`.git-history-sanitize.yml`](.git-history-sanitize.yml)
after copying this repository layout into a real project.

Install the published release wheel rather than this checkout's sources:

```bash
pipx install https://github.com/f4irline/git-history-sanitize/releases/download/v0.1.1/git_history_sanitize-0.1.0-py3-none-any.whl
```

Then run the small wrapper against the real repository's Git database:

```bash
./run.sh /path/to/invoice-reminders/.git /path/to/build/sanitized.git
```

The wrapper deliberately does only `doctor`, `plan`, `rewrite`, and `verify`.
It never creates commits, edits the source repository, or removes an existing
output. Trust the machine that holds the original Git database; share only the
verified output repository.
