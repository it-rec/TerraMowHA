from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import COMPATIBILITY_INFO_DP, SCHEDULE_DP, WEEKDAY_TO_DEVICE
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin

if TYPE_CHECKING:
    from .hub import TerraMowHub

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TerraMow switch entities."""
    basic_data = config_entry.runtime_data

    entities: list[SwitchEntity] = [
        ThoroughCornerCuttingSwitch(basic_data, hass),
        ScheduleSwitch(basic_data, hass),
    ]
    entities.extend(
        ScheduleWeekdaySwitch(basic_data, hass, day) for day in WEEKDAY_TO_DEVICE
    )

    async_add_entities(entities)


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


class ScheduleSwitch(PushUpdateMixin, TerraMowEntity, SwitchEntity):
    """Master switch for scheduled mowing (dp_122 ``global_disabled``).

    Off pauses all schedules without deleting them; it does not dock a job
    already running. The state is the device's own report from the last
    dp_122 GET (unknown until read); a change waits for the device reply and
    is confirmed by reading the list again. Unavailable on firmware below
    schedule protocol version 2 (dp_127 ``module.schedule``).
    """

    _push_dp_ids = (SCHEDULE_DP, COMPATIBILITY_INFO_DP)

    _attr_translation_key = "schedule"

    _unique_id_suffix = "schedule"

    @property
    def available(self) -> bool:
        hub = self.hub
        return super().available and hub is not None and hub.schedule_switch_supported

    @property
    def is_on(self) -> bool | None:
        hub = self.hub
        return hub.schedule_enabled if hub else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        hub = self.hub
        if not hub:
            _LOGGER.error("Lawn mower not available")
            return
        await self._write(hub, enabled)

    async def _write(self, hub: TerraMowHub, enabled: bool) -> None:
        await hub.async_set_schedule_enabled(enabled)


class ScheduleWeekdaySwitch(ScheduleSwitch):
    """Whether time-slot schedules may run on one weekday (dp_122).

    On means the day is absent from ``disabled_week_days``. Independent of
    the master switch, which does not erase these choices. Unavailable in
    frequency schedule mode, where the device ignores the weekday list.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, basic_data: TerraMowBasicData, hass: HomeAssistant, day: str
    ) -> None:
        super().__init__(basic_data, hass)
        self._week_day = WEEKDAY_TO_DEVICE[day]
        self._attr_translation_key = f"schedule_{day}"
        self._unique_id_suffix = f"schedule_{day}"

    @property
    def available(self) -> bool:
        hub = self.hub
        return (
            super().available
            and hub is not None
            and hub.schedule_weekdays_configurable
        )

    @property
    def is_on(self) -> bool | None:
        hub = self.hub
        return hub.schedule_weekday_enabled(self._week_day) if hub else None

    async def _write(self, hub: TerraMowHub, enabled: bool) -> None:
        await hub.async_set_schedule_weekday_enabled(self._week_day, enabled)
