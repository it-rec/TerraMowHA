from __future__ import annotations

import logging

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, DOMAIN
from .entity import TerraMowEntity
from .entity_utils import safe_write_ha_state
from .const import COMPATIBILITY_INFO_DP

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow update entities."""
    basic_data = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        TerraMowFirmwareUpdate(basic_data, hass),
    ]

    async_add_entities(entities)


class TerraMowFirmwareUpdate(TerraMowEntity, UpdateEntity):
    """Update entity exposing the TerraMow firmware version."""

    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = UpdateEntityFeature(0)

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the firmware update entity."""
        super().__init__(basic_data, hass)
        _LOGGER.debug("TerraMowFirmwareUpdate entity created")

    async def async_added_to_hass(self) -> None:
        # UpdateEntity.state is a cached_property; without an explicit
        # async_write_ha_state() the cached "unknown" sticks even after
        # firmware_version_info populates. Push a refresh on every dp_127
        # message so the cache is invalidated as soon as data arrives.
        await super().async_added_to_hass()
        if self.basic_data.lawn_mower:
            self.basic_data.lawn_mower.register_callback(
                COMPATIBILITY_INFO_DP, self._handle_compat_info
            )

    async def _handle_compat_info(self, _payload: str) -> None:
        safe_write_ha_state(self)

    _unique_id_suffix = "firmware"

    def _format_version(self) -> str | None:
        """Build a version string from the firmware compatibility info."""
        if not self.basic_data.lawn_mower:
            return None

        info = self.basic_data.lawn_mower.firmware_version_info
        if not info:
            return None

        overall = info.get("overall")
        if overall is None:
            return None

        ha_version = info.get("module", {}).get("home_assistant")
        if ha_version is not None:
            return f"{overall}.{ha_version}"
        return str(overall)

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed firmware version."""
        return self._format_version()

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version.

        Updates are managed via the TerraMow app, so report the installed
        version to indicate that no update is available from Home Assistant.
        """
        return self._format_version()
