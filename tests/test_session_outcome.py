"""Session completion/reset semantics for the dp_113 session sensors.

Issues #204/#207, one design: the hub latches how the last mow session ended
(``session_outcome``), the session sensors snap progress to 100 % on a
completed job (never on an aborted one) and reset the time/area counters to
0, and the map card's job chip mirrors the same rules. Raw dp_113 values
stay reachable through ``raw_*`` attributes per the AGENTS.md derived-state
contract.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.map_card import build_status_payload
from custom_components.terramow.sensor import (
    _current_session_area,
    _current_session_attributes,
    _current_session_progress,
    _current_session_time,
    _raw_session_progress,
    _raw_session_time,
    _session_outcome_attributes,
)


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.150", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _mission(hub: TerraMowHub, mission: str, state: str) -> None:
    asyncio.run(
        hub.on_mission_status(json.dumps({"mission": mission, "state": state}))
    )


def _work(hub: TerraMowHub, **fields) -> None:
    asyncio.run(hub.on_current_work_data(json.dumps(fields)))


RUNNING_WORK = {
    "type": "MAP_AREA_TYPE_CLEANING",
    "total_area": 3000,  # 300 m²
    "clean_area": 2100,  # 210 m² -> 70 %
    "work_duration": 5400,
    "is_completed": False,
}


def _run_session(hub: TerraMowHub) -> None:
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    _work(hub, **RUNNING_WORK)


# ---------------------------------------------------------------------------
# hub.session_outcome
# ---------------------------------------------------------------------------


def test_outcome_latches_on_complete_and_abort() -> None:
    hub = _hub()
    _run_session(hub)
    assert hub.session_outcome is None  # running

    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert hub.session_outcome == "completed"

    _run_session(hub)
    assert hub.session_outcome is None  # a new session clears the latch

    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_ABORT")
    assert hub.session_outcome == "aborted"


def test_complete_without_a_mow_session_sets_no_outcome() -> None:
    hub = _hub()
    _mission(hub, "MISSION_RECHARGE", "MISSION_STATE_COMPLETE")
    assert hub.session_outcome is None


def test_device_is_completed_flag_is_the_fallback() -> None:
    hub = _hub()
    # e.g. HA restarted after the session finished: no dp_107 frame was seen
    _work(hub, **{**RUNNING_WORK, "is_completed": True})
    assert hub.session_outcome == "completed"

    hub = _hub()
    _work(hub, **RUNNING_WORK)  # is_completed False
    assert hub.session_outcome is None


def test_is_completed_is_ignored_while_a_session_is_latched() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    # a stale snapshot from the previous job may still say completed
    _work(hub, **{**RUNNING_WORK, "is_completed": True})
    assert hub.session_outcome is None


def test_malformed_work_data_sets_no_outcome() -> None:
    hub = _hub()
    hub._current_work_data = ["not", "a", "dict"]
    assert hub.session_outcome is None


# ---------------------------------------------------------------------------
# session sensors
# ---------------------------------------------------------------------------


def test_completed_session_snaps_progress_and_resets_counters() -> None:
    hub = _hub()
    _run_session(hub)
    assert _current_session_progress(hub) == 70.0
    assert _current_session_area(hub) == 210.0
    assert _current_session_time(hub) == 5400

    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert _current_session_progress(hub) == 100.0
    assert _current_session_area(hub) == 0.0
    assert _current_session_time(hub) == 0


def test_aborted_session_resets_without_the_100_percent_snap() -> None:
    hub = _hub()
    _run_session(hub)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_ABORT")
    assert _current_session_progress(hub) == 0.0
    assert _current_session_area(hub) == 0.0
    assert _current_session_time(hub) == 0


def test_raw_values_stay_reachable_via_attributes() -> None:
    hub = _hub()
    _run_session(hub)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")

    area_attrs = _current_session_attributes(hub)
    assert area_attrs["session_outcome"] == "completed"
    assert area_attrs["raw_area"] == 210.0
    assert area_attrs["work_type"] == "MAP_AREA_TYPE_CLEANING"

    progress_attrs = _session_outcome_attributes(
        _raw_session_progress, "raw_progress"
    )(hub)
    assert progress_attrs == {
        "session_outcome": "completed",
        "raw_progress": 70.0,
    }

    time_attrs = _session_outcome_attributes(_raw_session_time, "raw_duration")(hub)
    assert time_attrs == {"session_outcome": "completed", "raw_duration": 5400}


def test_outcome_attributes_are_empty_while_running() -> None:
    hub = _hub()
    _run_session(hub)
    assert _session_outcome_attributes(_raw_session_progress, "raw_progress")(
        hub
    ) == {}
    assert "session_outcome" not in _current_session_attributes(hub)


def test_outcome_attributes_omit_an_unreported_raw_value() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    # dp_113 never arrived: outcome is known but there is no raw value
    attrs = _session_outcome_attributes(_raw_session_time, "raw_duration")(hub)
    assert attrs == {"session_outcome": "completed"}


# ---------------------------------------------------------------------------
# map card job chip
# ---------------------------------------------------------------------------


def test_card_job_chip_mirrors_the_session_sensors() -> None:
    hub = _hub()
    _run_session(hub)
    assert build_status_payload(hub)["work"] == {
        "progress": 70.0,
        "area_m2": 210.0,
        "duration_s": 5400,
    }

    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert build_status_payload(hub)["work"] == {"progress": 100.0}

    _run_session(hub)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_ABORT")
    assert build_status_payload(hub)["work"] is None
