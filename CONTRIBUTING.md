# Local development and commit rules

The repository is initially local-only. Start with plain Python scripts and JSON files, without a database or separate services. Runtime data is excluded from Git; reviewed reproducible examples belong in `tests/fixtures/`. Do not add API keys, signing credentials, or populated local configuration files.

## Semantic commits

Use `<type>(<scope>): <imperative summary>` where helpful. Types include `feat`, `fix`, `test`, `docs`, `refactor`, and `chore`. A commit should express one independently understandable change, with the validation needed to review it.

Examples:

- `chore(repo): establish local development and agent rules`
- `feat(ingest): persist immutable market and rule snapshots`
- `feat(venue): capture outcome books and capability statuses`
- `docs(day1): document ingestion and live validation results`

Commit boundaries follow behavior rather than file type. A feature and its necessary tests can share a commit. Keep unrelated cleanup and later milestones separate. Do not commit broken intermediate code just to make smaller commits.

Before each commit:

1. Inspect `git status --short` and the working diff.
2. Run checks appropriate to the change; record unavailable checks.
3. Stage only the intended paths with `git add <paths>`.
4. Inspect `git diff --cached --check` and `git diff --cached` for mistakes, sensitive data, and unrelated changes.
5. Commit with a concrete message. Confirm the remaining working-tree state.

Use topic branches for later independent work when useful. Do not change branches with unrelated uncommitted changes. Keep `main` as the initial local baseline; there is no remote publishing requirement.

## Validation policy

Deterministic tests use small saved fixtures and do not depend on network access, paid model calls, or credentials. Live smoke checks are explicitly invoked and record their observation time and outcomes. Documentation changes need link/path and whitespace checks rather than artificial unit tests.

The implementation README will define setup and runnable commands as they become available. This document does not claim that an implementation or test suite already exists.

## Local repository configuration

`.gitattributes` declares LF line endings for source files. Once Git metadata is writable, the suggested repository-local settings are:

```sh
git config --local core.autocrlf input
git config --local core.whitespace trailing-space,space-before-tab
```

Whitespace checks support review; they are not a security scanner or a substitute for inspecting staged content. No remote or custom hooks are installed by default.
