# Pull requests

Every change reaches `main` through a PR; `main` is protected ([`github-repo-setup.md`](github-repo-setup.md)).

## Flow

1. Branch from up-to-date `main`.
2. Commit focused changes; keep the PR under ~30 files (split if larger).
3. Run local checks that apply (`uv run ruff check .`, `uv run pytest -m "not e2e"`).
4. Push and open the PR with a body following [`pull_request_template.md`](../.github/pull_request_template.md).

```bash
git switch -c chore/add-ci
git push -u origin HEAD
gh pr create --title "Add CI and protect main" --body-file /tmp/pr-body.md
```

## Branch names

`<type>/<issue#>-<slug>` when an issue exists (`task`, `defect`, …). No issue: `chore/<slug>`.

## Title

Imperative, under ~72 characters, no trailing period. It becomes the squash commit message.

## Body

Fill every template section; write `N/A` with a reason rather than deleting one.

| Section | Contents |
|---------|----------|
| Summary | What changed and why |
| Issue | `Refs #n` for related issues |
| Authority | `docs/` paths that authorize the change, or `N/A` with reason |
| Changes | Notable files or areas |
| Test plan | Commands run and results |
| Evidence | Usually `N/A` with reason for this library |

### `Refs`, not `Closes`

Prefer `Refs #n`. Avoid `Closes` / `Fixes` / `Resolves` unless you intentionally want GitHub to close the issue on merge.

## `PR hygiene` check

Required check ([`pr-hygiene.yml`](../.github/workflows/pr-hygiene.yml)). Rules in [`pr_hygiene.py`](../.github/scripts/pr_hygiene.py):

| Rule | Fails when |
|------|------------|
| `closing-keywords` | Title or body has `Closes #n` / `Fixes #n` / `Resolves #n` |
| `title-format` | Title empty, over 72 characters, or ends with a period |
| `template-sections` | A template `##` section is missing, empty, or bare `N/A` |

## Auto-merge

Same-repo non-draft PRs squash-merge when required checks pass on a branch up to date with `main` ([`automerge.yml`](../.github/workflows/automerge.yml)). Use **draft** while incomplete; add **`no-automerge`** only when asked.
