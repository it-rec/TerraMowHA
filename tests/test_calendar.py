"""Coverage for the mowing-schedule calendar entity.

Feeds dp_138 schedule slots and, against a fixed clock, asserts the calendar
surfaces the next (or currently active) mowing window, handles missing/rolled
schedules, past-midnight slots and the get-events window query.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.calendar import (
    EVENT_SUMMARY,
    TerraMowScheduleCalendar,
    async_setup_entry,
)
from custom_components.terramow.hub import TerraMowHub

NOW = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.160", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def _cal(hub: TerraMowHub) -> TerraMowScheduleCalendar:
    return TerraMowScheduleCalendar(hub.basic_data, hub.hass)


def _feed(hub: TerraMowHub, payload: dict) -> None:
    asyncio.run(hub.on_schedule_data(json.dumps(payload)))


def _event_at(cal: TerraMowScheduleCalendar, now: datetime):
    with patch("custom_components.terramow.calendar.dt_util.now", return_value=now):
        return cal.event


# ---------------------------------------------------------------------------
# platform setup
# ---------------------------------------------------------------------------


def test_async_setup_entry_creates_calendar() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(runtime_data=hub.basic_data)
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert len(added) == 1
    assert isinstance(added[0], TerraMowScheduleCalendar)


# ---------------------------------------------------------------------------
# no-event paths
# ---------------------------------------------------------------------------


def test_event_none_without_lawn_mower() -> None:
    hub = _hub()
    hub.basic_data.lawn_mower = None
    assert _event_at(_cal(hub), NOW) is None


def test_event_none_when_no_schedule() -> None:
    hub = _hub()
    cal = _cal(hub)
    assert _event_at(cal, NOW) is None  # no dp_138 yet
    _feed(hub, {"exist": False})
    assert _event_at(cal, NOW) is None


def test_event_none_when_start_time_incomplete() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(hub, {"exist": True, "start_time": {"hour": 9}})
    assert _event_at(cal, NOW) is None


# ---------------------------------------------------------------------------
# upcoming / active / rolled-over events
# ---------------------------------------------------------------------------


def test_upcoming_event_today() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "item_id": 3,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    event = _event_at(cal, NOW)  # 08:00 -> today's 09:05 slot is upcoming
    assert event is not None
    assert event.start == datetime(2026, 7, 4, 9, 5, tzinfo=timezone.utc)
    assert event.end == datetime(2026, 7, 4, 11, 30, tzinfo=timezone.utc)
    assert event.summary == EVENT_SUMMARY
    assert event.uid == "3"


def test_active_event_is_returned_while_running() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    # 10:00 is inside the window -> the active slot (today) is returned
    event = _event_at(cal, datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc))
    assert event is not None
    assert event.start == datetime(2026, 7, 4, 9, 5, tzinfo=timezone.utc)
    assert event.uid is None  # no item_id -> no uid


def test_event_rolls_to_tomorrow_after_end() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    # 12:00 is past today's end -> the next occurrence is tomorrow
    event = _event_at(cal, datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc))
    assert event is not None
    assert event.start == datetime(2026, 7, 5, 9, 5, tzinfo=timezone.utc)


def test_missing_end_time_defaults_to_one_hour() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(hub, {"exist": True, "start_time": {"hour": 9, "minute": 0}})
    event = _event_at(cal, NOW)
    assert event is not None
    assert event.end - event.start == (
        datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
        - datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc)
    )


def test_past_midnight_slot_extends_end_by_a_day() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 23, "minute": 0},
            "end_time": {"hour": 1, "minute": 0},
        },
    )
    event = _event_at(cal, NOW)  # 08:00 -> tonight 23:00 to 01:00 next day
    assert event is not None
    assert event.start == datetime(2026, 7, 4, 23, 0, tzinfo=timezone.utc)
    assert event.end == datetime(2026, 7, 5, 1, 0, tzinfo=timezone.utc)


def test_active_past_midnight_slot_returns_the_running_slot() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 23, "minute": 0},
            "end_time": {"hour": 1, "minute": 0},
        },
    )
    # 00:30 is inside the slot that *began the previous day* at 23:00; it must be
    # reported as the currently-running event, not tonight's upcoming one.
    event = _event_at(cal, datetime(2026, 7, 4, 0, 30, tzinfo=timezone.utc))
    assert event is not None
    assert event.start == datetime(2026, 7, 3, 23, 0, tzinfo=timezone.utc)
    assert event.end == datetime(2026, 7, 4, 1, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# async_get_events window query
# ---------------------------------------------------------------------------


def _get_events(cal, start, end, now=NOW):
    with patch("custom_components.terramow.calendar.dt_util.now", return_value=now):
        return asyncio.run(cal.async_get_events(cal.hass, start, end))


def test_get_events_returns_event_in_window() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    events = _get_events(
        cal,
        datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1


def test_get_events_excludes_event_outside_window() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    events = _get_events(
        cal,
        datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 4, 13, 0, tzinfo=timezone.utc),
    )
    assert events == []


def test_get_events_returns_one_occurrence_per_day_in_wide_window() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    # a three-day window yields the daily-recurring slot once per day
    events = _get_events(
        cal,
        datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 7, 0, 0, tzinfo=timezone.utc),
    )
    assert [e.start for e in events] == [
        datetime(2026, 7, 4, 9, 5, tzinfo=timezone.utc),
        datetime(2026, 7, 5, 9, 5, tzinfo=timezone.utc),
        datetime(2026, 7, 6, 9, 5, tzinfo=timezone.utc),
    ]


def test_get_events_empty_without_schedule() -> None:
    hub = _hub()
    cal = _cal(hub)
    events = _get_events(
        cal,
        datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc),
    )
    assert events == []


# ---------------------------------------------------------------------------
# non-UTC timezone handling (dt_util.now() is the local, tz-aware clock)
# ---------------------------------------------------------------------------


def test_event_is_built_in_the_local_timezone() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    tz = timezone(timedelta(hours=-5))  # a non-UTC local clock
    event = _event_at(cal, datetime(2026, 7, 4, 8, 0, tzinfo=tz))
    assert event is not None
    # the slot is computed in the same local timezone as "now", not UTC
    assert event.start == datetime(2026, 7, 4, 9, 5, tzinfo=tz)
    assert event.end == datetime(2026, 7, 4, 11, 30, tzinfo=tz)
    assert event.start.utcoffset() == timedelta(hours=-5)


def test_event_rolls_over_in_local_timezone() -> None:
    hub = _hub()
    cal = _cal(hub)
    _feed(
        hub,
        {
            "exist": True,
            "start_time": {"hour": 9, "minute": 5},
            "end_time": {"hour": 11, "minute": 30},
        },
    )
    tz = timezone(timedelta(hours=9))  # e.g. JST
    # 12:00 local is past today's local end -> next occurrence is tomorrow, local
    event = _event_at(cal, datetime(2026, 7, 4, 12, 0, tzinfo=tz))
    assert event is not None
    assert event.start == datetime(2026, 7, 5, 9, 5, tzinfo=tz)
