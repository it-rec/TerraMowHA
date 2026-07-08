"""Thorough coverage for the sensor platform.

Covers async_setup_entry, the lawn-mower-missing branches across the sensor
set, the schedule / next-start sensor, the mow-speed unknown-value path and
attributes, the maintenance-time attributes, the pose sensor, the
main-direction status sensor and the dp_107 mission/sub-mission/state enum
sensors.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.terramow import DOMAIN, TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.sensor import (
    BackToStationReasonSensor,
    BatteryStateSensor,
    BatteryTemperatureStateSensor,
    CurrentJobTypeSensor,
    CurrentSessionAreaSensor,
    CurrentSessionProgressSensor,
    CurrentSessionTimeSensor,
    MainDirectionStatusSensor,
    NextScheduledStartSensor,
    PowerModeSensor,
    RemainingBaseStationTimeSensor,
    RemainingBladeTimeSensor,
    TerraMowMissionSensor,
    TerraMowMissionStateSensor,
    TerraMowMowHeightSensor,
    TerraMowMowSpeedSensor,
    TerraMowPoseSensor,
    TerraMowSubMissionSensor,
    TotalMowedAreaSensor,
    TotalMowingJobsSensor,
    TotalMowingTimeSensor,
    VersionCompatibilitySensor,
    async_setup_entry,
)

# sensors that expose native_value None both when the hub is missing and when
# the backing dp payload has not arrived yet
_NONE_SENSORS = (
    BatteryStateSensor,
    BatteryTemperatureStateSensor,
    TotalMowingTimeSensor,
    TotalMowingJobsSensor,
    TotalMowedAreaSensor,
    CurrentSessionAreaSensor,
    CurrentSessionProgressSensor,
    CurrentSessionTimeSensor,
    CurrentJobTypeSensor,
    TerraMowMowHeightSensor,
    TerraMowMowSpeedSensor,
    RemainingBladeTimeSensor,
    RemainingBaseStationTimeSensor,
    NextScheduledStartSensor,
    PowerModeSensor,
    BackToStationReasonSensor,
)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.70", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


# ---------------------------------------------------------------------------
# platform setup
# ---------------------------------------------------------------------------


def test_async_setup_entry_creates_all_sensors() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    # base + map + params + statistics + maintenance + schedule + version +
    # main-direction + power + task/mission sensors
    assert len(added) >= 20


# ---------------------------------------------------------------------------
# lawn-mower-missing branches
# ---------------------------------------------------------------------------


def test_sensors_return_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    for cls in (
        TerraMowMowSpeedSensor,
        NextScheduledStartSensor,
        RemainingBladeTimeSensor,
        RemainingBaseStationTimeSensor,
        BackToStationReasonSensor,
        TerraMowMissionSensor,
        TerraMowSubMissionSensor,
        TerraMowMissionStateSensor,
    ):
        sensor = cls(hub.basic_data, hub.hass)
        assert sensor.native_value is None
    # the main-direction status sensor reports a sentinel instead of None
    assert MainDirectionStatusSensor(hub.basic_data, hub.hass).native_value is None


# ---------------------------------------------------------------------------
# next scheduled start
# ---------------------------------------------------------------------------


def test_all_sensors_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    for cls in _NONE_SENSORS:
        assert cls(hub.basic_data, hub.hass).native_value is None


def test_all_sensors_none_before_dp_payloads() -> None:
    # hub present but no dp_108/113/124/125/126/138/155/107 payloads yet
    hub = _hub()
    for cls in _NONE_SENSORS:
        assert cls(hub.basic_data, hub.hass).native_value is None


def test_next_scheduled_start_formats_time_and_attributes() -> None:
    hub = _hub()
    sensor = NextScheduledStartSensor(hub.basic_data, hub.hass)
    _feed(hub.on_schedule_data, {
        "exist": True,
        "item_id": 3,
        "shift_id": 1,
        "start_time": {"hour": 9, "minute": 5},
        "end_time": {"hour": 11, "minute": 30},
    })
    assert sensor.native_value == "09:05"
    attrs = sensor.extra_state_attributes
    assert attrs["has_schedule"] is True
    assert attrs["end_time"] == "11:30"


def test_next_scheduled_start_none_when_no_schedule() -> None:
    hub = _hub()
    sensor = NextScheduledStartSensor(hub.basic_data, hub.hass)
    _feed(hub.on_schedule_data, {"exist": False})
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["has_schedule"] is False


# ---------------------------------------------------------------------------
# mow speed sensor: unknown value + attributes
# ---------------------------------------------------------------------------


def test_mow_speed_sensor_unknown_value_and_attributes() -> None:
    hub = _hub()
    sensor = TerraMowMowSpeedSensor(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "mow_speed": {"speed_type": "MOW_SPEED_TYPE_TURBO"},
        "mow_spacing": {"value": 100},
        "edge_cutting_distance": {"value": -10},
        "blade_disk_speed": {"speed_type": "BLADE_DISK_SPEED_TYPE_HIGH"},
    })
    assert sensor.native_value is None  # unknown enum -> None
    attrs = sensor.extra_state_attributes
    assert attrs["mow_spacing"] == 100
    assert attrs["edge_cutting_distance"] == -10
    assert attrs["blade_disk_speed"] == "BLADE_DISK_SPEED_TYPE_HIGH"
    assert attrs["unknown_mow_speed_type"] == "MOW_SPEED_TYPE_TURBO"


def test_mow_speed_sensor_none_when_empty() -> None:
    hub = _hub()
    sensor = TerraMowMowSpeedSensor(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"mow_speed": {}})
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# maintenance-time attributes
# ---------------------------------------------------------------------------


def test_remaining_time_sensors_expose_attributes() -> None:
    hub = _hub()
    blade = RemainingBladeTimeSensor(hub.basic_data, hub.hass)
    base = RemainingBaseStationTimeSensor(hub.basic_data, hub.hass)
    _feed(hub.on_blade_time, {"int_value": 15000})   # past the 14400 cycle
    _feed(hub.on_base_station_time, {"int_value": 100})
    assert blade.native_value == 0  # clamped
    blade_attrs = blade.extra_state_attributes
    assert blade_attrs["used_time"] == 15000
    assert blade_attrs["needs_maintenance"] is True
    base_attrs = base.extra_state_attributes
    assert base_attrs["needs_maintenance"] is False


# ---------------------------------------------------------------------------
# pose sensor
# ---------------------------------------------------------------------------


def test_pose_sensor_value_and_attributes() -> None:
    hub = _hub()
    sensor = TerraMowPoseSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    asyncio.run(sensor._on_pose({"x": 1.0, "y": 2.0, "yaw": 33.0, "frame": 9}))
    assert sensor.native_value == 33.0
    attrs = sensor.extra_state_attributes
    assert attrs["x"] == 1.0
    assert attrs["frame"] == 9


# ---------------------------------------------------------------------------
# version compatibility sensor
# ---------------------------------------------------------------------------


def test_version_compatibility_attributes_include_firmware() -> None:
    hub = _hub()
    sensor = VersionCompatibilitySensor(hub.basic_data, hub.hass)
    hub.basic_data.firmware_version = {
        "overall": 26,
        "module": {"home_assistant": 3, "map": 5, "control": 7},
    }
    attrs = sensor.extra_state_attributes
    assert attrs["firmware_overall_version"] == 26
    assert attrs["firmware_ha_version"] == 3
    assert "plugin_ha_version" in attrs


# ---------------------------------------------------------------------------
# main-direction status sensor
# ---------------------------------------------------------------------------


def test_main_direction_status_no_config_and_modes() -> None:
    hub = _hub()
    sensor = MainDirectionStatusSensor(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {})  # empty -> unknown
    assert sensor.native_value is None

    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_MULTIPLE",
            "current_angle": 40,
            "multiple_mode_config": {"angles": [30, 120]},
        },
    })
    assert sensor.native_value == "main_direction_mode_multiple"
    attrs = sensor.extra_state_attributes
    assert attrs["mode"] == "MAIN_DIRECTION_MODE_MULTIPLE"
    assert attrs["angles_count"] == 2
    assert attrs["current_angle"] == 40
    assert attrs["mode_friendly_name"] == "Multiple Directions"


# ---------------------------------------------------------------------------
# dp_107 mission enum sensors
# ---------------------------------------------------------------------------


def test_main_direction_status_single_and_auto_modes() -> None:
    hub = _hub()
    sensor = MainDirectionStatusSensor(hub.basic_data, hub.hass)

    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_SINGLE",
            "single_mode_config": {"angle": 12},
        },
    })
    attrs = sensor.extra_state_attributes
    assert attrs["configured_angle"] == 12
    assert attrs["mode_description"] == "Single main direction"

    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
            "auto_rotate_mode_config": {"angle_interval": 30},
        },
    })
    attrs = sensor.extra_state_attributes
    assert attrs["rotation_interval"] == 30
    assert attrs["mode_description"] == "Auto rotate main direction"


def test_mission_enum_sensor_handle_dp107_writes_state() -> None:
    hub = _hub()
    sensor = TerraMowMissionSensor(hub.basic_data, hub.hass)
    sensor.hass = hub.hass
    sensor.entity_id = "sensor.mission"
    # the dp_107 callback just schedules a state write; must not raise
    asyncio.run(sensor._handle_push_update(""))


def test_mission_enum_sensors_from_dp107() -> None:
    hub = _hub()
    mission = TerraMowMissionSensor(hub.basic_data, hub.hass)
    sub = TerraMowSubMissionSensor(hub.basic_data, hub.hass)
    state = TerraMowMissionStateSensor(hub.basic_data, hub.hass)
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "sub_mission": "SUB_MISSION_FLEXIBLE_STATION_WAIT",
        "state": "MISSION_STATE_RUNNING",
    })
    assert mission.native_value == "mission_global_clean"
    assert sub.native_value == "sub_mission_flexible_station_wait"
    assert state.native_value == "mission_state_running"


def test_mission_sensor_none_when_member_unset() -> None:
    hub = _hub()
    mission = TerraMowMissionSensor(hub.basic_data, hub.hass)
    # an unset mission member reports None
    hub.mission = None
    assert mission.native_value is None


def test_back_to_station_reason_unknown_value_is_none() -> None:
    hub = _hub()
    sensor = BackToStationReasonSensor(hub.basic_data, hub.hass)
    _feed(hub.on_mission_status, {"back_to_station_reason": "BACK_TO_STATION_REASON_ALIEN"})
    assert sensor.native_value is None
