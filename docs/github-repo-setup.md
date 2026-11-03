# GitHub repo setup

Apply once (admin). Outcomes below; tools are judgement (`gh`, Settings UI).

## 1. Actions

Actions enabled so required checks and auto-merge can run.

## 2. Protect `main`

Ruleset on default branch, **Active**, bypass empty:

| Rule | Value |
|------|-------|
| Restrict deletions | On |
| Block force pushes | On |
| Require a pull request before merging | On; 0 required approvals |
| Require status checks to pass | On; branches up to date; checks: `PR hygiene`, `Code lint`, `Unit tests`, `Coverage` |

## 3. Merge settings

- Squash only (merge commits and rebase off)
- Squash message default: PR title and description
- Always suggest updating PR branches
- Allow auto-merge
- Automatically delete head branches

## 4. Labels

At least `no-automerge` (opt out of auto-merge).

## Related

- [`pull-requests.md`](pull-requests.md)
- Workflows under [`.github/workflows/`](../.github/workflows/)
