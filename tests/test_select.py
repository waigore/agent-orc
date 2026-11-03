from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_orc.config import ConfigError, load_config
from agent_orc.select import resolve_selected_agents


def _cfg(tmp_path: Path):
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "one": {
                        "skill": "one",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "a",
                    },
                    "two": {
                        "skill": "two",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "b",
                    },
                    "off": {
                        "skill": "off",
                        "provider": "p",
                        "enabled": False,
                        "prompt": "c",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return load_config(cfg_dir)


def test_yes_selects_enabled(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    selected = resolve_selected_agents(cfg, yes=True, interactive=False)
    assert [a.name for a in selected] == ["one", "two"]


def test_agents_csv(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    selected = resolve_selected_agents(cfg, agents_csv="two", interactive=False)
    assert [a.name for a in selected] == ["two"]


def test_unknown_agent(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with pytest.raises(ConfigError, match="unknown"):
        resolve_selected_agents(cfg, agents_csv="nope", interactive=False)
