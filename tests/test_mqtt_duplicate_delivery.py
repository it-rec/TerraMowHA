"""Overlapping-subscription duplicate suppression.

``_async_on_connected`` subscribes ``#`` for broker-wide discovery *on top of*
the specific topic filters, and brokers commonly deliver one copy per matching
subscription. These tests pin what the suppression drops (a byte-identical
redelivery inside the window) and — more importantly — what it must never drop:
a changed payload, a slow republish, or a repeat on a different topic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.terramow import hub as hub_module
from custom_components.terramow.const import POSE_TOPIC
from custom_components.terramow.hub import (
    MQTT_DUPLICATE_TRACKED_TOPICS,
    TerraMowHub,
)


class _Msg:
    """The plain topic/payload shape ``on_mqtt_message`` consumes."""

    def __init__(self, topic: str, payload: str) -> None:
        self.topic = topic
        self.payload = payload.encode()


def _hub() -> TerraMowHub:
    basic_data = MagicMock()
    basic_data.host = "192.0.2.60"
    basic_data.password = "secret"
    hub = TerraMowHub(basic_data, MagicMock())
    return hub


def _deliver(hub: TerraMowHub, topic: str, payload: str) -> None:
    hub.on_mqtt_message(None, None, _Msg(topic, payload))


def _pose_calls(hub: TerraMowHub, monkeypatch: Any) -> list[dict[str, Any]]:
    """Record every pose that reaches the dispatch layer."""
    seen: list[dict[str, Any]] = []

    def _capture(targets: list[Any], *args: Any) -> None:
        seen.append(args[0])

    monkeypatch.setattr(hub, "_dispatch_batch", _capture)
    return seen


def test_identical_redelivery_is_dropped(monkeypatch: Any) -> None:
    """The second copy of one publish never reaches the handlers."""
    hub = _hub()
    seen = _pose_calls(hub, monkeypatch)

    payload = '{"x": 1.0, "y": 2.0, "yaw": 0.5}'
    _deliver(hub, POSE_TOPIC, payload)
    _deliver(hub, POSE_TOPIC, payload)  # the "#" copy of the same publish

    assert len(seen) == 1
    assert hub._duplicate_deliveries[POSE_TOPIC] == 1


def test_changed_payload_always_passes(monkeypatch: Any) -> None:
    """Only byte-identical repeats are suppressed — a moving mower is not."""
    hub = _hub()
    seen = _pose_calls(hub, monkeypatch)

    for x in (1.0, 1.0, 2.0, 2.0, 3.0):
        _deliver(hub, POSE_TOPIC, f'{{"x": {x}, "y": 0.0, "yaw": 0.0}}')

    # three distinct poses through, two redeliveries dropped
    assert [pose["x"] for pose in seen] == [1.0, 2.0, 3.0]
    assert hub._duplicate_deliveries[POSE_TOPIC] == 2


def test_repeat_after_the_window_passes(monkeypatch: Any) -> None:
    """A genuinely unchanged republish is not suppressed forever.

    A docked mower reports the same pose at ~2 Hz; that is five times the
    window and must keep flowing.
    """
    hub = _hub()
    seen = _pose_calls(hub, monkeypatch)
    clock = {"t": 1000.0}
    monkeypatch.setattr(hub_module.time, "monotonic", lambda: clock["t"])

    payload = '{"x": 0.0, "y": 0.0, "yaw": 0.0}'
    _deliver(hub, POSE_TOPIC, payload)
    clock["t"] += 0.001  # the "#" copy, same broker flush
    _deliver(hub, POSE_TOPIC, payload)
    clock["t"] += 0.5  # the next 2 Hz report, unchanged
    _deliver(hub, POSE_TOPIC, payload)

    assert len(seen) == 2
    assert hub._duplicate_deliveries[POSE_TOPIC] == 1


def test_window_is_measured_from_the_first_copy(monkeypatch: Any) -> None:
    """Suppressing a copy must not extend the window.

    Otherwise a topic republishing faster than the window would be silenced
    indefinitely: every drop would push the deadline out again.
    """
    hub = _hub()
    seen = _pose_calls(hub, monkeypatch)
    clock = {"t": 500.0}
    monkeypatch.setattr(hub_module.time, "monotonic", lambda: clock["t"])

    payload = '{"x": 9.0, "y": 9.0, "yaw": 0.0}'
    _deliver(hub, POSE_TOPIC, payload)
    for _ in range(5):
        clock["t"] += 0.15  # each inside the window of the PREVIOUS delivery
        _deliver(hub, POSE_TOPIC, payload)

    # 0.15 * 2 = 0.30 > the 0.2 window, so every second repeat gets through
    assert len(seen) == 3


def test_same_payload_on_a_different_topic_passes(monkeypatch: Any) -> None:
    """The check is per topic; two topics sharing a payload are unrelated."""
    hub = _hub()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        hub, "_handle_map_info", lambda payload: calls.append(("map", payload))
    )
    monkeypatch.setattr(
        hub, "_handle_model_name", lambda payload: calls.append(("model", payload))
    )

    _deliver(hub, hub_module.MAP_INFO_TOPIC, "{}")
    _deliver(hub, hub_module.MODEL_NAME_TOPIC, "{}")

    assert [kind for kind, _ in calls] == ["map", "model"]
    assert not hub._duplicate_deliveries


def test_tracked_topics_are_bounded(monkeypatch: Any) -> None:
    """The "#" subscription cannot grow the bookkeeping without bound."""
    hub = _hub()
    monkeypatch.setattr(hub, "_dispatch_batch", lambda *args: None)

    for index in range(MQTT_DUPLICATE_TRACKED_TOPICS + 50):
        _deliver(hub, f"discovered/topic/{index}", "payload")

    assert len(hub._last_delivery) == MQTT_DUPLICATE_TRACKED_TOPICS
    # The oldest topics were evicted; the newest are still tracked.
    assert "discovered/topic/0" not in hub._last_delivery
    assert f"discovered/topic/{MQTT_DUPLICATE_TRACKED_TOPICS + 49}" in hub._last_delivery


def test_evicted_topics_drop_their_duplicate_counter(monkeypatch: Any) -> None:
    """The per-topic counter stays a subset of the tracked topics."""
    hub = _hub()
    monkeypatch.setattr(hub, "_dispatch_batch", lambda *args: None)

    _deliver(hub, "discovered/topic/first", "payload")
    _deliver(hub, "discovered/topic/first", "payload")  # counted
    assert hub._duplicate_deliveries["discovered/topic/first"] == 1

    for index in range(MQTT_DUPLICATE_TRACKED_TOPICS + 1):
        _deliver(hub, f"discovered/topic/{index}", "payload")

    assert "discovered/topic/first" not in hub._last_delivery
    assert "discovered/topic/first" not in hub._duplicate_deliveries
    assert set(hub._duplicate_deliveries) <= set(hub._last_delivery)


def test_counter_is_exported_in_the_diagnostics_snapshot(monkeypatch: Any) -> None:
    """The count is what proves (or refutes) the double delivery in the field."""
    hub = _hub()
    monkeypatch.setattr(hub, "_dispatch_batch", lambda *args: None)

    _deliver(hub, POSE_TOPIC, '{"x": 0.0}')
    _deliver(hub, POSE_TOPIC, '{"x": 0.0}')

    snapshot = hub.diagnostics_snapshot()
    assert snapshot["duplicate_deliveries"] == {POSE_TOPIC: 1}
    # A copy, not the live counter
    assert snapshot["duplicate_deliveries"] is not hub._duplicate_deliveries
