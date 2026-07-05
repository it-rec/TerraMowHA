"""Event entity for the TerraMow integration.

Turns the mower's dp_107 mission/state transitions into discrete Home
Assistant events so automations can react to *happenings* ("mowing finished",
"returned because of rain", "fault detected") instead of polling the
lawn-mower activity. The phase mapping mirrors the lawn-mower entity so the two
never disagree.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .entity import TerraMowEntity
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

EVENT_STARTED = "mowing_started"
EVENT_PAUSED = "paused"
EVENT_RETURNING = "returning"
EVENT_DOCKED = "docked"
EVENT_COMPLETED = "mowing_completed"
EVENT_ERROR = "error"

EVENT_TYPES = [
    EVENT_STARTED,
    EVENT_PAUSED,
    EVENT_RETURNING,
    EVENT_DOCKED,
    EVENT_COMPLETED,
    EVENT_ERROR,
]

# The internal "phase" (mirrors the lawn-mower activity mapping) -> event type.
_PHASE_EVENTS = {
    "mowing": EVENT_STARTED,
    "paused": EVENT_PAUSED,
    "returning": EVENT_RETURNING,
    "docked": EVENT_DOCKED,
    "error": EVENT_ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow event entity."""
    basic_data = config_entry.runtime_data
    async_add_entities([TerraMowMowerEventEntity(basic_data, hass)])


class TerraMowMowerEventEntity(TerraMowEntity, EventEntity):
    """Fires an event on every notable mower state transition."""

    _attr_translation_key = "mower_event"
    _unique_id_suffix = "mower_event"
    _attr_event_types = EVENT_TYPES

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the event entity."""
        super().__init__(basic_data, hass)
        self._last_phase: str | None = None
        self._was_complete = False
        self._pending: deque[tuple[str, dict[str, Any]]] = deque()
        # _detect_event mutates _last_phase/_was_complete and is reachable from
        # both the event loop (dp_107 updates) and the MQTT worker thread
        # (connection-state changes), so guard the read-modify-write.
        self._detect_lock = threading.Lock()

    @property
    def hub(self) -> TerraMowHub:
        """Return the hub behind this entity."""
        return self.basic_data.lawn_mower  # type: ignore[no-any-return]

    @property
    def available(self) -> bool:
        """Stay available while the mower exists, independent of transient
        connection drops, so mission events keep flowing after a reconnect."""
        return self.basic_data.lawn_mower is not None

    async def async_added_to_hass(self) -> None:
        """Seed the current phase (without firing) and track transitions."""
        await super().async_added_to_hass()
        # Record the phase we start in so we don't fire a spurious event for
        # the state that was already present before the entity existed.
        self._last_phase = self._compute_phase()
        self._was_complete = (
            self.hub.mission_state == MissionState.MISSION_STATE_COMPLETE
        )
        self.hub.register_state_listener(self._on_hub_state)

    def _compute_phase(self) -> str:
        """Derive the semantic phase from the hub state (mirrors lawn_mower)."""
        hub = self.hub
        # Only a real device fault is an ``error`` event. A dropped MQTT
        # connection is routine (mower asleep/docked/after a DHCP IP change)
        # and must not fire a spurious error event on every cycle; the phase
        # then falls back to the last known mission state. The lawn_mower
        # entity already surfaces the connection loss as an ERROR state.
        if hub.has_error:
            return "error"
        state = hub.mission_state
        if state == MissionState.MISSION_STATE_RUNNING:
            if hub.mission in MOW_MISSIONS:
                if hub.sub_mission == SubMission.SUB_MISSION_FLEXIBLE_STATION_WAIT:
                    return "paused"
                if hub.sub_mission == SubMission.SUB_MISSION_SAVING_MAP:
                    return "docked"
                return "mowing"
            if hub.mission in RECHARGE_MISSIONS:
                return "returning"
            return "docked"
        if state == MissionState.MISSION_STATE_PAUSE:
            return "paused"
        return "docked"

    def _event_attributes(self) -> dict[str, Any]:
        """Snapshot the raw mission fields as event attributes."""
        hub = self.hub
        return {
            "mission": hub.mission.value if hub.mission is not None else None,
            "sub_mission": (
                hub.sub_mission.value if hub.sub_mission is not None else None
            ),
            "state": (
                hub.mission_state.value if hub.mission_state is not None else None
            ),
            "back_to_station_reason": hub.back_to_station_reason,
            "has_error": hub.has_error,
        }

    def _detect_event(self) -> tuple[str, dict[str, Any]] | None:
        """Return the (event_type, attributes) to fire, or None if unchanged."""
        completed = self.hub.mission_state == MissionState.MISSION_STATE_COMPLETE
        phase = self._compute_phase()
        attributes = self._event_attributes()

        with self._detect_lock:
            # Completion is a distinct, momentary signal worth its own event.
            if completed and not self._was_complete:
                self._was_complete = True
                self._last_phase = phase
                return EVENT_COMPLETED, attributes
            if not completed:
                self._was_complete = False

            if phase != self._last_phase:
                self._last_phase = phase
                return _PHASE_EVENTS[phase], attributes
            return None

    def _on_hub_state(self) -> None:
        """Handle a hub state change (may run on the MQTT worker thread)."""
        detected = self._detect_event()
        if detected is None:
            return
        self._pending.append(detected)
        # Fire on the event loop; _trigger_event / state writes are not
        # thread-safe.
        self.hass.add_job(self._async_drain_pending)

    async def _async_drain_pending(self) -> None:
        """Fire any queued events on the event loop."""
        fired = False
        while self._pending:
            event_type, attributes = self._pending.popleft()
            self._trigger_event(event_type, attributes)
            fired = True
        if fired:
            self.async_write_ha_state()
