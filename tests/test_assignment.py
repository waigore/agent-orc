from __future__ import annotations

from pathlib import Path

import pytest

from agent_orc.assignment import (
    UNASSIGNED_ISSUE,
    IssueListError,
    IssueOwnership,
    list_issue_numbers,
    parse_issue_numbers,
    render_agent_prompt,
)


def test_render_agent_prompt() -> None:
    text = render_agent_prompt("id={parallel_id} issue={issue}", parallel_id=2, issue="9")
    assert text == "id=2 issue=9"
    assert UNASSIGNED_ISSUE == "none"


def test_parse_issue_numbers() -> None:
    assert parse_issue_numbers('[{"number": 12}, {"number": 4}]') == [12, 4]


@pytest.mark.parametrize(
    "raw",
    ["", "nope", '{"number": 1}', "[{}]", '[{"number": 0}]', '[{"number": true}]'],
)
def test_parse_issue_numbers_rejects(raw: str) -> None:
    with pytest.raises(IssueListError):
        parse_issue_numbers(raw)


def test_list_issue_numbers(tmp_path: Path) -> None:
    numbers = list_issue_numbers(
        ["python3", "-c", "print('[{\"number\": 3}]')"],
        cwd=tmp_path,
    )
    assert numbers == [3]


def test_list_issue_numbers_nonzero(tmp_path: Path) -> None:
    with pytest.raises(IssueListError):
        list_issue_numbers(["python3", "-c", "raise SystemExit(1)"], cwd=tmp_path)


@pytest.mark.asyncio
async def test_claim_first_free_in_list_order_then_release() -> None:
    table = IssueOwnership()
    first = await table.claim("review#1", [12, 4, 4])
    second = await table.claim("review#2", [12, 4])
    blocked = await table.claim("refine#1", [4, 12])
    assert first == 12
    assert second == 4
    assert blocked is None
    await table.release("review#1")
    assert await table.claim("refine#1", [12, 4]) == 12
    await table.release("nobody")
