"""Shared base entity for the TerraMow integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from . import TerraMowBasicData


class TerraMowEntity(Entity):
    """Base class shared by all TerraMow entities.

    Provides the common device registry entry, the ``unique_id`` scheme
    and the default availability check, so the platform modules only
    carry their platform-specific logic.
    """

    _attr_has_entity_name = True

    # Suffix appended to the per-device unique id. Subclasses set this (or
    # override ``unique_id`` for historical id formats); the lawn mower
    # entity itself keeps ``None`` for its suffix-less id.
    _unique_id_suffix: str | None = None

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant | None = None,
    ) -> None:
        super().__init__()
        self.basic_data = basic_data
        self.host = basic_data.host
        if hass is not None:
            self.hass = hass

    @property
    def device_uid(self) -> str:
        """Return the stable device identity: serial once known, else host."""
        return self.basic_data.device_uid or self.host

    @property
    def device_info(self) -> DeviceInfo:
        """Return the shared device registry entry."""
        lawn_mower = self.basic_data.lawn_mower
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_uid)},
            name="TerraMow",
            manufacturer="TerraMow",
            model=lawn_mower.device_model if lawn_mower else None,
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity.

        The ``lawn_mower.terramow@`` prefix is historical — every platform
        shares it, so do not "fix" it: changing it would orphan the entity
        registry entries of existing installs.
        """
        if self._unique_id_suffix is None:
            return f"lawn_mower.terramow@{self.device_uid}"
        return f"lawn_mower.terramow@{self.device_uid}.{self._unique_id_suffix}"

    @property
    def available(self) -> bool:
        """Return True while the device connection is healthy.

        Entities go unavailable instead of showing stale data when the
        MQTT connection to the mower is lost (quality scale
        ``entity-unavailable`` rule).
        """
        lawn_mower = self.basic_data.lawn_mower
        return lawn_mower is not None and not lawn_mower.connection_error
