"""Data point payload → entity state tests.

Feeds realistic device payloads through the hub's handlers and asserts
what the entities report to Home Assistant, including the write path
(select/number/switch publishing back to the device).
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.binary_sensor import (
    PowerSwitchSensor,
    TerraMowChargingSensor,
    TerraMowMapDetectedBinarySensor,
    TerraMowProblemSensor,
    TerraMowRainSensor,
    TerraMowSavingDataBinarySensor,
)
from custom_components.terramow.const import BLADE_MAINTENANCE_CYCLE_MINUTES
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import MowingHeightNumber
from custom_components.terramow.select import MowSpeedSelect
from custom_components.terramow.sensor import (
    BatterySensor,
    BatteryStateSensor,
    BatteryTemperatureStateSensor,
    CurrentJobTypeSensor,
    CurrentSessionAreaSensor,
    CurrentSessionProgressSensor,
    CurrentSessionTimeSensor,
    MainDirectionStatusSensor,
    NextScheduledStartSensor,
    RemainingBladeTimeSensor,
    TerraMowMissionSensor,
    TotalMowedAreaSensor,
    TotalMowingJobsSensor,
    TotalMowingTimeSensor,
)
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    return TerraMowHub(basic_data, MagicMock())


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


# ---------------------------------------------------------------------------
# dp_8 / dp_108 — battery
# ---------------------------------------------------------------------------


def test_battery_level_from_dp8() -> None:
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)
    sensor.set_capacity('{"int_value": 76}')
    assert sensor.native_value == 76


def test_battery_status_sensors_from_dp108() -> None:
    hub = _hub()
    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_CHARGING",
        "tempreture": "BATTERY_TEMPRETURE_NORMAL",
        "charger_connected": True,
        "is_switch_on": False,
    })
    assert BatteryStateSensor(hub.basic_data, hub.hass).native_value == "battery_state_charging"
    assert (
        BatteryTemperatureStateSensor(hub.basic_data, hub.hass).native_value
        == "battery_tempreture_normal"
    )
    assert TerraMowChargingSensor(hub.basic_data, hub.hass).is_on is True
    assert PowerSwitchSensor(hub.basic_data, hub.hass).is_on is False


# ---------------------------------------------------------------------------
# dp_124 — lifetime statistics
# ---------------------------------------------------------------------------


def test_statistics_sensors_from_dp124() -> None:
    hub = _hub()
    _feed(hub.on_statistics_data, {
        "duration": 7200,
        "clean_times": 12,
        "clean_area": 1234,  # 0.1 m² units
    })
    assert TotalMowingTimeSensor(hub.basic_data, hub.hass).native_value == 7200
    assert TotalMowingJobsSensor(hub.basic_data, hub.hass).native_value == 12
    assert TotalMowedAreaSensor(hub.basic_data, hub.hass).native_value == 123.4


# ---------------------------------------------------------------------------
# dp_113 — current session
# ---------------------------------------------------------------------------


def test_current_session_sensors_from_dp113() -> None:
    hub = _hub()
    _feed(hub.on_current_work_data, {
        "clean_area": 500,   # 0.1 m² -> 50 m²
        "total_area": 1000,  # 0.1 m² -> 100 m²
        "work_duration": 903,
        "type": "MAP_AREA_TYPE_CLEANING",
        "is_completed": False,
    })
    assert CurrentSessionAreaSensor(hub.basic_data, hub.hass).native_value == 50.0
    assert CurrentSessionProgressSensor(hub.basic_data, hub.hass).native_value == 50.0
    assert CurrentSessionTimeSensor(hub.basic_data, hub.hass).native_value == 903
    assert CurrentJobTypeSensor(hub.basic_data, hub.hass).native_value == "map_area_type_cleaning"


def test_session_progress_is_capped_at_100() -> None:
    hub = _hub()
    _feed(hub.on_current_work_data, {"clean_area": 1050, "total_area": 1000})
    assert CurrentSessionProgressSensor(hub.basic_data, hub.hass).native_value == 100.0


def test_unknown_job_type_reports_none() -> None:
    hub = _hub()
    _feed(hub.on_current_work_data, {"type": "MAP_AREA_TYPE_FROM_THE_FUTURE"})
    assert CurrentJobTypeSensor(hub.basic_data, hub.hass).native_value is None


# ---------------------------------------------------------------------------
# dp_126 — blade maintenance timer
# ---------------------------------------------------------------------------


def test_remaining_blade_time_from_dp126() -> None:
    hub = _hub()
    _feed(hub.on_blade_time, {"int_value": 400})
    sensor = RemainingBladeTimeSensor(hub.basic_data, hub.hass)
    assert sensor.native_value == BLADE_MAINTENANCE_CYCLE_MINUTES - 400

    # An overdue blade must clamp at 0, not go negative
    _feed(hub.on_blade_time, {"int_value": BLADE_MAINTENANCE_CYCLE_MINUTES + 99})
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["needs_maintenance"] is True


# ---------------------------------------------------------------------------
# dp_138 — schedule
# ---------------------------------------------------------------------------


def test_next_scheduled_start_from_dp138() -> None:
    hub = _hub()
    sensor = NextScheduledStartSensor(hub.basic_data, hub.hass)
    _feed(hub.on_schedule_data, {"exist": True, "start_time": {"hour": 9, "minute": 5}})
    assert sensor.native_value == "09:05"

    _feed(hub.on_schedule_data, {"exist": False})
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# dp_107 — task status
# ---------------------------------------------------------------------------


def test_task_status_binary_sensors_from_dp107() -> None:
    hub = _hub()
    _feed(hub.on_mission_status, {
        "mission": "MISSION_GLOBAL_CLEAN",
        "state": "MISSION_STATE_RUNNING",
        "has_error": True,
        "is_saving_data": True,
        "back_to_station_reason": "BACK_TO_STATION_REASON_RAINING",
    })
    assert TerraMowProblemSensor(hub.basic_data, hub.hass).is_on is True
    assert TerraMowRainSensor(hub.basic_data, hub.hass).is_on is True
    assert TerraMowSavingDataBinarySensor(hub.basic_data, hub.hass).is_on is True
    assert TerraMowMissionSensor(hub.basic_data, hub.hass).native_value == "mission_global_clean"


# ---------------------------------------------------------------------------
# dp_117 — map status
# ---------------------------------------------------------------------------


def test_map_detected_from_dp117() -> None:
    hub = _hub()
    sensor = TerraMowMapDetectedBinarySensor(hub.basic_data, hub.hass)
    _feed(hub.on_map_status, {"is_map_detected": True, "map_id": 3})
    assert sensor.is_on is True
    _feed(hub.on_map_status, {"is_map_detected": False})
    assert sensor.is_on is False


# ---------------------------------------------------------------------------
# dp_155 — global parameters (read and write paths)
# ---------------------------------------------------------------------------


def test_global_param_sensors_from_dp155() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {
        "mow_height": {"value": 45},
        "mow_speed": {"speed_type": "MOW_SPEED_TYPE_LOW"},
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })
    assert MowingHeightNumber(hub.basic_data, hub.hass).native_value == 45.0
    assert (
        MowSpeedSelect(hub.basic_data, hub.hass).current_option == "mow_speed_type_low"
    )
    assert (
        MainDirectionStatusSensor(hub.basic_data, hub.hass).native_value
        == "main_direction_mode_multiple"
    )


def test_mow_speed_select_round_trip() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("mow_speed_type_low"))

    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/155/app"
    assert json.loads(payload) == {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_LOW"}}
    assert select.current_option == "mow_speed_type_low"


def test_mow_speed_select_rejects_invalid_option() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("warp_speed"))
    hub.mqtt_client.publish.assert_not_called()


def test_mowing_height_number_write_path() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    number = MowingHeightNumber(hub.basic_data, hub.hass)

    asyncio.run(number.async_set_native_value(52.0))

    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/155/app"
    assert json.loads(payload) == {"mow_height": {"value": 52}}


# ---------------------------------------------------------------------------
# map info — thorough corner cutting switch
# ---------------------------------------------------------------------------


def test_corner_cutting_switch_reads_map_info() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    assert switch.is_on is None  # no map info yet

    hub._update_map_info({"mow_param": {"enable_thorough_corner_cutting": True}})
    assert switch.is_on is True


def test_corner_cutting_switch_write_path() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)

    asyncio.run(switch.async_turn_on())

    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/155/app"
    assert json.loads(payload) == {"enable_thorough_corner_cutting": True}
