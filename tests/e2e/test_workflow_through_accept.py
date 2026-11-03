"""E2E: dummy issue from pending-review through status:accepted.

Requires gh auth, a target project with .orc config + labels, and real provider CLIs.
Set ORC_E2E_REPO_ROOT to that project (agent-orc itself has no .orc/).

Run only after unit/integration: pytest -m \"not e2e\" && pytest -m e2e
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from agent_orc.github_gh import (
    GhError,
    close_issue,
    create_issue,
    gh_available,
    issue_status_label,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = (
    Path(os.environ.get("ORC_E2E_REPO_ROOT", "")).expanduser().resolve()
    if os.environ.get("ORC_E2E_REPO_ROOT")
    else None
)
TIMEOUT_SEC = int(os.environ.get("ORC_E2E_TIMEOUT", "5400"))
POLL_SEC = int(os.environ.get("ORC_E2E_POLL", "30"))
HAPPY = {
    "status:pending-review",
    "status:pending-implementation",
    "status:pending-verification",
    "status:pending-acceptance",
    "status:accepted",
}


@pytest.mark.e2e
def test_dummy_issue_reaches_accepted() -> None:
    if not gh_available():
        pytest.skip("gh not authenticated")
    if TARGET_ROOT is None:
        pytest.skip("set ORC_E2E_REPO_ROOT to a project with .orc/config.yaml")
    if not (TARGET_ROOT / ".orc" / "config.yaml").is_file():
        pytest.skip(f"missing {TARGET_ROOT / '.orc' / 'config.yaml'}")

    body = """## Summary
[orc-e2e] Trivial task for agent-orc end-to-end workflow.

## Acceptance criteria
- [ ] Review passes this issue to pending-implementation
- [ ] Implement posts a deliverables comment (minimal PR or doc touch OK)
- [ ] Verify and accept reach status:accepted
"""
    try:
        number = create_issue(
            "[orc-e2e] agent-orc workflow probe",
            body,
            ["type:task", "status:pending-review"],
            cwd=str(TARGET_ROOT),
        )
    except GhError as exc:
        pytest.skip(f"cannot create issue: {exc}")

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "agent-orc",
            "--yes",
            "-n",
            "8",
            "--repo-root",
            str(TARGET_ROOT),
            "--config-dir",
            str(TARGET_ROOT / ".orc"),
        ],
        cwd=str(PACKAGE_ROOT),
        start_new_session=True,
    )

    deadline = time.monotonic() + TIMEOUT_SEC
    last_status: str | None = None
    diverted = False
    try:
        while time.monotonic() < deadline:
            status = issue_status_label(number, cwd=str(TARGET_ROOT))
            last_status = status
            if status == "status:accepted":
                break
            if status and status not in HAPPY:
                diverted = True
                break
            if proc.poll() is not None and status != "status:accepted":
                # orchestrator finished iterations; keep polling briefly
                if time.monotonic() + 120 < deadline:
                    deadline = time.monotonic() + 120
            time.sleep(POLL_SEC)
        else:
            pytest.fail(f"timeout waiting for accepted; last status={last_status} issue=#{number}")

        if diverted:
            pytest.fail(f"issue #{number} left happy path at {last_status}")
        assert last_status == "status:accepted"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            close_issue(number, cwd=str(TARGET_ROOT))
        except GhError:
            pass
