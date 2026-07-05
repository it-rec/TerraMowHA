"""Calendar entity for the TerraMow integration.

The mower publishes its next scheduled mowing slot on dp_138 as a start/end
time-of-day. This surfaces that slot as a read-only Home Assistant calendar so
the upcoming mow shows up on the calendar card and can drive time-based
automations, instead of being buried in a single "next start" sensor string.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TerraMowConfigEntry
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

EVENT_SUMMARY = "Mowing"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow schedule calendar."""
    basic_data = config_entry.runtime_data
    async_add_entities([TerraMowScheduleCalendar(basic_data, hass)])


class TerraMowScheduleCalendar(PushUpdateMixin, TerraMowEntity, CalendarEntity):
    """Read-only calendar exposing the mower's next scheduled mow (dp_138)."""

    _attr_translation_key = "schedule"
    _unique_id_suffix = "schedule"
    _push_dp_ids = (138,)

    def _build_event(self, now: datetime) -> CalendarEvent | None:
        """Build the next mowing event relative to ``now`` (None if unset)."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return None
        data = lawn_mower.schedule_data
        if not data or not data.get("exist", False):
            return None

        start_time = data.get("start_time", {})
        if "hour" not in start_time or "minute" not in start_time:
            return None

        start = now.replace(
            hour=start_time["hour"], minute=start_time["minute"], second=0, microsecond=0
        )
        end_time = data.get("end_time", {})
        if "hour" in end_time and "minute" in end_time:
            end = now.replace(
                hour=end_time["hour"], minute=end_time["minute"], second=0, microsecond=0
            )
        else:
            end = start + timedelta(hours=1)

        # An end at/before the start means the slot runs past midnight.
        if end <= start:
            end += timedelta(days=1)
        # Once today's slot is over, the next occurrence is tomorrow.
        if now >= end:
            start += timedelta(days=1)
            end += timedelta(days=1)

        item_id = data.get("item_id")
        return CalendarEvent(
            start=start,
            end=end,
            summary=EVENT_SUMMARY,
            uid=str(item_id) if item_id is not None else None,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next (or currently active) mowing event."""
        return self._build_event(dt_util.now())

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return the scheduled event if it overlaps the requested window."""
        event = self._build_event(dt_util.now())
        if event is None:
            return []
        if event.start < end_date and event.end > start_date:
            return [event]
        return []
