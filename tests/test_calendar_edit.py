"""Tests for editing the schedule calendar (dp_122 ADD / MODIFY / DELETE).

The device stores weekdays and local wall-clock times only, so the calendar
maps the HA event subset it can express and rejects everything else before
any write. These tests pin that mapping: timed and all-day windows, one-time
(``run_once``) limits, DAILY/WEEKLY rules, whole-series-only edits, rule
preservation on update and the time-slot availability gate.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.calendar.const import CalendarEntityFeature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.calendar import TerraMowScheduleCalendar
from custom_components.terramow.hub import TerraMowHub

# Saturday 08:00 UTC; the HA time zone is pinned to UTC below.
NOW = datetime(2026, 7, 4, 8, 0, tzinfo=UTC)
SAT = "WEEK_DAY_SATURDAY"


@pytest.fixture(autouse=True)
def utc_time_zone():
    previous = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(UTC)
    yield
    dt_util.set_default_time_zone(previous)


def _cal(
    *, received: bool = True, mode: str | None = None
) -> tuple[TerraMowScheduleCalendar, TerraMowHub]:
    basic_data = TerraMowBasicData(host="192.0.2.161", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    basic_data.lawn_mower = hub
    hub._full_schedule_received = received
    hub._full_schedule = {"items": []}
    if mode is not None:
        hub._full_schedule["schedule_mode"] = mode
    hub.async_add_schedule = AsyncMock(return_value=5)  # type: ignore[method-assign]
    hub.async_modify_schedule = AsyncMock()  # type: ignore[method-assign]
    hub.async_delete_schedule = AsyncMock()  # type: ignore[method-assign]
    cal = TerraMowScheduleCalendar(basic_data, hub.hass)
    cal.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return cal, hub


def _run(coro: Any) -> Any:
    with patch("custom_components.terramow.calendar.dt_util.now", return_value=NOW):
        return asyncio.run(coro)


def _config(mock: AsyncMock) -> dict[str, Any]:
    item = mock.await_args.args[-1]
    assert item["schedule_type"] == "SCHEDULE_TYPE_GLOBAL_V2"
    return item["global_schedule_v2"]["basic_config"]


def _at(hour: int, minute: int = 0, day: int = 4) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=UTC)


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


def test_features_follow_time_slot_list() -> None:
    edit = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
    )
    assert _cal()[0].supported_features == edit
    assert _cal(received=False)[0].supported_features == CalendarEntityFeature(0)
    frequency = _cal(mode="SCHEDULE_MODE_FREQUENCY")[0]
    assert frequency.supported_features == CalendarEntityFeature(0)
    with pytest.raises(ServiceValidationError) as err:
        _run(frequency.async_delete_event("1"))
    assert err.value.translation_key == "schedule_unavailable"

    cal, _ = _cal()
    cal.basic_data.lawn_mower = None
    assert cal.supported_features == CalendarEntityFeature(0)
    with pytest.raises(ServiceValidationError):
        _run(cal.async_create_event(dtstart=_at(9), dtend=_at(10)))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rrule", "week_days"),
    [
        ("FREQ=WEEKLY", [SAT]),
        ("RRULE:FREQ=WEEKLY;INTERVAL=1;WKST=MO;BYDAY=SA,MO", ["WEEK_DAY_MONDAY", SAT]),
        (
            "FREQ=DAILY",
            [
                "WEEK_DAY_MONDAY",
                "WEEK_DAY_TUESDAY",
                "WEEK_DAY_WEDNESDAY",
                "WEEK_DAY_THURSDAY",
                "WEEK_DAY_FRIDAY",
                SAT,
                "WEEK_DAY_SUNDAY",
            ],
        ),
    ],
)
def test_create_recurring(rrule: str, week_days: list[str]) -> None:
    cal, hub = _cal()
    _run(cal.async_create_event(dtstart=_at(9, 30), dtend=_at(11), rrule=rrule))
    config = _config(hub.async_add_schedule)
    assert config == {
        "week_days": week_days,
        "start_time": {"hour": 9, "minute": 30},
        "end_time": {"hour": 11, "minute": 0},
        "disabled": False,
    }
    cal.async_write_ha_state.assert_called_once()


def test_create_recurring_window_already_started_is_allowed() -> None:
    # 07:00-09:00 on Saturday is in progress at 08:00; recurring is fine.
    cal, hub = _cal()
    _run(cal.async_create_event(dtstart=_at(7), dtend=_at(9), rrule="FREQ=WEEKLY"))
    assert hub.async_add_schedule.await_count == 1


def test_create_one_time_next_occurrence() -> None:
    cal, hub = _cal()
    _run(cal.async_create_event(dtstart=_at(9), dtend=_at(10)))
    config = _config(hub.async_add_schedule)
    assert config["week_days"] == [SAT]
    assert config["run_once"] is True


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (_at(7), _at(9)),  # already started
        (_at(8), _at(9)),  # starts exactly now
        (_at(9, day=11), _at(10, day=11)),  # one week ahead: not the next one
    ],
)
def test_create_one_time_outside_next_window(start: datetime, end: datetime) -> None:
    cal, hub = _cal()
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_create_event(dtstart=start, dtend=end))
    assert err.value.translation_key == "calendar_one_time_window"
    hub.async_add_schedule.assert_not_awaited()


def test_create_all_day_single_day() -> None:
    cal, hub = _cal()
    _run(
        cal.async_create_event(
            dtstart=date(2026, 7, 6), dtend=date(2026, 7, 7), rrule="FREQ=WEEKLY"
        )
    )
    config = _config(hub.async_add_schedule)
    assert config["week_days"] == ["WEEK_DAY_MONDAY"]
    assert config["start_time"] == {"hour": 0, "minute": 0}
    assert config["end_time"] == {"hour": 23, "minute": 59}


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 7, 6), date(2026, 7, 8)),  # multi-day all-day
        (date(2026, 7, 6), _at(10, day=6)),  # mixed types
        (_at(22), _at(1, day=5)),  # overnight
        (_at(10), _at(10)),  # zero length
        (_at(11), _at(10)),  # end before start
        (_at(9).replace(second=30), _at(10)),  # not whole minutes
        (_at(9), _at(10).replace(microsecond=5)),
    ],
)
def test_create_invalid_window(start: Any, end: Any) -> None:
    cal, hub = _cal()
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_create_event(dtstart=start, dtend=end, rrule="FREQ=WEEKLY"))
    assert err.value.translation_key == "calendar_invalid_window"
    hub.async_add_schedule.assert_not_awaited()


@pytest.mark.parametrize(
    "rrule",
    [
        "FREQ=MONTHLY",
        "FREQ=WEEKLY;INTERVAL=2",
        "FREQ=DAILY;INTERVAL=3",
        "FREQ=WEEKLY;COUNT=3",
        "FREQ=WEEKLY;UNTIL=20261231",
        "FREQ=DAILY;BYDAY=MO",
        "FREQ=WEEKLY;BYDAY=MO",  # does not contain the start day (Sat)
        "FREQ=WEEKLY;BYDAY=1SA",
        "FREQ=WEEKLY;FREQ=DAILY",
        "FREQ",
        "INTERVAL=1",
    ],
)
def test_create_unsupported_rule(rrule: str) -> None:
    cal, hub = _cal()
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_create_event(dtstart=_at(9), dtend=_at(10), rrule=rrule))
    assert err.value.translation_key == "calendar_unsupported_rule"
    hub.async_add_schedule.assert_not_awaited()


def test_create_uses_local_time_zone() -> None:
    # 07:00 UTC is 09:00 in Berlin (summer): the device stores local time.
    berlin = timezone(timedelta(hours=2))
    cal, hub = _cal()
    with patch(
        "custom_components.terramow.calendar.dt_util.as_local",
        side_effect=lambda value: value.astimezone(berlin),
    ):
        _run(cal.async_create_event(dtstart=_at(7), dtend=_at(8), rrule="FREQ=WEEKLY"))
    config = _config(hub.async_add_schedule)
    assert config["start_time"] == {"hour": 9, "minute": 0}


# ---------------------------------------------------------------------------
# update / delete
# ---------------------------------------------------------------------------


def _with_item(hub: TerraMowHub, item_id: int, **config: Any) -> None:
    item: dict[str, Any] = {
        "schedule_type": "SCHEDULE_TYPE_GLOBAL_V2",
        "global_schedule_v2": {"basic_config": config},
    }
    if item_id:
        item["id"] = item_id
    hub._full_schedule["items"].append(item)


def test_update_with_rule() -> None:
    cal, hub = _cal()
    _with_item(hub, 3, week_days=["WEEK_DAY_MONDAY"])
    _run(
        cal.async_update_event(
            "3",
            {"dtstart": _at(9), "dtend": _at(10), "rrule": "FREQ=WEEKLY;BYDAY=SA,SU"},
            recurrence_id="",
            recurrence_range="",
        )
    )
    assert hub.async_modify_schedule.await_args.args[0] == 3
    config = _config(hub.async_modify_schedule)
    assert config["week_days"] == [SAT, "WEEK_DAY_SUNDAY"]
    assert "disabled" not in config  # preserved by MODIFY
    assert "run_once" not in config
    cal.async_write_ha_state.assert_called_once()


def test_update_without_rule_keeps_weekdays() -> None:
    cal, hub = _cal()
    _with_item(hub, 0, week_days=[SAT, "WEEK_DAY_TUESDAY", "BOGUS"])
    _run(cal.async_update_event("0", {"dtstart": _at(14), "dtend": _at(15)}))
    config = _config(hub.async_modify_schedule)
    assert config["week_days"] == [SAT, "WEEK_DAY_TUESDAY"]
    assert config["start_time"] == {"hour": 14, "minute": 0}


def test_update_without_rule_moved_off_its_weekdays() -> None:
    cal, hub = _cal()
    _with_item(hub, 3, week_days=["WEEK_DAY_MONDAY"])
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_update_event("3", {"dtstart": _at(14), "dtend": _at(15)}))
    assert err.value.translation_key == "calendar_unsupported_rule"
    hub.async_modify_schedule.assert_not_awaited()


def test_update_without_rule_keeps_one_time() -> None:
    cal, hub = _cal()
    _with_item(hub, 3, week_days=["WEEK_DAY_MONDAY"], run_once=True)
    _run(cal.async_update_event("3", {"dtstart": _at(14), "dtend": _at(15)}))
    config = _config(hub.async_modify_schedule)
    assert config["week_days"] == [SAT]
    assert config["run_once"] is True


def test_update_explicit_no_rule_becomes_one_time() -> None:
    cal, hub = _cal()
    _with_item(hub, 3, week_days=[SAT])
    _run(
        cal.async_update_event(
            "3", {"dtstart": _at(14), "dtend": _at(15), "rrule": None}
        )
    )
    assert _config(hub.async_modify_schedule)["run_once"] is True


def test_update_item_missing_from_cache() -> None:
    # Unknown locally: no weekdays to keep, so the rule is required.
    cal, hub = _cal()
    hub._full_schedule["items"].append("junk")
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_update_event("8", {"dtstart": _at(14), "dtend": _at(15)}))
    assert err.value.translation_key == "calendar_unsupported_rule"


@pytest.mark.parametrize(
    ("recurrence_id", "recurrence_range"),
    [("20260704T090000", None), (None, "THISANDFUTURE")],
)
def test_single_occurrence_edits_rejected(
    recurrence_id: str | None, recurrence_range: str | None
) -> None:
    cal, hub = _cal()
    event = {"dtstart": _at(9), "dtend": _at(10)}
    for call in (
        cal.async_update_event("3", event, recurrence_id, recurrence_range),
        cal.async_delete_event("3", recurrence_id, recurrence_range),
    ):
        with pytest.raises(ServiceValidationError) as err:
            _run(call)
        assert err.value.translation_key == "calendar_whole_series_only"
    hub.async_modify_schedule.assert_not_awaited()
    hub.async_delete_schedule.assert_not_awaited()


@pytest.mark.parametrize("uid", ["abc", "-1"])
def test_invalid_uid(uid: str) -> None:
    cal, hub = _cal()
    with pytest.raises(ServiceValidationError) as err:
        _run(cal.async_delete_event(uid))
    assert err.value.translation_key == "calendar_invalid_uid"
    with pytest.raises(ServiceValidationError):
        _run(cal.async_update_event(uid, {"dtstart": _at(9), "dtend": _at(10)}))
    hub.async_delete_schedule.assert_not_awaited()


def test_delete_whole_series() -> None:
    cal, hub = _cal()
    _run(cal.async_delete_event("0", recurrence_id="", recurrence_range=""))
    hub.async_delete_schedule.assert_awaited_once_with(0)
    cal.async_write_ha_state.assert_called_once()
