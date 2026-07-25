"""Todo platform: the maintenance the mower is actually asking for.

The blade and base-station counters already drive repair issues, but a repair
issue is a dashboard interruption — fine for "your firmware is too old", less
fine for a chore you plan to do at the weekend. The same two counters make a
better todo list: an item appears when the device's own counter says the
service interval is up, and ticking it off resets that counter on the mower.

The list is therefore empty exactly when there is nothing to do, and every
item is backed by a number the device reported — never a schedule this
integration invented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.todo import TodoItem, TodoListEntity
from homeassistant.components.todo.const import TodoItemStatus, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowConfigEntry
from .const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
)
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin

if TYPE_CHECKING:
    from .hub import TerraMowHub

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class MaintenanceTask:
    """One counter-backed maintenance chore."""

    uid: str
    # Data point carrying the used-minutes counter, and the field inside it.
    dp_id: int
    hub_attribute: str
    counter_field: str
    cycle_minutes: int


TASKS: tuple[MaintenanceTask, ...] = (
    MaintenanceTask(
        uid="blade",
        dp_id=126,
        hub_attribute="blade_time",
        counter_field="int_value",
        cycle_minutes=BLADE_MAINTENANCE_CYCLE_MINUTES,
    ),
    MaintenanceTask(
        uid="base_station",
        dp_id=125,
        hub_attribute="base_station_time",
        counter_field="int_value",
        cycle_minutes=BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    ),
)

# Todo item summaries are plain strings — Home Assistant has no translation
# mechanism for them the way it has for entity names — so, exactly like the
# map HUD labels in map_strings.py, they live in an in-code table selected by
# the UI language. English is complete and is the fallback for every missing
# key and every language not listed.
ITEM_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "blade": "Clean or replace the blade disc",
        "base_station": "Clean the base station",
        "used": "{used} h of {cycle} h used",
    },
    "de": {
        "blade": "Messerteller reinigen oder ersetzen",
        "base_station": "Basisstation reinigen",
        "used": "{used} h von {cycle} h genutzt",
    },
    "fr": {
        "blade": "Nettoyer ou remplacer le disque de lames",
        "base_station": "Nettoyer la station de base",
        "used": "{used} h sur {cycle} h utilisées",
    },
    "es": {
        "blade": "Limpiar o sustituir el disco de cuchillas",
        "base_station": "Limpiar la estación base",
        "used": "{used} h de {cycle} h utilizadas",
    },
    "it": {
        "blade": "Pulire o sostituire il disco lame",
        "base_station": "Pulire la stazione base",
        "used": "{used} h di {cycle} h utilizzate",
    },
    "nl": {
        "blade": "Messchijf reinigen of vervangen",
        "base_station": "Basisstation reinigen",
        "used": "{used} u van {cycle} u gebruikt",
    },
    "pt": {
        "blade": "Limpar ou substituir o disco de lâminas",
        "base_station": "Limpar a estação base",
        "used": "{used} h de {cycle} h utilizadas",
    },
    "zh-Hans": {
        "blade": "清洁或更换刀盘",
        "base_station": "清洁基站",
        "used": "已使用 {used} 小时 / {cycle} 小时",
    },
}


def item_strings(language: str | None) -> dict[str, str]:
    """Return the item labels for ``language``, filled in from English."""
    table = dict(ITEM_STRINGS["en"])
    if language:
        table.update(ITEM_STRINGS.get(language, {}))
    return table


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow maintenance list."""
    async_add_entities([MaintenanceTodoList(config_entry.runtime_data, hass)])


class MaintenanceTodoList(PushUpdateMixin, TerraMowEntity, TodoListEntity):
    """Maintenance the device's own counters say is due.

    Items are generated, not stored: there is no add or delete, only marking
    one done — which is what actually resets the counter on the mower. Home
    Assistant is told so through the supported features, so the UI never
    offers a button that could not work.
    """

    _push_dp_ids = (125, 126)

    _attr_translation_key = "maintenance"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    _unique_id_suffix = "maintenance"

    def _used_minutes(self, hub: TerraMowHub, task: MaintenanceTask) -> int | None:
        """The device's used-minutes counter for a task, if it reported one."""
        payload = getattr(hub, task.hub_attribute, None)
        if not isinstance(payload, dict):
            return None
        value = payload.get(task.counter_field)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """The chores whose service interval the device reports as reached."""
        hub = self.hub
        if hub is None:
            return None
        labels = item_strings(self.hass.config.language)
        items: list[TodoItem] = []
        for task in TASKS:
            used = self._used_minutes(hub, task)
            if used is None or used < task.cycle_minutes:
                continue
            items.append(
                TodoItem(
                    uid=task.uid,
                    summary=labels[task.uid],
                    status=TodoItemStatus.NEEDS_ACTION,
                    description=labels["used"].format(
                        used=round(used / 60), cycle=round(task.cycle_minutes / 60)
                    ),
                )
            )
        return items

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Completing an item resets the counter it came from.

        Anything else — renaming, un-completing — is ignored: the item is a
        view of a device counter, so the only edit with a meaning on the
        mower is "done".
        """
        if item.status != TodoItemStatus.COMPLETED:
            return
        hub = self.hub
        if hub is None:
            _LOGGER.error("Lawn mower not available")
            return
        for task in TASKS:
            if task.uid == item.uid:
                _LOGGER.info("Maintenance done: resetting the %s counter", task.uid)
                hub.publish_data_point(task.dp_id, {"int_value": 0})
                return
        _LOGGER.warning("Unknown maintenance item %s", item.uid)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw counters, so the list can be reconciled."""
        hub = self.hub
        if hub is None:
            return {}
        return {
            f"{task.uid}_used_minutes": self._used_minutes(hub, task)
            for task in TASKS
        }
