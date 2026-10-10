"""Thorough coverage for the number platform.

Covers async_setup_entry, the lawn-mower-missing / no-global-params branches,
the mode availability chain (event cache, device-data fallback, connection
guard), the mode-change event listener and each entity's
extra_state_attributes.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import DOMAIN, TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import (
    EdgeCuttingDistanceNumber,
    MainDirectionAutoRotateIntervalNumber,
    MainDirectionSingleAngleNumber,
    MowingHeightNumber,
    MowingSpacingNumber,
    MultipleDirectionAngle1Number,
    MultipleDirectionAngle2Number,
    async_setup_entry,
)


def _hub(states_get=None) -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.60", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.hass.states.get = states_get or MagicMock(return_value=None)
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _state(value: str):
    return MagicMock(return_value=SimpleNamespace(state=value))


# ---------------------------------------------------------------------------
# platform setup
# ---------------------------------------------------------------------------


def test_async_setup_entry_creates_all_numbers() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert len(added) == 9


# ---------------------------------------------------------------------------
# lawn-mower-missing / empty-params branches
# ---------------------------------------------------------------------------


def test_mowing_numbers_return_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    for cls in (MowingHeightNumber, EdgeCuttingDistanceNumber, MowingSpacingNumber):
        number = cls(hub.basic_data, hub.hass)
        assert number.native_value is None
        # setting a value logs an error and does not publish
        asyncio.run(number.async_set_native_value(50.0))
    hub.mqtt_client.publish.assert_not_called()


def test_mowing_numbers_return_none_with_empty_params() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {})  # global params present but empty dict is falsy
    number = MowingHeightNumber(hub.basic_data, hub.hass)
    assert number.native_value is None


def test_mowing_spacing_attributes_without_current_value() -> None:
    hub = _hub()
    number = MowingSpacingNumber(hub.basic_data, hub.hass)
    # no lawn_mower data yet -> attrs carry the static hints only
    hub.basic_data.lawn_mower = None
    attrs = number.extra_state_attributes
    assert "valid_range" in attrs
    assert "current_mow_spacing" not in attrs


# ---------------------------------------------------------------------------
# mode availability chain
# ---------------------------------------------------------------------------


def test_single_angle_available_from_cached_mode() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    number._cached_mode = "MAIN_DIRECTION_MODE_SINGLE"
    assert number.available is True

    hub2 = _hub()
    number2 = MainDirectionSingleAngleNumber(hub2.basic_data, hub2.hass)
    number2._cached_mode = "MAIN_DIRECTION_MODE_MULTIPLE"
    assert number2.available is False


def test_availability_follows_device_reported_mode() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"},
    })
    assert number.available is True

    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })
    assert number.available is False


def test_cached_mode_takes_priority_until_device_push() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_MULTIPLE"},
    })
    number._cached_mode = "MAIN_DIRECTION_MODE_SINGLE"
    assert number._current_main_direction_mode() == "MAIN_DIRECTION_MODE_SINGLE"
    # the cache survives reads (availability is evaluated repeatedly per write)
    assert number._cached_mode == "MAIN_DIRECTION_MODE_SINGLE"

    # a dp_155 push makes the device data authoritative again
    number.entity_id = "number.terramow_test"
    number.async_write_ha_state = MagicMock()
    asyncio.run(number._handle_push_update("{}"))
    assert number._cached_mode is None
    assert number._current_main_direction_mode() == "MAIN_DIRECTION_MODE_MULTIPLE"


def test_mode_change_listener_updates_cache() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    number.entity_id = "number.terramow_test"
    number.async_write_ha_state = MagicMock()

    # the listener is registered when the entity is added to hass
    number._register_mode_change_listener()
    _event_name, callback = hub.hass.bus.async_listen.call_args.args
    asyncio.run(callback(SimpleNamespace(data={
        "device_host": number.host,
        "new_mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
    })))
    assert number._cached_mode == "MAIN_DIRECTION_MODE_AUTO_ROTATE"
    number.async_write_ha_state.assert_called_once()

    # an event for a different host is ignored
    number._cached_mode = None
    asyncio.run(callback(SimpleNamespace(data={"device_host": "other", "new_mode": "x"})))
    assert number._cached_mode is None


# ---------------------------------------------------------------------------
# mode-dependent numbers: unavailable branches + attributes
# ---------------------------------------------------------------------------


def _device_mode(hub, mode: str) -> None:
    hub.hass.states.get = MagicMock(return_value=None)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": mode,
            "current_angle": 33,
            "single_mode_config": {"angle": 10},
            "auto_rotate_mode_config": {"angle_interval": 20},
            "multiple_mode_config": {"angles": [30, 120]},
        },
    })


def test_numbers_unavailable_in_wrong_mode_do_not_publish() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_SINGLE")
    for cls in (
        MainDirectionAutoRotateIntervalNumber,
        MultipleDirectionAngle1Number,
        MultipleDirectionAngle2Number,
    ):
        number = cls(hub.basic_data, hub.hass)
        assert number.available is False
        assert number.native_value is None
        asyncio.run(number.async_set_native_value(15.0))
    hub.mqtt_client.publish.assert_not_called()


def test_mode_numbers_expose_current_angle_attributes() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_SINGLE")
    single = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    assert single.extra_state_attributes["current_robot_angle"] == 33

    _device_mode(hub, "MAIN_DIRECTION_MODE_AUTO_ROTATE")
    auto = MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass)
    assert auto.native_value == 20.0
    assert "current_robot_angle" in auto.extra_state_attributes

    _device_mode(hub, "MAIN_DIRECTION_MODE_MULTIPLE")
    angle2 = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    assert angle2.native_value == 120.0
    assert "current_robot_angle" in angle2.extra_state_attributes


def test_single_angle_native_value_none_when_angle_missing() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_SINGLE",
            "single_mode_config": {},
        },
    })
    assert number.native_value is None


# ---------------------------------------------------------------------------
# per-mode write paths and paired-angle attributes
# ---------------------------------------------------------------------------


def test_single_angle_write_publishes_wrapped_angle() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_SINGLE")
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    asyncio.run(number.async_set_native_value(365.0))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    cfg = json.loads(payload)["main_direction_angle_config"]
    assert cfg["mode"] == "MAIN_DIRECTION_MODE_SINGLE"
    assert cfg["single_mode_config"]["angle"] == 5


def test_auto_rotate_write_publishes_interval() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_AUTO_ROTATE")
    number = MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass)
    asyncio.run(number.async_set_native_value(45.0))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    cfg = json.loads(payload)["main_direction_angle_config"]
    assert cfg["auto_rotate_mode_config"] == {"angle_interval": 45}


def test_multiple_angle2_write_preserves_angle1() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_MULTIPLE")
    number = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    asyncio.run(number.async_set_native_value(200.0))
    _topic, payload = hub.mqtt_client.publish.call_args.args
    cfg = json.loads(payload)["main_direction_angle_config"]
    # existing angle1 (30) preserved, new angle2 wrapped into range
    assert cfg["multiple_mode_config"]["angles"] == [30, 200]


def test_multiple_angle_attributes_show_paired_angles() -> None:
    hub = _hub()
    _device_mode(hub, "MAIN_DIRECTION_MODE_MULTIPLE")
    angle1 = MultipleDirectionAngle1Number(hub.basic_data, hub.hass)
    angle2 = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    a1 = angle1.extra_state_attributes
    a2 = angle2.extra_state_attributes
    assert a1["paired_angle2"] == 120
    assert a1["angle_difference"] == 90
    assert a2["paired_angle1"] == 30
    assert angle1.native_value == 30.0


_ALL_MODE_NUMBERS = (
    MainDirectionSingleAngleNumber,
    MainDirectionAutoRotateIntervalNumber,
    MultipleDirectionAngle1Number,
    MultipleDirectionAngle2Number,
)


def test_mode_numbers_unavailable_without_lawn_mower() -> None:
    for cls in _ALL_MODE_NUMBERS:
        hub = _hub()  # selector returns None -> device fallback
        hub.basic_data.lawn_mower = None
        number = cls(hub.basic_data, hub.hass)
        assert number.available is False
        assert number.native_value is None
        asyncio.run(number.async_set_native_value(20.0))
        hub.mqtt_client.publish.assert_not_called()


def test_mode_number_connection_guard_beats_cached_mode() -> None:
    # Regression: even with a matching cached mode, the base connectivity
    # check must win — a disconnected/missing hub means unavailable.
    for cls, mode in (
        (MainDirectionSingleAngleNumber, "MAIN_DIRECTION_MODE_SINGLE"),
        (MainDirectionAutoRotateIntervalNumber, "MAIN_DIRECTION_MODE_AUTO_ROTATE"),
        (MultipleDirectionAngle1Number, "MAIN_DIRECTION_MODE_MULTIPLE"),
        (MultipleDirectionAngle2Number, "MAIN_DIRECTION_MODE_MULTIPLE"),
    ):
        hub = _hub()
        number = cls(hub.basic_data, hub.hass)
        number._cached_mode = mode
        hub.basic_data.lawn_mower = None
        assert number.available is False
        asyncio.run(number.async_set_native_value(20.0))
        hub.mqtt_client.publish.assert_not_called()


def test_plain_number_available_follows_connection_only() -> None:
    # entities without a _required_mode use the base connectivity check alone
    hub = _hub()
    number = MowingHeightNumber(hub.basic_data, hub.hass)
    assert number.available is True
    hub.connection_error = True
    assert number.available is False


def test_mode_helper_returns_none_without_lawn_mower() -> None:
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    assert number._current_main_direction_mode() is None


def test_mode_helper_cached_and_empty_paths_for_all() -> None:
    for cls in _ALL_MODE_NUMBERS:
        # cached mode is preferred and retained across reads
        hub = _hub()
        number = cls(hub.basic_data, hub.hass)
        number._cached_mode = "MAIN_DIRECTION_MODE_AUTO_ROTATE"
        assert number._current_main_direction_mode() == "MAIN_DIRECTION_MODE_AUTO_ROTATE"
        assert number._cached_mode == "MAIN_DIRECTION_MODE_AUTO_ROTATE"

        # no cache and no device data yet -> mode unknown
        hub2 = _hub()
        number2 = cls(hub2.basic_data, hub2.hass)
        assert number2._current_main_direction_mode() is None


def test_every_mode_number_registers_a_working_listener() -> None:
    for cls in (
        MainDirectionAutoRotateIntervalNumber,
        MultipleDirectionAngle1Number,
        MultipleDirectionAngle2Number,
    ):
        hub = _hub()
        number = cls(hub.basic_data, hub.hass)
        number.entity_id = "number.terramow_test"
        number.async_write_ha_state = MagicMock()
        number._register_mode_change_listener()
        _event_name, callback = hub.hass.bus.async_listen.call_args.args
        asyncio.run(callback(SimpleNamespace(data={
            "device_host": number.host,
            "new_mode": "MAIN_DIRECTION_MODE_MULTIPLE",
        })))
        assert number._cached_mode == "MAIN_DIRECTION_MODE_MULTIPLE"


def test_mode_listener_registers_unsub_for_teardown() -> None:
    # Regression: the bus listener's unsubscribe callable must be handed to
    # async_on_remove so it is torn down on reload/removal instead of leaking
    # and writing state on a dead entity.
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    number.entity_id = "number.terramow_test"
    unsub = hub.hass.bus.async_listen.return_value
    number._register_mode_change_listener()
    assert unsub in number._on_remove


def test_plain_number_does_not_register_mode_listener() -> None:
    # Only angle controllers listen for the mode-change event; a plain number
    # (e.g. mowing height) must not register a listener when added to hass.
    hub = _hub()
    number = MowingHeightNumber(hub.basic_data, hub.hass)
    with patch(
        "custom_components.terramow.entity_utils.PushUpdateMixin.async_added_to_hass",
        AsyncMock(),
    ):
        asyncio.run(number.async_added_to_hass())
    hub.hass.bus.async_listen.assert_not_called()


def test_angle_number_registers_mode_listener_on_add() -> None:
    # Conversely, adding an angle controller registers exactly one listener.
    hub = _hub()
    number = MainDirectionSingleAngleNumber(hub.basic_data, hub.hass)
    number.entity_id = "number.terramow_test"
    with patch(
        "custom_components.terramow.entity_utils.PushUpdateMixin.async_added_to_hass",
        AsyncMock(),
    ):
        asyncio.run(number.async_added_to_hass())
    hub.hass.bus.async_listen.assert_called_once()
