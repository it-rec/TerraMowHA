"""Residual branch/line coverage for the number and select platforms.

Fills the gaps left by test_number_full.py / test_select_full.py: the
empty-global-params return paths, the mode-change listener host/new_mode
branches, every extra_state_attributes short-circuit, the equal-angle
warnings, plus the select platform's zone-parse errors, mow/blade speed
edge cases, the device-confirmation listener, the delayed related-entity
refresh and the high-grass edge-trim selector.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import DOMAIN, TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow import select as select_mod
from custom_components.terramow.const import (
    MOW_SPEED_TYPE_AUTO,
)
from custom_components.terramow.number import (
    EdgeCuttingDistanceNumber,
    MainDirectionAutoRotateIntervalNumber,
    MainDirectionSingleAngleNumber,
    MowingSpacingNumber,
    MultipleDirectionAngle1Number,
    MultipleDirectionAngle2Number,
)
from custom_components.terramow.select import (
    BladeSpeedSelect,
    HighGrassEdgeTrimModeSelect,
    MainDirectionModeSelect,
    MowSpeedSelect,
    TerraMowZoneSelect,
)


def _hub(states_get=None) -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.61", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.hass.states.get = states_get or MagicMock(return_value=None)
    return hub


def _shub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.86", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.hass.async_create_task = MagicMock(
        side_effect=lambda c: c.close() if hasattr(c, "close") else None
    )
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _state(value: str):
    return MagicMock(return_value=SimpleNamespace(state=value))


# ---------------------------------------------------------------------------
# number.py: empty-global-params return paths
# ---------------------------------------------------------------------------


def test_number_native_value_none_with_empty_global_params() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {})  # present but falsy dict
    for cls in (EdgeCuttingDistanceNumber, MowingSpacingNumber):
        number = cls(hub.basic_data, hub.hass)
        assert number.native_value is None


def test_mowing_spacing_attrs_without_current_when_params_present() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {"mow_spacing": {"value": 100}})
    number = MowingSpacingNumber(hub.basic_data, hub.hass)
    attrs = number.extra_state_attributes
    # params present but no current_mow_spacing reported by the device
    assert "current_mow_spacing" not in attrs
    assert attrs["valid_range"].startswith("80-140")


# ---------------------------------------------------------------------------
# number.py: mode-change listener host / new_mode branches
# ---------------------------------------------------------------------------


def test_single_angle_listener_without_new_mode_still_writes() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    number.async_write_ha_state = MagicMock()
    number._cached_mode = "sentinel"

    _event_name, callback = hub.hass.bus.async_listen.call_args.args
    # matching host but no new_mode -> cache untouched, state still written
    asyncio.run(callback(SimpleNamespace(data={"device_host": number.host})))
    assert number._cached_mode == "sentinel"
    number.async_write_ha_state.assert_called_once()


_MODE_CLASSES = (
    (MainDirectionAutoRotateIntervalNumber, "MAIN_DIRECTION_MODE_AUTO_ROTATE"),
    (MultipleDirectionAngle1Number, "MAIN_DIRECTION_MODE_MULTIPLE"),
    (MultipleDirectionAngle2Number, "MAIN_DIRECTION_MODE_MULTIPLE"),
)


def test_mode_number_listener_host_mismatch_and_missing_new_mode() -> None:
    for cls, _mode in _MODE_CLASSES:
        hub = _hub()
        number = cls(hub.basic_data, hub.hass)
        number.async_write_ha_state = MagicMock()
        _event_name, callback = hub.hass.bus.async_listen.call_args.args

        # a different host is ignored (callback exits, no write)
        asyncio.run(callback(SimpleNamespace(data={"device_host": "other", "new_mode": "x"})))
        number.async_write_ha_state.assert_not_called()

        # matching host without new_mode -> writes but keeps the cache
        number._cached_mode = "keep"
        asyncio.run(callback(SimpleNamespace(data={"device_host": number.host})))
        assert number._cached_mode == "keep"
        number.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# number.py: available / native_value with empty params
# ---------------------------------------------------------------------------


def test_single_angle_available_and_value_with_empty_params() -> None:
    # device fallback with empty params -> unavailable
    hub = _hub()
    _feed(hub.on_global_params, {})
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    assert number.available is False

    # available via the selector but empty params -> no value
    hub2 = _hub(states_get=_state("MAIN_DIRECTION_MODE_SINGLE"))
    _feed(hub2.on_global_params, {})
    number2 = MainDirectionSingleAngleNumber(hub2.basic_data, hub2.hass)
    assert number2.available is True
    assert number2.native_value is None


def test_mode_numbers_available_false_and_value_none_with_empty_params() -> None:
    for cls, mode in _MODE_CLASSES:
        hub = _hub()
        _feed(hub.on_global_params, {})
        number = cls(hub.basic_data, hub.hass)
        assert number.available is False

        hub2 = _hub(states_get=_state(mode))
        _feed(hub2.on_global_params, {})
        number2 = cls(hub2.basic_data, hub2.hass)
        assert number2.available is True
        assert number2.native_value is None


# ---------------------------------------------------------------------------
# number.py: extra_state_attributes short-circuits
# ---------------------------------------------------------------------------


def test_single_angle_attributes_short_circuits() -> None:
    # no lawn_mower
    hub = _hub()
    hub.basic_data.lawn_mower = None
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    assert "current_robot_angle" not in number.extra_state_attributes

    # lawn_mower present but empty params
    hub2 = _hub()
    _feed(hub2.on_global_params, {})
    number2 = MainDirectionSingleAngleNumber(hub2.basic_data, hub2.hass)
    assert "current_robot_angle" not in number2.extra_state_attributes

    # params present but no current_angle reported
    hub3 = _hub()
    _feed(hub3.on_global_params, {"main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"}})
    number3 = MainDirectionSingleAngleNumber(hub3.basic_data, hub3.hass)
    assert "current_robot_angle" not in number3.extra_state_attributes


def test_auto_rotate_attributes_short_circuits() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    number = MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass)
    assert "current_robot_angle" not in number.extra_state_attributes

    hub2 = _hub()
    _feed(hub2.on_global_params, {})
    number2 = MainDirectionAutoRotateIntervalNumber(hub2.basic_data, hub2.hass)
    assert "current_robot_angle" not in number2.extra_state_attributes

    hub3 = _hub()
    _feed(hub3.on_global_params, {"main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE"}})
    number3 = MainDirectionAutoRotateIntervalNumber(hub3.basic_data, hub3.hass)
    assert "current_robot_angle" not in number3.extra_state_attributes


def test_multiple_angle1_attributes_short_circuits() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    number = MultipleDirectionAngle1Number(hub.basic_data, hub.hass)
    assert "paired_angle2" not in number.extra_state_attributes

    hub2 = _hub()
    _feed(hub2.on_global_params, {})
    number2 = MultipleDirectionAngle1Number(hub2.basic_data, hub2.hass)
    assert "paired_angle2" not in number2.extra_state_attributes

    # config with no current_angle and a single-element angles list
    hub3 = _hub()
    _feed(hub3.on_global_params, {
        "main_direction_angle_config": {"multiple_mode_config": {"angles": [30]}},
    })
    number3 = MultipleDirectionAngle1Number(hub3.basic_data, hub3.hass)
    attrs = number3.extra_state_attributes
    assert "current_robot_angle" not in attrs
    assert "paired_angle2" not in attrs


def test_multiple_angle2_attributes_short_circuits() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    number = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    assert "paired_angle1" not in number.extra_state_attributes

    hub2 = _hub()
    _feed(hub2.on_global_params, {})
    number2 = MultipleDirectionAngle2Number(hub2.basic_data, hub2.hass)
    assert "paired_angle1" not in number2.extra_state_attributes

    # no current_angle, empty angles list
    hub3 = _hub()
    _feed(hub3.on_global_params, {
        "main_direction_angle_config": {"multiple_mode_config": {"angles": []}},
    })
    number3 = MultipleDirectionAngle2Number(hub3.basic_data, hub3.hass)
    attrs3 = number3.extra_state_attributes
    assert "current_robot_angle" not in attrs3
    assert "paired_angle1" not in attrs3

    # single-element angles list -> paired_angle1 set but no difference
    hub4 = _hub()
    _feed(hub4.on_global_params, {
        "main_direction_angle_config": {
            "current_angle": 5,
            "multiple_mode_config": {"angles": [42]},
        },
    })
    number4 = MultipleDirectionAngle2Number(hub4.basic_data, hub4.hass)
    attrs4 = number4.extra_state_attributes
    assert attrs4["paired_angle1"] == 42
    assert "angle_difference" not in attrs4


# ---------------------------------------------------------------------------
# number.py: equal-angle warning write paths
# ---------------------------------------------------------------------------


def test_multiple_angle1_write_warns_when_equal_to_angle2() -> None:
    hub = _hub(states_get=_state("MAIN_DIRECTION_MODE_MULTIPLE"))
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"multiple_mode_config": {"angles": [30, 90]}},
    })
    number = MultipleDirectionAngle1Number(hub.basic_data, hub.hass)
    # set angle1 equal to the existing angle2 (90) -> warning branch, still publishes
    asyncio.run(number.async_set_native_value(90.0))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    angles = json.loads(payload)["main_direction_angle_config"]["multiple_mode_config"]["angles"]
    assert angles == [90, 90]


def test_multiple_angle2_write_warns_when_equal_to_angle1() -> None:
    hub = _hub(states_get=_state("MAIN_DIRECTION_MODE_MULTIPLE"))
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"multiple_mode_config": {"angles": [45, 200]}},
    })
    number = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    # set angle2 equal to the existing angle1 (45) -> warning branch, still publishes
    asyncio.run(number.async_set_native_value(45.0))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    angles = json.loads(payload)["main_direction_angle_config"]["multiple_mode_config"]["angles"]
    assert angles == [45, 45]


# ---------------------------------------------------------------------------
# select.py: zone selector edge cases
# ---------------------------------------------------------------------------


def test_zone_select_init_without_lawn_mower_skips_callback() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    assert select.options == ["no_zones_available"]


def test_zone_select_invalid_option_warns() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("does_not_exist"))
    hub.mqtt_client.publish.assert_not_called()


def test_zone_select_option_without_id_and_parse_error() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    # option in options but lacking the "(ID: n)" suffix -> else warning
    select._options = ["weird_zone"]
    asyncio.run(select.async_select_option("weird_zone"))
    hub.mqtt_client.publish.assert_not_called()

    # option with a non-integer id -> ValueError swallowed
    select._options = ["Bad (ID: NaN)"]
    asyncio.run(select.async_select_option("Bad (ID: NaN)"))
    hub.mqtt_client.publish.assert_not_called()


def test_zone_select_start_clean_without_lawn_mower() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    select._options = ["Front (ID: 5)"]
    hub.basic_data.lawn_mower = None
    asyncio.run(select.async_select_option("Front (ID: 5)"))
    hub.mqtt_client.publish.assert_not_called()


def test_zone_select_update_options_empty_map_info() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select._on_map_info({}))
    assert select.options == ["no_zones_available"]
    assert select.current_option == "no_zones_available"
    # empty map info -> no attributes
    assert select.extra_state_attributes == {}


def test_zone_select_keeps_valid_current_option() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    map_info = {"id": 1, "regions": [{"id": 1, "sub_regions": [{"id": 7, "name": "A"}]}]}
    asyncio.run(select._on_map_info(map_info))
    assert select.current_option == "all_zones"
    # a second identical update keeps the already-valid current option
    asyncio.run(select._on_map_info(map_info))
    assert select.current_option == "all_zones"


def test_zone_select_attrs_without_region_clean() -> None:
    hub = _shub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select._on_map_info({
        "id": 3,
        "regions": [{"id": 1, "sub_regions": [{"id": 7, "name": "A"}]}],
        "clean_info": {"mode": "MAP_CLEAN_INFO_MODE_GLOBAL"},
    }))
    attrs = select.extra_state_attributes
    assert attrs["map_id"] == 3
    # clean mode is not select-region -> no selected zones reported
    assert "currently_selected_zones" not in attrs


# ---------------------------------------------------------------------------
# select.py: mow speed edge cases
# ---------------------------------------------------------------------------


def test_mow_speed_device_speed_type_none_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    # no firmware auto support and no device value -> AUTO not exposed
    assert len(select.options) == 3


def test_mow_speed_device_speed_type_none_when_not_string() -> None:
    hub = _shub()
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": 123}})
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    # a non-string device speed_type is ignored -> AUTO stays hidden
    assert len(select.options) == 3


def test_mow_speed_repeated_unknown_speed_type_logs_once() -> None:
    hub = _shub()
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_WEIRD"}})
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    assert select.current_option is None
    assert select._unknown_speed_type == "MOW_SPEED_TYPE_WEIRD"
    # a repeated read of the same unknown value takes the already-warned path
    assert select.current_option is None


def test_mow_speed_select_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("mow_speed_type_low"))
    hub.mqtt_client.publish.assert_not_called()


def test_mow_speed_attributes_include_auto_when_supported() -> None:
    hub = _shub()
    hub.basic_data.firmware_version = {"module": {"mow_speed": 3}}
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    attrs = select.extra_state_attributes
    assert attrs["auto_speed_supported"] is True
    assert MOW_SPEED_TYPE_AUTO in attrs["available_speeds"]


# ---------------------------------------------------------------------------
# select.py: blade speed edge cases
# ---------------------------------------------------------------------------


def test_blade_speed_current_option_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    assert select.current_option == "blade_disk_speed_type_medium"


def test_blade_speed_current_option_ignores_invalid_device_value() -> None:
    hub = _shub()
    _feed(hub.on_global_params, {"blade_disk_speed": {"speed_type": "BOGUS"}})
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    # an unrecognised device value keeps the cached default
    assert select.current_option == "blade_disk_speed_type_medium"


def test_blade_speed_select_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("blade_disk_speed_type_low"))
    hub.mqtt_client.publish.assert_not_called()


def test_blade_speed_extra_state_attributes() -> None:
    hub = _shub()
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    assert "BLADE_DISK_SPEED_TYPE_HIGH" in select.extra_state_attributes["available_speeds"]


# ---------------------------------------------------------------------------
# select.py: main direction mode select
# ---------------------------------------------------------------------------


def test_mode_select_device_confirmation_listener() -> None:
    hub = _shub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    _event_name, callback = hub.hass.bus.async_listen.call_args.args

    # matching host + confirmed_mode clears the pending mode
    select._pending_mode = "MAIN_DIRECTION_MODE_MULTIPLE"
    asyncio.run(callback(SimpleNamespace(data={
        "device_host": select.host,
        "confirmed_mode": "MAIN_DIRECTION_MODE_MULTIPLE",
    })))
    assert select._pending_mode is None

    # a different host is ignored
    select._pending_mode = "MAIN_DIRECTION_MODE_SINGLE"
    asyncio.run(callback(SimpleNamespace(data={"device_host": "other", "confirmed_mode": "x"})))
    assert select._pending_mode == "MAIN_DIRECTION_MODE_SINGLE"

    # matching host but no confirmed_mode is a no-op
    asyncio.run(callback(SimpleNamespace(data={"device_host": select.host})))
    assert select._pending_mode == "MAIN_DIRECTION_MODE_SINGLE"


def test_mode_select_effective_mode_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select._pending_mode = None
    select._current_option = "MAIN_DIRECTION_MODE_MULTIPLE"
    assert select.get_effective_mode() == "MAIN_DIRECTION_MODE_MULTIPLE"


def test_mode_select_effective_mode_ignores_invalid_device_mode() -> None:
    hub = _shub()
    _feed(hub.on_global_params, {"main_direction_angle_config": {"mode": "BOGUS_MODE"}})
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select._pending_mode = None
    select._current_option = "MAIN_DIRECTION_MODE_SINGLE"
    # an unknown device mode is rejected -> falls back to current_option
    assert select.get_effective_mode() == "MAIN_DIRECTION_MODE_SINGLE"


def test_mode_select_options_are_lowercase_tokens() -> None:
    hub = _shub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    assert "main_direction_mode_single" in select.options


def test_mode_select_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("main_direction_mode_single"))
    hub.mqtt_client.publish.assert_not_called()


def test_mode_select_unknown_mode_publishes_bare_config() -> None:
    hub = _shub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    # an allowed option that matches none of the per-mode config branches
    select._attr_options = list(select._attr_options) + ["MAIN_DIRECTION_MODE_EXTRA"]
    asyncio.run(select.async_select_option("main_direction_mode_extra"))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    cfg = json.loads(payload)["main_direction_angle_config"]
    assert cfg == {"mode": "MAIN_DIRECTION_MODE_EXTRA"}


def test_mode_select_delayed_update_invokes_force_update() -> None:
    hub = _shub()
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    hub.hass.states.get = MagicMock(return_value=None)  # no related entities exist
    collected: list = []
    hub.hass.async_create_task = MagicMock(side_effect=collected.append)

    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select._notify_angle_controllers_mode_change("A", "B")
    assert hub.hass.bus.fire.called
    assert collected
    # run the scheduled delayed_update coroutine -> executes the executor job
    for coro in collected:
        asyncio.run(coro)
    hub.hass.async_add_executor_job.assert_called_once()


def test_mode_select_force_update_swallows_entity_error(monkeypatch) -> None:
    hub = _shub()
    hub.hass.states.get = MagicMock(return_value=SimpleNamespace(state="1"))
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)

    def _boom(*_a, **_k):
        raise RuntimeError("nope")

    monkeypatch.setattr(select_mod.entity_component, "async_update_entity", _boom)
    # the per-entity update failure is caught at debug level, not re-raised
    select._force_update_related_entities()


def test_mode_select_timeout_noop_without_pending(monkeypatch) -> None:
    hub = _shub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    select._pending_mode = None

    async def _instant(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _instant)
    asyncio.run(select._clear_pending_mode_after_timeout())
    select.async_write_ha_state.assert_not_called()


def test_mode_select_device_confirmed_ignored_without_pending() -> None:
    hub = _shub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select._pending_mode = None
    before = select._current_option
    select.on_device_mode_confirmed("MAIN_DIRECTION_MODE_MULTIPLE")
    assert select._pending_mode is None
    assert select._current_option == before


def test_mode_select_attrs_short_circuits() -> None:
    # no lawn_mower -> only the static status is present
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select._pending_mode = None
    attrs = select.extra_state_attributes
    assert attrs["status"] == "active"
    assert "current_angle" not in attrs

    # params with no current_angle and an unrecognised mode
    hub2 = _shub()
    _feed(hub2.on_global_params, {"main_direction_angle_config": {"mode": "SOMETHING_ELSE"}})
    select2 = MainDirectionModeSelect(hub2.basic_data, hub2.hass)
    select2._pending_mode = None
    attrs2 = select2.extra_state_attributes
    assert "current_angle" not in attrs2
    assert "single_angle" not in attrs2
    assert "multiple_angles" not in attrs2
    assert "auto_rotate_interval" not in attrs2


# ---------------------------------------------------------------------------
# select.py: high grass edge trim mode select
# ---------------------------------------------------------------------------


def test_high_grass_options_are_lowercase_tokens() -> None:
    hub = _shub()
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    assert len(select.options) == 2
    assert "high_grass_edge_trim_standard" in select.options


def test_high_grass_current_option_none_paths() -> None:
    # no lawn_mower -> mow_param unavailable
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    assert select.current_option is None

    # mow_param present but not a dict
    hub2 = _shub()
    hub2._map_info = {"mow_param": "not-a-dict"}
    select2 = HighGrassEdgeTrimModeSelect(hub2.basic_data, hub2.hass)
    assert select2.current_option is None

    # trim config present but not a dict
    hub3 = _shub()
    hub3._map_info = {"mow_param": {"high_grass_edge_trim_mode": "nope"}}
    select3 = HighGrassEdgeTrimModeSelect(hub3.basic_data, hub3.hass)
    assert select3.current_option is None

    # trim mode is an unknown enum value
    hub4 = _shub()
    hub4._map_info = {"mow_param": {"high_grass_edge_trim_mode": {"mode": "UNKNOWN"}}}
    select4 = HighGrassEdgeTrimModeSelect(hub4.basic_data, hub4.hass)
    assert select4.current_option is None


def test_high_grass_invalid_option() -> None:
    hub = _shub()
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("high_grass_edge_trim_bogus"))
    hub.mqtt_client.publish.assert_not_called()


def test_high_grass_select_without_lawn_mower() -> None:
    hub = _shub()
    hub.basic_data.lawn_mower = None
    select = HighGrassEdgeTrimModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("high_grass_edge_trim_standard"))
    hub.mqtt_client.publish.assert_not_called()
