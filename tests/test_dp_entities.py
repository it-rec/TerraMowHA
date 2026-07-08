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
    BINARY_SENSORS,
    TerraMowBinarySensor,
)
from custom_components.terramow.const import BLADE_MAINTENANCE_CYCLE_MINUTES
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import MowingHeightNumber
from custom_components.terramow.select import MowSpeedSelect
from custom_components.terramow.sensor import (
    SENSORS,
    BatterySensor,
    TerraMowSensor,
)
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch

_SENSOR_DESCRIPTIONS = {description.key: description for description in SENSORS}
_BINARY_DESCRIPTIONS = {
    description.key: description for description in BINARY_SENSORS
}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    return TerraMowHub(basic_data, MagicMock())


def _sensor(hub: TerraMowHub, key: str) -> TerraMowSensor:
    return TerraMowSensor(hub.basic_data, hub.hass, _SENSOR_DESCRIPTIONS[key])


def _binary(hub: TerraMowHub, key: str) -> TerraMowBinarySensor:
    return TerraMowBinarySensor(hub.basic_data, hub.hass, _BINARY_DESCRIPTIONS[key])


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def test_niche_diagnostics_disabled_by_default() -> None:
    hub = _hub()
    # niche / redundant readouts are off by default (enable on demand)
    disabled = [
        "sunrise", "sunset", "move_mode", "map_mode", "mow_mode",
        "last_event", "rain_sensor_threshold", "after_rain_resume_delay",
        "cellular_connection_type",
    ]
    for key in disabled:
        assert _sensor(hub, key).entity_registry_enabled_default is False
    # broadly-useful diagnostics stay enabled
    enabled_sensors = [
        "active_errors", "cellular_signal_rsrp", "cellular_signal_rsrq",
    ]
    for key in enabled_sensors:
        assert _sensor(hub, key).entity_registry_enabled_default is True
    enabled_binary = [
        "extreme_weather", "cliff_detection", "slope_detection",
        "after_rain_auto_resume", "cellular_enabled",
    ]
    for key in enabled_binary:
        assert _binary(hub, key).entity_registry_enabled_default is True


# ---------------------------------------------------------------------------
# dp_116 / dp_123 — active errors + event log (unofficial)
# ---------------------------------------------------------------------------


def test_active_errors_sensor_from_dp116() -> None:
    hub = _hub()
    sensor = _sensor(hub, "active_errors")
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
    sensor = _sensor(hub, "last_event")
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
# dp_150 — advanced settings (unofficial, read-only)
# ---------------------------------------------------------------------------


def test_advanced_settings_entities_from_dp150() -> None:
    hub = _hub()
    cliff = _binary(hub, "cliff_detection")
    slope = _binary(hub, "slope_detection")
    resume = _binary(hub, "after_rain_auto_resume")
    threshold = _sensor(hub, "rain_sensor_threshold")
    delay = _sensor(hub, "after_rain_resume_delay")
    # no data yet -> None everywhere
    assert cliff.is_on is None and threshold.native_value is None and delay.native_value is None
    _feed(hub.on_advanced_settings, {
        "enable_cliff_detection": {"value": True},
        "enable_slope_detection": {"value": False},
        "rain_sensor_threshold": {"upper_limit": 1000},
        "after_rain_stop_setting": {
            "enable_auto_resume": True,
            "auto_resume_delay_time": {"hours": 2, "minutes": 30},
        },
    })
    assert cliff.is_on is True
    assert slope.is_on is False
    assert resume.is_on is True
    assert threshold.native_value == 1000
    assert delay.native_value == 150  # 2h30m -> 150 minutes


def test_advanced_settings_entities_degrade_gracefully() -> None:
    hub = _hub()
    cliff = _binary(hub, "cliff_detection")
    threshold = _sensor(hub, "rain_sensor_threshold")
    delay = _sensor(hub, "after_rain_resume_delay")
    # malformed / missing nested fields -> None, never a crash
    _feed(hub.on_advanced_settings, {
        "enable_cliff_detection": {"value": "x"},        # non-bool
        "rain_sensor_threshold": "nope",                 # non-dict
        "after_rain_stop_setting": {"auto_resume_delay_time": {}},  # empty delay
    })
    assert cliff.is_on is None
    assert threshold.native_value is None
    assert delay.native_value is None
    # a partial delay (only minutes) still computes
    _feed(hub.on_advanced_settings, {
        "after_rain_stop_setting": {"auto_resume_delay_time": {"minutes": 45}},
    })
    assert delay.native_value == 45
    # a non-dict node partway down a nested path -> None
    _feed(hub.on_advanced_settings, {"enable_cliff_detection": "x"})
    assert cliff.is_on is None
    # a non-dict after_rain_stop_setting, and a dict without the delay -> None
    _feed(hub.on_advanced_settings, {"after_rain_stop_setting": "nope"})
    assert delay.native_value is None
    _feed(hub.on_advanced_settings, {"after_rain_stop_setting": {}})
    assert delay.native_value is None
    # without a lawn mower -> None
    hub.basic_data.lawn_mower = None
    assert cliff.is_on is None and threshold.native_value is None and delay.native_value is None


def test_dp150_force_and_dp152_manual_mapping_binary_sensors() -> None:
    hub = _hub()
    fsb = _binary(hub, "force_single_base_station")
    fcn = _binary(hub, "force_cellular_network")
    reloc = _binary(hub, "manual_mapping_relocation")
    takeover = _binary(hub, "manual_mapping_takeover")
    boundary = _binary(hub, "manual_mapping_boundary_closed")
    # all disabled by default and None without data
    for ent in (fsb, fcn, reloc, takeover, boundary):
        assert ent.entity_registry_enabled_default is False
        assert ent.is_on is None
    _feed(hub.on_advanced_settings, {
        "force_single_base_station_mode": {"value": True},
        "force_cellular_network": {"value": False},
    })
    assert fsb.is_on is True and fcn.is_on is False
    _feed(hub.on_environment_info, {
        "manual_mapping": {
            "need_relocation": True, "need_takeover": False, "is_boundary_closed": True,
        },
    })
    assert reloc.is_on is True and takeover.is_on is False and boundary.is_on is True
    # a non-dict manual_mapping and a non-bool field degrade to None
    _feed(hub.on_environment_info, {"manual_mapping": "nope"})
    assert reloc.is_on is None
    _feed(hub.on_environment_info, {"manual_mapping": {"need_relocation": 1}})
    assert reloc.is_on is None
    # without a lawn mower -> None
    hub.basic_data.lawn_mower = None
    assert fsb.is_on is None and reloc.is_on is None


def test_dp118_map_save_progress_sensor() -> None:
    hub = _hub()
    progress = _sensor(hub, "map_save_progress")
    # transient diagnostic: disabled by default, None without data
    assert progress.entity_registry_enabled_default is False
    assert progress.native_value is None
    _feed(hub.on_map_save_progress, {"int_value": 0})
    assert progress.native_value == 0
    _feed(hub.on_map_save_progress, {"int_value": 55})
    assert progress.native_value == 55
    _feed(hub.on_map_save_progress, {"int_value": 100})
    assert progress.native_value == 100
    # a non-int / missing value degrades to None
    _feed(hub.on_map_save_progress, {"int_value": "x"})
    assert progress.native_value is None
    _feed(hub.on_map_save_progress, {"other": 1})
    assert progress.native_value is None
    # without a lawn mower -> None
    hub.basic_data.lawn_mower = None
    assert progress.native_value is None


def test_dp134_state_flag_binary_sensor() -> None:
    hub = _hub()
    flag = _binary(hub, "state_flag_134")
    # undecoded diagnostic: disabled by default, None without data
    assert flag.entity_registry_enabled_default is False
    assert flag.is_on is None
    # no attributes_fn -> the entity default (no extra attributes)
    assert flag.extra_state_attributes is None
    _feed(hub.on_state_flag_134, {"enum_value": 1})
    assert flag.is_on is True
    _feed(hub.on_state_flag_134, {"enum_value": 0})
    assert flag.is_on is False
    # an unexpected (non 0/1) value degrades to unknown
    _feed(hub.on_state_flag_134, {"enum_value": 2})
    assert flag.is_on is None
    _feed(hub.on_state_flag_134, {"other": 1})
    assert flag.is_on is None
    # without a lawn mower -> None
    hub.basic_data.lawn_mower = None
    assert flag.is_on is None


# ---------------------------------------------------------------------------
# dp_154 — operating modes (unofficial)
# ---------------------------------------------------------------------------


def test_operating_mode_sensors_from_dp154() -> None:
    hub = _hub()
    move = _sensor(hub, "move_mode")
    mapm = _sensor(hub, "map_mode")
    mow = _sensor(hub, "mow_mode")
    assert move.native_value is None
    _feed(hub.on_operating_modes, {
        "move_mode": "MOVE_MODE_MOW",
        "map_mode": "MAP_MODE_BASE_STATION",
        "mow_mode": "MOW_MODE_GLOBAL",
    })
    assert move.native_value == "MOVE_MODE_MOW"
    assert mapm.native_value == "MAP_MODE_BASE_STATION"
    assert mow.native_value == "MOW_MODE_GLOBAL"
    # missing / non-string field -> None
    _feed(hub.on_operating_modes, {"move_mode": 5})
    assert move.native_value is None
    assert mapm.native_value is None
    # without a lawn mower -> None
    hub.basic_data.lawn_mower = None
    assert move.native_value is None


# ---------------------------------------------------------------------------
# dp_152 / dp_157 — environment & weather (unofficial)
# ---------------------------------------------------------------------------


def test_environment_sensors_from_dp152() -> None:
    hub = _hub()
    sunrise = _sensor(hub, "sunrise")
    sunset = _sensor(hub, "sunset")
    defog = _binary(hub, "defogger_heating")
    illum = _binary(hub, "illumination_light")
    daylight = _binary(hub, "daylight")
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
    weather = _binary(hub, "extreme_weather")
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
    # without a lawn mower -> empty attributes
    hub.basic_data.lawn_mower = None
    assert weather.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# dp_135 — cellular / 4G (unofficial)
# ---------------------------------------------------------------------------


def test_cellular_sensors_disabled_report_none() -> None:
    hub = _hub()
    rsrp = _sensor(hub, "cellular_signal_rsrp")
    rsrq = _sensor(hub, "cellular_signal_rsrq")
    ctype = _sensor(hub, "cellular_connection_type")
    enabled = _binary(hub, "cellular_enabled")
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
    rsrp = _sensor(hub, "cellular_signal_rsrp")
    rsrq = _sensor(hub, "cellular_signal_rsrq")
    enabled = _binary(hub, "cellular_enabled")
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
    assert _sensor(hub, "battery_state").native_value == "battery_state_charging"
    assert (
        _sensor(hub, "battery_temperature_state").native_value
        == "battery_tempreture_normal"
    )
    assert _binary(hub, "charging_state").is_on is True
    assert _binary(hub, "power_switch").is_on is False


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
    assert _sensor(hub, "total_mowing_time").native_value == 7200
    assert _sensor(hub, "total_mowing_jobs").native_value == 12
    assert _sensor(hub, "total_mowed_area").native_value == 123.4


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
    assert _sensor(hub, "current_session_area").native_value == 50.0
    assert _sensor(hub, "current_session_progress").native_value == 50.0
    assert _sensor(hub, "current_session_time").native_value == 903
    assert _sensor(hub, "current_job_type").native_value == "map_area_type_cleaning"


def test_session_progress_is_capped_at_100() -> None:
    hub = _hub()
    _feed(hub.on_current_work_data, {"clean_area": 1050, "total_area": 1000})
    assert _sensor(hub, "current_session_progress").native_value == 100.0


def test_unknown_job_type_reports_none() -> None:
    hub = _hub()
    _feed(hub.on_current_work_data, {"type": "MAP_AREA_TYPE_FROM_THE_FUTURE"})
    assert _sensor(hub, "current_job_type").native_value is None


# ---------------------------------------------------------------------------
# dp_126 — blade maintenance timer
# ---------------------------------------------------------------------------


def test_remaining_blade_time_from_dp126() -> None:
    hub = _hub()
    _feed(hub.on_blade_time, {"int_value": 400})
    sensor = _sensor(hub, "remaining_blade_time")
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
    sensor = _sensor(hub, "next_scheduled_start")
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
    assert _binary(hub, "problem").is_on is True
    assert _binary(hub, "rain_detected").is_on is True
    assert _binary(hub, "saving_data").is_on is True
    assert _sensor(hub, "mission").native_value == "mission_global_clean"


# ---------------------------------------------------------------------------
# dp_117 — map status
# ---------------------------------------------------------------------------


def test_map_detected_from_dp117() -> None:
    hub = _hub()
    sensor = _binary(hub, "map_detected")
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
        _sensor(hub, "main_direction_status").native_value
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
