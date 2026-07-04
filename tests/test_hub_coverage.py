"""Coverage for hub message routing, lifecycle, retry and device-registry paths.

Complements test_hub_fetch / test_hub_commands by exercising the branches those
files leave open: the on_mqtt_message topic dispatcher, start()/async_stop()
lifecycle, the path/history-path meta pending/throttle/retry/requeue logic, the
retry schedulers/cancellers, the command rate-limit and mission-state guards and
the device-registry firmware/model updates.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    MAP_INFO_TOPIC,
    MAP_META_TOPIC,
    MODEL_NAME_TOPIC,
    PATH_HISTORY_META_TOPIC,
    PATH_META_TOPIC,
    POSE_TOPIC,
)
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.130", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub._last_control_time = 0.0
    # run executor jobs inline; swallow fire-and-forget coroutines
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    hub.hass.async_create_task = MagicMock(
        side_effect=lambda c: c.close() if hasattr(c, "close") else None
    )
    return hub


def _msg(topic: str, payload) -> MagicMock:
    m = MagicMock()
    m.topic = topic
    m.payload = payload.encode() if isinstance(payload, str) else payload
    return m


META_P = {"seq": 5, "http_port": 8080, "http_path": "/p", "token": "t"}
META_H = {"seq": 5, "http_port": 8080, "http_path": "/h", "token": "t"}
META_M = {"seq": 5, "http_port": 8080, "http_path": "/m", "token": "t"}


class _FakeResp:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self.headers = headers if headers is not None else {"ETag": "e"}

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


# ---------------------------------------------------------------------------
# on_mqtt_message dispatch
# ---------------------------------------------------------------------------


def test_on_mqtt_message_routes_every_topic() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg(MAP_META_TOPIC, '{"seq": 1}'))
    hub.on_mqtt_message(None, None, _msg(PATH_META_TOPIC, '{"seq": 2}'))
    hub.on_mqtt_message(None, None, _msg(PATH_HISTORY_META_TOPIC, '{"seq": 3}'))
    hub.on_mqtt_message(None, None, _msg(POSE_TOPIC, '{"x": 9}'))
    hub.on_mqtt_message(
        None, None, _msg(MAP_INFO_TOPIC, '{"map_state": "MAP_STATE_COMPLETE"}')
    )
    hub.on_mqtt_message(None, None, _msg(MODEL_NAME_TOPIC, "TerraMow S1200"))

    assert hub._map_meta == {"seq": 1}
    assert hub._path_meta == {"seq": 2}
    assert hub._history_path_meta == {"seq": 3}
    assert hub._pose == {"x": 9}
    assert hub.device_model == "TerraMow S1200"


def test_on_mqtt_message_invalid_json_is_swallowed() -> None:
    hub = _hub()
    for topic in (
        MAP_META_TOPIC,
        PATH_META_TOPIC,
        PATH_HISTORY_META_TOPIC,
        POSE_TOPIC,
        MAP_INFO_TOPIC,
    ):
        # must not raise
        hub.on_mqtt_message(None, None, _msg(topic, "not-json"))


def test_on_mqtt_message_data_point_and_invalid_topic() -> None:
    hub = _hub()
    hub.register_all_callbacks()
    # a registered data point routes to its callback
    hub.on_mqtt_message(
        None, None, _msg("data_point/107/robot", '{"mission": "MISSION_IDLE"}')
    )
    # an unrecognised topic is ignored without raising
    hub.on_mqtt_message(None, None, _msg("garbage/topic", "x"))


# ---------------------------------------------------------------------------
# start() / async_stop()
# ---------------------------------------------------------------------------


def test_start_launches_thread_and_registers_callbacks() -> None:
    hub = _hub()
    with (
        patch("custom_components.terramow.hub.mqtt_client.Client") as client_cls,
        patch("custom_components.terramow.hub.threading.Thread") as thread_cls,
    ):
        hub.start()
    client_cls.assert_called_once()
    thread_cls.return_value.start.assert_called_once()
    assert 107 in hub.callbacks


def test_async_stop_joins_alive_thread_and_warns() -> None:
    hub = _hub()
    thread = MagicMock()
    thread.is_alive.return_value = True  # never dies -> join + warning
    hub.mqtt_thread = thread
    asyncio.run(hub.async_stop())
    thread.join.assert_called_once()


# ---------------------------------------------------------------------------
# path / history-path meta: pending, throttle, retry, requeue
# ---------------------------------------------------------------------------


def test_path_meta_pending_replacement_while_fetching() -> None:
    hub = _hub()
    hub._fetching_path = True
    asyncio.run(hub._async_handle_path_meta(META_P))
    assert hub._pending_path_meta == META_P


def test_history_path_meta_pending_replacement_while_fetching() -> None:
    hub = _hub()
    hub._fetching_history_path = True
    asyncio.run(hub._async_handle_history_path_meta(META_H))
    assert hub._pending_history_path_meta == META_H


def test_path_meta_no_seq_throttle_skips_fetch() -> None:
    hub = _hub()
    hub._path_no_seq_last_fetch = time.monotonic()
    no_seq = {"seq": -1, "http_port": 1, "http_path": "/p", "token": "t"}
    with patch(
        "custom_components.terramow.hub.async_get_clientsession"
    ) as session:
        asyncio.run(hub._async_handle_path_meta(no_seq))
    session.assert_not_called()


def test_history_path_meta_no_seq_throttle_skips_fetch() -> None:
    hub = _hub()
    hub._history_path_no_seq_last_fetch = time.monotonic()
    no_seq = {"seq": -1, "http_port": 1, "http_path": "/h", "token": "t"}
    with patch(
        "custom_components.terramow.hub.async_get_clientsession"
    ) as session:
        asyncio.run(hub._async_handle_history_path_meta(no_seq))
    session.assert_not_called()


def test_path_meta_failure_schedules_retry() -> None:
    hub = _hub()
    with _patch_session(_FakeResp(status=500)):
        asyncio.run(hub._async_handle_path_meta(META_P))
    assert hub._path_retry_meta == META_P
    assert hub.hass.async_create_task.called


def test_history_path_meta_failure_schedules_retry() -> None:
    hub = _hub()
    with _patch_session(_FakeResp(status=500)):
        asyncio.run(hub._async_handle_history_path_meta(META_H))
    assert hub._history_path_retry_meta == META_H


def test_path_meta_requeues_pending_after_completion() -> None:
    hub = _hub()
    newer = {"seq": 99, "http_port": 1, "http_path": "/p", "token": "t"}

    async def fake_fetch(meta, etag):
        # a newer meta arrives while this fetch is in flight
        hub._pending_path_meta = newer
        return ({"id": 1, "points": []}, "e", True, False)

    hub._async_fetch_json = fake_fetch  # type: ignore[method-assign]
    asyncio.run(hub._async_handle_path_meta(META_P))
    # the finally block requeues the newer pending meta
    assert hub.hass.async_create_task.called
    assert hub._pending_path_meta is None


def test_map_meta_requeues_pending_after_completion() -> None:
    hub = _hub()
    newer = {"seq": 99, "http_port": 1, "http_path": "/m", "token": "t"}

    async def fake_fetch(meta, etag):
        hub._pending_map_meta = newer
        return ({"id": 1, "map_state": "MAP_STATE_COMPLETE"}, "e", True, False)

    hub._async_fetch_json = fake_fetch  # type: ignore[method-assign]
    asyncio.run(hub._async_handle_map_meta(META_M))
    assert hub.hass.async_create_task.called
    assert hub._pending_map_meta is None


# ---------------------------------------------------------------------------
# retry coroutines + schedulers/cancellers
# ---------------------------------------------------------------------------


def test_async_retry_path_runs_cached_meta() -> None:
    hub = _hub()
    hub._path_retry_meta = META_P
    with (
        patch("asyncio.sleep", AsyncMock()),
        _patch_session(_FakeResp(200, b'{"id": 3, "points": []}')),
    ):
        asyncio.run(hub._async_retry_path(0.0))
    assert hub.path_data["id"] == 3


def test_async_retry_path_cancelled_returns_cleanly() -> None:
    hub = _hub()
    hub._path_retry_meta = META_P
    with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
        asyncio.run(hub._async_retry_path(1.0))
    # cancellation short-circuits before re-fetching
    assert hub.path_data == {}


def test_reset_retry_cancels_active_tasks() -> None:
    hub = _hub()
    for attr, reset in (
        ("_map_retry_task", hub._reset_map_retry),
        ("_path_retry_task", hub._reset_path_retry),
        ("_history_path_retry_task", hub._reset_history_path_retry),
    ):
        task = MagicMock()
        task.done.return_value = False
        setattr(hub, attr, task)
        reset()
        task.cancel.assert_called_once()
        assert getattr(hub, attr) is None


def test_schedule_retry_is_noop_when_task_still_running() -> None:
    hub = _hub()
    task = MagicMock()
    task.done.return_value = False
    hub._map_retry_task = task
    hub._schedule_map_retry(META_M)
    # the existing task is kept; no new task scheduled
    assert hub._map_retry_task is task


# ---------------------------------------------------------------------------
# command rate-limit + mission-state guards
# ---------------------------------------------------------------------------


def _feed(hub: TerraMowHub, payload: dict) -> None:
    asyncio.run(hub.on_mission_status(json.dumps(payload)))


def test_commands_blocked_by_rate_limiter() -> None:
    hub = _hub()
    hub._last_control_time = time.monotonic()  # a command just happened
    hub.start_mowing()
    hub.pause()
    hub.dock()
    hub.start_select_region_clean([1])
    hub.mqtt_client.publish.assert_not_called()


def test_start_mowing_while_running_does_not_republish() -> None:
    hub = _hub()
    _feed(hub, {"mission": "MISSION_GLOBAL_CLEAN", "mission_state": "MISSION_STATE_RUNNING"})
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()
    hub.start_mowing()
    hub.mqtt_client.publish.assert_not_called()


def test_pause_station_wait_is_ignored() -> None:
    hub = _hub()
    _feed(
        hub,
        {
            "mission": "MISSION_GLOBAL_CLEAN",
            "sub_mission": "SUB_MISSION_FLEXIBLE_STATION_WAIT",
            "mission_state": "MISSION_STATE_RUNNING",
        },
    )
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()
    hub.pause()
    hub.mqtt_client.publish.assert_not_called()


def test_pause_already_paused_is_ignored() -> None:
    hub = _hub()
    _feed(hub, {"mission": "MISSION_GLOBAL_CLEAN", "mission_state": "MISSION_STATE_PAUSE"})
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()
    hub.pause()
    hub.mqtt_client.publish.assert_not_called()


def test_pause_non_mow_paused_is_ignored() -> None:
    hub = _hub()
    _feed(hub, {"mission": "MISSION_IDLE", "mission_state": "MISSION_STATE_PAUSE"})
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()
    hub.pause()
    hub.mqtt_client.publish.assert_not_called()


def test_dock_while_recharging_running_is_ignored() -> None:
    hub = _hub()
    _feed(hub, {"mission": "MISSION_RECHARGE", "mission_state": "MISSION_STATE_RUNNING"})
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()
    hub.dock()
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# device registry updates + model-name handling
# ---------------------------------------------------------------------------


def test_update_device_sw_version_writes_when_changed() -> None:
    hub = _hub()
    reg = MagicMock()
    device = MagicMock()
    device.sw_version = "old"
    device.id = "dev-1"
    reg.async_get_device.return_value = device
    with patch("custom_components.terramow.hub.dr.async_get", return_value=reg):
        asyncio.run(hub._async_update_device_sw_version("new"))
    reg.async_update_device.assert_called_once()


def test_update_device_sw_version_handles_registry_error() -> None:
    hub = _hub()
    with patch(
        "custom_components.terramow.hub.dr.async_get", side_effect=RuntimeError("boom")
    ):
        # must swallow the error
        asyncio.run(hub._async_update_device_sw_version("new"))


def test_update_device_model_writes_and_warns_when_missing() -> None:
    hub = _hub()
    reg = MagicMock()
    device = MagicMock()
    device.id = "dev-1"
    reg.async_get_device.return_value = device
    with patch("custom_components.terramow.hub.dr.async_get", return_value=reg):
        asyncio.run(hub._async_update_device_model("TerraMow S1200"))
    reg.async_update_device.assert_called_once()

    reg.async_get_device.return_value = None
    reg.async_update_device.reset_mock()
    with patch("custom_components.terramow.hub.dr.async_get", return_value=reg):
        asyncio.run(hub._async_update_device_model("TerraMow S1200"))
    reg.async_update_device.assert_not_called()


def test_handle_model_name_empty_keeps_default() -> None:
    hub = _hub()
    before = hub.device_model
    hub._handle_model_name("   ")
    assert hub.device_model == before


def test_handle_model_name_non_string_is_swallowed() -> None:
    hub = _hub()
    # a non-string payload makes .strip() raise; the handler must swallow it
    hub._handle_model_name(123)  # type: ignore[arg-type]


def test_update_device_model_handles_registry_error() -> None:
    hub = _hub()
    with patch(
        "custom_components.terramow.hub.dr.async_get", side_effect=RuntimeError("boom")
    ):
        asyncio.run(hub._async_update_device_model("TerraMow S1200"))


# ---------------------------------------------------------------------------
# fetch-exception retry + history requeue + history retry cancellation
# ---------------------------------------------------------------------------


def test_path_meta_fetch_exception_schedules_retry() -> None:
    hub = _hub()

    async def boom(meta, etag):
        raise RuntimeError("network down")

    hub._async_fetch_json = boom  # type: ignore[method-assign]
    asyncio.run(hub._async_handle_path_meta(META_P))
    assert hub._path_retry_meta == META_P


def test_history_path_meta_fetch_exception_schedules_retry() -> None:
    hub = _hub()

    async def boom(meta, etag):
        raise RuntimeError("network down")

    hub._async_fetch_json = boom  # type: ignore[method-assign]
    asyncio.run(hub._async_handle_history_path_meta(META_H))
    assert hub._history_path_retry_meta == META_H


def test_history_path_meta_requeues_pending_after_completion() -> None:
    hub = _hub()
    newer = {"seq": 99, "http_port": 1, "http_path": "/h", "token": "t"}

    async def fake_fetch(meta, etag):
        hub._pending_history_path_meta = newer
        return ({"id": 1, "points": []}, "e", True, False)

    hub._async_fetch_json = fake_fetch  # type: ignore[method-assign]
    asyncio.run(hub._async_handle_history_path_meta(META_H))
    assert hub.hass.async_create_task.called
    assert hub._pending_history_path_meta is None


def test_async_retry_history_path_cancelled_returns_cleanly() -> None:
    hub = _hub()
    hub._history_path_retry_meta = META_H
    with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
        asyncio.run(hub._async_retry_history_path(1.0))
    assert hub.history_path_data == {}
