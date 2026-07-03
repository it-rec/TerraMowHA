"""Shared base entity for the TerraMow integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

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
    def device_info(self) -> DeviceInfo:
        """Return the shared device registry entry."""
        lawn_mower = self.basic_data.lawn_mower
        return DeviceInfo(
            identifiers={("TerraMowLawnMower", self.basic_data.host)},
            name="TerraMow",
            manufacturer="TerraMow",
            model=lawn_mower.device_model if lawn_mower else None,
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        if self._unique_id_suffix is None:
            return f"lawn_mower.terramow@{self.host}"
        return f"lawn_mower.terramow@{self.host}.{self._unique_id_suffix}"

    @property
    def available(self) -> bool:
        """Return True while the shared device connection exists."""
        return self.basic_data.lawn_mower is not None
