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
    MAX_COVERAGE_POINTS,
    MAX_SESSION_PATH_POINTS,
    TerraMowHub,
    _compact_segments,
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


def test_archive_skips_coverage_when_segment_collapses(monkeypatch) -> None:
    # The session leg archives, but if its coarse coverage copy collapses to
    # nothing the coverage list simply gets no segment (defensive branch).
    hub = _hub()
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    monkeypatch.setattr(
        "custom_components.terramow.hub._slim_coverage_segment",
        lambda run: None,
    )
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")  # recharge dock
    hub._apply_path_data(DOCK_RESET)
    assert len(hub.session_path_segments) == 1  # session leg still archived
    assert hub.coverage_segments == []  # coverage copy skipped


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


def test_slim_coverage_segment_caps_and_coarsens() -> None:
    from custom_components.terramow.hub import (
        COVERAGE_MAX_POINTS_PER_SEGMENT,
        _slim_coverage_segment,
    )

    # A dense zig-zag: 120 sharp turns, each far more than the RDP epsilon, so
    # simplification keeps them all — then the hard cap thins it down.
    run = [{"x": i * 200, "y": 0 if i % 2 == 0 else 300} for i in range(120)]
    seg = _slim_coverage_segment(run)
    assert seg is not None
    assert len(seg) <= COVERAGE_MAX_POINTS_PER_SEGMENT
    # endpoints survive the thinning so the swath still spans the whole run
    assert seg[0] == {"x": 0, "y": 0}
    assert seg[-1]["x"] == 119 * 200
    # a run that collapses below two points yields nothing
    assert _slim_coverage_segment([{"x": 5, "y": 5}] * 3) is None


def test_coverage_over_budget_is_thinned_not_dropped() -> None:
    # Enough detailed tracks to bust the point budget. Every one of them is
    # lawn the mower really mowed, so the compaction has to keep them all and
    # pay for the budget in vertices instead (issue #326).
    detailed = [
        [{"x": i, "y": y} for y in range(0, 4000, 100)]
        for i in range(MAX_COVERAGE_POINTS // 40 + 20)
    ]
    hub = _hub()
    hub._coverage_segments = [list(segment) for segment in detailed]
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    hub._apply_path_data(DOCK_RESET)

    assert len(hub.coverage_segments) == len(detailed) + 1
    assert (
        sum(len(segment) for segment in hub.coverage_segments)
        <= MAX_COVERAGE_POINTS
    )
    # the oldest tracks lost detail but still span the ground they covered
    oldest = hub.coverage_segments[0]
    assert len(oldest) < len(detailed[0])
    assert oldest[0] == detailed[0][0]
    assert oldest[-1] == detailed[0][-1]


def test_compact_segments_drops_only_at_the_per_segment_floor() -> None:
    floor = 4
    segments = [
        [{"x": i, "y": y} for y in range(floor)] for i in range(20)
    ]
    _compact_segments(segments, floor * 10, floor, 90.0, 300.0)
    assert len(segments) == 10
    # dropping starts at the oldest end
    assert segments[0][0] == {"x": 10, "y": 0}


def test_compact_segments_leaves_a_list_inside_its_budget_alone() -> None:
    segments = [[{"x": 0, "y": 0}, {"x": 1, "y": 1}]]
    _compact_segments(segments, 100, 4, 90.0, 300.0)
    assert segments == [[{"x": 0, "y": 0}, {"x": 1, "y": 1}]]


def test_compaction_shrinks_without_cutting_corners() -> None:
    """Shrinking must not draw lines the mower never drove (issue #332).

    An L-shaped track thinned by index can lose its corner vertex, bridging
    the two legs with a ghost diagonal across the lawn. Re-simplifying keeps
    the corner and drops the collinear filler instead.
    """
    from custom_components.terramow.hub import _shrink_segment

    leg_a = [{"x": float(x), "y": 0.0} for x in range(0, 2000, 100)]
    leg_b = [{"x": 1900.0, "y": float(y)} for y in range(100, 2100, 100)]
    segments = [leg_a + leg_b]
    _compact_segments(segments, 10, 4, 25.0, 200.0)
    shrunk = segments[0]
    assert 2 < len(shrunk) <= 10
    assert shrunk[0] == {"x": 0.0, "y": 0.0}
    assert shrunk[-1] == {"x": 1900.0, "y": 2000.0}
    # the corner survives: no diagonal from (0,0) to (1900,2000)
    assert {"x": 1900.0, "y": 0.0} in shrunk

    # a segment nothing can be shaved off (every vertex is a huge deviation)
    jagged = [
        {"x": float(i * 1000), "y": 0.0 if i % 2 == 0 else 1e7}
        for i in range(8)
    ]
    assert _shrink_segment(list(jagged), 4, 25.0, 200.0) == jagged
    # an irreducible archive over budget falls back to dropping oldest whole
    segments = [list(jagged), list(jagged)]
    _compact_segments(segments, 8, 4, 25.0, 200.0)
    assert segments == [jagged]

    # degenerate targets leave the polyline untouched
    assert _shrink_segment(list(jagged), 8, 25.0, 200.0) == jagged
    assert _shrink_segment(list(jagged), 1, 25.0, 200.0) == jagged

    # malformed points (no coordinates) can only be thinned by index
    opaque = [{"n": i} for i in range(8)]
    thinned = _shrink_segment(list(opaque), 4, 25.0, 200.0)
    assert len(thinned) == 4
    assert thinned[0] == {"n": 0}
    assert thinned[-1] == {"n": 7}


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


def test_a_resumed_job_keeps_the_coverage_despite_the_completion_flag() -> None:
    """Sunset docking reports the job complete; the next morning resumes it.

    Reported on issue #214: a job stopped at dusk and finished the next day
    showed an empty map at 84 % progress — everything mowed the day before was
    gone. The completion flag had latched the cycle as done, so the first mow
    frame of the resumed job wiped it.
    """
    hub = _hub()
    hub._coverage_segments = [SEGMENT]
    hub._coverage_cycle_done = True
    # The device carries yesterday's progress in its counters.
    _work(hub, clean_area=1770, work_duration=7200, is_completed=False)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    assert hub.coverage_segments == [SEGMENT]
    # The cycle is evidently still running.
    assert hub._coverage_cycle_done is False


def test_counter_restart_while_mowing_clears_the_previous_cycle() -> None:
    """A new job restarts the device counters; the old coverage must go.

    The other half of issue #214: a fresh session drew the previous session's
    coverage over the whole lawn while progress read 17 %. The previous
    cycle's end had not latched, so nothing cleared it — but the device had
    plainly restarted, its session counters dropped from 367 m² to zero.
    """
    hub = _hub()
    # Yesterday's finished job: the counters keep their final value.
    _work(hub, clean_area=3677, work_duration=7200, is_completed=True)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._coverage_segments = [SEGMENT]
    hub._session_path_segments = [SEGMENT]
    # The device begins a new job and restarts its counters.
    _work(hub, clean_area=0, work_duration=0, is_completed=False)
    assert hub.coverage_segments == []
    assert hub._session_path_segments == []


def test_counter_frames_that_are_not_a_fresh_start_leave_the_coverage() -> None:
    """Only a drop from positive to zero counts as a new cycle."""
    hub = _hub()
    hub._coverage_segments = [SEGMENT]
    # Already at zero: nothing restarted.
    _work(hub, clean_area=0, work_duration=0, is_completed=False)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    _work(hub, clean_area=0, work_duration=0, is_completed=False)
    assert hub.coverage_segments == [SEGMENT]
    # Still counting up: a running job, not a new one.
    _work(hub, clean_area=500, work_duration=60, is_completed=False)
    _work(hub, clean_area=900, work_duration=120, is_completed=False)
    assert hub.coverage_segments == [SEGMENT]


def test_counter_restart_with_nothing_drawn_only_drops_the_latch() -> None:
    """Nothing to clear: no needless store write, but the latch still lifts."""
    hub = _hub()
    _work(hub, clean_area=1000, work_duration=600, is_completed=False)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._coverage_cycle_done = True
    _work(hub, clean_area=0, work_duration=0, is_completed=False)
    assert hub.coverage_segments == []
    assert hub._coverage_cycle_done is False


def test_a_recharge_dock_keeps_the_counters_and_the_coverage() -> None:
    """A mid-session dock must not look like a new cycle.

    The counters keep counting across a recharge, so the drop-to-zero signal
    never fires and everything mowed before the dock stays on the map — the
    behaviour issue #214 asked for in the first place.
    """
    hub = _hub()
    _work(hub, clean_area=1200, work_duration=3600, is_completed=False)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    hub._coverage_segments = [SEGMENT]
    _mission(hub, "MISSION_RECHARGE", "MISSION_STATE_RUNNING")
    _work(hub, clean_area=1200, work_duration=3900, is_completed=False)
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


def test_compaction_never_draws_across_ground_the_mower_missed() -> None:
    """A saturated archive loses old tracks, not the shape of every track.

    From a real store on 2026-08-04: 2277 segments ground down to the 8-point
    floor, spanning 7 m on average — drawn as straight lines across the lawn
    and across gaps the mower never crossed (issue #332). The cause was an
    unbounded tolerance: it doubled until the shape was gone, and compaction
    re-simplifies already-simplified points, so the error compounded pass over
    pass. Coarsening now stops at ``SESSION_PATH_MAX_SIMPLIFY_MM`` and the
    oldest tracks are dropped whole instead. An honest gap beats a line
    through lawn the mower never touched.
    """
    from custom_components.terramow.hub import (
        SESSION_PATH_MAX_SIMPLIFY_MM,
        _compact_segments,
    )

    def hairpin(index: int) -> list[dict[str, float]]:
        """One stripe: down one side, back up 600 mm over."""
        x = float(index * 2000)
        down = [{"x": x, "y": float(y)} for y in range(0, 3001, 100)]
        up = [
            {"x": x + 600.0, "y": float(y)} for y in range(3000, -1, -100)
        ]
        return down + up

    segments = [hairpin(i) for i in range(20)]
    _compact_segments(segments, 40, 8, 25.0, SESSION_PATH_MAX_SIMPLIFY_MM)

    assert sum(len(segment) for segment in segments) <= 40
    # the budget was met by dropping the oldest stripes whole ...
    assert len(segments) == 10
    assert segments[0][0]["x"] == 20000.0
    # ... not by flattening the survivors: both legs of every hairpin remain,
    # so no drawn line cuts through the unmowed strip between them.
    for segment in segments:
        assert len({point["x"] for point in segment}) == 2
        ys = [point["y"] for point in segment]
        assert max(ys) - min(ys) == 3000.0


def test_shrink_stops_at_the_fidelity_ceiling() -> None:
    """At the ceiling there is no coarser tolerance left to try."""
    from custom_components.terramow.hub import _shrink_segment

    line = [{"x": float(x), "y": 0.0} for x in range(0, 1000, 100)]
    assert _shrink_segment(list(line), 2, 200.0, 200.0) == line


def test_archive_health_shows_what_only_the_disk_store_showed() -> None:
    """Diagnostics must be able to tell a sick archive from a healthy one.

    When issue #332 was investigated the damage — 2277 segments ground to the
    8-point floor, gaps up to 23 m — could only be seen by reading the store
    off the device's disk. A bug reporter cannot be asked to do that, so the
    distribution is summarised here instead. Coordinates stay local; the
    lawn's geometry is private.
    """
    from custom_components.terramow.hub import _archive_health

    # Healthy: dense tracks, sub-metre steps, nothing sitting at the floor.
    healthy = [
        [{"x": float(x), "y": float(run * 500)} for x in range(0, 2000, 100)]
        for run in range(3)
    ]
    report = _archive_health(healthy, 20000, 8)
    assert report["segments"] == 3
    assert report["points"] == 60
    assert report["budget"] == 20000
    assert report["point_floor"] == 8
    assert report["segments_at_floor"] == 0
    assert report["points_per_segment"] == {"min": 20, "median": 20, "max": 20}
    assert report["point_gap_mm"]["max"] == 100.0

    # Sick: every track at the floor, 23 m between consecutive points.
    sick = [[{"x": 0.0, "y": 0.0}, {"x": 23000.0, "y": 0.0}] for _ in range(50)]
    report = _archive_health(sick, 20000, 8)
    assert report["segments_at_floor"] == 50
    assert report["points_per_segment"]["median"] == 2
    assert report["point_gap_mm"]["max"] == 23000.0

    # An empty archive has no numbers to report and must not blow up.
    empty = _archive_health([], 20000, 8)
    assert empty["segments"] == 0
    assert empty["points"] == 0
    assert empty["points_per_segment"] == {
        "min": None,
        "median": None,
        "max": None,
    }
    assert empty["point_gap_mm"] == {
        "median": None,
        "p90": None,
        "p99": None,
        "max": None,
    }

    # Malformed points carry no distance; the summary still comes back.
    malformed = _archive_health([[{"n": 0}, {"n": 1}]], 20000, 8)
    assert malformed["points"] == 2
    assert malformed["point_gap_mm"]["max"] is None


def test_hub_reports_both_archives_for_diagnostics() -> None:
    hub = _hub()
    hub._session_path_segments = [list(SEGMENT)]
    hub._coverage_segments = [list(SEGMENT), list(SEGMENT)]
    health = hub.path_archive_health
    assert health["session_path"]["segments"] == 1
    assert health["session_path"]["budget"] == MAX_SESSION_PATH_POINTS
    assert health["coverage"]["segments"] == 2
    assert health["coverage"]["budget"] == MAX_COVERAGE_POINTS
    assert health["coverage"]["point_gap_mm"]["max"] == 5000.0
