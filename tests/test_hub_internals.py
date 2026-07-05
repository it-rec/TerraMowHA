"""Tests for the hub's protocol internals.

Covers the map/path meta sequencing, the HTTP fetch helper, model name
and compatibility handling, MQTT topic routing edge cases, shutdown and
the diagnostics export built on top of the hub state.
"""

import asyncio
import gzip
import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import CompatibilityStatus
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    return TerraMowHub(basic_data, MagicMock())


# ---------------------------------------------------------------------------
# meta seq parsing / pending replacement
# ---------------------------------------------------------------------------


def test_get_meta_seq() -> None:
    hub = _hub()
    assert hub._get_meta_seq({"seq": 7}, "map") == 7
    assert hub._get_meta_seq({"seq": "12"}, "map") == 12
    assert hub._get_meta_seq({}, "map") == -1
    assert hub._get_meta_seq({"seq": "not-a-number"}, "map") == -1


def test_should_replace_pending() -> None:
    hub = _hub()
    # nothing pending -> always replace
    assert hub._should_replace_pending(None, 5, "map") is True
    # newer seq wins, older/equal seq does not
    assert hub._should_replace_pending({"seq": 3}, 5, "map") is True
    assert hub._should_replace_pending({"seq": 5}, 5, "map") is False
    assert hub._should_replace_pending({"seq": 7}, 5, "map") is False
    # seq-less meta only replaces seq-less pending
    assert hub._should_replace_pending({"seq": 3}, -1, "map") is False
    assert hub._should_replace_pending({}, -1, "map") is True
    # a sequenced meta replaces a seq-less pending
    assert hub._should_replace_pending({}, 4, "map") is True


def test_retry_delay_ladder() -> None:
    hub = _hub()
    assert [hub._get_retry_delay(i) for i in range(6)] == [
        2.0, 5.0, 10.0, 30.0, 30.0, 30.0,
    ]


# ---------------------------------------------------------------------------
# map info building from HTTP map data
# ---------------------------------------------------------------------------


def test_build_map_info_maps_alternate_field_names() -> None:
    hub = _hub()
    info = hub._build_map_info_from_map_data(
        {"mapId": 4, "mapName": "Garten", "mapState": "MAP_STATE_COMPLETE"}
    )
    assert info["id"] == 4
    assert info["name"] == "Garten"
    assert info["map_state"] == "MAP_STATE_COMPLETE"


def test_build_map_info_resets_base_on_new_map_id() -> None:
    hub = _hub()
    hub._map_info = {"id": 1, "name": "Alt", "regions": [{"id": 9}]}
    info = hub._build_map_info_from_map_data({"id": 2, "name": "Neu"})
    # data from the old map must not leak into the new one
    assert info["id"] == 2
    assert info["name"] == "Neu"
    assert "regions" not in info


def test_build_map_info_defaults_and_invalid_input() -> None:
    hub = _hub()
    assert hub._build_map_info_from_map_data("not-a-dict") is None
    assert hub._build_map_info_from_map_data({}) is None
    info = hub._build_map_info_from_map_data({"name": "OhneState"})
    assert info["map_state"] == "unknown"


# ---------------------------------------------------------------------------
# HTTP fetch helper
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.last_url: str | None = None
        self.last_headers: dict | None = None

    def get(self, url, headers=None, timeout=None):
        self.last_url = url
        self.last_headers = headers
        return self._response


def _fetch(hub, monkeypatch, response, meta, etag=None):
    session = _FakeSession(response)
    monkeypatch.setattr(
        "custom_components.terramow.hub.async_get_clientsession",
        lambda hass: session,
    )
    result = asyncio.run(hub._async_fetch_json(meta, etag))
    return result, session


META = {"http_port": 8080, "http_path": "/map", "token": "tok"}


def test_fetch_json_success(monkeypatch) -> None:
    hub = _hub()
    body = json.dumps({"id": 1}).encode()
    (data, etag, ok, not_modified), session = _fetch(
        hub, monkeypatch, _FakeResponse(200, body, {"ETag": "abc"}), META
    )
    assert (data, etag, ok, not_modified) == ({"id": 1}, "abc", True, False)
    assert session.last_url == "http://192.0.2.10:8080/map"
    assert session.last_headers["Authorization"] == "Bearer tok"


def test_fetch_json_gzip_body(monkeypatch) -> None:
    hub = _hub()
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, arg: fn(arg))
    body = gzip.compress(json.dumps({"id": 2}).encode())
    (data, _etag, ok, _nm), _ = _fetch(hub, monkeypatch, _FakeResponse(200, body), META)
    assert ok is True
    assert data == {"id": 2}


def test_fetch_json_304_keeps_etag(monkeypatch) -> None:
    hub = _hub()
    (data, etag, ok, not_modified), session = _fetch(
        hub, monkeypatch, _FakeResponse(304), META, etag="cached"
    )
    assert (data, etag, ok, not_modified) == (None, "cached", True, True)
    assert session.last_headers["If-None-Match"] == "cached"


def test_fetch_json_http_error(monkeypatch) -> None:
    hub = _hub()
    (data, _etag, ok, _nm), _ = _fetch(hub, monkeypatch, _FakeResponse(500), META)
    assert data is None
    assert ok is False


def test_fetch_json_incomplete_meta() -> None:
    hub = _hub()
    data, etag, ok, not_modified = asyncio.run(
        hub._async_fetch_json({"http_port": 8080}, None)
    )
    assert (data, ok) == (None, False)


# ---------------------------------------------------------------------------
# meta handlers: seq dedup, session reset, retry scheduling
# ---------------------------------------------------------------------------


def _stub_fetch(hub, results):
    """Replace the HTTP fetch with a scripted async stub."""
    calls = []

    async def fake_fetch(meta, etag):
        calls.append(meta)
        return results.pop(0)

    hub._async_fetch_json = fake_fetch
    return calls


def test_map_meta_fetches_and_dedupes_by_seq() -> None:
    hub = _hub()
    calls = _stub_fetch(hub, [({"id": 1}, "e1", True, False)])
    meta = {"seq": 3, **META}

    asyncio.run(hub._async_handle_map_meta(meta))
    assert hub._map_seq == 3
    assert hub._map_data == {"id": 1}
    assert hub._map_etag == "e1"
    assert len(calls) == 1

    # same seq again -> ignored, no second fetch
    asyncio.run(hub._async_handle_map_meta(meta))
    assert len(calls) == 1


def test_map_meta_schedules_retry_on_failure() -> None:
    hub = _hub()
    _stub_fetch(hub, [(None, None, False, False)])
    hub._schedule_map_retry = MagicMock()

    meta = {"seq": 1, **META}
    asyncio.run(hub._async_handle_map_meta(meta))

    hub._schedule_map_retry.assert_called_once_with(meta)
    assert hub._map_seq == -1  # failed fetch must not consume the seq


def test_path_meta_backward_seq_resets_session() -> None:
    hub = _hub()
    hub._path_seq = 50
    hub._path_etag = "old"
    _stub_fetch(hub, [({"points": []}, "new", True, False)])

    asyncio.run(hub._async_handle_path_meta({"seq": 2, **META}))

    # backward seq means a new mowing session: old state cleared, fetch ran
    assert hub._path_seq == 2
    assert hub._path_etag == "new"
    assert hub._path_data == {"points": []}


def test_history_path_meta_backward_seq_resets_session() -> None:
    hub = _hub()
    hub._history_path_seq = 9
    _stub_fetch(hub, [({"paths": [1]}, None, True, False)])

    asyncio.run(hub._async_handle_history_path_meta({"seq": 0, **META}))

    assert hub._history_path_seq == 0
    assert hub._history_path_data == {"paths": [1]}


def test_map_meta_stores_pending_while_fetching() -> None:
    hub = _hub()
    hub._fetching_map = True
    asyncio.run(hub._async_handle_map_meta({"seq": 5, **META}))
    assert hub._pending_map_meta == {"seq": 5, **META}


# ---------------------------------------------------------------------------
# model name / firmware version / compatibility
# ---------------------------------------------------------------------------


def test_handle_model_name_updates_and_notifies() -> None:
    hub = _hub()
    listener = MagicMock()
    hub.register_state_listener(listener)

    hub._handle_model_name("  TerraMow S800  \n")

    assert hub.device_model == "TerraMow S800"
    listener.assert_called_once()
    hub.hass.add_job.assert_called_once_with(
        hub._async_update_device_model, "TerraMow S800"
    )


def test_handle_empty_model_name_keeps_default() -> None:
    hub = _hub()
    hub._handle_model_name("   ")
    assert hub.device_model == "TerraMow S1200"
    hub.hass.add_job.assert_not_called()


def test_format_firmware_version() -> None:
    fmt = TerraMowHub._format_firmware_version
    assert fmt({"overall": 26, "module": {"home_assistant": 3}}) == "26.3"
    assert fmt({"overall": 26}) == "26"
    assert fmt({}) is None


def test_compatibility_info_updates_basic_data() -> None:
    hub = _hub()
    payload = json.dumps({"overall": 26, "module": {"home_assistant": 3}})
    asyncio.run(hub.on_compatibility_info(payload))

    assert hub.basic_data.compatibility_status == CompatibilityStatus.COMPATIBLE
    assert hub.basic_data.firmware_version == {
        "overall": 26,
        "module": {"home_assistant": 3},
    }
    # device page firmware version scheduled
    hub.hass.add_job.assert_called_once_with(
        hub._async_update_device_sw_version, "26.3"
    )
    assert hub.firmware_version_info == {"overall": 26, "module": {"home_assistant": 3}}


def test_compatibility_info_upgrade_required() -> None:
    hub = _hub()
    payload = json.dumps({"overall": 20, "module": {"home_assistant": 1}})
    asyncio.run(hub.on_compatibility_info(payload))
    assert hub.basic_data.compatibility_status == CompatibilityStatus.UPGRADE_REQUIRED


# ---------------------------------------------------------------------------
# MQTT topic routing edge cases
# ---------------------------------------------------------------------------


def _msg(topic: str, payload: bytes):
    msg = MagicMock()
    msg.topic = topic
    msg.payload = payload
    return msg


def test_pose_topic_dispatches_to_pose_callbacks() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.register_pose_callback(cb)

    hub.on_mqtt_message(None, None, _msg("pose/current", b'{"x": 1.5, "yaw": 90}'))

    assert hub.pose == {"x": 1.5, "yaw": 90}
    hub.hass.add_job.assert_called_with(cb, {"x": 1.5, "yaw": 90})


def test_model_topic_routes_to_model_handler() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg("model/name", b"TerraMow S800"))
    assert hub.device_model == "TerraMow S800"


def test_map_info_topic_updates_map_and_notifies_callbacks() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.register_map_callback(cb)

    payload = json.dumps({"id": 1, "name": "Rasen", "map_state": "MAP_STATE_COMPLETE"})
    hub.on_mqtt_message(None, None, _msg("map/current/info", payload.encode()))

    assert hub.map_info["name"] == "Rasen"
    hub.hass.add_job.assert_called_with(cb, hub.map_info)


def test_register_map_callback_replays_existing_data() -> None:
    hub = _hub()
    hub._map_info = {"id": 1}
    cb = MagicMock()
    hub.register_map_callback(cb)
    hub.hass.add_job.assert_called_once_with(cb, {"id": 1})


def test_invalid_topic_is_ignored() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg("something/else", b"{}"))
    hub.hass.add_job.assert_not_called()


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


def test_async_stop_disconnects_and_clears_state() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub._pending_map_meta = {"seq": 1}

    asyncio.run(hub.async_stop())

    assert hub._stop_event.is_set()
    hub.mqtt_client.disconnect.assert_called_once()
    assert hub._pending_map_meta is None


# ---------------------------------------------------------------------------
# diagnostics export
# ---------------------------------------------------------------------------


def test_diagnostics_redacts_secrets_and_exports_hub_state() -> None:
    from custom_components.terramow.const import DOMAIN
    from custom_components.terramow.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    hub = _hub()
    hub.register_all_callbacks()
    asyncio.run(hub.on_battery_status(json.dumps({"state": "BATTERY_STATE_CHARGED"})))

    entry = MagicMock()
    entry.entry_id = "entry-1"
    entry.data = {"host": "192.0.2.10", "password": "secret"}
    entry.options = {}

    entry.runtime_data = hub.basic_data
    hass = MagicMock()

    diagnostics = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert diagnostics["entry"]["data"]["host"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"
    assert diagnostics["device"]["model"] == "TerraMow S1200"
    assert diagnostics["device"]["connection_error"] is False
    assert 107 in diagnostics["device"]["registered_data_points"]
    assert diagnostics["state"]["battery_status"] == {"state": "BATTERY_STATE_CHARGED"}


def test_diagnostics_without_loaded_data() -> None:
    from custom_components.terramow.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = MagicMock()
    entry.entry_id = "missing"
    entry.data = {}
    entry.options = {}
    entry.runtime_data = None
    hass = MagicMock()

    diagnostics = asyncio.run(async_get_config_entry_diagnostics(hass, entry))
    assert diagnostics["error"] == "integration data not loaded"
