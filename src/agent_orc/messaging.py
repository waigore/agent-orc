"""No-op message bus stub for future agent-to-agent communication."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_subscribers: dict[str, list[Callable[[Any], None]]] = {}


def publish(topic: str, payload: Any = None) -> None:
    for callback in _subscribers.get(topic, []):
        callback(payload)


def subscribe(topic: str, callback: Callable[[Any], None]) -> None:
    _subscribers.setdefault(topic, []).append(callback)


def clear_subscribers() -> None:
    _subscribers.clear()
