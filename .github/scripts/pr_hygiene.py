#!/usr/bin/env python3
"""Lint a pull request against docs/pull-requests.md.

Each rule takes the PR and returns findings; add a rule by writing a
function with that signature and listing it in RULES.

Reads PR_TITLE, PR_BODY, and optional PR_CHANGED_FILES (newline-separated
paths) from the environment, or the body from stdin when title/body env
vars are unset.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "pull_request_template.md"
TITLE_MAX = 72


@dataclass(frozen=True)
class PullRequest:
    title: str
    body: str
    changed_paths: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class Finding:
    rule: str
    field: str
    line: int
    message: str

    def location(self) -> str:
        return f"{self.field} line {self.line}" if self.line else self.field


KEYWORD = r"close[sd]?|fix(?:e[sd])?|resolve[sd]?"
ISSUE_REF = r"#\d+|[\w.-]+/[\w.-]+#\d+|https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+"
CLOSING = re.compile(
    rf"\b(?:{KEYWORD})\b\s*:?\s+(?:{ISSUE_REF})|\b(?:{KEYWORD}):(?:{ISSUE_REF})",
    re.IGNORECASE,
)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HEADING = re.compile(r"^##\s+(.+?)\s*#*\s*$")
BARE_NA = re.compile(r"^n/?a\.?$", re.IGNORECASE)


def headings(markdown: str) -> list[str]:
    return [m.group(1) for line in markdown.splitlines() if (m := HEADING.match(line))]


REQUIRED_SECTIONS = headings(TEMPLATE.read_text(encoding="utf-8"))


def parse_sections(body: str) -> dict[str, tuple[int, str]]:
    """Map lowercased `## Heading` to (heading line, content with HTML comments removed)."""
    uncommented = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), body)
    sections: dict[str, tuple[int, str]] = {}
    current: str | None = None
    for n, line in enumerate(uncommented.splitlines(), 1):
        if m := HEADING.match(line):
            current = m.group(1).lower()
            sections[current] = (n, "")
        elif current is not None:
            start, content = sections[current]
            sections[current] = (start, content + line + "\n")
    return sections


def closing_keywords(pr: PullRequest) -> list[Finding]:
    """Prefer `Refs #n` so merges do not auto-close issues unless intentional."""
    return [
        Finding(
            "closing-keywords",
            field,
            n,
            f"'{m.group(0)}' would close the issue on merge; use 'Refs #n' instead.",
        )
        for field, text in (("title", pr.title), ("body", pr.body))
        for n, line in enumerate(text.splitlines(), 1)
        for m in CLOSING.finditer(line)
    ]


def title_format(pr: PullRequest) -> list[Finding]:
    """Title is the squash subject: non-empty, <= TITLE_MAX chars, no trailing period."""
    title = pr.title.strip()
    if not title:
        return [Finding("title-format", "title", 0, "title is empty.")]
    findings = []
    if len(title) > TITLE_MAX:
        findings.append(
            Finding(
                "title-format",
                "title",
                0,
                f"title is {len(title)} characters; keep it at most {TITLE_MAX}.",
            )
        )
    if title.endswith("."):
        findings.append(Finding("title-format", "title", 0, "title ends with a period; drop it."))
    return findings


def template_sections(
    pr: PullRequest, required: Sequence[str] = REQUIRED_SECTIONS
) -> list[Finding]:
    """Every template section is present and filled; `N/A` needs a reason."""
    sections = parse_sections(pr.body)
    findings = []
    for name in required:
        if name.lower() not in sections:
            findings.append(
                Finding("template-sections", "body", 0, f"missing section '## {name}'.")
            )
            continue
        line, content = sections[name.lower()]
        text = content.strip()
        if not text:
            findings.append(
                Finding(
                    "template-sections",
                    "body",
                    line,
                    f"section '## {name}' is empty; fill it or write 'N/A' with a reason.",
                )
            )
        elif BARE_NA.match(text):
            findings.append(
                Finding(
                    "template-sections",
                    "body",
                    line,
                    f"section '## {name}' is 'N/A' without a reason.",
                )
            )
    return findings


RULES: list[Callable[[PullRequest], list[Finding]]] = [
    closing_keywords,
    title_format,
    template_sections,
]


def lint(pr: PullRequest) -> list[Finding]:
    return [finding for rule in RULES for finding in rule(pr)]


def changed_paths_from_env() -> tuple[str, ...]:
    raw = os.environ.get("PR_CHANGED_FILES", "")
    return tuple(line for line in raw.splitlines() if line.strip())


def main() -> int:
    paths = changed_paths_from_env()
    if "PR_TITLE" in os.environ or "PR_BODY" in os.environ:
        pr = PullRequest(os.environ.get("PR_TITLE", ""), os.environ.get("PR_BODY", ""), paths)
    else:
        pr = PullRequest("", sys.stdin.read(), paths)

    findings = lint(pr)
    for f in findings:
        print(f"::error title=PR hygiene ({f.rule})::{f.location()}: {f.message}")
    if findings:
        print(f"PR hygiene: {len(findings)} error(s). See docs/pull-requests.md.")
        return 1
    print(f"PR hygiene: OK across {len(RULES)} rule(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
