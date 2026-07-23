"""Cycle-level mowed coverage (issue #202, approach B).

The firmware does not expose its bird-view raster locally, so the hub
accumulates its own coverage from the mow tracks — across sessions, until the
cycle ends. Covers accumulation (mid-session archive + final-leg harvest),
the clearing rules (manual clear, completed cycle + next start, map switch),
persistence and the scene feed.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    MAX_COVERAGE_SEGMENTS,
    TerraMowHub,
)

SEGMENT = [{"x": 0, "y": 0}, {"x": 5000, "y": 0}]


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.160", password="secret")
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


def _path(points, path_id: int = 101, map_id: int = 1) -> dict:
    return {
        "id": path_id,
        "map_id": map_id,
        "type": "NAVIGATION_PATH_TYPE_REALTIME",
        "points": [
            {"position": {"x": x, "y": y}, "type": kind}
            for x, y, kind in points
        ],
    }


def _clean(*coords):
    return [(x, y, "PATH_POINT_TYPE_CLEANING") for x, y in coords]


MOW_TRACK = _path(_clean((0, 0), (5000, 0), (5000, 1000), (0, 1000)))
DOCK_RESET = _path([], path_id=101)


# ---------------------------------------------------------------------------
# accumulation
# ---------------------------------------------------------------------------


def test_mid_session_archive_feeds_both_lists() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")  # recharge dock
    hub._apply_path_data(DOCK_RESET)
    assert len(hub.session_path_segments) == 1
    assert hub.coverage_segments == hub.session_path_segments


def test_complete_harvests_the_final_leg_and_marks_the_cycle_done() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert hub.session_path_segments == []
    assert len(hub.coverage_segments) == 1  # the final leg, harvested
    assert hub._coverage_cycle_done is True


def test_abort_harvests_but_does_not_end_the_cycle() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_ABORT")
    assert len(hub.coverage_segments) == 1
    assert hub._coverage_cycle_done is False


def test_harvest_skips_an_empty_or_degenerate_path() -> None:
    hub = _hub()
    hub._path_data = {}
    hub._harvest_current_path_into_coverage()  # no points at all
    assert hub.coverage_segments == []
    # identical cleaning points dedupe to a single pixel -> not a segment
    hub._path_data = _path(_clean((500, 500), (500, 500), (500, 500)))
    hub._harvest_current_path_into_coverage()
    assert hub.coverage_segments == []
    # single-point runs (isolated cleaning points around a transit) are
    # skipped before simplification — no drawable segment either
    hub._path_data = _path(
        [
            (500, 500, "PATH_POINT_TYPE_CLEANING"),
            (600, 600, "PATH_POINT_TYPE_RETURN"),
            (700, 700, "PATH_POINT_TYPE_CLEANING"),
        ]
    )
    hub._harvest_current_path_into_coverage()
    assert hub.coverage_segments == []


def test_coverage_is_capped() -> None:
    hub = _hub()
    hub._coverage_segments = [
        [{"x": i, "y": 0}, {"x": i, "y": 9000}]
        for i in range(MAX_COVERAGE_SEGMENTS)
    ]
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    hub._apply_path_data(DOCK_RESET)
    assert len(hub.coverage_segments) == MAX_COVERAGE_SEGMENTS


# ---------------------------------------------------------------------------
# clearing rules
# ---------------------------------------------------------------------------


def test_next_session_after_a_completed_cycle_clears_the_coverage() -> None:
    hub = _hub()
    hub._coverage_segments = [SEGMENT]
    hub._coverage_cycle_done = True
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    assert hub.coverage_segments == []
    assert hub._coverage_cycle_done is False


def test_next_session_mid_cycle_keeps_the_coverage() -> None:
    hub = _hub()
    hub._coverage_segments = [SEGMENT]
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    assert hub.coverage_segments == [SEGMENT]


def test_manual_end_clears_the_coverage_with_the_session() -> None:
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._coverage_segments = [SEGMENT]
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    _work(hub, clean_area=0, work_duration=0, is_completed=False)
    assert hub.coverage_segments == []
    assert hub._coverage_cycle_done is False


def test_map_switch_clears_the_coverage() -> None:
    hub = _hub()
    hub._map_data = {"id": 1}
    hub._coverage_segments = [SEGMENT]
    hub._apply_map_data({"id": 2, "width": 10, "height": 10, "resolution": 100})
    assert hub.coverage_segments == []


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_save_payload_carries_the_coverage_and_cycle_flag() -> None:
    hub = _hub()
    hub._coverage_segments = [SEGMENT]
    hub._coverage_cycle_done = True
    data = hub._session_path_save_data()
    assert data["coverage_segments"] == [SEGMENT]
    assert data["coverage_cycle_done"] is True


def test_restore_loads_the_coverage_immediately() -> None:
    hub = _hub()
    store = hub._get_session_path_store()
    store.async_load = AsyncMock(
        return_value={
            "map_id": 1,
            "segments": [],
            "coverage_segments": [SEGMENT],
            "coverage_cycle_done": True,
        }
    )
    asyncio.run(hub.async_restore_session_paths())
    assert hub.coverage_segments == [SEGMENT]
    assert hub._coverage_cycle_done is True
    assert hub._restored_session_paths is None  # nothing parked


def test_restore_map_mismatch_clears_the_coverage() -> None:
    hub = _hub()
    store = hub._get_session_path_store()
    store.async_load = AsyncMock(
        return_value={"map_id": 1, "coverage_segments": [SEGMENT]}
    )
    asyncio.run(hub.async_restore_session_paths())
    hub._apply_map_data({"id": 2, "width": 10, "height": 10, "resolution": 100})
    assert hub.coverage_segments == []


def test_adoption_merges_restored_segments_into_the_coverage() -> None:
    # Upgrade path: a store written before the coverage layer existed has
    # session segments but no coverage — adoption must not lose them there.
    hub = _hub()
    store = hub._get_session_path_store()
    store.async_load = AsyncMock(
        return_value={"map_id": None, "segments": [SEGMENT]}
    )
    asyncio.run(hub.async_restore_session_paths())
    _work(hub, clean_area=413)
    assert hub.session_path_segments == [SEGMENT]
    assert hub.coverage_segments == [SEGMENT]
    # a second adoption of identical data must not duplicate
    hub._restored_session_paths = [SEGMENT]
    _work(hub, clean_area=413)
    assert hub.coverage_segments.count(SEGMENT) == 1


# ---------------------------------------------------------------------------
# scene feed
# ---------------------------------------------------------------------------


def test_scene_payload_renders_the_cycle_coverage() -> None:
    from custom_components.terramow.map_card import build_scene_payload

    hub = _hub()
    hub._map_data = {
        "id": 1,
        "name": "Garden",
        "map_state": "MAP_STATE_COMPLETE",
        "width": 100,
        "height": 80,
        "resolution": 100,
        "origin": {"x": 0, "y": 0},
        "regions": [],
    }
    hub._coverage_segments = [SEGMENT]
    payload = build_scene_payload(hub)
    assert payload["session_paths"] == [[[0, 0], [5000, 0]]]
