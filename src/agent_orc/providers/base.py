"""Provider command rendering."""

from __future__ import annotations

from collections.abc import Sequence


def render_command(
    template: Sequence[str],
    *,
    prompt: str,
    workdir: str,
    skill: str,
) -> list[str]:
    """Substitute {prompt}, {workdir}, {skill} in each argv element."""
    mapping = {"prompt": prompt, "workdir": workdir, "skill": skill}
    rendered: list[str] = []
    for part in template:
        out = part
        for key, value in mapping.items():
            out = out.replace("{" + key + "}", value)
        rendered.append(out)
    return rendered
