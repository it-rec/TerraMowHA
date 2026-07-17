"""Coverage for the persistent unknown-dp JSONL logger.

The logger appends undocumented-dp *changes* to a restart-proof file in the HA
config dir, gated on the integration's debug-logging level. Covers the write /
append / rotate / error paths of the helper and the debug-gated call site in
``on_mqtt_message`` (including the change-only guard).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow import hub as hub_module
from custom_components.terramow.hub import (
    UNKNOWN_DP_LOG_FILE,
    UNKNOWN_DP_LOG_MAX_BYTES,
    TerraMowHub,
)


def _hub(tmp_path) -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.170", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.hass.config.path = lambda name: str(tmp_path / name)
    return hub


def _lines(tmp_path):
    p = tmp_path / UNKNOWN_DP_LOG_FILE
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line]


def _feed_unknown(hub, payload=b'{"int_value": 7}'):
    hub.on_mqtt_message(
        None, None, SimpleNamespace(topic="data_point/9999/robot", payload=payload)
    )


def test_persist_writes_line(tmp_path):
    hub = _hub(tmp_path)
    hub._persist_unknown_dp(1.5, 200, '{"int_value": 5}')
    assert _lines(tmp_path) == [
        {"t": 1.5, "dp": 200, "payload": '{"int_value": 5}'}
    ]


def test_persist_appends(tmp_path):
    hub = _hub(tmp_path)
    hub._persist_unknown_dp(1.0, 200, "a")
    hub._persist_unknown_dp(2.0, 201, "b")  # existing small file -> no rotation
    assert [r["dp"] for r in _lines(tmp_path)] == [200, 201]


def test_persist_rotates_at_cap(tmp_path):
    hub = _hub(tmp_path)
    target = tmp_path / UNKNOWN_DP_LOG_FILE
    target.write_text("old\n")
    with patch(
        "custom_components.terramow.hub.os.path.getsize",
        return_value=UNKNOWN_DP_LOG_MAX_BYTES,
    ):
        hub._persist_unknown_dp(3.0, 202, "fresh")
    assert (tmp_path / f"{UNKNOWN_DP_LOG_FILE}.1").read_text() == "old\n"
    assert _lines(tmp_path) == [{"t": 3.0, "dp": 202, "payload": "fresh"}]


def test_persist_swallows_write_error(tmp_path):
    hub = _hub(tmp_path)
    with patch(
        "custom_components.terramow.hub.open", create=True, side_effect=OSError("full")
    ):
        hub._persist_unknown_dp(1.0, 200, "x")  # must not raise
    assert _lines(tmp_path) == []


def test_on_message_persists_when_debug(tmp_path, monkeypatch):
    hub = _hub(tmp_path)
    monkeypatch.setattr(hub_module._LOGGER, "isEnabledFor", lambda level: True)
    _feed_unknown(hub)
    rows = _lines(tmp_path)
    assert len(rows) == 1
    assert rows[0]["dp"] == 9999
    assert rows[0]["payload"] == '{"int_value": 7}'


def test_on_message_no_persist_when_not_debug(tmp_path, monkeypatch):
    hub = _hub(tmp_path)
    monkeypatch.setattr(hub_module._LOGGER, "isEnabledFor", lambda level: False)
    _feed_unknown(hub)
    assert _lines(tmp_path) == []


def test_repeat_payload_not_persisted_twice(tmp_path, monkeypatch):
    hub = _hub(tmp_path)
    monkeypatch.setattr(hub_module._LOGGER, "isEnabledFor", lambda level: True)
    _feed_unknown(hub)
    _feed_unknown(hub)  # identical payload -> no value change -> no new line
    assert len(_lines(tmp_path)) == 1
