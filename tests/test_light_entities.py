"""Coverage for the mow-speed select, the buttons and the switch.

Exercises the firmware-gated AUTO option of the mow-speed select, the three
one-shot buttons (blade/base-station reset and edge trim) and the thorough
corner-cutting switch.
"""

import asyncio
import json
from unittest.mock import MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.button import (
    EdgeTrimButton,
    ResetBaseStationTimerButton,
    ResetBladeTimerButton,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.select import MowSpeedSelect
from custom_components.terramow.switch import ThoroughCornerCuttingSwitch


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.30", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# mow speed select
# ---------------------------------------------------------------------------


def test_mow_speed_select_read_and_write() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_LOW"}})
    assert select.current_option == "mow_speed_type_low"

    asyncio.run(select.async_select_option("mow_speed_type_medium"))
    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_MEDIUM"}}


def test_mow_speed_select_hides_auto_without_firmware_support() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    # no firmware feature info -> AUTO is not offered
    assert select.options == [
        "mow_speed_type_low",
        "mow_speed_type_medium",
        "mow_speed_type_adaptive_high",
    ]

    # trying to select AUTO anyway is rejected without publishing
    asyncio.run(select.async_select_option("mow_speed_type_auto"))
    hub.mqtt_client.publish.assert_not_called()


def test_mow_speed_select_exposes_auto_with_firmware_support() -> None:
    hub = _hub()
    hub.basic_data.firmware_version = {"module": {"mow_speed": 5}}
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    assert "mow_speed_type_auto" in select.options

    asyncio.run(select.async_select_option("mow_speed_type_auto"))
    topic, command = _published(hub)
    assert command == {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_AUTO"}}


def test_mow_speed_select_surfaces_unknown_device_value() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"mow_speed": {"speed_type": "MOW_SPEED_TYPE_TURBO"}})

    assert select.current_option is None
    assert select.extra_state_attributes["unknown_speed_type"] == "MOW_SPEED_TYPE_TURBO"


# ---------------------------------------------------------------------------
# buttons
# ---------------------------------------------------------------------------


def test_reset_blade_timer_button() -> None:
    hub = _hub()
    button = ResetBladeTimerButton(hub.basic_data, hub.hass)
    asyncio.run(button.async_press())
    topic, command = _published(hub)
    assert topic == "data_point/126/app"
    assert command == {"int_value": 0}


def test_reset_base_station_timer_button() -> None:
    hub = _hub()
    button = ResetBaseStationTimerButton(hub.basic_data, hub.hass)
    asyncio.run(button.async_press())
    topic, command = _published(hub)
    assert topic == "data_point/125/app"
    assert command == {"int_value": 0}


def test_edge_trim_button_starts_edge_trim() -> None:
    hub = _hub()
    # clear the command rate limiter so the one-shot command is accepted
    hub._last_control_time = 0.0
    button = EdgeTrimButton(hub.basic_data, hub.hass)
    asyncio.run(button.async_press())
    topic, command = _published(hub)
    assert topic == "data_point/103/app"
    assert command["mode"] == "START_MODE_EDGE_TRIM_CLEAN"


# ---------------------------------------------------------------------------
# thorough corner cutting switch (dp_155 via mow_param)
# ---------------------------------------------------------------------------


def test_corner_cutting_switch_read_path() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)
    assert switch.is_on is None

    hub._update_map_info({"mow_param": {"enable_thorough_corner_cutting": True}})
    assert switch.is_on is True


def test_corner_cutting_switch_write_path() -> None:
    hub = _hub()
    switch = ThoroughCornerCuttingSwitch(hub.basic_data, hub.hass)

    asyncio.run(switch.async_turn_on())
    topic, command = _published(hub)
    assert topic == "data_point/155/app"
    assert command == {"enable_thorough_corner_cutting": True}

    asyncio.run(switch.async_turn_off())
    _, command = _published(hub)
    assert command == {"enable_thorough_corner_cutting": False}
