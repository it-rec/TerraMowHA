"""Coverage for the hub's HTTP map/path fetch + decompress orchestration."""

import asyncio
import gzip
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import DOMAIN
import custom_components.terramow.hub as hub_module
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.120", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    # run executor jobs (gzip.decompress) inline and swallow fire-and-forget tasks
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    hub.hass.async_create_task = MagicMock(
        side_effect=lambda c: c.close() if hasattr(c, "close") else None
    )
    return hub


META = {"seq": 5, "http_port": 8080, "http_path": "/map", "token": "tok"}


class _FakeResp:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self.headers = headers if headers is not None else {"ETag": "etag-1"}

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, headers=None, timeout=None):
        return self._resp


def _patch_session(resp):
    return patch(
        "custom_components.terramow.hub.async_get_clientsession",
        return_value=_FakeSession(resp),
    )


async def _fetch(hub, meta=META, etag=None, resp=None):
    with _patch_session(resp):
        return await hub._async_fetch_json(meta, etag)


# ---------------------------------------------------------------------------
# _async_fetch_json
# ---------------------------------------------------------------------------


async def test_fetch_json_incomplete_meta() -> None:
    hub = _hub()
    data, etag, ok, not_mod = await hub._async_fetch_json({"seq": 1}, "e")
    assert data is None and ok is False and not_mod is False and etag == "e"


async def test_fetch_json_success_returns_data_and_etag() -> None:
    hub = _hub()
    resp = _FakeResp(status=200, body=b'{"id": 3}', headers={"ETag": "new-etag"})
    data, etag, ok, not_mod = await _fetch(hub, resp=resp)
    assert data == {"id": 3}
    assert etag == "new-etag"
    assert ok is True and not_mod is False


async def test_fetch_json_not_modified() -> None:
    hub = _hub()
    resp = _FakeResp(status=304)
    data, etag, ok, not_mod = await _fetch(hub, etag="keep", resp=resp)
    assert data is None and etag == "keep" and ok is True and not_mod is True


async def test_fetch_json_http_error() -> None:
    hub = _hub()
    resp = _FakeResp(status=503)
    data, etag, ok, not_mod = await _fetch(hub, etag="e", resp=resp)
    assert data is None and ok is False and not_mod is False


async def test_fetch_json_gzip_body_is_decompressed() -> None:
    hub = _hub()
    payload = gzip.compress(b'{"id": 9}')
    resp = _FakeResp(status=200, body=payload, headers={})
    data, etag, ok, _ = await _fetch(hub, etag="prev", resp=resp)
    assert data == {"id": 9}
    # no ETag header -> keep the previous one
    assert etag == "prev"
    assert ok is True


async def test_fetch_json_parses_in_executor() -> None:
    # Both gzip and plain bodies must decode+parse in the executor, never on
    # the event loop: large ha_map_v1/ha_path_v1 payloads stall it otherwise.
    hub = _hub()
    resp = _FakeResp(status=200, body=b'{"id": 3}')
    data, *_ = await _fetch(hub, resp=resp)
    assert data == {"id": 3}
    (fn, arg), _kwargs = hub.hass.async_add_executor_job.call_args
    assert fn is hub_module._decompress_and_parse
    assert arg == b'{"id": 3}'


# ---------------------------------------------------------------------------
# meta handlers: success, seq guard, retry
# ---------------------------------------------------------------------------


async def test_handle_map_meta_success_updates_map() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.map_callbacks.append(cb)
    resp = _FakeResp(status=200, body=b'{"id": 1, "map_state": "MAP_STATE_COMPLETE"}')
    with _patch_session(resp):
        await hub._async_handle_meta(hub._map_channel, META)
    assert hub.map_data["id"] == 1
    assert hub._map_channel.seq == 5


async def test_handle_map_meta_seq_guard_skips_duplicate() -> None:
    hub = _hub()
    hub._map_channel.seq = 10
    called = MagicMock()
    with patch(
        "custom_components.terramow.hub.async_get_clientsession", called
    ):
        # seq == current (not backward) -> skipped by the seq guard
        await hub._async_handle_meta(hub._map_channel, {"seq": 10, "http_port": 1, "http_path": "/m", "token": "t"})
    called.assert_not_called()


async def test_handle_map_meta_backward_seq_resets_and_refetches() -> None:
    hub = _hub()
    hub._map_channel.seq = 10
    resp = _FakeResp(status=200, body=b'{"id": 9, "map_state": "MAP_STATE_COMPLETE"}')
    # seq 4 < 10 -> new-session reset, then the fetch proceeds (a new map would
    # otherwise stay hidden behind the seq guard until a reload)
    with _patch_session(resp):
        await hub._async_handle_meta(hub._map_channel, {"seq": 4, "http_port": 1, "http_path": "/m", "token": "t"})
    assert hub.map_data["id"] == 9
    assert hub._map_channel.seq == 4


async def test_handle_map_meta_schedules_retry_on_failure() -> None:
    hub = _hub()
    resp = _FakeResp(status=500)
    with _patch_session(resp):
        await hub._async_handle_meta(hub._map_channel, META)
    # a retry task was scheduled and retry meta cached
    assert hub._map_channel.retry_meta == META
    assert hub.hass.async_create_task.called


async def test_handle_path_meta_success_and_backward_reset() -> None:
    hub = _hub()
    hub._path_channel.seq = 8
    cb = MagicMock()
    hub.path_callbacks.append(cb)
    resp = _FakeResp(status=200, body=b'{"id": 2, "map_id": 1, "points": []}')
    # seq 3 < 8 -> backward reset, then fetch proceeds
    with _patch_session(resp):
        await hub._async_handle_meta(hub._path_channel, {"seq": 3, "http_port": 1, "http_path": "/p", "token": "t"})
    assert hub.path_data["id"] == 2
    assert hub._path_channel.seq == 3


async def test_handle_history_path_meta_success() -> None:
    hub = _hub()
    resp = _FakeResp(status=200, body=b'{"id": 7, "map_id": 1, "points": []}')
    with _patch_session(resp):
        await hub._async_handle_meta(hub._history_path_channel, 
            {"seq": 2, "http_port": 1, "http_path": "/h", "token": "t"}
        )
    assert hub.history_path_data["id"] == 7
    assert hub._history_path_channel.seq == 2


# ---------------------------------------------------------------------------
# meta/seq/retry helpers
# ---------------------------------------------------------------------------


def test_meta_seq_and_pending_helpers() -> None:
    hub = _hub()
    assert hub._get_meta_seq({"seq": 4}, "map") == 4
    assert hub._get_meta_seq({"seq": "bad"}, "map") == -1  # invalid -> -1

    assert hub._should_replace_pending(None, 3, "map") is True
    assert hub._should_replace_pending({"seq": 2}, 5, "map") is True
    assert hub._should_replace_pending({"seq": 9}, 5, "map") is False
    assert hub._should_replace_pending({"seq": -1}, -1, "map") is True


def test_retry_delay_progression_and_reset() -> None:
    hub = _hub()
    assert hub._get_retry_delay(0) == 2.0
    assert hub._get_retry_delay(1) == 5.0
    assert hub._get_retry_delay(99) == 30.0  # clamps to the last delay

    # scheduling then resetting clears the retry state
    hub._schedule_meta_retry(hub._map_channel, META)
    assert hub._map_channel.retry_meta == META
    hub._reset_meta_retry(hub._map_channel)
    assert hub._map_channel.retry_meta is None and hub._map_channel.retry_count == 0
    hub._schedule_meta_retry(hub._path_channel, META)
    hub._reset_meta_retry(hub._path_channel)
    assert hub._path_channel.retry_meta is None
    hub._schedule_meta_retry(hub._history_path_channel, META)
    hub._reset_meta_retry(hub._history_path_channel)
    assert hub._history_path_channel.retry_meta is None
    hub._reset_pending_meta()
    assert hub._map_channel.pending_meta is None


def test_schedule_retry_noop_after_stop_requested() -> None:
    # Once shutdown has started, no new retry task may be scheduled (otherwise a
    # retry could fire against a torn-down entry).
    hub = _hub()
    hub._stop_event.set()
    hub.hass.async_create_task.reset_mock()
    hub._schedule_meta_retry(hub._map_channel, META)
    hub._schedule_meta_retry(hub._path_channel, META)
    hub._schedule_meta_retry(hub._history_path_channel, META)
    hub.hass.async_create_task.assert_not_called()
    assert hub._map_channel.retry_meta is None
    assert hub._path_channel.retry_meta is None
    assert hub._history_path_channel.retry_meta is None


def test_build_map_info_from_map_data() -> None:
    hub = _hub()
    assert hub._build_map_info_from_map_data("not-a-dict") is None
    info = hub._build_map_info_from_map_data({"id": 1, "name": "Garten", "regions": []})
    assert info["id"] == 1 and info["name"] == "Garten"
    # a new map id resets the accumulated base
    hub._map_info = {"id": 1, "name": "old"}
    info2 = hub._build_map_info_from_map_data({"map_id": 2})
    assert info2["id"] == 2


# ---------------------------------------------------------------------------
# retry coroutines + no-seq throttle
# ---------------------------------------------------------------------------


async def test_retry_coroutines_refetch() -> None:
    resp = _FakeResp(status=200, body=b'{"id": 1, "map_state": "MAP_STATE_COMPLETE"}')
    hub = _hub()
    hub._map_channel.retry_meta = META
    with patch("asyncio.sleep", AsyncMock()), _patch_session(resp):
        await hub._async_retry_meta(hub._map_channel, 0.0)
    assert hub.map_data["id"] == 1

    hub2 = _hub()
    hub2._path_channel.retry_meta = {"seq": 1, "http_port": 1, "http_path": "/p", "token": "t"}
    with patch("asyncio.sleep", AsyncMock()), _patch_session(
        _FakeResp(body=b'{"id": 2, "map_id": 1, "points": []}')
    ):
        await hub2._async_retry_meta(hub2._path_channel, 0.0)
    assert hub2.path_data["id"] == 2

    hub3 = _hub()
    hub3._history_path_channel.retry_meta = {"seq": 1, "http_port": 1, "http_path": "/h", "token": "t"}
    with patch("asyncio.sleep", AsyncMock()), _patch_session(
        _FakeResp(body=b'{"id": 3, "map_id": 1, "points": []}')
    ):
        await hub3._async_retry_meta(hub3._history_path_channel, 0.0)
    assert hub3.history_path_data["id"] == 3


async def test_retry_coroutine_cancelled() -> None:
    hub = _hub()
    hub._map_channel.retry_meta = META
    # a cancelled sleep returns early without fetching
    with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
        await hub._async_retry_meta(hub._map_channel, 0.0)
    assert hub.map_data == {}


async def test_map_meta_no_seq_is_throttled() -> None:
    hub = _hub()
    resp = _FakeResp(status=200, body=b'{"id": 1, "map_state": "MAP_STATE_COMPLETE"}')
    no_seq = {"http_port": 1, "http_path": "/m", "token": "t"}  # no seq -> -1
    with _patch_session(resp):
        await hub._async_handle_meta(hub._map_channel, no_seq)
    assert hub.map_data["id"] == 1
    # an immediate second no-seq meta is throttled (min interval not elapsed)
    session_call = MagicMock()
    with patch("custom_components.terramow.hub.async_get_clientsession", session_call):
        await hub._async_handle_meta(hub._map_channel, no_seq)
    session_call.assert_not_called()


# ---------------------------------------------------------------------------
# device registry updates (real hass)
# ---------------------------------------------------------------------------


def _real_hub(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.120", CONF_PASSWORD: "secret"},
        unique_id="192.0.2.120",
    )
    entry.add_to_hass(hass)
    hub = TerraMowHub(TerraMowBasicData(host="192.0.2.120", password="secret"), hass)
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("terramow", "192.0.2.120")},
    )
    return hub, reg


async def test_update_device_sw_version_and_model(hass: HomeAssistant) -> None:
    hub, reg = _real_hub(hass)
    await hub._async_update_device_sw_version("26.3")
    await hub._async_update_device_model("TerraMow-Pro")
    device = reg.async_get_device({("terramow", "192.0.2.120")})
    assert device.sw_version == "26.3"
    assert device.model == "TerraMow-Pro"


async def test_update_device_model_missing_device_warns(hass: HomeAssistant) -> None:
    # a hub whose device is not registered -> the "not found" branch, no raise
    hub = TerraMowHub(TerraMowBasicData(host="192.0.2.199", password="s"), hass)
    await hub._async_update_device_model("X")


async def test_update_device_sw_version_swallows_errors() -> None:
    # MagicMock hass makes dr.async_get raise -> caught and logged
    hub = _hub()
    await hub._async_update_device_sw_version("1.0")


# ---------------------------------------------------------------------------
# hub properties + command no-op branches
# ---------------------------------------------------------------------------


import json as _json  # noqa: E402


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(_json.dumps(payload)))


def test_hub_compat_and_task_properties() -> None:
    hub = _hub()
    assert isinstance(hub.compatibility_status, str)
    assert isinstance(hub.compatibility_message, str)
    assert hub.firmware_version_info == {}
    assert hub.is_saving_data is False
    assert hub.is_data_conversion_in_progress is False


def test_start_mowing_while_running_is_noop() -> None:
    hub = _hub()
    hub._last_control_time = 0.0
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING",
    })
    hub.mqtt_client.publish.reset_mock()
    hub.start_mowing()  # already mowing -> no command
    hub.mqtt_client.publish.assert_not_called()


def test_pause_while_already_paused_is_noop() -> None:
    hub = _hub()
    hub._last_control_time = 0.0
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_PAUSE",
    })
    hub.mqtt_client.publish.reset_mock()
    hub.pause()  # already paused -> no command
    hub.mqtt_client.publish.assert_not_called()


def test_pause_non_mow_mission_running_publishes() -> None:
    hub = _hub()
    hub._last_control_time = 0.0
    _feed(hub.on_mission_status, {"mission": "MISSION_IDLE", "state": "MISSION_STATE_RUNNING"})
    hub.pause()  # running non-mow mission -> pause command (dp_105)
    topic, _payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/105/app"
