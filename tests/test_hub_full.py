"""Thorough coverage for the hub's MQTT plumbing.

Covers the dp handlers' invalid-JSON guards, the callback registrars, the
connect/disconnect callbacks, the message router (meta/pose/map/model/data
topics) and the model-name / map-info handlers.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

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
from custom_components.terramow.hub import TerraMowHub


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
    assert hub.hass.add_job.call_count == 4

    with pytest.raises(ValueError):
        hub.register_map_callback("nope")


# ---------------------------------------------------------------------------
# connect / disconnect callbacks
# ---------------------------------------------------------------------------


def test_on_mqtt_connect_subscribes_and_clears_error() -> None:
    hub = _hub()
    hub.connection_error = True
    client = MagicMock()
    hub.on_mqtt_connect(client, None, None, 0)
    # 201 data-point topics + info/meta/pose/model subscriptions
    assert client.subscribe.call_count > 200
    assert hub.connection_error is False
    # a compatibility-info request was published
    assert hub.mqtt_client.publish.called


def test_on_mqtt_connect_failure_sets_error() -> None:
    hub = _hub()
    hub.on_mqtt_connect(MagicMock(), None, None, 5)
    assert hub.connection_error is True


def test_on_mqtt_disconnect_unexpected_sets_error() -> None:
    hub = _hub()
    hub.on_mqtt_disconnect(None, None, 0)  # clean disconnect -> no error
    assert hub.connection_error is False
    hub.on_mqtt_disconnect(None, None, 1)  # unexpected -> error
    assert hub.connection_error is True


# ---------------------------------------------------------------------------
# message router
# ---------------------------------------------------------------------------


def test_on_mqtt_message_routes_meta_and_pose_topics() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, _msg(MAP_META_TOPIC, {"url": "u"}))
    assert hub._map_meta == {"url": "u"}
    hub.on_mqtt_message(None, None, _msg(PATH_META_TOPIC, {"url": "p"}))
    assert hub._path_meta == {"url": "p"}
    hub.on_mqtt_message(None, None, _msg(PATH_HISTORY_META_TOPIC, {"url": "h"}))
    assert hub._history_path_meta == {"url": "h"}

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
    assert hub.hass.add_job.called


def test_on_mqtt_message_handles_unknown_and_invalid_topics() -> None:
    hub = _hub()
    # unknown but well-formed dp topic -> logged once, then again
    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", "payload"))
    hub.on_mqtt_message(None, None, _msg("data_point/199/robot", "payload"))
    assert 199 in hub._seen_unknown_dp_ids
    # a completely invalid topic is ignored without raising
    hub.on_mqtt_message(None, None, _msg("garbage/topic", "x"))


def test_on_mqtt_message_meta_invalid_json_is_swallowed() -> None:
    hub = _hub()
    hub.on_mqtt_message(None, None, SimpleNamespace(topic=MAP_META_TOPIC, payload=b"not-json"))
    # nothing stored, no exception
    assert hub._map_meta in ({}, None) or hub._map_meta == {}


# ---------------------------------------------------------------------------
# map-info / model-name handlers + mode-change notification
# ---------------------------------------------------------------------------


def test_handle_map_info_updates_and_notifies() -> None:
    hub = _hub()
    cb = MagicMock()
    hub.map_callbacks.append(cb)
    hub._handle_map_info(json.dumps({"id": 7, "map_state": "MAP_STATE_COMPLETE"}))
    assert hub.map_info["id"] == 7
    assert hub.hass.add_job.called
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


def test_mqtt_loop_success_and_failure_iterations() -> None:
    # success iteration: connect + loop_forever, then stop
    hub = _hub()
    hub._stop_event = MagicMock()
    hub._stop_event.is_set.side_effect = [False, True]
    hub.mqtt_client.is_connected.return_value = False
    hub.mqtt_loop()
    hub.mqtt_client.connect.assert_called_once()
    hub.mqtt_client.loop_forever.assert_called_once()

    # failure iteration: connect raises -> error state + backoff wait
    hub2 = _hub()
    hub2._stop_event = MagicMock()
    hub2._stop_event.is_set.side_effect = [False, True]
    hub2.mqtt_client.is_connected.return_value = False
    hub2.mqtt_client.connect.side_effect = OSError("unreachable")
    hub2.mqtt_loop()
    assert hub2.connection_error is True
    hub2._stop_event.wait.assert_called()
