"""Light platform: the mower's illumination lamp (dp_152).

The device reports ``is_illuminate_light_on`` in its environment block. The
write format is undocumented, so the toggle goes through the hub's verified
dp_152 negotiation: it only reports success once the mower reports the lamp
in the requested state, and raises otherwise.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowConfigEntry
from .const import ENVIRONMENT_INFO_DP
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# Path to the lamp flag inside the dp_152 environment block.
ILLUMINATION_PATH = ("is_illuminate_light_on",)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow light entity."""
    async_add_entities([IlluminationLight(config_entry.runtime_data, hass)])


class IlluminationLight(PushUpdateMixin, TerraMowEntity, LightEntity):
    """The mower's illumination lamp.

    On/off only — the device reports a bare boolean, with no brightness or
    colour information, so the entity declares ``ColorMode.ONOFF`` rather than
    inventing capabilities it cannot control.

    Disabled by default: dp_152 writes are undocumented and current firmware
    may drop them (the dp_122 schedule writes behave that way), in which case
    switching raises instead of silently doing nothing. The read-only
    *Illumination* binary sensor stays available either way.
    """

    _push_dp_ids = (ENVIRONMENT_INFO_DP,)

    _attr_translation_key = "illumination_light"
    _attr_entity_registry_enabled_default = False
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    _unique_id_suffix = "illumination_light"

    @property
    def is_on(self) -> bool | None:
        hub = self.hub
        if not hub or not hub.environment_info:
            return None
        value = hub.resolve_setting(hub.environment_info, ILLUMINATION_PATH)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(False)

    async def _write(self, on: bool) -> None:
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        await hub.async_write_environment_setting(ILLUMINATION_PATH, on)
        safe_write_ha_state(self)
