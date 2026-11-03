from __future__ import annotations

from agent_orc.providers import render_command


def test_render_substitutions() -> None:
    cmd = render_command(
        ["agent", "-p", "{prompt}", "--ws", "{workdir}", "{skill}"],
        prompt="hello world",
        workdir="/tmp/wt",
        skill="issue-workflow-review-agent",
    )
    assert cmd == [
        "agent",
        "-p",
        "hello world",
        "--ws",
        "/tmp/wt",
        "issue-workflow-review-agent",
    ]
