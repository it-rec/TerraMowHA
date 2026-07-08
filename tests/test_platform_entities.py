"""Coverage for the platform entities not yet exercised elsewhere.

Selects (blade speed, main direction mode, high grass, zones), the
mode-dependent numbers, map sensors, pose/power/back-to-station sensors,
navigation/upgrade binary sensors and the firmware update entity.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.binary_sensor import (
    BINARY_SENSORS,
    TerraMowBinarySensor,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.map_sensor import (
    TerraMowCleanModeSensor,
    TerraMowMapAreaSensor,
    TerraMowMapStatusSensor,
)
from custom_components.terramow.number import MainDirectionSingleAngleNumber
from custom_components.terramow.select import (
    BladeSpeedSelect,
    HighGrassEdgeTrimModeSelect,
    MainDirectionModeSelect,
    TerraMowZoneSelect,
)
from custom_components.terramow.sensor import (
    SENSORS,
    BatterySensor,
    TerraMowMowSpeedSensor,
    TerraMowPoseSensor,
    TerraMowSensor,
)
from custom_components.terramow.update import TerraMowFirmwareUpdate

_SENSOR_DESCRIPTIONS = {description.key: description for description in SENSORS}
_BINARY_DESCRIPTIONS = {
    description.key: description for description in BINARY_SENSORS
}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _sensor(hub: TerraMowHub, key: str) -> TerraMowSensor:
    return TerraMowSensor(hub.basic_data, hub.hass, _SENSOR_DESCRIPTIONS[key])


def _binary(hub: TerraMowHub, key: str) -> TerraMowBinarySensor:
    return TerraMowBinarySensor(hub.basic_data, hub.hass, _BINARY_DESCRIPTIONS[key])


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# blade speed select
# ---------------------------------------------------------------------------


def test_blade_speed_select_read_path() -> None:
    hub = _hub()
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    # default before any device data
    assert select.current_option == "blade_disk_speed_type_medium"

    _feed(hub.on_global_params, {"blade_disk_speed": {"speed_type": "BLADE_DISK_SPEED_TYPE_HIGH"}})
    assert select.current_option == "blade_disk_speed_type_high"
    assert select.options == [
        "blade_disk_speed_type_low",
        "blade_disk_speed_type_medium",
        "blade_disk_speed_type_high",
    ]


def test_blade_speed_select_write_path() -> None:
    hub = _hub()
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("blade_disk_speed_type_low"))

    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"blade_disk_speed": {"speed_type": "BLADE_DISK_SPEED_TYPE_LOW"}}

    hub.mqtt_client.publish.reset_mock()
    asyncio.run(select.async_select_option("ludicrous_speed"))
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# main direction mode select
# ---------------------------------------------------------------------------


def test_main_direction_mode_select_tracks_device_mode() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })
    assert select.current_option == "main_direction_mode_multiple"


# ---------------------------------------------------------------------------
# high grass edge trim mode select
# ---------------------------------------------------------------------------


def test_high_grass_select_reads_map_info() -> None:
    hub = _hub()
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    assert select.current_option is None

    hub._update_map_info({
        "mow_param": {"high_grass_edge_trim_mode": {"mode": "HIGH_GRASS_EDGE_TRIM_INTENSIVE"}},
    })
    assert select.current_option == "high_grass_edge_trim_intensive"


def test_high_grass_select_write_path() -> None:
    hub = _hub()
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("high_grass_edge_trim_standard"))

    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"high_grass_edge_trim_mode": {"mode": "HIGH_GRASS_EDGE_TRIM_STANDARD"}}


# ---------------------------------------------------------------------------
# zone select
# ---------------------------------------------------------------------------

MAP_INFO_WITH_ZONES = {
    "id": 1,
    "regions": [
        {
            "id": 100,
            "name": "Hauptfläche",
            "sub_regions": [
                {"id": 7, "name": "Rasen vorne"},
                {"id": 8, "name": ""},
            ],
        },
    ],
}


def test_zone_select_builds_options_from_map_info() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    assert select.options == ["no_zones_available"]

    asyncio.run(select._on_map_info(MAP_INFO_WITH_ZONES))

    assert select.options == [
        "all_zones",
        "Rasen vorne (ID: 7)",
        "Sub-zone 8 (ID: 8)",
    ]
    assert select.current_option == "all_zones"


def test_zone_select_starts_zone_clean() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select._on_map_info(MAP_INFO_WITH_ZONES))

    asyncio.run(select.async_select_option("Rasen vorne (ID: 7)"))

    topic, command = _published(hub)
    assert topic == "data_point/103/app"
    assert command["mode"] == "START_MODE_SELECT_REGION_CLEAN"
    assert command["select_region_clean"] == {"region_ids": [7]}
    assert select.current_option == "Rasen vorne (ID: 7)"


def test_zone_select_special_options_do_not_publish() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select._on_map_info(MAP_INFO_WITH_ZONES))

    asyncio.run(select.async_select_option("all_zones"))
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# main direction single angle number (mode-dependent availability)
# ---------------------------------------------------------------------------


def _single_angle_number(hub) -> MainDirectionSingleAngleNumber:
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    # no mode-selector entity in these tests -> fall back to device data
    hub.hass.states.get = MagicMock(return_value=None)
    return number


def test_single_angle_number_reads_angle_in_single_mode() -> None:
    hub = _hub()
    number = _single_angle_number(hub)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_SINGLE",
            "single_mode_config": {"angle": 42},
        },
    })
    assert number.available is True
    assert number.native_value == 42.0


def test_single_angle_number_unavailable_in_multiple_mode() -> None:
    hub = _hub()
    number = _single_angle_number(hub)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })
    assert number.available is False
    assert number.native_value is None


def test_single_angle_number_write_wraps_angle() -> None:
    hub = _hub()
    number = _single_angle_number(hub)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_SINGLE",
            "single_mode_config": {"angle": 0},
        },
    })

    asyncio.run(number.async_set_native_value(370.0))

    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command["main_direction_angle_config"]["single_mode_config"]["angle"] == 10


# ---------------------------------------------------------------------------
# map sensors
# ---------------------------------------------------------------------------


def test_map_status_sensor_from_dp117() -> None:
    hub = _hub()
    sensor = TerraMowMapStatusSensor(hub.basic_data, hub.hass)
    _feed(hub.on_map_status, {
        "map_state": "MAP_STATE_COMPLETE",
        "is_map_detected": True,
        "map_id": 3,
    })
    assert sensor.native_value == "map_state_complete"
    attrs = sensor.extra_state_attributes
    assert attrs["is_map_detected"] is True
    assert attrs["map_id"] == 3


def test_map_area_sensor_converts_units() -> None:
    hub = _hub()
    sensor = TerraMowMapAreaSensor(hub.basic_data, hub.hass)
    asyncio.run(sensor._on_map_info({"total_area": 2560}))
    assert sensor.native_value == 256.0


def test_clean_mode_sensor_reports_selected_regions() -> None:
    hub = _hub()
    sensor = TerraMowCleanModeSensor(hub.basic_data, hub.hass)
    asyncio.run(sensor._on_map_info({
        "clean_info": {
            "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
            "select_region": {"region_id": [1, 2]},
        },
    }))
    assert sensor.native_value == "map_clean_info_mode_select_region"
    assert sensor.extra_state_attributes["selected_regions"] == [1, 2]


# ---------------------------------------------------------------------------
# pose / power mode / back-to-station / mow speed / battery attributes
# ---------------------------------------------------------------------------


def test_pose_sensor_reports_yaw_and_attributes() -> None:
    hub = _hub()
    sensor = TerraMowPoseSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None

    asyncio.run(sensor._on_pose({"x": 1.2, "y": 3.4, "yaw": 90.5, "frame": 8}))
    assert sensor.native_value == 90.5
    assert sensor.extra_state_attributes["x"] == 1.2
    assert sensor.extra_state_attributes["frame"] == 8


def test_power_mode_sensor_from_dp107() -> None:
    hub = _hub()
    sensor = _sensor(hub, "power_mode")
    _feed(hub.on_mission_status, {"power_mode": "POWER_MODE_STANDBY"})
    assert sensor.native_value == "power_mode_standby"


def test_back_to_station_reason_sensor_from_dp107() -> None:
    hub = _hub()
    sensor = _sensor(hub, "back_to_station_reason")
    _feed(hub.on_mission_status, {
        "back_to_station_reason": "BACK_TO_STATION_REASON_LOW_BATTERY",
    })
    assert sensor.native_value == "back_to_station_reason_low_battery"


def test_mow_speed_sensor_from_dp155() -> None:
    hub = _hub()
    sensor = TerraMowMowSpeedSensor(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_LOW"}})
    assert sensor.native_value == "mow_speed_type_low"


def test_battery_sensor_attributes_fix_temperature_typo() -> None:
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)
    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_CHARGED",
        "tempreture": "BATTERY_TEMPRETURE_NORMAL",
        "charger_connected": True,
        "is_switch_on": True,
    })
    attrs = sensor.extra_state_attributes
    # the firmware typo is normalised for display
    assert attrs["temperature"] == "BATTERY_TEMPERATURE_NORMAL"
    assert attrs["charger_connected"] is True


# ---------------------------------------------------------------------------
# binary sensors from dp_107 flags
# ---------------------------------------------------------------------------


def test_navigation_and_upgrade_binary_sensors() -> None:
    hub = _hub()
    located = _binary(hub, "navigation_located")
    upgrading = _binary(hub, "firmware_upgrading")

    _feed(hub.on_mission_status, {
        "is_robot_navi_located": True,
        "is_upgrading": False,
    })
    assert located.is_on is True
    assert upgrading.is_on is False


# ---------------------------------------------------------------------------
# firmware update entity
# ---------------------------------------------------------------------------


def test_update_entity_reports_firmware_version() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    assert update.installed_version is None

    # dp_127 compatibility number is only a fallback until dp_102 arrives
    _feed(hub.on_compatibility_info, {"overall": 26, "module": {"home_assistant": 3}})
    assert update.installed_version == "26.3"

    # dp_102 carries the real app version and takes precedence
    _feed(hub.on_device_info, {"version": "9.9.210", "sn": "X"})
    assert update.installed_version == "9.9.210"
    # updates run through the TerraMow app, so HA must not offer one
    assert update.latest_version == update.installed_version


def test_update_entity_in_progress_from_is_upgrading() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    assert update.in_progress is False
    _feed(hub.on_mission_status, {"is_upgrading": True})
    assert update.in_progress is True


def test_update_entity_exposes_component_versions() -> None:
    hub = _hub()
    update = TerraMowFirmwareUpdate(hub.basic_data, hub.hass)
    assert update.extra_state_attributes == {}
    _feed(hub.on_component_versions, {"ap_app": "9.9.210", "main_controller": "09.09.210"})
    assert update.extra_state_attributes["component_versions"]["ap_app"] == "9.9.210"
