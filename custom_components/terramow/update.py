from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import COMPATIBILITY_INFO_DP
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow update entities."""
    basic_data = config_entry.runtime_data

    entities = [
        TerraMowFirmwareUpdate(basic_data, hass),
    ]

    async_add_entities(entities)


class TerraMowFirmwareUpdate(PushUpdateMixin, TerraMowEntity, UpdateEntity):
    """Update entity exposing the TerraMow firmware version."""

    # UpdateEntity.state is a cached_property; without an explicit
    # async_write_ha_state() the cached "unknown" sticks even after the
    # version/upgrade state populates. Push a refresh on every relevant
    # message: dp_102 (real version), dp_127 (compat fallback), dp_129
    # (component versions) and dp_107 (is_upgrading -> in_progress).
    _push_dp_ids = (102, COMPATIBILITY_INFO_DP, 129, 107)

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

    _unique_id_suffix = "firmware"

    def _format_version(self) -> str | None:
        """Return the firmware version to display.

        Prefer the real version the TerraMow app shows (dp_102 ``version``,
        e.g. "9.9.210"); fall back to the dp_127 compatibility number
        ("overall.ha_module", e.g. "28.3") only until dp_102 has arrived.
        """
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower:
            return None

        real_version = cast("str | None", lawn_mower.firmware_version_name)
        if real_version:
            return real_version

        info = lawn_mower.firmware_version_info
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

    @property
    def in_progress(self) -> bool:
        """Return whether a firmware upgrade is currently running (dp_107)."""
        lawn_mower = self.basic_data.lawn_mower
        return bool(lawn_mower and lawn_mower.is_upgrading)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the per-component firmware versions (dp_129) as attributes."""
        lawn_mower = self.basic_data.lawn_mower
        if not lawn_mower or not lawn_mower.component_versions:
            return {}
        return {"component_versions": lawn_mower.component_versions}
