"""Coverage for the remaining core-module branches.

Fills the last gaps in hub.py (compatibility edge cases, MQTT-dispatch error
handlers, path/history seq guards, request-compat error), entity_utils.py
(the push-update mixin registration), __init__.py (service idempotency,
lawn-mower-not-ready, unload branches) and config_flow.py (disconnect-error
tolerance, the discovery password fallbacks, reauth cannot-connect).
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import (
    SERVICE_START_SELECT_REGION,
    TerraMowBasicData,
    _async_register_services,
    async_unload_entry,
)
from custom_components.terramow.const import DOMAIN
from custom_components.terramow.hub import TerraMowHub


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.140", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    hub.hass.async_create_task = MagicMock(
        side_effect=lambda c: c.close() if hasattr(c, "close") else None
    )
    return hub


# ---------------------------------------------------------------------------
# hub: version compatibility edge cases
# ---------------------------------------------------------------------------


def test_compatibility_incompatible_logs_error() -> None:
    hub = _hub()
    hub.basic_data.entry_id = "e1"
    with patch("custom_components.terramow.hub.async_sync_compatibility_issue") as sync:
        # a non-numeric "overall" makes the version comparison raise ->
        # INCOMPATIBLE, but the payload still formats to a version string
        asyncio.run(
            hub.on_compatibility_info(
                json.dumps({"overall": "x", "module": {"home_assistant": 3}})
            )
        )
    from custom_components.terramow.const import CompatibilityStatus

    assert hub.basic_data.compatibility_status == CompatibilityStatus.INCOMPATIBLE
    sync.assert_called_once()


def test_compatibility_processing_error_is_swallowed() -> None:
    hub = _hub()
    # a list payload survives JSON decoding but blows up firmware formatting,
    # exercising the outer error handler
    asyncio.run(hub.on_compatibility_info(json.dumps([1, 2, 3])))


def test_compatibility_invalid_json_is_swallowed() -> None:
    hub = _hub()
    asyncio.run(hub.on_compatibility_info("not-json"))


# ---------------------------------------------------------------------------
# hub: on_mqtt_message error handlers + invalid seq
# ---------------------------------------------------------------------------


def _msg(topic: str, payload: str) -> MagicMock:
    m = MagicMock()
    m.topic = topic
    m.payload = payload.encode()
    return m


def test_mqtt_message_topic_handlers_swallow_dispatch_errors() -> None:
    from custom_components.terramow.const import (
        MAP_META_TOPIC,
        PATH_HISTORY_META_TOPIC,
        PATH_META_TOPIC,
        POSE_TOPIC,
    )

    hub = _hub()
    hub.hass.loop.call_soon_threadsafe = MagicMock(side_effect=RuntimeError("loop closed"))
    # a registered pose callback ensures the pose branch also schedules a job
    hub.pose_callbacks.append(MagicMock())
    for topic in (MAP_META_TOPIC, PATH_META_TOPIC, PATH_HISTORY_META_TOPIC, POSE_TOPIC):
        # valid JSON, but scheduling the async handler raises -> swallowed
        hub.on_mqtt_message(None, None, _msg(topic, '{"seq": 1}'))


def test_mqtt_message_undecodable_payload_is_dropped() -> None:
    hub = _hub()
    msg = MagicMock()
    msg.topic = "data_point/8/robot"
    msg.payload = b"\xff\xfe\xfa"  # not valid UTF-8
    # must not raise: a raising on_message would wedge the reconnect loop
    hub.on_mqtt_message(None, None, msg)
    hub.hass.loop.call_soon_threadsafe.assert_not_called()


def test_dispatch_runs_coroutine_sync_and_raising_targets() -> None:
    hub = _hub()
    # run the scheduled closure inline
    hub.hass.loop.call_soon_threadsafe = MagicMock(side_effect=lambda fn: fn())
    created: list = []
    hub.hass.async_create_task = MagicMock(side_effect=created.append)

    async def async_target(value):
        return value

    hub._dispatch(async_target, 1)
    assert len(created) == 1
    created[0].close()

    sync_target = MagicMock()
    hub._dispatch(sync_target, 2)
    sync_target.assert_called_once_with(2)

    # a raising target is contained inside the dispatch closure
    hub._dispatch(MagicMock(side_effect=RuntimeError("boom")), 3)


def test_diagnostics_snapshot_returns_copies() -> None:
    hub = _hub()
    hub._seen_unknown_dp_ids.add(42)
    hub._unknown_dp_payloads[42] = "{}"
    from collections import deque

    hub._unknown_dp_history[42] = deque([(1.0, "{}")], maxlen=5)
    snap = hub.diagnostics_snapshot()
    assert snap["seen_unknown_dp_ids"] == [42]
    assert snap["unknown_dp_payloads"] == {42: "{}"}
    assert snap["unknown_dp_history"] == {42: [(1.0, "{}")]}
    # mutating the snapshot must not touch the hub's live structures
    snap["unknown_dp_history"][42].append((2.0, "x"))
    assert len(hub._unknown_dp_history[42]) == 1


def test_handle_map_info_swallows_update_error() -> None:
    hub = _hub()
    # a list payload decodes but breaks _update_map_info
    hub._handle_map_info("[1, 2, 3]")


def test_get_meta_seq_warns_on_invalid_seq() -> None:
    hub = _hub()
    assert hub._get_meta_seq({"seq": "not-an-int"}, "map") == -1


# ---------------------------------------------------------------------------
# hub: path / history seq guards + no-seq success + request-compat error
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status=200, body=b'{"id": 1, "points": []}'):
        self.status = status
        self._body = body
        self.headers = {"ETag": "e"}

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _patch_session(resp):
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    return patch(
        "custom_components.terramow.hub.async_get_clientsession", return_value=session
    )


def test_path_meta_equal_seq_is_skipped() -> None:
    hub = _hub()
    hub._path_seq = 5
    with patch("custom_components.terramow.hub.async_get_clientsession") as session:
        asyncio.run(
            hub._async_handle_path_meta(
                {"seq": 5, "http_port": 1, "http_path": "/p", "token": "t"}
            )
        )
    session.assert_not_called()


def test_history_path_meta_equal_seq_is_skipped() -> None:
    hub = _hub()
    hub._history_path_seq = 5
    with patch("custom_components.terramow.hub.async_get_clientsession") as session:
        asyncio.run(
            hub._async_handle_history_path_meta(
                {"seq": 5, "http_port": 1, "http_path": "/h", "token": "t"}
            )
        )
    session.assert_not_called()


def test_path_meta_no_seq_success_records_fetch_time() -> None:
    hub = _hub()
    no_seq = {"seq": -1, "http_port": 1, "http_path": "/p", "token": "t"}
    with _patch_session(_FakeResp()):
        asyncio.run(hub._async_handle_path_meta(no_seq))
    assert hub._path_no_seq_last_fetch > 0


def test_history_path_meta_no_seq_success_records_fetch_time() -> None:
    hub = _hub()
    no_seq = {"seq": -1, "http_port": 1, "http_path": "/h", "token": "t"}
    with _patch_session(_FakeResp()):
        asyncio.run(hub._async_handle_history_path_meta(no_seq))
    assert hub._history_path_no_seq_last_fetch > 0


def test_request_compatibility_info_swallows_publish_error() -> None:
    hub = _hub()
    hub.mqtt_client.publish.side_effect = RuntimeError("no broker")
    hub._request_compatibility_info()  # must not raise


def test_async_stop_without_mqtt_client() -> None:
    hub = _hub()
    hub.mqtt_client = None
    asyncio.run(hub.async_stop())  # no client -> nothing to disconnect/join


def test_async_stop_joins_thread_that_stops() -> None:
    hub = _hub()
    thread = MagicMock()
    # alive when checked, stopped after the join -> no warning
    thread.is_alive.side_effect = [True, False]
    hub.mqtt_thread = thread
    asyncio.run(hub.async_stop())
    thread.join.assert_called_once()


def test_compatibility_without_overall_skips_sw_version() -> None:
    hub = _hub()
    hub.basic_data.entry_id = "e1"
    with patch("custom_components.terramow.hub.async_sync_compatibility_issue"):
        # no "overall" -> firmware formatting returns None -> device update skipped
        asyncio.run(
            hub.on_compatibility_info(json.dumps({"module": {"home_assistant": 3}}))
        )


def test_get_meta_seq_invalid_without_warn() -> None:
    hub = _hub()
    assert hub._get_meta_seq({"seq": "x"}, "map", warn=False) == -1


def test_retry_coroutines_noop_without_cached_meta() -> None:
    hub = _hub()
    with patch("asyncio.sleep", AsyncMock()):
        for retry in (
            hub._async_retry_map,
            hub._async_retry_path,
            hub._async_retry_history_path,
        ):
            asyncio.run(retry(0.0))  # no cached meta -> nothing to re-fetch


def test_map_meta_fetch_exception_schedules_retry() -> None:
    hub = _hub()

    async def boom(meta, etag):
        raise RuntimeError("network")

    hub._async_fetch_json = boom  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_map_meta(
            {"seq": 5, "http_port": 1, "http_path": "/m", "token": "t"}
        )
    )
    assert hub._map_retry_meta is not None


def test_map_meta_success_without_data_or_pending() -> None:
    hub = _hub()

    async def no_data(meta, etag):
        # ok, but no body and no etag -> skips the data/map-info branch
        return None, None, True, False

    hub._async_fetch_json = no_data  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_map_meta(
            {"seq": 7, "http_port": 1, "http_path": "/m", "token": "t"}
        )
    )
    assert hub._map_seq == 7


def test_update_device_sw_version_noop_when_unchanged() -> None:
    hub = _hub()
    reg = MagicMock()
    device = MagicMock()
    device.sw_version = "1.2.3"
    reg.async_get_device.return_value = device
    with patch("custom_components.terramow.hub.dr.async_get", return_value=reg):
        asyncio.run(hub._async_update_device_sw_version("1.2.3"))
    reg.async_update_device.assert_not_called()


# ---------------------------------------------------------------------------
# hub: command mission-state fall-through branches (no publish)
# ---------------------------------------------------------------------------


def _feed_mission(hub: TerraMowHub, mission: str, state: str) -> None:
    asyncio.run(hub.on_mission_status(json.dumps({"mission": mission, "state": state})))
    hub._last_control_time = 0.0
    hub.mqtt_client.publish.reset_mock()


def test_start_mowing_mow_mission_idle_state_is_noop() -> None:
    hub = _hub()
    _feed_mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_IDLE")
    hub.start_mowing()
    hub.mqtt_client.publish.assert_not_called()


def test_pause_mow_mission_idle_state_is_noop() -> None:
    hub = _hub()
    _feed_mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_IDLE")
    hub.pause()
    hub.mqtt_client.publish.assert_not_called()


def test_pause_non_mow_idle_state_is_noop() -> None:
    hub = _hub()
    _feed_mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    hub.pause()
    hub.mqtt_client.publish.assert_not_called()


def test_dock_recharge_idle_state_is_noop() -> None:
    hub = _hub()
    _feed_mission(hub, "MISSION_RECHARGE", "MISSION_STATE_IDLE")
    hub.dock()
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# hub: mqtt_loop with no client + meta pending/data-none/requeue partials
# ---------------------------------------------------------------------------


def test_mqtt_loop_without_client_skips_connect_and_loops() -> None:
    hub = _hub()
    hub.mqtt_client = None
    # run exactly one iteration: enter the loop once, then stop
    hub._stop_event.is_set = MagicMock(side_effect=[False, True])
    hub.mqtt_loop()  # no client -> skips connect and loop_forever, returns cleanly


def test_mqtt_loop_skips_connect_when_already_connected() -> None:
    hub = _hub()
    client = hub.mqtt_client
    client.is_connected.return_value = True  # already connected -> skip connect

    def stop(*_a):
        hub._stop_event.set()

    client.loop_forever.side_effect = stop
    hub.mqtt_loop()
    client.connect.assert_not_called()
    client.loop_forever.assert_called_once()


def test_map_meta_keeps_newer_pending_while_fetching() -> None:
    hub = _hub()
    hub._fetching_map = True
    hub._pending_map_meta = {"seq": 99, "http_port": 1, "http_path": "/m", "token": "t"}
    # an older meta arrives -> the newer pending is kept
    asyncio.run(
        hub._async_handle_map_meta(
            {"seq": 5, "http_port": 1, "http_path": "/m", "token": "t"}
        )
    )
    assert hub._pending_map_meta["seq"] == 99


def test_map_meta_data_without_map_info_skips_update() -> None:
    hub = _hub()

    async def fetch(meta, etag):
        return {"id": 1}, "e", True, False

    hub._async_fetch_json = fetch  # type: ignore[method-assign]
    hub._build_map_info_from_map_data = lambda data: None  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_map_meta(
            {"seq": 6, "http_port": 1, "http_path": "/m", "token": "t"}
        )
    )
    assert hub._map_data == {"id": 1}


def test_map_meta_stale_pending_is_not_requeued() -> None:
    hub = _hub()

    async def fetch(meta, etag):
        # a stale (older) meta is queued during the fetch
        hub._pending_map_meta = {"seq": 1, "http_port": 1, "http_path": "/m", "token": "t"}
        return {"id": 1, "map_state": "MAP_STATE_COMPLETE"}, "e", True, False

    hub._async_fetch_json = fetch  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_map_meta(
            {"seq": 7, "http_port": 1, "http_path": "/m", "token": "t"}
        )
    )
    # map_seq advanced to 7; the stale pending (seq 1) is dropped, not requeued
    assert hub._map_seq == 7
    assert hub._pending_map_meta is None


def test_path_meta_keeps_newer_pending_while_fetching() -> None:
    hub = _hub()
    hub._fetching_path = True
    hub._pending_path_meta = {"seq": 99, "http_port": 1, "http_path": "/p", "token": "t"}
    asyncio.run(
        hub._async_handle_path_meta(
            {"seq": 5, "http_port": 1, "http_path": "/p", "token": "t"}
        )
    )
    assert hub._pending_path_meta["seq"] == 99


def test_path_meta_stale_pending_is_not_requeued() -> None:
    hub = _hub()

    async def fetch(meta, etag):
        hub._pending_path_meta = {"seq": 1, "http_port": 1, "http_path": "/p", "token": "t"}
        return {"id": 1, "points": []}, "e", True, False

    hub._async_fetch_json = fetch  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_path_meta(
            {"seq": 7, "http_port": 1, "http_path": "/p", "token": "t"}
        )
    )
    assert hub._path_seq == 7
    assert hub._pending_path_meta is None


def test_history_meta_keeps_newer_pending_while_fetching() -> None:
    hub = _hub()
    hub._fetching_history_path = True
    hub._pending_history_path_meta = {
        "seq": 99, "http_port": 1, "http_path": "/h", "token": "t"
    }
    asyncio.run(
        hub._async_handle_history_path_meta(
            {"seq": 5, "http_port": 1, "http_path": "/h", "token": "t"}
        )
    )
    assert hub._pending_history_path_meta["seq"] == 99


def test_history_meta_success_invokes_callbacks_and_drops_stale_pending() -> None:
    hub = _hub()
    hub.history_path_callbacks.append(MagicMock())

    async def fetch(meta, etag):
        hub._pending_history_path_meta = {
            "seq": 1, "http_port": 1, "http_path": "/h", "token": "t"
        }
        return {"id": 1, "points": []}, "e", True, False

    hub._async_fetch_json = fetch  # type: ignore[method-assign]
    asyncio.run(
        hub._async_handle_history_path_meta(
            {"seq": 7, "http_port": 1, "http_path": "/h", "token": "t"}
        )
    )
    assert hub._history_path_data == {"id": 1, "points": []}
    assert hub._pending_history_path_meta is None


# ---------------------------------------------------------------------------
# __init__: unload failure leaves everything in place
# ---------------------------------------------------------------------------


async def test_unload_failure_keeps_state(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)
    entry.runtime_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    _async_register_services(hass)

    with (
        patch("custom_components.terramow.async_clear_compatibility_issue") as clear,
        patch.object(
            hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
        ),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is False
    # cleanup is skipped and the shared service remains
    clear.assert_not_called()
    assert hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)


# ---------------------------------------------------------------------------
# entity_utils: PushUpdateMixin registration
# ---------------------------------------------------------------------------


def test_push_update_mixin_registers_dp_and_map_callbacks() -> None:
    from homeassistant.helpers.entity import Entity

    from custom_components.terramow.entity_utils import PushUpdateMixin

    class _Probe(PushUpdateMixin, Entity):
        _push_dp_ids = (107, 108)
        _push_map_info = True

    lawn_mower = MagicMock()
    probe = _Probe()
    probe.basic_data = SimpleNamespace(lawn_mower=lawn_mower)
    with patch(
        "homeassistant.helpers.entity.Entity.async_added_to_hass", AsyncMock()
    ):
        asyncio.run(probe.async_added_to_hass())

    assert lawn_mower.register_callback.call_count == 2
    lawn_mower.register_map_callback.assert_called_once()


def test_push_update_mixin_registers_dp_only_without_map() -> None:
    from homeassistant.helpers.entity import Entity

    from custom_components.terramow.entity_utils import PushUpdateMixin

    class _Probe(PushUpdateMixin, Entity):
        _push_dp_ids = (107,)
        _push_map_info = False

    lawn_mower = MagicMock()
    probe = _Probe()
    probe.basic_data = SimpleNamespace(lawn_mower=lawn_mower)
    with patch(
        "homeassistant.helpers.entity.Entity.async_added_to_hass", AsyncMock()
    ):
        asyncio.run(probe.async_added_to_hass())

    lawn_mower.register_callback.assert_called_once()
    lawn_mower.register_map_callback.assert_not_called()


def test_push_update_mixin_noop_without_lawn_mower() -> None:
    from homeassistant.helpers.entity import Entity

    from custom_components.terramow.entity_utils import PushUpdateMixin

    class _Probe(PushUpdateMixin, Entity):
        _push_dp_ids = (107,)

    probe = _Probe()
    probe.basic_data = SimpleNamespace(lawn_mower=None)
    with patch(
        "homeassistant.helpers.entity.Entity.async_added_to_hass", AsyncMock()
    ):
        asyncio.run(probe.async_added_to_hass())


# ---------------------------------------------------------------------------
# __init__: service registration idempotency + unload branches
# ---------------------------------------------------------------------------

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


async def test_register_services_is_idempotent(hass: HomeAssistant) -> None:
    _async_register_services(hass)
    # a second call returns early because the service already exists
    _async_register_services(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)


async def test_service_raises_when_lawn_mower_not_ready(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)
    # entry is loaded but its runtime_data has no lawn mower yet
    entry.runtime_data = TerraMowBasicData(host="192.0.2.10", password="secret")

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("lawn_mower", DOMAIN, "u", config_entry=entry)
    entity_id = ent_reg.async_get_entity_id("lawn_mower", DOMAIN, "u")

    _async_register_services(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_SELECT_REGION,
            {"entity_id": entity_id, "region_ids": [1]},
            blocking=True,
        )


async def test_unload_without_lawn_mower_removes_service(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)
    entry.runtime_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    _async_register_services(hass)

    with (
        patch("custom_components.terramow.async_clear_compatibility_issue"),
        patch.object(
            hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
        ),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    # it was the only entry, so the shared service is gone
    assert not hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION)


# ---------------------------------------------------------------------------
# config_flow: disconnect tolerance + discovery fallbacks + reauth
# ---------------------------------------------------------------------------


def test_validate_input_tolerates_disconnect_error() -> None:
    from custom_components.terramow import config_flow as cf

    fake = MagicMock()

    def connect(host, port, timeout):
        # simulate the broker accepting the credentials
        fake.on_connect(fake, None, None, 0)

    fake.connect.side_effect = connect
    fake.disconnect.side_effect = RuntimeError("already gone")

    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))

    with patch.object(cf, "create_mqtt_client", return_value=fake):
        result = asyncio.run(
            cf.validate_input(hass, {CONF_HOST: "192.0.2.1", CONF_PASSWORD: "p"})
        )
    assert isinstance(result, dict)


async def test_user_pass_step_without_discovery_delegates(hass: HomeAssistant) -> None:
    from custom_components.terramow.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = hass
    flow._discovered_host = None
    result = await flow.async_step_user_pass(None)
    # falls back to the normal user step form
    assert result["type"].value == "form"


async def test_reauth_confirm_cannot_connect(hass: HomeAssistant) -> None:
    from custom_components.terramow.config_flow import CannotConnect

    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "newpass"}
        )
    assert result["type"].value == "form"
    assert result["errors"] == {"base": "cannot_connect"}
