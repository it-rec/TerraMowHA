"""Coverage for the advanced control paths.

The mow speed AUTO gating, the main direction mode select write path and
the multi-angle / auto-rotate numbers with their mode-dependent
availability.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.number import (
    EdgeCuttingDistanceNumber,
    MainDirectionAutoRotateIntervalNumber,
    MultipleDirectionAngle1Number,
    MultipleDirectionAngle2Number,
)
from custom_components.terramow.select import MainDirectionModeSelect, MowSpeedSelect


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    # no entity registry in these tests: force the device-data fallback and
    # close coroutines handed to async_create_task instead of scheduling them
    hub.hass.states.get = MagicMock(return_value=None)
    hub.hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# mow speed AUTO gating
# ---------------------------------------------------------------------------


def test_auto_speed_hidden_on_old_firmware() -> None:
    hub = _hub()
    hub.basic_data.firmware_version = {"module": {"mow_speed": 2}}
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    assert "mow_speed_type_auto" not in select.options

    asyncio.run(select.async_select_option("mow_speed_type_auto"))
    hub.mqtt_client.publish.assert_not_called()
    assert select.extra_state_attributes["auto_speed_supported"] is False


def test_auto_speed_exposed_on_supported_firmware() -> None:
    hub = _hub()
    hub.basic_data.firmware_version = {"module": {"mow_speed": 3}}
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    assert "mow_speed_type_auto" in select.options

    asyncio.run(select.async_select_option("mow_speed_type_auto"))
    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_AUTO"}}


def test_auto_speed_exposed_when_device_reports_auto() -> None:
    """Fallback: old firmware info but the device already runs AUTO."""
    hub = _hub()
    hub.basic_data.firmware_version = {"module": {"mow_speed": 2}}
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_AUTO"}})

    select = MowSpeedSelect(hub.basic_data, hub.hass)
    assert "mow_speed_type_auto" in select.options
    assert select.current_option == "mow_speed_type_auto"


def test_feature_version_parsing_tolerates_odd_values() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)

    for firmware, expected in [
        ({"module": {"mow_speed": "3"}}, 3),
        ({"module": {"mow_speed": True}}, None),
        ({"module": {"mow_speed": "n/a"}}, None),
        ({}, None),
        (None, None),
    ]:
        hub.basic_data.firmware_version = firmware
        assert select._get_mow_speed_feature_version() == expected


# ---------------------------------------------------------------------------
# main direction mode select write path
# ---------------------------------------------------------------------------


def test_mode_select_write_preserves_existing_angles() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_SINGLE",
            "multiple_mode_config": {"angles": [30, 120]},
        },
    })
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("main_direction_mode_multiple"))

    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    config = command["main_direction_angle_config"]
    assert config["mode"] == "MAIN_DIRECTION_MODE_MULTIPLE"
    # existing device angles must be kept, not reset to defaults
    assert config["multiple_mode_config"]["angles"] == [30, 120]

    # optimistic feedback: pending mode wins until the device confirms
    assert select.current_option == "main_direction_mode_multiple"
    # angle controllers were notified via the HA event bus
    assert hub.hass.bus.fire.called


def test_mode_select_write_uses_defaults_without_device_config() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    asyncio.run(select.async_select_option("main_direction_mode_auto_rotate"))

    _topic, command = _published(hub)
    config = command["main_direction_angle_config"]
    assert config["auto_rotate_mode_config"] == {"angle_interval": 15}


def test_mode_select_rejects_unknown_mode() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("main_direction_mode_zigzag"))
    hub.mqtt_client.publish.assert_not_called()


def test_mode_select_confirmation_clears_pending_mode() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select.async_select_option("main_direction_mode_multiple"))
    assert select._pending_mode == "MAIN_DIRECTION_MODE_MULTIPLE"

    select.on_device_mode_confirmed("MAIN_DIRECTION_MODE_MULTIPLE")
    assert select._pending_mode is None


# ---------------------------------------------------------------------------
# multi-angle numbers
# ---------------------------------------------------------------------------

MULTIPLE_PARAMS = {
    "main_direction_angle_config": {
        "mode": "MAIN_DIRECTION_MODE_MULTIPLE",
        "multiple_mode_config": {"angles": [30, 120]},
    },
}


def test_angle1_reads_first_angle_in_multiple_mode() -> None:
    hub = _hub()
    _feed(hub.on_global_params, MULTIPLE_PARAMS)
    number = MultipleDirectionAngle1Number(hub.basic_data, hub.hass)
    assert number.available is True
    assert number.native_value == 30.0

    # unavailable outside multiple mode
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"},
    })
    assert number.available is False


def test_angle1_write_preserves_second_angle() -> None:
    hub = _hub()
    _feed(hub.on_global_params, MULTIPLE_PARAMS)
    number = MultipleDirectionAngle1Number(hub.basic_data, hub.hass)

    asyncio.run(number.async_set_native_value(405.0))  # wraps to 45

    _topic, command = _published(hub)
    assert command["main_direction_angle_config"]["multiple_mode_config"]["angles"] == [45, 120]


def test_angle2_write_preserves_first_angle() -> None:
    hub = _hub()
    _feed(hub.on_global_params, MULTIPLE_PARAMS)
    number = MultipleDirectionAngle2Number(hub.basic_data, hub.hass)
    assert number.native_value == 120.0

    asyncio.run(number.async_set_native_value(200.0))

    _topic, command = _published(hub)
    assert command["main_direction_angle_config"]["multiple_mode_config"]["angles"] == [30, 200]


# ---------------------------------------------------------------------------
# auto-rotate interval number
# ---------------------------------------------------------------------------


def test_auto_rotate_interval_read_and_write() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {
            "mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE",
            "auto_rotate_mode_config": {"angle_interval": 20},
        },
    })
    number = MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass)
    assert number.available is True
    assert number.native_value == 20.0

    asyncio.run(number.async_set_native_value(25.0))
    _topic, command = _published(hub)
    assert command["main_direction_angle_config"]["auto_rotate_mode_config"] == {
        "angle_interval": 25,
    }


def test_auto_rotate_interval_unavailable_in_single_mode() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_SINGLE"},
    })
    number = MainDirectionAutoRotateIntervalNumber(hub.basic_data, hub.hass)
    assert number.available is False
    hub.mqtt_client.publish.reset_mock()
    asyncio.run(number.async_set_native_value(25.0))
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# edge cutting distance number (read + write)
# ---------------------------------------------------------------------------


def test_edge_cutting_distance_read_and_write() -> None:
    hub = _hub()
    _feed(hub.on_global_params, {"edge_cutting_distance": {"value": 80}})
    number = EdgeCuttingDistanceNumber(hub.basic_data, hub.hass)
    assert number.native_value == 80.0

    asyncio.run(number.async_set_native_value(95.0))
    _topic, command = _published(hub)
    assert command == {"edge_cutting_distance": {"value": 95}}
