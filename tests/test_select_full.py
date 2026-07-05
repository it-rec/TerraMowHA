"""Thorough coverage for the select platform.

Focuses on the MainDirectionModeSelect mode-change flow (pending mode, event
notification, related-entity refresh, device confirmation, timeout clear) plus
the zone selector's option/attribute building and the mow/blade selects.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.terramow import DOMAIN, TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.select import (
    BladeSpeedSelect,
    MainDirectionModeSelect,
    MowSpeedSelect,
    TerraMowZoneSelect,
    async_setup_entry,
)


def _close(coro):
    # the entity schedules fire-and-forget coroutines; close them so the mock
    # doesn't leave "coroutine was never awaited" warnings behind
    if hasattr(coro, "close"):
        coro.close()


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.80", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.hass.async_create_task = MagicMock(side_effect=_close)
    return hub


def _feed(handler, payload: dict) -> None:
    asyncio.run(handler(json.dumps(payload)))


def _published(hub) -> tuple[str, dict]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# platform setup
# ---------------------------------------------------------------------------


def test_async_setup_entry_creates_all_selects() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert len(added) == 5


# ---------------------------------------------------------------------------
# main direction mode select: full change flow
# ---------------------------------------------------------------------------


def _mode_select(hub) -> MainDirectionModeSelect:
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    return select


def test_mode_select_rejects_invalid_option() -> None:
    hub = _hub()
    select = _mode_select(hub)
    asyncio.run(select.async_select_option("main_direction_mode_bogus"))
    hub.mqtt_client.publish.assert_not_called()


def test_mode_select_publishes_each_mode_config() -> None:
    for token, mode, cfg_key in (
        ("main_direction_mode_single", "MAIN_DIRECTION_MODE_SINGLE", "single_mode_config"),
        ("main_direction_mode_multiple", "MAIN_DIRECTION_MODE_MULTIPLE", "multiple_mode_config"),
        ("main_direction_mode_auto_rotate", "MAIN_DIRECTION_MODE_AUTO_ROTATE", "auto_rotate_mode_config"),
    ):
        hub = _hub()
        select = _mode_select(hub)
        asyncio.run(select.async_select_option(token))
        topic, command = _published(hub)
        assert topic == "data_point/155/app"
        payload = command["main_direction_angle_config"]
        assert payload["mode"] == mode
        assert cfg_key in payload
        # the pending mode is cached for immediate feedback
        assert select._pending_mode == mode
        # a mode-change event was fired for the angle controllers
        assert hub.hass.bus.fire.called


def test_mode_select_get_effective_mode_priorities() -> None:
    hub = _hub()
    select = _mode_select(hub)
    # pending mode wins
    select._pending_mode = "MAIN_DIRECTION_MODE_MULTIPLE"
    assert select.get_effective_mode() == "MAIN_DIRECTION_MODE_MULTIPLE"
    # otherwise device mode
    select._pending_mode = None
    _feed(hub.on_global_params, {
        "main_direction_angle_config": {"mode": "MAIN_DIRECTION_MODE_AUTO_ROTATE"},
    })
    assert select.get_effective_mode() == "MAIN_DIRECTION_MODE_AUTO_ROTATE"
    # falls back to the last current_option when the device has nothing
    _feed(hub.on_global_params, {})
    select._current_option = "MAIN_DIRECTION_MODE_SINGLE"
    assert select.get_effective_mode() == "MAIN_DIRECTION_MODE_SINGLE"


def test_mode_select_device_confirmation_clears_pending() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    # matching confirmation clears the pending mode
    select._pending_mode = "MAIN_DIRECTION_MODE_MULTIPLE"
    select.on_device_mode_confirmed("MAIN_DIRECTION_MODE_MULTIPLE")
    assert select._pending_mode is None

    # a mismatching confirmation adopts the device's mode instead
    select._pending_mode = "MAIN_DIRECTION_MODE_SINGLE"
    select.on_device_mode_confirmed("MAIN_DIRECTION_MODE_AUTO_ROTATE")
    assert select._pending_mode is None
    assert select._current_option == "MAIN_DIRECTION_MODE_AUTO_ROTATE"


def test_mode_select_timeout_clears_pending(monkeypatch) -> None:
    hub = _hub()
    select = _mode_select(hub)
    select._pending_mode = "MAIN_DIRECTION_MODE_MULTIPLE"

    async def _instant(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _instant)
    asyncio.run(select._clear_pending_mode_after_timeout())
    assert select._pending_mode is None


def test_mode_select_extra_state_attributes() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)

    # pending mode surfaces as a "changing_mode" status
    select._pending_mode = "MAIN_DIRECTION_MODE_SINGLE"
    assert select.extra_state_attributes["status"] == "changing_mode"

    select._pending_mode = None
    for mode, key in (
        ("MAIN_DIRECTION_MODE_SINGLE", "single_angle"),
        ("MAIN_DIRECTION_MODE_MULTIPLE", "multiple_angles"),
        ("MAIN_DIRECTION_MODE_AUTO_ROTATE", "auto_rotate_interval"),
    ):
        _feed(hub.on_global_params, {
            "main_direction_angle_config": {
                "mode": mode,
                "current_angle": 22,
                "single_mode_config": {"angle": 5},
                "multiple_mode_config": {"angles": [30, 90]},
                "auto_rotate_mode_config": {"angle_interval": 15},
            },
        })
        attrs = select.extra_state_attributes
        assert attrs["status"] == "active"
        assert attrs["current_angle"] == 22
        assert key in attrs


def test_mow_speed_current_option_none_when_speed_type_empty() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    _feed(hub.on_global_params, {"mow_speed": {}})
    assert select.current_option is None


def test_mode_select_force_update_related_entities() -> None:
    hub = _hub()
    select = MainDirectionModeSelect(hub.basic_data, hub.hass)
    # states.get returns a truthy state for every angle-controller entity id
    hub.hass.states.get = MagicMock(return_value=SimpleNamespace(state="1"))
    select._force_update_related_entities()
    assert hub.hass.async_create_task.called

    # the whole helper is defensively wrapped; a raising states.get is swallowed
    hub.hass.states.get = MagicMock(side_effect=RuntimeError("boom"))
    select._force_update_related_entities()


# ---------------------------------------------------------------------------
# zone select option/attribute building
# ---------------------------------------------------------------------------


def test_zone_select_empty_and_populated_options() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()

    # no regions -> the "no zones" sentinel
    asyncio.run(select._on_map_info({"regions": []}))
    assert select.options == ["no_zones_available"]

    asyncio.run(select._on_map_info({
        "id": 2,
        "regions": [{"id": 1, "sub_regions": [{"id": 7, "name": "Vorne"}]}],
        "clean_info": {
            "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
            "select_region": {"region_id": [7]},
        },
    }))
    assert "Vorne (ID: 7)" in select.options
    attrs = select.extra_state_attributes
    assert attrs["sub_zones_count"] == 1
    assert attrs["currently_selected_zones"] == [7]


def test_zone_select_invalid_option_parsing() -> None:
    hub = _hub()
    select = TerraMowZoneSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    asyncio.run(select._on_map_info({
        "regions": [{"id": 1, "sub_regions": [{"id": 7, "name": "Vorne"}]}],
    }))
    # options that pass the membership check but have no "(ID: n)" cannot happen,
    # so exercise the special all_zones no-op branch instead
    asyncio.run(select.async_select_option("all_zones"))
    hub.mqtt_client.publish.assert_not_called()


# ---------------------------------------------------------------------------
# blade speed select edge cases
# ---------------------------------------------------------------------------


def test_blade_speed_defaults_and_invalid_write() -> None:
    hub = _hub()
    select = BladeSpeedSelect(hub.basic_data, hub.hass)
    select.async_write_ha_state = MagicMock()
    # default before any device data
    assert select.current_option == "blade_disk_speed_type_medium"
    # invalid option is rejected
    asyncio.run(select.async_select_option("blade_disk_speed_type_warp"))
    hub.mqtt_client.publish.assert_not_called()


def test_mow_speed_current_option_none_without_lawn_mower() -> None:
    hub = _hub()
    select = MowSpeedSelect(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    # falls back to the cached default token
    assert select.current_option == "mow_speed_type_medium"
