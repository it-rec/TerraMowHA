"""Tests for the maintenance todo list.

The list is a view of two device counters, not stored state: an item exists
exactly while the mower says the interval is up, and completing one resets
the counter that produced it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.todo import TodoItem
from homeassistant.components.todo.const import TodoItemStatus, TodoListEntityFeature
from homeassistant.core import HomeAssistant

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.todo import (
    ITEM_STRINGS,
    MaintenanceTodoList,
    async_setup_entry as todo_setup,
    item_strings,
)

HOST = "192.0.2.10"


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value = MagicMock(rc=0)
    return hub


def _todo(hub: TerraMowHub) -> MaintenanceTodoList:
    return MaintenanceTodoList(hub.basic_data, hub.hass)


async def _report(hub: TerraMowHub, *, blade: int | None, base: int | None) -> None:
    if blade is not None:
        await hub.on_blade_time(json.dumps({"int_value": blade}))
    if base is not None:
        await hub.on_base_station_time(json.dumps({"int_value": base}))


def _published(hub: TerraMowHub) -> tuple[str, dict[str, Any]]:
    topic, payload = hub.mqtt_client.publish.call_args.args
    return topic, json.loads(payload)


# ---------------------------------------------------------------------------
# item generation
# ---------------------------------------------------------------------------


async def test_setup_creates_the_list(hub: TerraMowHub) -> None:
    added: list[Any] = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data)
    await todo_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]
    assert len(added) == 1
    assert isinstance(added[0], MaintenanceTodoList)


async def test_the_list_is_empty_while_nothing_is_due(hub: TerraMowHub) -> None:
    await _report(hub, blade=100, base=100)
    assert _todo(hub).todo_items == []


async def test_no_counters_yet_means_no_items(hub: TerraMowHub) -> None:
    assert _todo(hub).todo_items == []


async def test_an_item_appears_when_the_interval_is_reached(
    hub: TerraMowHub,
) -> None:
    await _report(hub, blade=BLADE_MAINTENANCE_CYCLE_MINUTES, base=0)

    items = _todo(hub).todo_items
    assert items is not None
    assert [item.uid for item in items] == ["blade"]
    assert items[0].status is TodoItemStatus.NEEDS_ACTION
    assert items[0].summary == ITEM_STRINGS["en"]["blade"]
    # The description carries the device's own numbers, not a guess.
    assert items[0].description == "240 h of 240 h used"


async def test_both_chores_can_be_due_at_once(hub: TerraMowHub) -> None:
    await _report(
        hub,
        blade=BLADE_MAINTENANCE_CYCLE_MINUTES + 600,
        base=BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    )

    items = _todo(hub).todo_items
    assert items is not None
    assert [item.uid for item in items] == ["blade", "base_station"]
    assert items[0].description == "250 h of 240 h used"


async def test_unusable_counters_produce_no_item(hub: TerraMowHub) -> None:
    await hub.on_blade_time(json.dumps({"int_value": True}))  # bool, not a count
    await hub.on_base_station_time(json.dumps({"other": 1}))
    assert _todo(hub).todo_items == []


async def test_a_non_object_payload_produces_no_item(hub: TerraMowHub) -> None:
    """dp_125/126 are cached verbatim, so a stray list must not crash the list."""
    await hub.on_blade_time("[1, 2]")
    assert _todo(hub).todo_items == []
    assert _todo(hub).extra_state_attributes["blade_used_minutes"] is None


async def test_the_list_is_unknown_without_a_hub(hub: TerraMowHub) -> None:
    todo = _todo(hub)
    hub.basic_data.lawn_mower = None
    assert todo.todo_items is None
    assert todo.extra_state_attributes == {}


async def test_attributes_expose_the_raw_counters(hub: TerraMowHub) -> None:
    await _report(hub, blade=1200, base=None)
    assert _todo(hub).extra_state_attributes == {
        "blade_used_minutes": 1200,
        "base_station_used_minutes": None,
    }


# ---------------------------------------------------------------------------
# completing an item
# ---------------------------------------------------------------------------


async def test_only_updating_is_offered(hub: TerraMowHub) -> None:
    """No add/delete: the items are a device view, not a stored list."""
    assert _todo(hub).supported_features is TodoListEntityFeature.UPDATE_TODO_ITEM


async def test_completing_the_blade_item_resets_its_counter(
    hub: TerraMowHub,
) -> None:
    await _report(hub, blade=BLADE_MAINTENANCE_CYCLE_MINUTES, base=0)
    todo = _todo(hub)

    await todo.async_update_todo_item(
        TodoItem(uid="blade", summary="x", status=TodoItemStatus.COMPLETED)
    )

    assert _published(hub) == ("data_point/126/app", {"int_value": 0})


async def test_completing_the_base_station_item_resets_its_counter(
    hub: TerraMowHub,
) -> None:
    todo = _todo(hub)
    await todo.async_update_todo_item(
        TodoItem(uid="base_station", summary="x", status=TodoItemStatus.COMPLETED)
    )
    assert _published(hub) == ("data_point/125/app", {"int_value": 0})


async def test_a_non_completed_edit_touches_nothing(hub: TerraMowHub) -> None:
    todo = _todo(hub)
    await todo.async_update_todo_item(
        TodoItem(uid="blade", summary="renamed", status=TodoItemStatus.NEEDS_ACTION)
    )
    hub.mqtt_client.publish.assert_not_called()


async def test_an_unknown_item_is_ignored(hub: TerraMowHub) -> None:
    todo = _todo(hub)
    await todo.async_update_todo_item(
        TodoItem(uid="nope", summary="x", status=TodoItemStatus.COMPLETED)
    )
    hub.mqtt_client.publish.assert_not_called()


async def test_completing_without_a_hub_does_not_publish(hub: TerraMowHub) -> None:
    todo = _todo(hub)
    mqtt = hub.mqtt_client
    hub.basic_data.lawn_mower = None
    await todo.async_update_todo_item(
        TodoItem(uid="blade", summary="x", status=TodoItemStatus.COMPLETED)
    )
    mqtt.publish.assert_not_called()


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------


def test_item_strings_fall_back_to_english() -> None:
    assert item_strings("de")["blade"] == ITEM_STRINGS["de"]["blade"]
    # A language with no table at all still gets a complete set.
    assert item_strings("xx") == ITEM_STRINGS["en"]
    assert item_strings(None) == ITEM_STRINGS["en"]


def test_every_language_table_uses_known_keys() -> None:
    expected = set(ITEM_STRINGS["en"])
    for language, table in ITEM_STRINGS.items():
        assert set(table) <= expected, language
        assert "{used}" in table["used"] and "{cycle}" in table["used"], language
