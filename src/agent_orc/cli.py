"""agent-orc CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from agent_orc.config import ConfigError, load_config
from agent_orc.logging_setup import setup_orchestrator_logging
from agent_orc.select import resolve_selected_agents
from agent_orc.shutdown import ShutdownController
from agent_orc.supervisor import run_supervisor

logger = logging.getLogger("agent_orc.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-orc",
        description=(
            "Orchestrate skill agents in isolated git worktrees of a target "
            "project. Config and skills come from that project "
            "(<repo>/.orc, <repo>/.agents/skills), not from the agent-orc package."
        ),
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=None,
        help="Each parallel slot runs N times, then exit (daemon if omitted)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip multi-select; run all enabled agents",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default=None,
        help="Comma-separated agent names (skips multi-select)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing config.yaml (default: <repo-root>/.orc)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Target git repository root (default: cwd)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        exit_code = run(args)
    except ConfigError as exc:
        print(f"agent-orc: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)


def run(args: argparse.Namespace) -> int:
    repo_root = (args.repo_root or Path.cwd()).resolve()
    config_dir = args.config_dir
    if config_dir is None:
        config_dir = repo_root / ".orc"
    config = load_config(config_dir)

    logs_dir = (repo_root / config.orchestrator.logs_dir).resolve()
    setup_orchestrator_logging(logs_dir)
    logger.info("loaded config from %s", config_dir)

    interactive = sys.stdin.isatty() and not args.yes and not args.agents
    selected = resolve_selected_agents(
        config,
        yes=args.yes,
        agents_csv=args.agents,
        interactive=interactive,
    )
    logger.info("selected agents: %s", ", ".join(a.name for a in selected))

    shutdown = ShutdownController()
    shutdown.install()

    return asyncio.run(
        run_supervisor(
            config,
            selected,
            count=args.count,
            shutdown=shutdown,
            repo_root=repo_root,
        )
    )


if __name__ == "__main__":
    main()
