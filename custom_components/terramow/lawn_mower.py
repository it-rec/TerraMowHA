"""Lawn mower entity for the TerraMow integration.

The MQTT/protocol logic lives in :mod:`.hub`; this entity only maps the
hub's mission state onto Home Assistant's ``LawnMowerActivity`` and
forwards the start/pause/dock commands.
"""

from __future__ import annotations

import logging
from typing import cast

from homeassistant.components.lawn_mower import LawnMowerEntity
from homeassistant.components.lawn_mower.const import (
    LawnMowerActivity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .entity import TerraMowEntity
from .entity_utils import safe_schedule_update_ha_state
from .hub import (
    MOW_MISSIONS,
    RECHARGE_MISSIONS,
    MissionState,
    SubMission,
    TerraMowHub,
)

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow lawn mower entity."""
    basic_data = config_entry.runtime_data

    async_add_entities([TerraMowLawnMowerEntity(basic_data, hass)])


class TerraMowLawnMowerEntity(TerraMowEntity, LawnMowerEntity):
    """The lawn mower entity, fed by the shared hub."""

    # Use the default icon
    _attr_translation_key = "lawn_mower"

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        """Initialize a lawn mower."""
        super().__init__(basic_data, hass)
        self._activity = LawnMowerActivity.DOCKED  # default state

        self._has_returning = hasattr(LawnMowerActivity, 'RETURNING')
        if not self._has_returning:
            _LOGGER.info("LawnMowerActivity.RETURNING not available in this HA version")

        _LOGGER.debug("TerraMowLawnMowerEntity created with host %s", self.host)

    @property
    def hub(self) -> TerraMowHub:
        """Return the hub behind this entity."""
        return cast("TerraMowHub", self.basic_data.lawn_mower)

    async def async_added_to_hass(self) -> None:
        """Track hub state changes (connection, dp_107, model name)."""
        await super().async_added_to_hass()
        self.hub.register_state_listener(self._on_hub_state)
        # The initial state may have arrived before the entity was created
        self.update_activity_from_state()

    def _on_hub_state(self) -> None:
        """Handle a hub state change (may run on the MQTT thread)."""
        self.update_activity_from_state()
        safe_schedule_update_ha_state(self)

    @property
    def activity(self) -> LawnMowerActivity:
        """Return the current activity of the lawn mower."""
        return self._activity

    @activity.setter
    def activity(self, value: LawnMowerActivity) -> None:
        """Set the current activity of the lawn mower."""
        old_activity = self._activity
        self._activity = value
        if old_activity != value:
            # Only log at INFO on an actual change, to avoid a line per dp_107
            _LOGGER.info("Activity changed from %s to %s", old_activity, value)
        _LOGGER.debug("State change details: mission=%s, sub_mission=%s, mission_state=%s, has_error=%s",
                     self.hub.mission, self.hub.sub_mission, self.hub.mission_state, self.hub.has_error)
        safe_schedule_update_ha_state(self)

    @property
    def available(self) -> bool:
        """Stay available during connection loss to surface ERROR.

        Unlike the other entities, the mower itself reports connection
        problems through its ERROR activity, which is more useful in
        automations than a bare "unavailable".
        """
        return self.basic_data.lawn_mower is not None

    @property
    def supported_features(self) -> LawnMowerEntityFeature:
        """Flag lawn mower features that are supported."""
        return LawnMowerEntityFeature.START_MOWING | LawnMowerEntityFeature.PAUSE | LawnMowerEntityFeature.DOCK

    def update_activity_from_state(self) -> None:
        """Update activity based on the hub's mission state."""
        hub = self.hub
        last_activity = self.activity

        if hub.connection_error or hub.has_error:
            self.activity = LawnMowerActivity.ERROR
        elif hub.mission_state == MissionState.MISSION_STATE_RUNNING:
            if hub.mission in MOW_MISSIONS:
                if hub.sub_mission == SubMission.SUB_MISSION_FLEXIBLE_STATION_WAIT:
                    # Waiting at the base station, equivalent to paused
                    self.activity = LawnMowerActivity.PAUSED
                elif hub.sub_mission == SubMission.SUB_MISSION_SAVING_MAP:
                    # Saving the map, equivalent to finished
                    self.activity = LawnMowerActivity.DOCKED
                else:
                    self.activity = LawnMowerActivity.MOWING
            elif hub.mission in RECHARGE_MISSIONS:
                if self._has_returning:
                    self.activity = LawnMowerActivity.RETURNING
                else:
                    # Older HA versions lack a RETURNING state; use DOCKED instead
                    self.activity = LawnMowerActivity.DOCKED
            else:
                self.activity = LawnMowerActivity.DOCKED
        elif hub.mission_state == MissionState.MISSION_STATE_PAUSE:
            self.activity = LawnMowerActivity.PAUSED
        else:
            self.activity = LawnMowerActivity.DOCKED

        if last_activity != self.activity:
            safe_schedule_update_ha_state(self)

    def start_mowing(self) -> None:
        """Start mowing implementation for lawn_mower entity."""
        self.hub.start_mowing()

    def pause(self) -> None:
        """Pause mowing implementation for lawn_mower entity."""
        self.hub.pause()

    def dock(self) -> None:
        """Docking implementation for lawn_mower entity."""
        self.hub.dock()
