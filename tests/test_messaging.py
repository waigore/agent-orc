from agent_orc.messaging import clear_subscribers, publish, subscribe


def test_publish_subscribe_noop_safe() -> None:
    clear_subscribers()
    seen: list[object] = []
    subscribe("t", seen.append)
    publish("t", {"ok": True})
    assert seen == [{"ok": True}]
    clear_subscribers()
    publish("t", 1)  # no subscribers
