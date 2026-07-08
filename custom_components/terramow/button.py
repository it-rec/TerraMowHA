from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowConfigEntry
from .entity import TerraMowEntity

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow button entities."""
    basic_data = config_entry.runtime_data

    entities = [
        EdgeTrimButton(basic_data, hass),
        ResetBladeTimerButton(basic_data, hass),
        ResetBaseStationTimerButton(basic_data, hass),
    ]

    async_add_entities(entities)

class TerraMowResetButtonBase(TerraMowEntity, ButtonEntity):
    """Base class for TerraMow reset buttons."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC


class ResetBladeTimerButton(TerraMowResetButtonBase):
    """Button to reset the mowing blade disk usage time."""

    _attr_translation_key = "reset_blade_timer"

    _unique_id_suffix = "reset_blade_timer"

    async def async_press(self) -> None:
        """Reset the blade timer by sending 0 to dp_126."""
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        _LOGGER.info("Resetting blade timer")
        hub.publish_data_point(126, {"int_value": 0})

class ResetBaseStationTimerButton(TerraMowResetButtonBase):
    """Button to reset the base station usage time."""

    _attr_translation_key = "reset_base_station_timer"

    _unique_id_suffix = "reset_base_station_timer"

    async def async_press(self) -> None:
        """Reset the base station timer by sending 0 to dp_125."""
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        _LOGGER.info("Resetting base station timer")
        hub.publish_data_point(125, {"int_value": 0})

class EdgeTrimButton(TerraMowEntity, ButtonEntity):
    """Button that starts the TerraMow in edge-trim mode."""

    _attr_translation_key = "edge_trim"

    _unique_id_suffix = "edge_trim"

    async def async_press(self) -> None:
        """Trigger edge-trim mowing."""
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        hub.start_edge_trim()
