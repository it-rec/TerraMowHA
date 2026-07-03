"""Shared helpers for TerraMow entities."""

from __future__ import annotations

import logging

from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


def _can_write_state(entity: Entity) -> bool:
    """Return True if the entity is registered and may write state.

    MQTT data can arrive before ``async_added_to_hass`` has completed or
    after the entity has been removed (e.g. on reload/reconfigure). Writing
    state in that window raises ``RuntimeError: Attribute hass is None``
    and floods the log (upstream issue #77).
    """
    return entity.hass is not None and entity.entity_id is not None


def safe_write_ha_state(entity: Entity) -> None:
    """Write state, silently skipping when the entity is not writable."""
    if not _can_write_state(entity):
        return
    try:
        entity.async_write_ha_state()
    except RuntimeError as err:
        _LOGGER.debug("Skipping state write for %s: %s", entity.entity_id, err)


def safe_schedule_update_ha_state(entity: Entity) -> None:
    """Schedule a state update, skipping when the entity is not writable."""
    if not _can_write_state(entity):
        return
    try:
        entity.schedule_update_ha_state()
    except RuntimeError as err:
        _LOGGER.debug("Skipping state update for %s: %s", entity.entity_id, err)
