"""Extra coverage for the lawn mower, update, switch, map and binary platforms.

Drives the remaining branches: the lawn-mower activity/command paths and the
old-HA ``RETURNING``-less compatibility fallback, the firmware update entity's
callback registration and version formatting, the corner-cutting switch's
mow_param edge cases, the map area / clean-mode sensors and the map/task
binary-sensor callback registration and empty-status paths.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.components.lawn_mower.const import LawnMowerEntityFeature

import custom_components.terramow.lawn_mower as lawn_mower_module
from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.binary_sensor import (
    BINARY_SENSORS,
    TerraMowBinarySensor,
)
from custom_components.terramow.const import COMPATIBILITY_INFO_DP
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.lawn_mower import TerraMowLawnMowerEntity
from custom_components.terramow.map_sensor import (
    TerraMowCleanModeSensor,
    TerraMowMapAreaSensor,
    TerraMowMapStatusSensor,
)
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch
from custom_components.terramow.update import TerraMowFirmwareUpdate

_BINARY_DESCRIPTIONS = {
    description.key: description for description in BINARY_SENSORS
}


def _binary(hub: TerraMowHub, key: str) -> TerraMowBinarySensor:
    return TerraMowBinarySensor(hub.basic_data, hub.hass, _BINARY_DESCRIPTIONS[key])


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.80", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub._last_control_time = 0.0
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


# ---------------------------------------------------------------------------
# lawn mower entity
# ---------------------------------------------------------------------------


def test_lawn_mower_added_to_hass_registers_and_syncs_activity() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING",
    })
    asyncio.run(entity.async_added_to_hass())
    # the initial hub state is picked up during add
    assert entity.activity == LawnMowerActivity.MOWING
    # the state listener was registered so future hub changes push through
    _feed(hub.on_mission_status, {"mission": "MISSION_IDLE", "state": "MISSION_STATE_IDLE"})
    assert entity.activity == LawnMowerActivity.DOCKED


def test_lawn_mower_on_hub_state_updates_activity() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_PAUSE",
    })
    entity._on_hub_state()
    assert entity.activity == LawnMowerActivity.PAUSED


def test_lawn_mower_supported_features() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    features = entity.supported_features
    assert features & LawnMowerEntityFeature.START_MOWING
    assert features & LawnMowerEntityFeature.PAUSE
    assert features & LawnMowerEntityFeature.DOCK


def test_lawn_mower_pause_and_dock_delegate_to_hub() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN", "state": "MISSION_STATE_RUNNING",
    })
    hub._last_control_time = 0.0
    entity.pause()
    topic, _ = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/105/app"

    hub._last_control_time = 0.0
    entity.dock()
    topic, _ = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/103/app"


def test_lawn_mower_recharge_without_returning_falls_back_to_docked() -> None:
    hub = _hub()
    entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    # simulate an old HA build lacking LawnMowerActivity.RETURNING
    entity._has_returning = False
    _feed(hub.on_mission_status, {
        "mission": "MISSION_RECHARGE", "state": "MISSION_STATE_RUNNING",
    })
    entity.update_activity_from_state()
    assert entity.activity == LawnMowerActivity.DOCKED


def test_lawn_mower_init_logs_when_returning_absent() -> None:
    hub = _hub()
    fake_activity = SimpleNamespace(DOCKED="docked")  # no RETURNING attribute
    with patch.object(lawn_mower_module, "LawnMowerActivity", fake_activity):
        entity = TerraMowLawnMowerEntity(hub.basic_data, hub.hass)
    assert entity._has_returning is False


# ---------------------------------------------------------------------------
# firmware update entity
# ---------------------------------------------------------------------------


def test_update_added_to_hass_registers_refresh_callbacks() -> None:
    hub = _hub()
    mock_lm = MagicMock()
    hub.basic_data.lawn_mower = mock_lm
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    asyncio.run(update.async_added_to_hass())
    # refreshes on real version (102), compat fallback (127), component
    # versions (129) and is_upgrading (107)
    registered = {c.args[0] for c in mock_lm.register_callback.call_args_list}
    assert registered == {102, COMPATIBILITY_INFO_DP, 129, 107}


def test_update_added_to_hass_without_lawn_mower_is_noop() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    asyncio.run(update.async_added_to_hass())  # must not raise
    assert update.installed_version is None


def test_update_format_version_none_when_overall_missing() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    # firmware info present but without an "overall" key -> no version string
    hub.basic_data.firmware_version = {"module": {"home_assistant": 3}}
    assert update.installed_version is None
    assert update.latest_version is None


# ---------------------------------------------------------------------------
# thorough corner cutting switch
# ---------------------------------------------------------------------------


def test_corner_switch_none_when_mow_param_not_dict() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    hub._map_info = {"mow_param": "not-a-dict"}
    assert switch.is_on is None


def test_corner_switch_none_when_flag_absent() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    hub._map_info = {"mow_param": {}}
    assert switch.is_on is None


def test_corner_switch_reflects_flag_value() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    hub._map_info = {"mow_param": {"enable_thorough_corner_cutting": True}}
    assert switch.is_on is True
    hub._map_info = {"mow_param": {"enable_thorough_corner_cutting": False}}
    assert switch.is_on is False


# ---------------------------------------------------------------------------
# map sensors
# ---------------------------------------------------------------------------


def test_map_area_sensor_without_lawn_mower_skips_callback() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = TerraMowMapAreaSensor(hub.basic_data, hub.hass)
    # no map_info registered, no lawn_mower -> None
    assert sensor.native_value is None


def test_map_status_sensor_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = TerraMowMapStatusSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_map_area_sensor_value_and_zero() -> None:
    hub = _hub()
    sensor = TerraMowMapAreaSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None  # no map_info yet
    asyncio.run(sensor._on_map_info({"total_area": 1234}))
    assert sensor.native_value == 123.4
    # a zero total_area is a legitimate reading of 0.0 m^2, not unknown
    asyncio.run(sensor._on_map_info({"total_area": 0}))
    assert sensor.native_value == 0.0
    # only a missing field is unknown
    asyncio.run(sensor._on_map_info({"id": 1}))
    assert sensor.native_value is None


def test_clean_mode_sensor_value_and_attributes() -> None:
    hub = _hub()
    sensor = TerraMowCleanModeSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None  # no map_info yet
    assert sensor.extra_state_attributes == {}

    # a select-region job exposes the region ids as attributes
    asyncio.run(sensor._on_map_info({
        "clean_info": {
            "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
            "select_region": {"region_id": [1, 2, 3]},
        },
    }))
    assert sensor.native_value == "map_clean_info_mode_select_region"
    attrs = sensor.extra_state_attributes
    assert attrs["selected_regions"] == [1, 2, 3]
    assert attrs["selected_regions_count"] == 3

    # a global job (no select_region) yields no extra attributes
    asyncio.run(sensor._on_map_info({
        "clean_info": {"mode": "MAP_CLEAN_INFO_MODE_GLOBAL"},
    }))
    assert sensor.native_value == "map_clean_info_mode_global"
    assert sensor.extra_state_attributes == {}


def test_clean_mode_sensor_unknown_mode_is_none() -> None:
    hub = _hub()
    sensor = TerraMowCleanModeSensor(hub.basic_data, hub.hass)
    asyncio.run(sensor._on_map_info({"clean_info": {"mode": "MAP_CLEAN_INFO_MODE_ALIEN"}}))
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# map / task binary sensor callback registration + empty status
# ---------------------------------------------------------------------------


def test_map_binary_sensor_registers_dp117_callback() -> None:
    hub = _hub()
    mock_lm = MagicMock()
    hub.basic_data.lawn_mower = mock_lm
    sensor = _binary(hub, "map_detected")
    asyncio.run(sensor.async_added_to_hass())
    mock_lm.register_callback.assert_called_once_with(117, sensor._handle_push_update)
    # the unsubscribe returned by the hub is wired up for teardown
    assert mock_lm.register_callback.return_value in sensor._on_remove


def test_map_binary_sensor_added_without_lawn_mower_is_noop() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = _binary(hub, "map_detected")
    asyncio.run(sensor.async_added_to_hass())  # must not raise
    assert sensor.is_on is None


def test_map_binary_sensor_dp117_handler_writes_state() -> None:
    hub = _hub()
    sensor = _binary(hub, "map_backing_up")
    sensor.entity_id = "binary_sensor.map_backing_up"
    sensor.async_write_ha_state = MagicMock()
    asyncio.run(sensor._handle_push_update(""))
    sensor.async_write_ha_state.assert_called_once()


def test_task_binary_sensor_registers_dp107_callback() -> None:
    hub = _hub()
    mock_lm = MagicMock()
    hub.basic_data.lawn_mower = mock_lm
    sensor = _binary(hub, "saving_data")
    asyncio.run(sensor.async_added_to_hass())
    mock_lm.register_callback.assert_called_once_with(107, sensor._handle_push_update)
    # the unsubscribe returned by the hub is wired up for teardown
    assert mock_lm.register_callback.return_value in sensor._on_remove


def test_task_binary_sensor_added_without_lawn_mower_is_noop() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = _binary(hub, "saving_data")
    asyncio.run(sensor.async_added_to_hass())  # must not raise
    assert sensor.is_on is None


def test_task_binary_sensor_dp107_handler_writes_state() -> None:
    hub = _hub()
    sensor = _binary(hub, "saving_data")
    sensor.entity_id = "binary_sensor.saving_data"
    sensor.async_write_ha_state = MagicMock()
    asyncio.run(sensor._handle_push_update(""))
    sensor.async_write_ha_state.assert_called_once()


def test_task_binary_sensor_none_when_task_status_empty() -> None:
    hub = _hub()
    # lawn_mower present but no dp_107 payload -> empty task_status -> None
    sensor = _binary(hub, "saving_data")
    assert sensor.is_on is None
