"""Shared fixtures: temp git repo, short config, fake provider script."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

# Re-export helper for fixtures/tests
from helpers import write_test_config  # noqa: F401


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "orc-test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "orc-test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "fake_agent.py"
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json, os, sys, time
            from pathlib import Path
            marker = Path(os.environ.get("ORC_FAKE_MARKER", "marker.txt"))
            delay = float(os.environ.get("ORC_FAKE_DELAY", "0"))
            code = int(os.environ.get("ORC_FAKE_EXIT", "0"))
            if delay:
                time.sleep(delay)
            record = Path(os.environ.get("ORC_FAKE_RECORD", "record.jsonl"))
            if not record.is_absolute():
                record = Path.cwd() / record
            record.parent.mkdir(parents=True, exist_ok=True)
            with record.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"cwd": os.getcwd(), "argv": sys.argv[1:]}) + "\\n")
            marker.write_text("ok", encoding="utf-8")
            print("fake-agent ok", flush=True)
            raise SystemExit(code)
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script
