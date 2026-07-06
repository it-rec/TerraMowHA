"""Calendar entity for the TerraMow integration.

Two data points describe the mowing schedule:

- dp_138 (official) is the single *next* upcoming slot, pushed by the device.
- dp_122 (unofficial, reverse-engineered) is the *full weekly schedule* — every
  time slot with its week-days and start/end. It is only sent in response to a
  ``SCHEDULE_CMD_TYPE_GET`` request, which the hub issues on connect.

When the full schedule is available the calendar renders every recurring slot
across the week; otherwise it falls back to the reliable dp_138 next-slot view.
See ``docs/en/developers/data_point_unofficial.md`` for the dp_122 payload.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

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

# dp_122 week-day enum -> Python weekday() index (Monday = 0).
_WEEKDAY_INDEX = {
    "WEEK_DAY_MONDAY": 0,
    "WEEK_DAY_TUESDAY": 1,
    "WEEK_DAY_WEDNESDAY": 2,
    "WEEK_DAY_THURSDAY": 3,
    "WEEK_DAY_FRIDAY": 4,
    "WEEK_DAY_SATURDAY": 5,
    "WEEK_DAY_SUNDAY": 6,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow schedule calendar."""
    basic_data = config_entry.runtime_data
    async_add_entities([TerraMowScheduleCalendar(basic_data, hass)])


class TerraMowScheduleCalendar(PushUpdateMixin, TerraMowEntity, CalendarEntity):
    """Read-only calendar of the mower's schedule.

    Renders the full weekly schedule (dp_122) when available, otherwise the
    official next scheduled mow (dp_138).
    """

    _attr_translation_key = "schedule"
    _unique_id_suffix = "schedule"
    _push_dp_ids = (138, 122)

    # -- Full weekly schedule (dp_122, unofficial) ---------------------------

    def _use_weekly(self) -> bool:
        """Whether the full weekly schedule (dp_122) is available."""
        lawn_mower = self.basic_data.lawn_mower
        return bool(lawn_mower is not None and lawn_mower.full_schedule)

    def _slot_from_config(
        self, anchor: datetime, config: dict[str, Any], item_id: Any
    ) -> CalendarEvent | None:
        """Build a mowing slot from one ``basic_config``, dated on ``anchor``.

        Only the time-of-day is taken from the config; the date comes from
        ``anchor``. An end at/before the start means the slot runs past midnight.
        """
        start_time = config.get("start_time", {})
        if "hour" not in start_time or "minute" not in start_time:
            return None

        start = anchor.replace(
            hour=start_time["hour"], minute=start_time["minute"], second=0, microsecond=0
        )
        end_time = config.get("end_time", {})
        if "hour" in end_time and "minute" in end_time:
            end = anchor.replace(
                hour=end_time["hour"], minute=end_time["minute"], second=0, microsecond=0
            )
        else:
            end = start + timedelta(hours=1)

        if end <= start:
            end += timedelta(days=1)

        return CalendarEvent(
            start=start,
            end=end,
            summary=EVENT_SUMMARY,
            uid=str(item_id) if item_id is not None else None,
        )

    def _weekly_events_on(self, anchor: datetime) -> list[CalendarEvent]:
        """Return every weekly slot that *starts* on ``anchor``'s date."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return []
        schedule = lawn_mower.full_schedule
        if not schedule or schedule.get("global_disabled", False):
            return []

        weekday = anchor.weekday()
        disabled_days = schedule.get("disabled_week_days") or []
        if any(_WEEKDAY_INDEX.get(day) == weekday for day in disabled_days):
            return []

        events: list[CalendarEvent] = []
        for item in schedule.get("items", []):
            if not isinstance(item, dict):
                continue
            schedule_v2 = item.get("global_schedule_v2")
            if not isinstance(schedule_v2, dict):
                continue
            config = schedule_v2.get("basic_config")
            if not isinstance(config, dict) or config.get("disabled", False):
                continue
            week_days = config.get("week_days") or []
            indices = {_WEEKDAY_INDEX[day] for day in week_days if day in _WEEKDAY_INDEX}
            if weekday not in indices:
                continue
            slot = self._slot_from_config(anchor, config, item.get("id"))
            if slot is not None:
                events.append(slot)
        return events

    def _next_weekly_event(self, now: datetime) -> CalendarEvent | None:
        """Return the active or next upcoming weekly event relative to ``now``."""
        upcoming: list[CalendarEvent] = []
        # Look back one day (for past-midnight slots) through a full week ahead.
        for offset in range(-1, 8):
            anchor = (now + timedelta(days=offset)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            for slot in self._weekly_events_on(anchor):
                if slot.start <= now < slot.end:
                    return slot
                if slot.start > now:
                    upcoming.append(slot)
        if not upcoming:
            return None
        return min(upcoming, key=lambda event: event.start)

    def _weekly_events_in_window(
        self, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return every weekly occurrence overlapping the ``[start, end)`` window."""
        events: list[CalendarEvent] = []
        day = (start_date - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        last_day = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= last_day:
            for slot in self._weekly_events_on(day):
                if slot.start < end_date and slot.end > start_date:
                    events.append(slot)
            day += timedelta(days=1)
        return events

    # -- Next-slot fallback (dp_138, official) -------------------------------

    def _slot_for_date(self, anchor: datetime) -> CalendarEvent | None:
        """Build the mowing slot that *starts* on ``anchor``'s date (or None).

        The device reports only a time-of-day; the returned slot uses
        ``anchor``'s date for the start. An end at/before the start means the
        slot runs past midnight and ends the following day.
        """
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return None
        data = lawn_mower.schedule_data
        if not data or not data.get("exist", False):
            return None

        start_time = data.get("start_time", {})
        if "hour" not in start_time or "minute" not in start_time:
            return None

        start = anchor.replace(
            hour=start_time["hour"], minute=start_time["minute"], second=0, microsecond=0
        )
        end_time = data.get("end_time", {})
        if "hour" in end_time and "minute" in end_time:
            end = anchor.replace(
                hour=end_time["hour"], minute=end_time["minute"], second=0, microsecond=0
            )
        else:
            end = start + timedelta(hours=1)

        # An end at/before the start means the slot runs past midnight.
        if end <= start:
            end += timedelta(days=1)

        item_id = data.get("item_id")
        return CalendarEvent(
            start=start,
            end=end,
            summary=EVENT_SUMMARY,
            uid=str(item_id) if item_id is not None else None,
        )

    def _build_event(self, now: datetime) -> CalendarEvent | None:
        """Build the currently-active or next mowing event relative to ``now``."""
        today = self._slot_for_date(now)
        if today is None:
            return None

        # A slot that began yesterday may still be running (past-midnight
        # schedules), in which case it is the active event, not tonight's.
        yesterday = self._slot_for_date(now - timedelta(days=1))
        if yesterday is not None and yesterday.start <= now < yesterday.end:
            return yesterday

        # Once today's slot is over, the next occurrence is tomorrow.
        if now >= today.end:
            return self._slot_for_date(now + timedelta(days=1))
        return today

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next (or currently active) mowing event.

        Prefers the full weekly schedule (dp_122) when available, otherwise
        falls back to the official single-slot view (dp_138).
        """
        now = dt_util.now()
        if self._use_weekly():
            return self._next_weekly_event(now)
        return self._build_event(now)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return every mowing occurrence overlapping the window.

        Uses the full weekly schedule (dp_122) when available, otherwise the
        daily-recurring single slot (dp_138).
        """
        if self._use_weekly():
            return self._weekly_events_in_window(start_date, end_date)

        events: list[CalendarEvent] = []
        # The schedule recurs daily. Walk each day whose slot could overlap the
        # window (start one day early so a past-midnight slot begun the prior
        # day is included) and keep the ones that actually overlap.
        day = (start_date - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        last_day = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= last_day:
            slot = self._slot_for_date(day)
            if slot is not None and slot.start < end_date and slot.end > start_date:
                events.append(slot)
            day += timedelta(days=1)
        return events
