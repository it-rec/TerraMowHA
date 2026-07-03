"""Tests for the enum conversion helpers in const.py."""

from custom_components.terramow.const import to_device_enum, to_ha_enum_state


def test_to_ha_enum_state_lowercases_device_enums() -> None:
    assert to_ha_enum_state("MISSION_IDLE") == "mission_idle"
    assert to_ha_enum_state("BATTERY_STATE_DISCHARGE") == "battery_state_discharge"


def test_to_ha_enum_state_handles_empty_and_non_string() -> None:
    assert to_ha_enum_state("") is None
    assert to_ha_enum_state(None) is None
    assert to_ha_enum_state(42) is None


def test_to_device_enum_uppercases_ha_options() -> None:
    assert to_device_enum("mow_speed_type_auto") == "MOW_SPEED_TYPE_AUTO"


def test_round_trip_is_stable() -> None:
    for value in (
        "MISSION_SCHEDULE_BUILD_MAP_AND_CLEAN",
        "MAIN_DIRECTION_MODE_AUTO_ROTATE",
        "HIGH_GRASS_EDGE_TRIM_INTENSIVE",
    ):
        assert to_device_enum(to_ha_enum_state(value)) == value


def test_to_device_enum_handles_empty_and_non_string() -> None:
    assert to_device_enum("") is None
    assert to_device_enum(None) is None
