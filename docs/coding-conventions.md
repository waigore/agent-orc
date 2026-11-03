# Coding conventions

Python package conventions for agent-orc. Extend these without contradicting them.

## Tooling

| Step | Command |
|------|---------|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format --check .` |

CI: [`.github/workflows/code-lint.yml`](../.github/workflows/code-lint.yml).

## Unit tests

| Step | Command |
|------|---------|
| Unit / integration | `uv run pytest -m "not e2e"` |

CI: [`.github/workflows/unit-tests.yml`](../.github/workflows/unit-tests.yml) job `Unit tests`.

## Coverage

| Step | Command |
|------|---------|
| Coverage | `uv run pytest -m "not e2e" --cov=agent_orc --cov-report=term-missing --cov-fail-under=80` |

Threshold: **80%** line coverage on `agent_orc` (e2e excluded). CI job `Coverage`.
