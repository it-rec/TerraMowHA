"""Thorough coverage for the hub's MQTT plumbing.

Covers the dp handlers' invalid-JSON guards, the callback registrars, the
connect/disconnect callbacks, the message router (meta/pose/map/model/data
topics) and the model-name / map-info handlers.
"""

import asyncio
import contextlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiomqtt
import pytest

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    MAP_INFO_TOPIC,
    MAP_META_TOPIC,
    MODEL_NAME_TOPIC,
    PATH_HISTORY_META_TOPIC,
    PATH_META_TOPIC,
    POSE_TOPIC,
)
from custom_components.terramow.hub import TerraMowHub, _HubMqttClient


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.100", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _msg(topic: str, payload):
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    return SimpleNamespace(topic=topic, payload=payload.encode())


# ---------------------------------------------------------------------------
# dp handler invalid-JSON guards
# ---------------------------------------------------------------------------


def test_dp_handlers_swallow_invalid_json() -> None:
    hub = _hub()
    handlers = [
        hub.on_global_params,
        hub.on_map_status,
        hub.on_current_work_data,
        hub.on_statistics_data,
        hub.on_base_station_time,
        hub.on_blade_time,
        hub.on_schedule_data,
        hub.on_battery_status,
        hub.on_mission_status,
        hub.on_compatibility_info,
    ]
    for handler in handlers:
        # must not raise on malformed payloads
        asyncio.run(handler("not-json"))


# ---------------------------------------------------------------------------
# callback registrars
# ---------------------------------------------------------------------------


def test_on_device_info_and_component_versions_branches() -> None:
    hub = _hub()
    # invalid JSON is swallowed
    asyncio.run(hub.on_device_info("not-json"))
    asyncio.run(hub.on_component_versions("not-json"))
    assert hub.firmware_version_name is None
    # non-dict payloads are ignored
    asyncio.run(hub.on_device_info(json.dumps([1, 2])))
    asyncio.run(hub.on_component_versions(json.dumps("x")))
    assert hub.component_versions == {}
    # a dict without a version stores info but exposes no version
    asyncio.run(hub.on_device_info(json.dumps({"sn": "X"})))
    assert hub.firmware_version_name is None
    # the real version (dp_102) and component versions (dp_129) are exposed
    asyncio.run(hub.on_device_info(json.dumps({"version": "9.9.210"})))
    assert hub.firmware_version_name == "9.9.210"
    asyncio.run(hub.on_component_versions(json.dumps({"ap_app": "9.9.210"})))
    assert hub.component_versions["ap_app"] == "9.9.210"


def test_on_error_list_and_event_data_branches() -> None:
    hub = _hub()
    # invalid JSON is swallowed
    asyncio.run(hub.on_error_list("not-json"))
    asyncio.run(hub.on_event_data("not-json"))
    assert hub.error_list == [] and hub.event_list == []
    # non-dict / wrong-typed inner fields are ignored
    asyncio.run(hub.on_error_list(json.dumps([1])))
    asyncio.run(hub.on_error_list(json.dumps({"error_list": "x"})))
    asyncio.run(hub.on_event_data(json.dumps([1])))
    asyncio.run(hub.on_event_data(json.dumps({"event_list": 5})))
    assert hub.error_list == [] and hub.event_list == []
    # valid payloads are stored
    asyncio.run(hub.on_error_list(json.dumps({"error_list": [{"code": 3}]})))
    asyncio.run(hub.on_event_data(json.dumps({"event_list": [{"code": 8, "time": "t"}]})))
    assert hub.error_list == [{"code": 3}]
    assert hub.event_list[-1]["code"] == 8


def test_on_cellular_info_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_cellular_info("not-json"))  # invalid JSON swallowed
    asyncio.run(hub.on_cellular_info(json.dumps([1])))  # non-dict ignored
    assert hub.cellular_info == {}
    asyncio.run(hub.on_cellular_info(json.dumps({"is_enabled": True, "RSRP": -95})))
    assert hub.cellular_info["RSRP"] == -95


def test_on_environment_and_weather_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_environment_info("not-json"))
    asyncio.run(hub.on_environment_info(json.dumps([1])))
    asyncio.run(hub.on_weather_info("not-json"))
    asyncio.run(hub.on_weather_info(json.dumps([1])))
    assert hub.environment_info == {} and hub.weather_info == {}
    asyncio.run(hub.on_environment_info(json.dumps({"is_defogger_heating": True})))
    asyncio.run(hub.on_weather_info(json.dumps({"has_extream_weather": True})))
    assert hub.environment_info["is_defogger_heating"] is True
    assert hub.weather_info["has_extream_weather"] is True


def test_on_operating_modes_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_operating_modes("not-json"))
    asyncio.run(hub.on_operating_modes(json.dumps([1])))
    assert hub.operating_modes == {}
    asyncio.run(hub.on_operating_modes(json.dumps({"move_mode": "MOVE_MODE_MOW"})))
    assert hub.operating_modes["move_mode"] == "MOVE_MODE_MOW"


def test_on_full_schedule_branches() -> None:
    hub = _hub()
    # invalid JSON and non-dict payloads are ignored
    asyncio.run(hub.on_full_schedule("not-json"))
    asyncio.run(hub.on_full_schedule(json.dumps([1])))
    assert hub.full_schedule == {}
    # ADD/DELETE acks (no schedule_list) leave the cache untouched
    asyncio.run(hub.on_full_schedule(json.dumps({"cmd_type": "SCHEDULE_CMD_TYPE_ADD"})))
    assert hub.full_schedule == {}
    # a non-dict schedule_list is rejected
    asyncio.run(hub.on_full_schedule(json.dumps({"schedule_list": [1]})))
    assert hub.full_schedule == {}
    # a GET response with a schedule_list is stored
    asyncio.run(
        hub.on_full_schedule(json.dumps({"schedule_list": {"items": [], "global_disabled": False}}))
    )
    assert hub.full_schedule == {"items": [], "global_disabled": False}


def test_on_state_flag_134_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_state_flag_134("not-json"))
    asyncio.run(hub.on_state_flag_134(json.dumps([1])))
    assert hub.state_flag_134 == {}
    asyncio.run(hub.on_state_flag_134(json.dumps({"enum_value": 1})))
    assert hub.state_flag_134 == {"enum_value": 1}


def test_on_map_save_progress_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_map_save_progress("not-json"))
    asyncio.run(hub.on_map_save_progress(json.dumps([1])))
    assert hub.map_save_progress == {}
    asyncio.run(hub.on_map_save_progress(json.dumps({"int_value": 55})))
    assert hub.map_save_progress == {"int_value": 55}


def test_request_full_schedule_publishes_get() -> None:
    hub = _hub()
    hub._request_full_schedule()
    assert hub.mqtt_client.publish.called
    topic = hub.mqtt_client.publish.call_args[0][0]
    payload = json.loads(hub.mqtt_client.publish.call_args[0][1])
    assert topic == "data_point/122/app"
    assert payload["cmd_type"] == "SCHEDULE_CMD_TYPE_GET"


def test_request_full_schedule_swallows_errors() -> None:
    hub = _hub()
    hub.mqtt_client.publish.side_effect = RuntimeError("boom")
    # must not raise -- the MQTT worker thread keeps running
    hub._request_full_schedule()


def test_on_advanced_settings_branches() -> None:
    hub = _hub()
    asyncio.run(hub.on_advanced_settings("not-json"))
    asyncio.run(hub.on_advanced_settings(json.dumps([1])))
    assert hub.advanced_settings == {}
    asyncio.run(hub.on_advanced_settings(json.dumps({"enable_cliff_detection": {"value": True}})))
    assert hub.advanced_settings["enable_cliff_detection"]["value"] is True


def test_register_callback_validates_and_stores() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.register_callback(155, cb)
    assert cb in hub.callbacks[155]
    with pytest.raises(ValueError):
        hub.register_callback(155, "not-callable")


def test_register_map_pose_path_callbacks_fire_when_data_present() -> None:
    hub = _hub()
    # seed existing data so registration triggers an immediate callback
    hub._map_info = {"id": 1}
    hub._pose = {"x": 1}
    hub._path_data = {"id": 2}
    hub._history_path_data = {"id": 3}
    for register in (
        hub.register_map_callback,
        hub.register_pose_callback,
        hub.register_path_callback,
        hub.register_history_path_callback,
    ):
        register(MagicMock())
    # each registrar scheduled its immediate callback on the loop
    assert hub.hass.loop.call_soon_threadsafe.call_count == 4

    with pytest.raises(ValueError):
        hub.register_map_callback("nope")


# ---------------------------------------------------------------------------
# connection setup (per-connect subscriptions and session priming)
# ---------------------------------------------------------------------------


def test_on_connected_subscribes_and_clears_error() -> None:
    hub = _hub()
    hub.connection_error = True
    client = MagicMock()
    client.subscribe = AsyncMock()
    asyncio.run(hub._async_on_connected(client))
    # wildcard data-point topic + info/meta/pose/model subscriptions
    subscribed = [c.args[0] for c in client.subscribe.await_args_list]
    assert "data_point/+/robot" in subscribed
    assert "data_point/+/app" in subscribed
    assert "#" in subscribed
    assert client.subscribe.await_count == 9
    assert hub.connection_error is False
    # a compatibility-info request was published
    assert hub.mqtt_client.publish.called


def test_on_connected_survives_denied_discovery_subscription() -> None:
    hub = _hub()

    async def subscribe(topic, *args, **kwargs):
        # the broker refusing the "#" discovery subscription must not break
        # the documented subscriptions around it
        if topic == "#":
            raise aiomqtt.MqttError("subscription denied")

    client = MagicMock()
    client.subscribe = AsyncMock(side_effect=subscribe)
    asyncio.run(hub._async_on_connected(client))
    subscribed = [c.args[0] for c in client.subscribe.await_args_list]
    assert subscribed[-1] == "model/name"
    assert hub.connection_error is False


# ---------------------------------------------------------------------------
# message router
# ---------------------------------------------------------------------------


def test_on_mqtt_message_routes_meta_and_pose_topics() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg(MAP_META_TOPIC, {"url": "u"}))
    hub.on_mqtt_message(None, None, _msg(PATH_META_TOPIC, {"url": "p"}))
    hub.on_mqtt_message(None, None, _msg(PATH_HISTORY_META_TOPIC, {"url": "h"}))
    # each meta topic was dispatched to its async handler on the loop
    assert hub.hass.loop.call_soon_threadsafe.call_count == 3

    pose_cb = MagicMock()
    hub.pose_callbacks.append(pose_cb)
    hub.on_mqtt_message(None, None, _msg(POSE_TOPIC, {"x": 1, "y": 2, "yaw": 3}))
    assert hub._pose == {"x": 1, "y": 2, "yaw": 3}


def test_on_mqtt_message_routes_map_and_model_topics() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg(MAP_INFO_TOPIC, {"id": 5, "name": "Garten"}))
    assert hub.map_info == {"id": 5, "name": "Garten"}

    hub.on_mqtt_message(None, None, _msg(MODEL_NAME_TOPIC, "TerraMow-X"))
    assert hub.device_model == "TerraMow-X"


def test_on_mqtt_message_routes_data_point_to_callbacks() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.register_callback(155, cb)
    hub.on_mqtt_message(None, None, _msg("data_point/155/robot", {"v": 1}))
    assert hub.hass.loop.call_soon_threadsafe.called


def test_on_mqtt_message_handles_unknown_and_invalid_topics() -> None:
    hub = _hub()
    # unknown but well-formed dp topic -> logged once, then again
    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", "payload"))
    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", "payload"))
    assert 199 in hub._seen_unknown_dp_ids
    # a completely invalid topic is ignored without raising
    hub.on_mqtt_message(None, None, _msg("garbage/topic", "x"))


def test_unknown_dp_history_records_changes_and_dedupes() -> None:
    from custom_components.terramow.hub import UNKNOWN_DP_HISTORY_MAXLEN

    hub = _hub()
    topic = "data_point/109/robot"
    # repeated identical payloads collapse to a single history entry
    hub.on_mqtt_message(None, None, _msg(topic, '{"int_value":54}'))
    hub.on_mqtt_message(None, None, _msg(topic, '{"int_value":54}'))
    history = hub._unknown_dp_history[109]
    assert [p for _, p in history] == ['{"int_value":54}']
    # a changed payload appends a new, timestamped entry
    hub.on_mqtt_message(None, None, _msg(topic, '{"int_value":58}'))
    assert [p for _, p in history] == ['{"int_value":54}', '{"int_value":58}']
    assert all(isinstance(ts, float) for ts, _ in history)
    # a different dp gets its own independent trace
    hub.on_mqtt_message(None, None, _msg("data_point/134/robot", '{"enum_value":1}'))
    assert list(hub._unknown_dp_history) == [109, 134]
    # the buffer is bounded: many distinct values keep only the most recent N
    for value in range(UNKNOWN_DP_HISTORY_MAXLEN + 5):
        hub.on_mqtt_message(None, None, _msg(topic, f'{{"int_value":{value}}}'))
    assert len(hub._unknown_dp_history[109]) == UNKNOWN_DP_HISTORY_MAXLEN
    assert hub._unknown_dp_history[109][-1][1] == (
        f'{{"int_value":{UNKNOWN_DP_HISTORY_MAXLEN + 4}}}'
    )


def test_on_mqtt_message_meta_invalid_json_is_swallowed() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, SimpleNamespace(topic=MAP_META_TOPIC, payload=b"not-json"))
    # nothing dispatched, no exception
    hub.hass.loop.call_soon_threadsafe.assert_not_called()


# ---------------------------------------------------------------------------
# map-info / model-name handlers + mode-change notification
# ---------------------------------------------------------------------------


def test_handle_map_info_updates_and_notifies() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.map_callbacks.append(cb)
    hub._handle_map_info(json.dumps({"id": 7, "map_state": "MAP_STATE_COMPLETE"}))
    assert hub.map_info["id"] == 7
    assert hub.hass.loop.call_soon_threadsafe.called
    # invalid JSON is swallowed
    hub._handle_map_info("not-json")


def test_handle_model_name_empty_keeps_default() -> None:
    hub = _hub()
    before = hub.device_model
    hub._handle_model_name("   ")
    assert hub.device_model == before


def test_global_params_mode_change_fires_event() -> None:
    hub = _hub()
    asyncio.run(hub.on_global_params(json.dumps({
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"},
    })))
    asyncio.run(hub.on_global_params(json.dumps({
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })))
    assert hub.hass.bus.fire.called


# ---------------------------------------------------------------------------
# misc command / helpers
# ---------------------------------------------------------------------------


def test_publish_data_point_without_client_raises() -> None:
    from homeassistant.exceptions import HomeAssistantError

    hub = _hub()
    hub.mqtt_client = None
    with pytest.raises(HomeAssistantError):
        hub.publish_data_point(155, {"v": 1})


def test_get_cmd_seq_increments() -> None:
    hub = _hub()
    first = hub.get_cmd_seq()
    assert hub.get_cmd_seq() == first + 1


class _FakeAiomqttClient:
    """aiomqtt.Client stand-in: async context manager + scripted messages."""

    def __init__(self, messages=(), stream_error=None):
        self._messages = list(messages)
        self._stream_error = stream_error
        self.subscribe = AsyncMock()
        self.publish = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    @property
    def messages(self):
        async def _iterate():
            for message in self._messages:
                yield message
            if self._stream_error is not None:
                raise self._stream_error

        return _iterate()


async def _run_runner_until(hub, condition, rounds: int = 200) -> None:
    """Run the connection task until ``condition()`` holds, then cancel it."""
    task = asyncio.get_running_loop().create_task(hub._async_mqtt_runner())
    for _ in range(rounds):
        await asyncio.sleep(0)
        if condition():
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_mqtt_runner_dispatches_messages_then_backs_off() -> None:
    # one connected session delivering a message, then a dropped connection
    hub = _hub()
    hub.on_mqtt_message = MagicMock()
    fake = _FakeAiomqttClient(
        messages=[SimpleNamespace(topic="robot/pose", payload=b"{}")],
        stream_error=aiomqtt.MqttError("connection lost"),
    )

    async def main() -> None:
        with patch(
            "custom_components.terramow.hub.aiomqtt.Client", return_value=fake
        ):
            await _run_runner_until(hub, lambda: hub.connection_error)

    asyncio.run(main())
    # the aiomqtt message was normalized to the paho-like topic/payload shape
    msg = hub.on_mqtt_message.call_args.args[2]
    assert msg.topic == "robot/pose"
    assert msg.payload == b"{}"
    # the per-connect setup ran, and the drop flagged the connection error
    assert fake.subscribe.await_count == 9
    assert hub.connection_error is True
    assert hub._aiomqtt_client is None


# ---------------------------------------------------------------------------
# the sync mqtt-client facade
# ---------------------------------------------------------------------------


def test_facade_reports_disconnected_and_rejects_publish() -> None:
    hub = _hub()
    facade = _HubMqttClient(hub)
    assert facade.is_connected() is False
    assert facade.publish("t", "p").rc != 0


def test_facade_publishes_from_loop_and_executor_threads() -> None:
    hub = _hub()
    client = MagicMock()
    client.publish = AsyncMock()
    hub._aiomqtt_client = client
    facade = _HubMqttClient(hub)
    assert facade.is_connected() is True

    async def main() -> None:
        loop = asyncio.get_running_loop()
        hub.hass.loop = loop
        hub.hass.async_create_task = MagicMock(side_effect=loop.create_task)

        # from the event loop: handed off via async_create_task
        assert facade.publish("t1", "p1", qos=1).rc == 0
        await asyncio.sleep(0)
        client.publish.assert_awaited_once_with("t1", "p1", qos=1)

        # from an executor thread: handed off via run_coroutine_threadsafe
        result = await loop.run_in_executor(None, facade.publish, "t2", "p2")
        assert result.rc == 0
        for _ in range(100):
            if client.publish.await_count == 2:
                break
            await asyncio.sleep(0.01)
        client.publish.assert_awaited_with("t2", "p2", qos=0)

    asyncio.run(main())


def test_facade_logs_async_publish_failure(caplog) -> None:
    hub = _hub()
    client = MagicMock()
    client.publish = AsyncMock(side_effect=aiomqtt.MqttError("gone"))
    hub._aiomqtt_client = client
    facade = _HubMqttClient(hub)

    async def main() -> None:
        loop = asyncio.get_running_loop()
        hub.hass.loop = loop
        hub.hass.async_create_task = MagicMock(side_effect=loop.create_task)
        assert facade.publish("t", "p").rc == 0  # accepted at handoff...
        await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR):
        asyncio.run(main())
    # ...but the delivery failure surfaces in the log
    assert "publish to t failed" in caplog.text


def test_mqtt_runner_clean_stream_end_counts_as_failure() -> None:
    # a message stream that ends without an error must still back off
    hub = _hub()
    fake = _FakeAiomqttClient(messages=[])

    async def main() -> None:
        with patch(
            "custom_components.terramow.hub.aiomqtt.Client", return_value=fake
        ):
            await _run_runner_until(hub, lambda: hub.connection_error)

    asyncio.run(main())
    assert hub.connection_error is True
