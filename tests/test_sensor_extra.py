"""Additional coverage for the sensor platform.

Fills the remaining line/branch gaps left by ``test_sensor_full``: the battery
attribute/enum fallbacks, the current-session attribute skip branches, the
progress sensor's dp_113 hook and zero-area guard, the maintenance-time and
mow-speed empty-attribute paths, the schedule end-time skip, the version
compatibility unique-id / native value / missing-firmware branch, the pose
sensor without a lawn mower, the main-direction unknown-mode path and the
mission enum unknown-value / dp_107 registration branches.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.sensor import (
    SENSORS,
    BatterySensor,
    TerraMowMowSpeedSensor,
    TerraMowPoseSensor,
    TerraMowSensor,
    VersionCompatibilitySensor,
)

_DESCRIPTIONS = {description.key: description for description in SENSORS}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.70", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _sensor(hub: TerraMowHub, key: str) -> TerraMowSensor:
    return TerraMowSensor(hub.basic_data, hub.hass, _DESCRIPTIONS[key])


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


# ---------------------------------------------------------------------------
# battery sensor attributes + enum fallbacks
# ---------------------------------------------------------------------------


def test_battery_sensor_attributes_and_missing_branches() -> None:
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)

    # no dp_108 payload yet -> only the always-present measured-health block
    attrs = sensor.extra_state_attributes
    assert set(attrs) == {"health"}

    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_CHARGING",
        "tempreture": "BATTERY_TEMPRETURE_NORMAL",
        "charger_connected": True,
        "is_switch_on": True,
    })
    attrs = sensor.extra_state_attributes
    assert attrs["state"] == "BATTERY_STATE_CHARGING"
    # firmware typo is normalised on the way out
    assert attrs["temperature"] == "BATTERY_TEMPERATURE_NORMAL"
    assert attrs["charger_connected"] is True

    # lawn mower dropped -> empty attributes
    hub.basic_data.lawn_mower = None
    assert sensor.extra_state_attributes == {}


def test_battery_sensor_attributes_survive_null_tempreture() -> None:
    # A dp_108 payload carrying an explicit null tempreture must not crash the
    # attribute read (None.replace would raise); it falls back to "unknown".
    hub = _hub()
    sensor = BatterySensor(hub.basic_data, hub.hass)
    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_CHARGING",
        "tempreture": None,
        "charger_connected": True,
        "is_switch_on": True,
    })
    attrs = sensor.extra_state_attributes
    assert attrs["temperature"] == "unknown"


def test_battery_state_and_temperature_unknown_values_are_none() -> None:
    hub = _hub()
    state = _sensor(hub, "battery_state")
    temp = _sensor(hub, "battery_temperature_state")
    _feed(hub.on_battery_status, {
        "state": "BATTERY_STATE_ALIEN",
        "tempreture": "BATTERY_TEMPRETURE_ALIEN",
    })
    assert state.native_value is None
    assert temp.native_value is None


# ---------------------------------------------------------------------------
# statistics / current session
# ---------------------------------------------------------------------------


def test_total_mowed_area_none_when_clean_area_missing() -> None:
    hub = _hub()
    sensor = _sensor(hub, "total_mowed_area")
    _feed(hub.on_statistics_data, {"clean_area": None, "duration": 5})
    assert sensor.native_value is None


def test_current_session_area_zero_and_missing() -> None:
    hub = _hub()
    sensor = _sensor(hub, "current_session_area")
    # a just-started session reports 0.0 m^2, not unknown
    _feed(hub.on_current_work_data, {"clean_area": 0})
    assert sensor.native_value == 0.0
    # only a missing field is unknown
    _feed(hub.on_current_work_data, {"total_area": 5})
    assert sensor.native_value is None


def test_current_session_area_attribute_skip_branches() -> None:
    hub = _hub()
    sensor = _sensor(hub, "current_session_area")

    # no dp_113 payload -> falsy current_work_data -> empty dict
    assert sensor.extra_state_attributes == {}

    # data present but every optional attribute is falsy/None -> empty dict
    _feed(hub.on_current_work_data, {
        "clean_area": 50,
        "type": "",
        "total_area": 0,
    })
    assert sensor.extra_state_attributes == {}

    # lawn mower dropped -> empty dict
    hub.basic_data.lawn_mower = None
    assert sensor.extra_state_attributes == {}


def test_current_session_progress_hook_and_zero_area_guard() -> None:
    hub = _hub()
    sensor = _sensor(hub, "current_session_progress")

    # registers the dp_113 callback without raising
    asyncio.run(sensor.async_added_to_hass())
    assert 113 in hub.callbacks

    # dp_113 hook just schedules a state write; must not raise
    asyncio.run(sensor._handle_push_update(""))

    # total_area <= 0 -> progress is None
    _feed(hub.on_current_work_data, {"total_area": 0, "clean_area": 10})
    assert sensor.native_value is None

    # without a lawn mower the registration is skipped
    hub.basic_data.lawn_mower = None
    other = _sensor(hub, "current_session_progress")
    asyncio.run(other.async_added_to_hass())


# ---------------------------------------------------------------------------
# maintenance-time empty branches
# ---------------------------------------------------------------------------


def test_remaining_time_attributes_empty_without_data() -> None:
    hub = _hub()
    blade = _sensor(hub, "remaining_blade_time")
    base = _sensor(hub, "remaining_base_station_time")

    # no dp payloads -> falsy time dicts -> empty attributes
    assert blade.extra_state_attributes == {}
    assert base.extra_state_attributes == {}

    # lawn mower dropped -> empty attributes
    hub.basic_data.lawn_mower = None
    assert blade.extra_state_attributes == {}
    assert base.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# mow speed: repeated unknown value + empty attributes
# ---------------------------------------------------------------------------


def test_mow_speed_repeated_unknown_value_warns_once() -> None:
    hub = _hub()
    sensor = TerraMowMowSpeedSensor(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_TURBO"}})
    # first read records the unknown type, second read hits the "already known"
    # branch and does not re-warn
    assert sensor.native_value is None
    assert sensor._unknown_speed_type == "MOW_SPEED_TYPE_TURBO"
    assert sensor.native_value is None
    assert sensor._unknown_speed_type == "MOW_SPEED_TYPE_TURBO"


def test_mow_speed_attributes_skip_and_empty_branches() -> None:
    hub = _hub()
    sensor = TerraMowMowSpeedSensor(hub.basic_data, hub.hass)

    # no dp_155 payload -> falsy global_params -> empty attributes
    assert sensor.extra_state_attributes == {}

    # global_params present (a known speed) but the optional sub-dicts carry no
    # usable keys, and no unknown speed type was recorded -> empty attributes
    _feed(hub.on_global_params, {
        "mow_speed": {"speed_type": "MOW_SPEED_TYPE_LOW"},
        "mow_spacing": {},
        "edge_cutting_distance": {},
        "blade_disk_speed": {},
    })
    assert sensor.extra_state_attributes == {}

    # lawn mower dropped -> empty attributes
    hub.basic_data.lawn_mower = None
    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# next scheduled start edge branches
# ---------------------------------------------------------------------------


def test_next_scheduled_start_incomplete_time_is_none() -> None:
    hub = _hub()
    sensor = _sensor(hub, "next_scheduled_start")
    # exists but start_time is missing the minute -> None, and end_time missing
    # the minute is skipped from the attributes
    _feed(hub.on_schedule_data, {
        "exist": True,
        "item_id": 1,
        "shift_id": 2,
        "start_time": {"hour": 9},
        "end_time": {"hour": 11},
    })
    assert sensor.native_value is None
    attrs = sensor.extra_state_attributes
    assert attrs["has_schedule"] is True
    assert "end_time" not in attrs


def test_next_scheduled_start_attributes_empty_without_data() -> None:
    hub = _hub()
    sensor = _sensor(hub, "next_scheduled_start")
    # no dp_138 payload -> falsy schedule_data -> empty attributes
    assert sensor.extra_state_attributes == {}
    # lawn mower dropped -> empty attributes
    hub.basic_data.lawn_mower = None
    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# version compatibility sensor
# ---------------------------------------------------------------------------


def test_version_compatibility_unique_id_value_and_missing_firmware() -> None:
    hub = _hub()
    sensor = VersionCompatibilitySensor(hub.basic_data, hub.hass)
    assert sensor.unique_id == "version_compatibility.terramow@192.0.2.70"
    # native_value proxies the basic-data compatibility status
    assert sensor.native_value == hub.basic_data.compatibility_status
    # no firmware info -> attributes omit the firmware.* keys
    hub.basic_data.firmware_version = None
    attrs = sensor.extra_state_attributes
    assert "firmware_overall_version" not in attrs
    assert "plugin_ha_version" in attrs


# ---------------------------------------------------------------------------
# pose sensor without a lawn mower
# ---------------------------------------------------------------------------


def test_pose_sensor_without_lawn_mower_skips_registration() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    sensor = TerraMowPoseSensor(hub.basic_data, hub.hass)
    asyncio.run(sensor.async_added_to_hass())  # must not raise
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# main-direction status: attribute guards + unknown mode
# ---------------------------------------------------------------------------


def test_main_direction_attributes_empty_without_data() -> None:
    hub = _hub()
    sensor = _sensor(hub, "main_direction_status")
    # no global params -> empty attributes
    assert sensor.extra_state_attributes == {}
    # lawn mower dropped -> empty attributes
    hub.basic_data.lawn_mower = None
    assert sensor.extra_state_attributes == {}


def test_main_direction_unknown_mode_uses_raw_name() -> None:
    hub = _hub()
    sensor = _sensor(hub, "main_direction_status")
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MYSTERY"},
    })
    attrs = sensor.extra_state_attributes
    # unrecognised mode: none of the per-mode blocks add keys, and the friendly
    # name falls back to the raw mode string
    assert attrs["mode"] == "MAIN_DIRECTION_MODE_MYSTERY"
    assert attrs["mode_friendly_name"] == "MAIN_DIRECTION_MODE_MYSTERY"
    assert "mode_description" not in attrs


# ---------------------------------------------------------------------------
# dp_107 mission enum sensors
# ---------------------------------------------------------------------------


def test_mission_enum_sensor_registers_dp107_callback() -> None:
    hub = _hub()
    sensor = _sensor(hub, "mission")
    asyncio.run(sensor.async_added_to_hass())
    assert 107 in hub.callbacks

    # without a lawn mower the dp_107 registration is skipped
    hub.basic_data.lawn_mower = None
    other = _sensor(hub, "mission")
    asyncio.run(other.async_added_to_hass())


def test_mission_sensor_unknown_value_is_none() -> None:
    hub = _hub()
    sensor = _sensor(hub, "mission")
    # a raw mission member outside the enum options normalises to None
    hub.mission = "MISSION_UNKNOWN_XYZ"
    assert sensor.native_value is None


def test_back_to_station_reason_without_lawn_mower_is_none() -> None:
    hub = _hub()
    sensor = _sensor(hub, "back_to_station_reason")
    hub.basic_data.lawn_mower = None
    assert sensor.native_value is None
