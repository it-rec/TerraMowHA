from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowConfigEntry
from .const import ADVANCED_SETTINGS_DP, ENVIRONMENT_INFO_DP
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin, safe_write_ha_state

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TerraMowAdvancedSwitchEntityDescription(SwitchEntityDescription):
    """Describes a writable nested setting inside a reported block."""

    # Data point carrying the setting (150 = advanced settings, 152 =
    # environment block).
    dp_id: int = ADVANCED_SETTINGS_DP

    # Path to the boolean inside that block, e.g.
    # ("enable_cliff_detection", "value").
    path: tuple[str, ...]


# Writable counterparts of the read-only dp_150 binary sensors. Disabled by
# default: dp_150 writes are undocumented and current firmware may drop them
# (the dp_122 schedule writes behave that way), in which case toggling raises
# instead of silently doing nothing. The diagnostic binary sensors stay as the
# read-only view for everyone else.
ADVANCED_SWITCHES: tuple[TerraMowAdvancedSwitchEntityDescription, ...] = (
    TerraMowAdvancedSwitchEntityDescription(
        key="cliff_detection",
        translation_key="cliff_detection",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        path=("enable_cliff_detection", "value"),
    ),
    TerraMowAdvancedSwitchEntityDescription(
        key="slope_detection",
        translation_key="slope_detection",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        path=("enable_slope_detection", "value"),
    ),
    TerraMowAdvancedSwitchEntityDescription(
        key="after_rain_auto_resume",
        translation_key="after_rain_auto_resume",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        path=("after_rain_stop_setting", "enable_auto_resume"),
    ),
    # dp_152 actuator: the windscreen/camera defogger heater.
    TerraMowAdvancedSwitchEntityDescription(
        key="defogger_heating",
        translation_key="defogger_heating",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        dp_id=ENVIRONMENT_INFO_DP,
        path=("is_defogger_heating",),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TerraMow switch entities."""
    basic_data = config_entry.runtime_data

    entities: list[SwitchEntity] = [
        ThoroughCornerCuttingSwitch(basic_data, hass),
    ]
    entities.extend(
        AdvancedSettingSwitch(basic_data, hass, description)
        for description in ADVANCED_SWITCHES
    )

    async_add_entities(entities)


class AdvancedSettingSwitch(PushUpdateMixin, TerraMowEntity, SwitchEntity):
    """Toggle for one boolean inside a reported settings block.

    Reads the device's own report and writes through the hub's verified
    negotiation, so a firmware that ignores the write surfaces an error
    instead of a switch that flips back on the next report.
    """

    entity_description: TerraMowAdvancedSwitchEntityDescription

    def __init__(
        self,
        basic_data: Any,
        hass: HomeAssistant,
        description: TerraMowAdvancedSwitchEntityDescription,
    ) -> None:
        super().__init__(basic_data, hass)
        self.entity_description = description
        self._unique_id_suffix = f"setting_{description.key}"
        self._push_dp_ids = (description.dp_id,)

    @property
    def is_on(self) -> bool | None:
        hub = self.hub
        if not hub:
            return None
        block = hub.setting_block(self.entity_description.dp_id)
        if not block:
            return None
        value = hub.resolve_setting(block, self.entity_description.path)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(False)

    async def _write(self, enabled: bool) -> None:
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        description = self.entity_description
        if description.dp_id == ENVIRONMENT_INFO_DP:
            await hub.async_write_environment_setting(description.path, enabled)
        else:
            await hub.async_write_advanced_setting(description.path, enabled)
        safe_write_ha_state(self)


class ThoroughCornerCuttingSwitch(PushUpdateMixin, TerraMowEntity, SwitchEntity):
    """Switch for enabling thorough corner cutting in mow_param.

    Note: enable_thorough_corner_cutting is reported under
    map_info["mow_param"], but the documented data point for global
    operation parameter writes is dp_155. Until a dedicated DP for the
    mow_param flags is documented, we publish the toggle to dp_155 with
    the matching sub-dict — adjust if firmware exposes a different DP.
    """

    _push_map_info = True

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "thorough_corner_cutting"

    _unique_id_suffix = "thorough_corner_cutting"

    def _get_mow_param(self) -> dict[str, Any] | None:
        hub = self.hub
        if not hub:
            return None
        map_info = hub.map_info
        if not map_info:
            return None
        mow_param = map_info.get('mow_param')
        if not isinstance(mow_param, dict):
            return None
        return mow_param

    @property
    def is_on(self) -> bool | None:
        mow_param = self._get_mow_param()
        if mow_param is None:
            return None
        value = mow_param.get('enable_thorough_corner_cutting')
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._publish(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._publish(False)

    async def _publish(self, enabled: bool) -> None:
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return

        command = {'enable_thorough_corner_cutting': enabled}
        _LOGGER.info("Setting thorough corner cutting to %s", enabled)
        hub.publish_data_point(155, command)
