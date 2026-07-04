"""Extra coverage for number and sensor platform entities.

Complements ``test_platform_entities`` by exercising the mowing-parameter
numbers (height/edge/spacing and the mode-dependent direction angles) and the
statistics/session/maintenance sensors that read dp_124/dp_113/dp_125/dp_126.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import (
    EdgeCuttingDistanceNumber,
    MainDirectionAutoRotateIntervalNumber,
    MowingHeightNumber,
    MowingSpacingNumber,
    MultipleDirectionAngle1Number,
    MultipleDirectionAngle2Number,
)
from custom_components.terramow.sensor import (
    BatterySensor,
    BatteryStateSensor,
    BatteryTemperatureStateSensor,
    CurrentJobTypeSensor,
    CurrentSessionAreaSensor,
    CurrentSessionProgressSensor,
    CurrentSessionTimeSensor,
    RemainingBaseStationTimeSensor,
    RemainingBladeTimeSensor,
    TerraMowMowHeightSensor,
    TotalMowedAreaSensor,
    TotalMowingJobsSensor,
    TotalMowingTimeSensor,
)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.20", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# mowing-parameter numbers (dp_155 global params)
# ---------------------------------------------------------------------------


def test_mowing_height_number_read_and_write() -> None:
    hub = _hub()
    number = MowingHeightNumber(hub.basic_data, hub.hass)
    assert number.native_value is None

    _feed(hub.on_global_params, {"mow_height": {"value": 45}})
    assert number.native_value == 45.0

    asyncio.run(number.async_set_native_value(50.0))
    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"mow_height": {"value": 50}}


def test_edge_cutting_distance_number_read_and_write() -> None:
    hub = _hub()
    number = EdgeCuttingDistanceNumber(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"edge_cutting_distance": {"value": -20}})
    assert number.native_value == -20.0

    asyncio.run(number.async_set_native_value(30.0))
    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"edge_cutting_distance": {"value": 30}}


def test_mowing_spacing_number_rejects_out_of_range() -> None:
    hub = _hub()
    number = MowingSpacingNumber(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "mow_spacing": {"value": 100},
        "current_mow_spacing": 90,
    })
    assert number.native_value == 100.0
    assert number.extra_state_attributes["current_mow_spacing"] == 90

    # valid value publishes
    asyncio.run(number.async_set_native_value(120.0))
    topic, command = _published(hub)
    assert command == {"mow_spacing": {"value": 120}}

    # out-of-range value is rejected without publishing
    hub.mqtt_client.publish.reset_mock()
    asyncio.run(number.async_set_native_value(200.0))
    hub.mqtt_client.publish.assert_not_called()


def _mode_number(number, hub):
    # no mode-selector entity in these tests -> fall back to device data
    hub.hass.states.get = MagicMock(return_value=None)
    return number


def test_auto_rotate_interval_number_mode_dependent() -> None:
    hub = _hub()
    number = _mode_number(
        MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass), hub
    )
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
            "auto_rotate_mode_config": {"angle_interval": 25},
        },
    })
    assert number.available is True
    assert number.native_value == 25.0

    asyncio.run(number.async_set_native_value(30.0))
    topic, command = _published(hub)
    cfg = command["main_direction_angle_config"]
    assert cfg["mode"] == "MAIN_DIRECTION_MODE_AUTO_ROTATE"
    assert cfg["auto_rotate_mode_config"] == {"angle_interval": 30}


def test_auto_rotate_interval_unavailable_in_single_mode() -> None:
    hub = _hub()
    number = _mode_number(
        MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass), hub
    )
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"},
    })
    assert number.available is False
    assert number.native_value is None

    asyncio.run(number.async_set_native_value(30.0))
    hub.mqtt_client.publish.assert_not_called()


def test_multiple_direction_angle_numbers_read_and_write() -> None:
    hub = _hub()
    angle1 = _mode_number(MultipleDirectionAngle1Number(hub.basic_data, hub.hass), hub)
    angle2 = _mode_number(MultipleDirectionAngle2Number(hub.basic_data, hub.hass), hub)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_MULTIPLE",
            "multiple_mode_config": {"angles": [30, 120]},
        },
    })
    assert angle1.available is True
    assert angle1.native_value == 30.0
    assert angle2.native_value == 120.0

    # setting angle1 preserves the existing angle2, wrapping into [0, 360)
    asyncio.run(angle1.async_set_native_value(400.0))
    topic, command = _published(hub)
    cfg = command["main_direction_angle_config"]
    assert cfg["mode"] == "MAIN_DIRECTION_MODE_MULTIPLE"
    assert cfg["multiple_mode_config"]["angles"] == [40, 120]


# ---------------------------------------------------------------------------
# battery sensors
# ---------------------------------------------------------------------------


def test_battery_sensor_capacity_from_dp8() -> None:
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None

    sensor.set_capacity(json.dumps({"int_value": 73}))
    assert sensor.native_value == 73

    # invalid JSON leaves the last value intact
    sensor.set_capacity("not-json")
    assert sensor.native_value == 73


def test_battery_state_and_temperature_sensors_from_dp108() -> None:
    hub = _hub()
    state = BatteryStateSensor(hub.basic_data, hub.hass)
    temperature = BatteryTemperatureStateSensor(hub.basic_data, hub.hass)
    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_CHARGING",
        "tempreture": "BATTERY_TEMPRETURE_OVERHEAT",
    })
    assert state.native_value == "battery_state_charging"
    assert temperature.native_value == "battery_tempreture_overheat"


# ---------------------------------------------------------------------------
# lifetime statistics sensors (dp_124)
# ---------------------------------------------------------------------------


def test_lifetime_statistics_sensors_from_dp124() -> None:
    hub = _hub()
    total_time = TotalMowingTimeSensor(hub.basic_data, hub.hass)
    total_jobs = TotalMowingJobsSensor(hub.basic_data, hub.hass)
    total_area = TotalMowedAreaSensor(hub.basic_data, hub.hass)
    assert total_time.native_value is None

    _feed(hub.on_statistics_data, {
        "duration": 3600,
        "clean_times": 12,
        "clean_area": 2560,  # 0.1 m^2 units -> 256.0 m^2
    })
    assert total_time.native_value == 3600
    assert total_jobs.native_value == 12
    assert total_area.native_value == 256.0


# ---------------------------------------------------------------------------
# current-session sensors (dp_113)
# ---------------------------------------------------------------------------


def test_current_session_sensors_from_dp113() -> None:
    hub = _hub()
    area = CurrentSessionAreaSensor(hub.basic_data, hub.hass)
    progress = CurrentSessionProgressSensor(hub.basic_data, hub.hass)
    session_time = CurrentSessionTimeSensor(hub.basic_data, hub.hass)
    job_type = CurrentJobTypeSensor(hub.basic_data, hub.hass)

    _feed(hub.on_current_work_data, {
        "clean_area": 2500,   # -> 250.0 m^2
        "total_area": 10000,  # -> progress 25%
        "work_duration": 900,
        "type": "MAP_AREA_TYPE_CLEANING",
        "is_completed": False,
    })
    assert area.native_value == 250.0
    assert progress.native_value == 25.0
    assert session_time.native_value == 900
    assert job_type.native_value == "map_area_type_cleaning"
    assert area.extra_state_attributes["work_type"] == "MAP_AREA_TYPE_CLEANING"


# ---------------------------------------------------------------------------
# maintenance countdown sensors (dp_125 / dp_126)
# ---------------------------------------------------------------------------


def test_remaining_maintenance_time_sensors() -> None:
    hub = _hub()
    blade = RemainingBladeTimeSensor(hub.basic_data, hub.hass)
    base = RemainingBaseStationTimeSensor(hub.basic_data, hub.hass)

    _feed(hub.on_blade_time, {"int_value": 400})
    _feed(hub.on_base_station_time, {"int_value": 200})
    # cycles are 14400 / 43200 minutes respectively
    assert blade.native_value == 14000
    assert base.native_value == 43000


def test_remaining_blade_time_never_negative() -> None:
    hub = _hub()
    blade = RemainingBladeTimeSensor(hub.basic_data, hub.hass)
    _feed(hub.on_blade_time, {"int_value": 999999})
    assert blade.native_value == 0


# ---------------------------------------------------------------------------
# mow height read-back sensor (dp_155)
# ---------------------------------------------------------------------------


def test_mow_height_sensor_from_dp155() -> None:
    hub = _hub()
    sensor = TerraMowMowHeightSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None
    _feed(hub.on_global_params, {"mow_height": {"value": 35}})
    assert sensor.native_value == 35
