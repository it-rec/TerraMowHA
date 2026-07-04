"""Shared helpers for TerraMow entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

# PushUpdateMixin is always combined with an Entity subclass at runtime, but as
# a standalone class it has no Entity base. Give mypy an Entity base (dropped at
# runtime) so it can resolve async_added_to_hass and treat ``self`` as an Entity.
if TYPE_CHECKING:
    _MixinBase = Entity
else:
    _MixinBase = object


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


class PushUpdateMixin(_MixinBase):
    """Refresh entity state as soon as the relevant MQTT data arrives.

    Entities that only read cached data point payloads otherwise rely on
    Home Assistant's default 30-second polling, so state changes lag even
    though the device pushes them instantly. Set ``_push_dp_ids`` to the
    data point IDs the entity reads (and/or ``_push_map_info`` for the
    map/current/info topic) and every message triggers a state write.
    """

    # Provided by the concrete TerraMowEntity subclass this mixin is used with.
    basic_data: Any

    _push_dp_ids: tuple[int, ...] = ()
    _push_map_info: bool = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        lawn_mower = getattr(self.basic_data, "lawn_mower", None)
        if lawn_mower is None:
            return
        for dp_id in self._push_dp_ids:
            lawn_mower.register_callback(dp_id, self._handle_push_update)
        if self._push_map_info:
            lawn_mower.register_map_callback(self._handle_map_push_update)

    async def _handle_push_update(self, _payload: str) -> None:
        safe_write_ha_state(self)

    async def _handle_map_push_update(self, _map_info: dict) -> None:
        safe_write_ha_state(self)
