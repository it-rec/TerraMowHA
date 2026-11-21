"""Calendar entity for the TerraMow integration.

Two data points describe the mowing schedule:

- dp_138 (official) is the single *next* upcoming slot, pushed by the device.
- dp_122 (unofficial, reverse-engineered) is the *full weekly schedule* — every
  time slot with its week-days and start/end. It is only sent in response to a
  ``SCHEDULE_CMD_TYPE_GET`` request, which the hub issues on connect.

When the full schedule is available the calendar renders every recurring slot
across the week; otherwise it falls back to the reliable dp_138 next-slot view.

Once a valid time-slot schedule list has been read the calendar is editable:
creating, updating and deleting events maps to the vendor-documented dp_122
``ADD`` / ``MODIFY`` / ``DELETE`` commands (see "Schedule Control" in
``docs/en/developers/data_point.md``). The device stores weekdays and local
wall-clock times only, so the calendar accepts the subset it can express:

- a timed window on one local day at whole minutes (end after start), or a
  single all-day day (device window 00:00-23:59);
- no repeat -> ``run_once`` on the start weekday, only for the next
  occurrence (start in the future, within 7 days);
- ``FREQ=DAILY`` (all seven weekdays) or ``FREQ=WEEKLY`` with an optional
  ``BYDAY`` set containing the start weekday; ``INTERVAL`` must be 1, and
  ``COUNT`` / ``UNTIL`` are rejected (the device has no end date).

Edits always affect the whole device item (series). Summaries, descriptions
and locations are not stored on the device and are not persisted.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.components.calendar.const import (
    EVENT_END,
    EVENT_RRULE,
    EVENT_START,
    CalendarEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TerraMowConfigEntry
from .const import DOMAIN
from .entity import TerraMowEntity
from .entity_utils import PushUpdateMixin
from .hub import TerraMowHub

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
# Python weekday() index -> dp_122 week-day enum; RFC 5545 BYDAY tokens.
_INDEX_WEEKDAY = {index: day for day, index in _WEEKDAY_INDEX.items()}
_BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

# A one-time (run_once) event may only target the next occurrence of its
# weekday/time: the device stores no date, so anything later is ambiguous.
ONE_TIME_HORIZON = timedelta(days=7)

_EDIT_FEATURES = (
    CalendarEntityFeature.CREATE_EVENT
    | CalendarEntityFeature.UPDATE_EVENT
    | CalendarEntityFeature.DELETE_EVENT
)


def _invalid(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def _weekly_rrule(week_days: list[Any]) -> str:
    """RRULE describing a device item's weekdays (in week order)."""
    indices = sorted(
        {_WEEKDAY_INDEX[day] for day in week_days if day in _WEEKDAY_INDEX}
    )
    return "FREQ=WEEKLY;BYDAY=" + ",".join(_BYDAY[index] for index in indices)


def _rule_week_days(rrule: str, start_weekday: int) -> list[str]:
    """Map a supported RRULE to device weekdays (week order), else raise.

    Supports ``FREQ=DAILY`` and ``FREQ=WEEKLY`` with optional ``INTERVAL=1``,
    ``WKST`` and (weekly only) unnumbered ``BYDAY`` containing the start day.
    """
    parts: dict[str, str] = {}
    for chunk in rrule.upper().removeprefix("RRULE:").split(";"):
        key, sep, value = chunk.partition("=")
        if not sep or key in parts:
            raise _invalid("calendar_unsupported_rule")
        parts[key] = value
    freq = parts.pop("FREQ", None)
    interval = parts.pop("INTERVAL", "1")
    parts.pop("WKST", None)
    byday = parts.pop("BYDAY", None)
    if parts or interval != "1" or freq not in ("DAILY", "WEEKLY"):
        raise _invalid("calendar_unsupported_rule")
    if freq == "DAILY":
        if byday is not None:
            raise _invalid("calendar_unsupported_rule")
        return [_INDEX_WEEKDAY[index] for index in range(7)]
    days = byday.split(",") if byday else [_BYDAY[start_weekday]]
    if any(day not in _BYDAY for day in days) or _BYDAY[start_weekday] not in days:
        raise _invalid("calendar_unsupported_rule")
    indices = sorted({_BYDAY.index(day) for day in days})
    return [_INDEX_WEEKDAY[index] for index in indices]


def _event_window(
    dtstart: Any, dtend: Any
) -> tuple[datetime, tuple[int, int, int, int]]:
    """Validate an event's start/end; return the local start and device times.

    A timed event must start and end on the same local day at whole minutes
    with end after start (no overnight windows). A single all-day day maps
    to the device window 00:00-23:59 (HA's all-day end date is exclusive).
    """
    if isinstance(dtstart, datetime) and isinstance(dtend, datetime):
        start = dt_util.as_local(dtstart)
        end = dt_util.as_local(dtend)
        if (
            start.date() != end.date()
            or end <= start
            or start.second
            or start.microsecond
            or end.second
            or end.microsecond
        ):
            raise _invalid("calendar_invalid_window")
        return start, (start.hour, start.minute, end.hour, end.minute)
    if (
        isinstance(dtstart, date)
        and isinstance(dtend, date)
        and not isinstance(dtstart, datetime)
        and not isinstance(dtend, datetime)
        and dtend == dtstart + timedelta(days=1)
    ):
        start = datetime.combine(
            dtstart, time(), tzinfo=dt_util.get_default_time_zone()
        )
        return start, (0, 0, 23, 59)
    raise _invalid("calendar_invalid_window")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TerraMow schedule calendar."""
    basic_data = config_entry.runtime_data
    async_add_entities([TerraMowScheduleCalendar(basic_data, hass)])


class TerraMowScheduleCalendar(PushUpdateMixin, TerraMowEntity, CalendarEntity):
    """Calendar of the mower's schedule (editable, see module docstring).

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
        self,
        anchor: datetime,
        config: dict[str, Any],
        item_id: Any,
        rrule: str | None = None,
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
            uid=str(item_id),
            rrule=rrule,
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
            # Protobuf omits a zero id; recurring items carry their RRULE so
            # the HA editor shows (and edits) the whole device series.
            rrule = None if config.get("run_once") else _weekly_rrule(week_days)
            slot = self._slot_from_config(anchor, config, item.get("id", 0), rrule)
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

    # -- Editing (dp_122 ADD / MODIFY / DELETE) ------------------------------

    @property
    def supported_features(self) -> CalendarEntityFeature:
        """Editable once a valid time-slot schedule list has been read."""
        hub = self.basic_data.lawn_mower
        if hub is not None and hub.schedule_editable:
            return _EDIT_FEATURES
        return CalendarEntityFeature(0)

    def _require_hub(self) -> TerraMowHub:
        hub: TerraMowHub | None = self.basic_data.lawn_mower
        if hub is None or not hub.schedule_editable:
            raise _invalid("schedule_unavailable")
        return hub

    @staticmethod
    def _item_id(uid: str) -> int:
        try:
            item_id = int(uid)
        except ValueError:
            raise _invalid("calendar_invalid_uid") from None
        if item_id < 0:
            raise _invalid("calendar_invalid_uid")
        return item_id

    @staticmethod
    def _build_item(
        event: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Translate an HA event into a device item (or raise).

        ``existing`` is the current device ``basic_config`` on update: an
        omitted RRULE keeps its weekdays/one-time choice, and ``disabled``
        is left out so MODIFY preserves the item's own flag.
        """
        start, (start_h, start_m, end_h, end_m) = _event_window(
            event[EVENT_START], event[EVENT_END]
        )
        if EVENT_RRULE in event or existing is None:
            rrule = event.get(EVENT_RRULE) or None
            run_once = rrule is None
            week_days = (
                [_INDEX_WEEKDAY[start.weekday()]]
                if rrule is None
                else _rule_week_days(rrule, start.weekday())
            )
        else:
            run_once = bool(existing.get("run_once"))
            current = existing.get("week_days") or []
            week_days = (
                [_INDEX_WEEKDAY[start.weekday()]]
                if run_once
                else [day for day in current if day in _WEEKDAY_INDEX]
            )
            if not run_once and _INDEX_WEEKDAY[start.weekday()] not in week_days:
                raise _invalid("calendar_unsupported_rule")
        if run_once:
            now = dt_util.now()
            if not now < start < now + ONE_TIME_HORIZON:
                raise _invalid("calendar_one_time_window")
        return TerraMowHub.build_schedule_item(
            week_days=week_days,
            start_hour=start_h,
            start_minute=start_m,
            end_hour=end_h,
            end_minute=end_m,
            disabled=None if existing is not None else False,
            run_once=run_once,
        )

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add a device schedule item for a new event."""
        hub = self._require_hub()
        item_id = await hub.async_add_schedule(self._build_item(kwargs))
        _LOGGER.debug("Calendar created schedule item %s", item_id)
        self.async_write_ha_state()

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Replace a device item; only whole-series edits are possible."""
        hub = self._require_hub()
        if recurrence_id or recurrence_range:
            raise _invalid("calendar_whole_series_only")
        item_id = self._item_id(uid)
        existing = next(
            (
                TerraMowHub._schedule_config(entry) or {}
                for entry in hub.full_schedule.get("items") or []
                if isinstance(entry, dict) and entry.get("id", 0) == item_id
            ),
            {},
        )
        await hub.async_modify_schedule(item_id, self._build_item(event, existing))
        self.async_write_ha_state()

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Delete a device item; only whole-series deletes are possible."""
        hub = self._require_hub()
        if recurrence_id or recurrence_range:
            raise _invalid("calendar_whole_series_only")
        await hub.async_delete_schedule(self._item_id(uid))
        self.async_write_ha_state()
