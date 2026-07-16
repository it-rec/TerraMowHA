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
from typing import Any, cast

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TerraMowBasicData, TerraMowConfigEntry
from .entity import TerraMowEntity
from .hub import MissionState, TerraMowHub, compute_phase

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
        # Last (display_sub_mission, display_mission_state) written to HA, so a
        # map-save decay (issue #142) re-writes the entity even when the phase
        # itself does not change (the mower stays "docked" throughout).
        self._shown_display: tuple[Any, Any] | None = None
        # _detect_event mutates _last_phase/_was_complete and is reachable from
        # both the event loop (dp_107 updates) and the MQTT worker thread
        # (connection-state changes), so guard the read-modify-write.
        self._detect_lock = threading.Lock()

    @property
    def hub(self) -> TerraMowHub:
        """Return the hub behind this entity."""
        return cast("TerraMowHub", self.basic_data.lawn_mower)

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
        self._shown_display = self._display_key()
        self.async_on_remove(self.hub.register_state_listener(self._on_hub_state))

    def _compute_phase(self) -> str:
        """Derive the semantic phase from the hub state (mirrors lawn_mower)."""
        # Only a real device fault is an ``error`` event. A dropped MQTT
        # connection must not fire a spurious error event on every cycle;
        # the phase then falls back to the last known mission state. The
        # lawn_mower entity already surfaces the connection loss as an
        # ERROR state (see compute_phase).
        return compute_phase(self.hub, connection_error_is_error=False)

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
            # Mirror the *combined* fault signal that actually fires the ``error``
            # event (compute_phase reads ``has_active_error``), not the raw dp_107
            # flag. A fault that only populates the dp_116 active-error list leaves
            # dp_107 ``has_error`` false, which made the attribute contradict the
            # ``error`` event it was attached to (issue #171).
            "has_error": hub.has_active_error,
        }

    def _display_key(self) -> tuple[Any, Any]:
        """The decayed (sub_mission, mission_state) used to spot a map-save decay."""
        return (self.hub.display_sub_mission, self.hub.display_mission_state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Keep the map-save sub-mission/state live over the event snapshot.

        The firmware leaves ``sub_mission=SAVING_MAP`` / ``state=RUNNING`` set
        after docking and never clears it, so the snapshot taken when the
        "docked" event fired would otherwise freeze on "Saving Map" / "Running"
        for hours (issue #142). Home Assistant applies ``extra_state_attributes``
        after the event's own ``state_attributes``, so these override the frozen
        pair with the decayed ``display_*`` values, which fall back to idle once
        the save is done (100 % upload) or after the safety timeout.
        """
        sub = self.hub.display_sub_mission
        state = self.hub.display_mission_state
        return {
            "sub_mission": sub.value if sub is not None else None,
            "state": state.value if state is not None else None,
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
        # Re-write on a map-save decay even without a phase change: the mower
        # stays "docked" while SAVING_MAP settles to idle, so no event fires but
        # the displayed attributes still need to refresh (issue #142).
        if detected is None and self._display_key() == self._shown_display:
            return
        if detected is not None:
            self._pending.append(detected)
        # Fire on the event loop; _trigger_event / state writes are not
        # thread-safe. The coroutine is created on the loop thread so a
        # failed schedule can't leave an un-awaited coroutine behind.
        self.hass.loop.call_soon_threadsafe(self._schedule_drain)

    def _schedule_drain(self) -> None:
        """Create the drain task (must run on the event loop)."""
        self.hass.async_create_task(self._async_drain_pending())

    async def _async_drain_pending(self) -> None:
        """Fire any queued events on the event loop."""
        fired = False
        while self._pending:
            event_type, attributes = self._pending.popleft()
            self._trigger_event(event_type, attributes)
            fired = True
        display = self._display_key()
        if fired or display != self._shown_display:
            self._shown_display = display
            self.async_write_ha_state()
