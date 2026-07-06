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
    CellularEnabledSensor,
    DaylightSensor,
    DefoggerHeatingSensor,
    ExtremeWeatherSensor,
    IlluminationLightSensor,
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
    ActiveErrorsSensor,
    CellularConnectionTypeSensor,
    CellularSignalRsrpSensor,
    CellularSignalRsrqSensor,
    LastEventSensor,
    MainDirectionStatusSensor,
    SunriseSensor,
    SunsetSensor,
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
# dp_116 / dp_123 — active errors + event log (unofficial)
# ---------------------------------------------------------------------------


def test_active_errors_sensor_from_dp116() -> None:
    hub = _hub()
    sensor = ActiveErrorsSensor(hub.basic_data, hub.hass)
    # no data yet -> zero active errors, no attributes
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes == {}
    _feed(hub.on_error_list, {"error_list": [{"code": 3}, {"code": 7}]})
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == {"errors": [{"code": 3}, {"code": 7}]}
    # without a lawn mower the sensor reports no value
    hub.basic_data.lawn_mower = None
    assert sensor.native_value is None


def test_last_event_sensor_from_dp123() -> None:
    hub = _hub()
    sensor = LastEventSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
    _feed(hub.on_event_data, {"event_list": [
        {"code": 1, "time": "2026-07-06T08:00:00Z"},
        {"code": 8, "time": "2026-07-06T08:27:38Z"},
    ]})
    assert sensor.native_value == 8
    assert sensor.extra_state_attributes == {"event_time": "2026-07-06T08:27:38Z"}
    # a malformed latest entry / missing fields degrade gracefully
    _feed(hub.on_event_data, {"event_list": ["oops"]})
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# dp_152 / dp_157 — environment & weather (unofficial)
# ---------------------------------------------------------------------------


def test_environment_sensors_from_dp152() -> None:
    hub = _hub()
    sunrise = SunriseSensor(hub.basic_data, hub.hass)
    sunset = SunsetSensor(hub.basic_data, hass=hub.hass)
    defog = DefoggerHeatingSensor(hub.basic_data, hub.hass)
    illum = IlluminationLightSensor(hub.basic_data, hub.hass)
    daylight = DaylightSensor(hub.basic_data, hub.hass)
    # no data yet -> None
    assert sunrise.native_value is None and defog.is_on is None
    _feed(hub.on_environment_info, {
        "is_defogger_heating": True,
        "is_illuminate_light_on": False,
        "sunrise": {"hour": 5, "minute": 29},
        "sunset": {"hour": 21, "minute": 7},
        "is_not_in_daylight_period": True,
    })
    assert sunrise.native_value == "05:29"
    assert sunset.native_value == "21:07"
    assert defog.is_on is True
    assert illum.is_on is False
    assert daylight.is_on is False  # inverted from is_not_in_daylight_period
    # a malformed time slot degrades to None (bad hour, bad minute, non-dict)
    _feed(hub.on_environment_info, {
        "sunrise": {"hour": "x", "minute": 0},   # bad hour
        "sunset": {"hour": 5, "minute": "x"},    # valid hour, bad minute
    })
    assert sunrise.native_value is None
    assert sunset.native_value is None
    # a non-dict slot is also handled
    _feed(hub.on_environment_info, {"sunrise": "nope"})
    assert sunrise.native_value is None
    # without a lawn mower the sensor reports no value
    hub.basic_data.lawn_mower = None
    assert sunrise.native_value is None


def test_extreme_weather_sensor_from_dp157() -> None:
    hub = _hub()
    weather = ExtremeWeatherSensor(hub.basic_data, hub.hass)
    assert weather.is_on is None
    assert weather.extra_state_attributes == {}
    _feed(hub.on_weather_info, {
        "has_extream_weather": True,
        "extream_weather_info_url": "https://example.invalid/w",
    })
    assert weather.is_on is True
    assert weather.extra_state_attributes == {"info_url": "https://example.invalid/w"}
    # no url -> no attribute
    _feed(hub.on_weather_info, {"has_extream_weather": False, "extream_weather_info_url": ""})
    assert weather.is_on is False
    assert weather.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# dp_135 — cellular / 4G (unofficial)
# ---------------------------------------------------------------------------


def test_cellular_sensors_disabled_report_none() -> None:
    hub = _hub()
    rsrp = CellularSignalRsrpSensor(hub.basic_data, hub.hass)
    rsrq = CellularSignalRsrqSensor(hub.basic_data, hub.hass)
    ctype = CellularConnectionTypeSensor(hub.basic_data, hub.hass)
    enabled = CellularEnabledSensor(hub.basic_data, hub.hass)
    # no dp_135 yet -> unavailable/None everywhere
    assert rsrp.native_value is None and enabled.is_on is None
    assert ctype.native_value is None
    # disabled modem: signal is None, type still reported, enabled False
    _feed(hub.on_cellular_info, {
        "is_enabled": False, "RSRP": 0, "RSRQ": 0, "type": "CELLULAR_TYPE_UNKNOWN",
    })
    assert rsrp.native_value is None
    assert rsrq.native_value is None
    assert ctype.native_value == "CELLULAR_TYPE_UNKNOWN"
    assert enabled.is_on is False
    # a missing/empty type degrades to None
    _feed(hub.on_cellular_info, {"is_enabled": False, "type": ""})
    assert ctype.native_value is None


def test_cellular_sensors_enabled_report_signal() -> None:
    hub = _hub()
    rsrp = CellularSignalRsrpSensor(hub.basic_data, hub.hass)
    rsrq = CellularSignalRsrqSensor(hub.basic_data, hub.hass)
    enabled = CellularEnabledSensor(hub.basic_data, hub.hass)
    _feed(hub.on_cellular_info, {
        "is_enabled": True, "RSRP": -95, "RSRQ": -12, "type": "CELLULAR_TYPE_LTE",
    })
    assert rsrp.native_value == -95
    assert rsrq.native_value == -12
    assert enabled.is_on is True
    # a non-integer signal value degrades to None
    _feed(hub.on_cellular_info, {"is_enabled": True, "RSRP": "x", "RSRQ": None})
    assert rsrp.native_value is None and rsrq.native_value is None


# ---------------------------------------------------------------------------
# dp_8 / dp_108 — battery
# ---------------------------------------------------------------------------


def test_battery_level_from_dp8() -> None:
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)
    asyncio.run(hub.on_battery_level('{"int_value": 76}'))
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
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
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
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("warp_speed"))
    hub.mqtt_client.publish.assert_not_called()


def test_mowing_height_number_write_path() -> None:
    hub = _hub()
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
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
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)

    asyncio.run(switch.async_turn_on())

    topic, payload = hub.mqtt_client.publish.call_args.args
    assert topic == "data_point/155/app"
    assert json.loads(payload) == {"enable_thorough_corner_cutting": True}
