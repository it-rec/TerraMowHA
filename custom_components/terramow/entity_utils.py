"""Shared helpers for TerraMow entities."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

# PushUpdateMixin is always combined with an Entity subclass at runtime, but as
# a standalone class it has no Entity base. Give mypy an Entity base (dropped at
# runtime) so it can resolve async_added_to_hass and treat ``self`` as an Entity.
if TYPE_CHECKING:
    _MixinBase = Entity
else:
    _MixinBase = object


def async_get_entry_device(
    device_registry: dr.DeviceRegistry,
    identifier: tuple[str, str],
    config_entry_id: str | None,
) -> dr.DeviceEntry | None:
    """Return the device with ``identifier`` owned by ``config_entry_id``.

    Newer Home Assistant releases no longer treat device identifiers as unique
    across config entries and deprecate ``async_get_device`` (it stops working
    in 2027.8) in favour of the entry-scoped ``async_get_device_by_identifier``.
    Use that when available and fall back to ``async_get_device`` on older
    cores, which still support the minimum version declared in ``hacs.json``.
    """
    get_by_identifier: (
        Callable[[tuple[str, str], str], dr.DeviceEntry | None] | None
    ) = getattr(device_registry, "async_get_device_by_identifier", None)
    if get_by_identifier is None:
        return device_registry.async_get_device({identifier})
    if config_entry_id is None:
        return None
    return get_by_identifier(identifier, config_entry_id)


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
        # Hand every unsubscribe to async_on_remove so a disabled/removed
        # entity is deregistered from the hub instead of leaking and being
        # invoked forever.
        for dp_id in self._push_dp_ids:
            self.async_on_remove(
                lawn_mower.register_callback(dp_id, self._handle_push_update)
            )
        if self._push_map_info:
            self.async_on_remove(
                lawn_mower.register_map_callback(self._handle_map_push_update)
            )

    async def _handle_push_update(self, _payload: str) -> None:
        safe_write_ha_state(self)

    async def _handle_map_push_update(self, _map_info: dict[str, Any]) -> None:
        safe_write_ha_state(self)
