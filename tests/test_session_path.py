"""Session-path persistence across a mid-session recharge dock (issue #214).

The firmware clears the realtime path whenever the mower docks — also when it
only recharges mid-session — which used to wipe the already-mowed track from
the map. These tests cover the hub's archive (when a path reset is preserved
vs. dropped, and when the archive is cleared), the scene/payload plumbing and
the camera render/legend integration.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import (  # noqa: E402
    MAX_PATH_WINDOW_PROBES,
    MAX_SESSION_PATH_POINTS,
    TerraMowHub,
    _lost_path_points,
)
from custom_components.terramow.map_card import build_scene_payload  # noqa: E402
from custom_components.terramow.map_scene import (  # noqa: E402
    build_render_metadata,
    build_scene,
    extract_cleaning_path_points,
    extract_cleaning_path_runs,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

MAP_DATA = {
    "id": 1,
    "name": "Garden",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 100,
    "height": 80,
    "resolution": 100,
    "origin": {"x": 0, "y": 0},
    "station_pose": {"x": 1200, "y": 3400, "theta": 1570},
    "regions": [
        {
            "id": 1,
            "name": "Main",
            "boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 10000, "y": 0},
                    {"x": 10000, "y": 8000},
                    {"x": 0, "y": 8000},
                ]
            },
            "sub_regions": [],
        }
    ],
}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.140", password="secret")
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


def _start_session(hub: TerraMowHub) -> None:
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")


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
# hub: archiving on a mid-session path reset
# ---------------------------------------------------------------------------


def test_mid_session_dock_archives_the_track() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)

    # dock to recharge: firmware resets mission to IDLE and clears the path
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    hub._apply_path_data(DOCK_RESET)

    assert len(hub.session_path_segments) == 1
    segment = hub.session_path_segments[0]
    # RDP-simplified but anchored at the original endpoints
    assert segment[0] == {"x": 0.0, "y": 0.0}
    assert segment[-1] == {"x": 0.0, "y": 1000.0}

    # the resumed mow starts a fresh path; the archive stays put
    resumed = _path(_clean((0, 1000), (1000, 2000)), path_id=102)
    _start_session(hub)
    hub._apply_path_data(resumed)
    assert len(hub.session_path_segments) == 1


def test_a_leg_with_a_transit_archives_one_segment_per_run() -> None:
    hub = _hub()
    _start_session(hub)
    # A single leg that mowed one stretch, transited across the yard, then
    # mowed another. Archiving it as one segment would draw a phantom diagonal
    # across the transit, so each mowing run is archived on its own.
    hub._apply_path_data(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (5000, 0, "PATH_POINT_TYPE_CLEANING"),
                (9000, 9000, "PATH_POINT_TYPE_RETURN"),
                (0, 2000, "PATH_POINT_TYPE_CLEANING"),
                (5000, 2000, "PATH_POINT_TYPE_CLEANING"),
            ]
        )
    )
    hub._apply_path_data(DOCK_RESET)

    assert len(hub.session_path_segments) == 2
    first, second = hub.session_path_segments
    assert first[0] == {"x": 0.0, "y": 0.0}
    assert first[-1] == {"x": 5000.0, "y": 0.0}
    assert second[0] == {"x": 0.0, "y": 2000.0}
    assert second[-1] == {"x": 5000.0, "y": 2000.0}


def test_second_recharge_archives_a_second_segment() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    hub._apply_path_data(DOCK_RESET)
    hub._apply_path_data(_path(_clean((0, 1000), (2000, 3000)), path_id=102))
    hub._apply_path_data(_path([], path_id=102))
    assert len(hub.session_path_segments) == 2


def test_growing_path_is_not_archived() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    extended = _path(_clean((0, 0), (5000, 0), (5000, 1000), (0, 1000), (0, 2000)))
    hub._apply_path_data(extended)
    hub._apply_path_data(extended)  # unchanged re-push
    assert hub.session_path_segments == []


def test_reset_without_active_session_is_not_archived() -> None:
    hub = _hub()
    hub._apply_path_data(MOW_TRACK)
    hub._apply_path_data(DOCK_RESET)  # the normal end-of-job clear
    assert hub.session_path_segments == []


def test_empty_old_path_is_not_archived() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(_path([]))
    hub._apply_path_data(MOW_TRACK)
    assert hub.session_path_segments == []


def test_map_switch_path_is_not_archived() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    hub._apply_path_data(_path(_clean((0, 0), (1000, 0)), path_id=201, map_id=2))
    assert hub.session_path_segments == []


def test_track_without_two_cleaning_points_is_not_archived() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (900, 900, "PATH_POINT_TYPE_RETURN"),
            ]
        )
    )
    hub._apply_path_data(DOCK_RESET)
    assert hub.session_path_segments == []


def test_degenerate_track_simplifying_to_a_point_is_not_archived() -> None:
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(_path(_clean((500, 500), (500, 500), (500, 500))))
    hub._apply_path_data(DOCK_RESET)
    assert hub.session_path_segments == []


def test_archive_keeps_every_leg_within_its_point_budget() -> None:
    hub = _hub()
    _start_session(hub)
    legs = 60
    for i in range(legs):
        hub._apply_path_data(
            _path(_clean((i, 0), (i, 1000)), path_id=100 + i)
        )
        hub._apply_path_data(_path([], path_id=100 + i))
    # Segments are tracks, not a queue: a long job must not push the first
    # legs of the lawn off the map (issue #326).
    assert len(hub.session_path_segments) == legs
    assert hub.session_path_segments[0][0] == {"x": 0.0, "y": 0.0}
    assert (
        sum(len(segment) for segment in hub.session_path_segments)
        <= MAX_SESSION_PATH_POINTS
    )


def test_sliding_path_window_archives_only_what_fell_out() -> None:
    """The firmware serves a bounded window of the current leg.

    When it slides forward, only the points that dropped off the front are
    archived — re-archiving the whole cached track on every push buried the
    earlier legs under duplicates of the current one (issue #326).
    """
    hub = _hub()
    _start_session(hub)
    track = _clean(*[(i * 200, 0) for i in range(20)])
    hub._apply_path_data(_path(track))

    slid = track[5:] + _clean((4000, 0), (4200, 0))
    hub._apply_path_data(_path(slid))
    assert len(hub.session_path_segments) == 1
    first = hub.session_path_segments[0]
    assert first[0] == {"x": 0.0, "y": 0.0}
    # the first surviving point is kept so the archived and live tracks touch
    assert first[-1] == {"x": 1000.0, "y": 0.0}

    slid_again = slid[5:] + _clean((4400, 0))
    hub._apply_path_data(_path(slid_again))
    assert len(hub.session_path_segments) == 2
    assert hub.session_path_segments[1][0] == {"x": 1000.0, "y": 0.0}
    assert hub.session_path_segments[1][-1] == {"x": 2000.0, "y": 0.0}


def test_reserved_identical_track_is_archived_only_once() -> None:
    """A track the firmware re-serves verbatim must not burn budget twice."""
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    hub._apply_path_data(DOCK_RESET)
    assert len(hub.session_path_segments) == 1

    # the same ground re-served under a new path id, then cleared again
    hub._apply_path_data(_path(_clean((0, 0), (5000, 0), (5000, 1000), (0, 1000)), path_id=103))
    hub._apply_path_data(_path([], path_id=103))
    assert len(hub.session_path_segments) == 1


def test_in_place_rewrite_of_the_live_path_is_not_archived() -> None:
    """A same-id decimated re-push covers the same ground: nothing to archive.

    Pre-#330 this archived the whole track on every rewrite; post-#330 the
    too-strict window match still did. Either way the archive flooded with
    duplicates of the current leg until the budget evicted the earlier legs
    (issues #326/#332).
    """
    hub = _hub()
    _start_session(hub)
    track = _clean(*[(i * 100, (i % 2) * 3000) for i in range(40)])
    hub._apply_path_data(_path(track))
    decimated = track[::2] + _clean((4100, 0))
    hub._apply_path_data(_path(decimated))
    assert hub.session_path_segments == []
    assert hub.coverage_segments == []


def test_finished_job_leg_is_not_archived_into_the_next_session() -> None:
    """Feedback on #326: the previous job's mowed area stayed on the map.

    After a job completes the firmware keeps serving its final leg as the
    current path until the next job replaces it. That replacement arrives
    after the new session is latched, so without the exemption the old job's
    leg was archived — and drawn — as ground the *new* job mowed.
    """
    hub = _hub()
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert hub.session_path_segments == []
    assert hub.coverage_segments  # the completed cycle stays visible

    # the finished leg may keep updating (same path id) without being adopted
    hub._apply_path_data(_path(_clean((0, 0), (5000, 0), (5000, 1000))))

    _start_session(hub)  # new job starts; the cycle coverage resets
    hub._apply_path_data(_path(_clean((0, 5000), (1000, 5000)), path_id=202))
    assert hub.session_path_segments == []
    assert hub.coverage_segments == []


def test_adopted_segments_survive_the_first_mow_frame_after_restart() -> None:
    """Restart mid-session: dp_113 may adopt the stored segments before the
    first dp_107 mow frame arrives. That frame sees no latched session, but
    the open work counters mark it as the same job continuing — it must not
    wipe what was just adopted (issue #332: paths messed up after upgrading)."""
    hub = _hub()
    hub._session_path_segments = [
        [{"x": 0.0, "y": 0.0}, {"x": 1000.0, "y": 0.0}]
    ]
    hub._current_work_data = {"work_duration": 12, "clean_area": 5}
    _start_session(hub)
    assert hub.session_path_segments


def test_fresh_session_with_junk_work_data_still_wipes_stale_archive() -> None:
    hub = _hub()
    hub._session_path_segments = [
        [{"x": 0.0, "y": 0.0}, {"x": 1000.0, "y": 0.0}]
    ]
    hub._current_work_data = ["not", "a", "dict"]  # type: ignore[assignment]
    _start_session(hub)
    assert hub.session_path_segments == []


def _data(points: list, path_id: int = 101) -> dict:
    return {"id": path_id, "map_id": 1, "points": points}


def test_lost_path_points_classifies_the_payload() -> None:
    old = [{"position": {"x": i, "y": 0}, "type": "T"} for i in range(6)]
    # unchanged / grown at the tail: nothing lost
    assert _lost_path_points(_data(old), _data(old)) is None
    assert _lost_path_points(_data(old), _data(old + old[:2])) is None
    assert _lost_path_points(_data([]), _data(old)) is None
    # the window slid: the head that fell out, plus the boundary point
    assert _lost_path_points(_data(old), _data(old[2:])) == old[:3]
    # cleared, replaced wholesale, or replaced by a new path id: everything
    # cached is lost
    assert _lost_path_points(_data(old), _data([])) == old
    assert (
        _lost_path_points(_data(old), _data([{"position": {"x": 9, "y": 9}}]))
        == old
    )
    fresh = [{"position": {"x": 90 + i, "y": 9}, "type": "T"} for i in range(6)]
    assert _lost_path_points(_data(old), _data(fresh, path_id=102)) == old
    # payloads missing the points list entirely count as cleared / empty
    assert _lost_path_points(_data(old), {"id": 101, "map_id": 1}) == old
    assert _lost_path_points({"id": 101, "map_id": 1}, _data(old)) is None
    # malformed points (no position, or junk coordinates) never match a
    # cached point, so such a payload counts as a wholesale replacement
    assert _lost_path_points(_data(old), _data([{"type": "T"}] * 6)) == old
    junk = [{"position": {"x": "junk", "y": 0}, "type": "T"}] * 6
    assert _lost_path_points(_data(old), _data(junk)) == old
    # a stalled mower repeats a point; the probe budget bounds the search and
    # falls back to archiving the whole cached track
    stalled = [old[0]] * (MAX_PATH_WINDOW_PROBES + 8) + [old[1]]
    assert _lost_path_points(_data(stalled), _data([old[0], old[1]])) == stalled
    # a repeated point does not fool the window match: the probe walks past
    # the earlier occurrence and still finds where the window really slid
    a, b, c, d = old[:4]
    looped = [a, b, a, b, c, d]
    assert _lost_path_points(_data(looped), _data([b, c, d])) == looped[:4]


def test_lost_path_points_tolerates_in_place_rewrites() -> None:
    """The firmware rewrites the current path without dropping any ground.

    The provisional live tail point moves between pushes, and a long track is
    decimated wholesale to stay bounded. Both keep the same path id and still
    cover the same lawn, so nothing may be archived — calling these "lost"
    re-archived the whole track on every push and buried the earlier legs
    under duplicates (issues #326/#332).
    """
    old = [{"position": {"x": i * 100, "y": 0}, "type": "T"} for i in range(8)]
    # the provisional last point was rewritten in place, then mowing went on
    rewritten = old[:-1] + [
        {"position": {"x": 705, "y": 3}, "type": "T"},
        {"position": {"x": 800, "y": 0}, "type": "T"},
    ]
    assert _lost_path_points(_data(old), _data(rewritten)) is None
    # the whole track was decimated to every second point
    decimated = old[::2] + [{"position": {"x": 800, "y": 0}, "type": "T"}]
    assert _lost_path_points(_data(old), _data(decimated)) is None
    # the same rewrite under a NEW path id is a different path: the cached
    # leg would vanish from the map, so it is lost in full
    assert _lost_path_points(_data(old), _data(decimated, path_id=102)) == old
    # a same-id payload sharing next to nothing with the cache is a
    # replacement, not a rewrite
    alien = [
        {"position": {"x": 9000 + i, "y": 9000}, "type": "T"} for i in range(8)
    ]
    assert _lost_path_points(_data(old), _data(alien)) == old
    # matching is by coordinates, not float identity: a serializer round-trip
    # re-serving the same track is still a continuation
    reserved = [
        {"position": {"x": float(p["position"]["x"]), "y": 0.0}, "type": "T"}
        for p in old
    ]
    assert _lost_path_points(_data(old), _data(reserved)) is None


# ---------------------------------------------------------------------------
# hub: clearing the archive
# ---------------------------------------------------------------------------


def _docked_mid_session(hub: TerraMowHub) -> None:
    _start_session(hub)
    hub._apply_path_data(MOW_TRACK)
    _mission(hub, "MISSION_IDLE", "MISSION_STATE_IDLE")
    hub._apply_path_data(DOCK_RESET)
    assert hub.session_path_segments


def test_session_complete_clears_the_archive() -> None:
    hub = _hub()
    _docked_mid_session(hub)
    _mission(hub, "MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    assert hub.session_path_segments == []


def test_resume_keeps_the_archive_but_a_fresh_session_drops_it() -> None:
    hub = _hub()
    _docked_mid_session(hub)

    # resuming the latched session keeps the archived track
    _start_session(hub)
    assert hub.session_path_segments

    # a mow frame arriving with no latched session (COMPLETE was missed or
    # the latch expired) treats the archive as stale and drops it
    hub._active_mow_mission = None
    _start_session(hub)
    assert hub.session_path_segments == []


def test_map_change_clears_the_archive() -> None:
    hub = _hub()
    hub._apply_map_data(MAP_DATA)
    _docked_mid_session(hub)

    hub._apply_map_data(MAP_DATA)  # same map: archive stays
    assert hub.session_path_segments

    hub._apply_map_data({**MAP_DATA, "id": 2})
    assert hub.session_path_segments == []


def test_map_data_without_previous_id_keeps_the_archive() -> None:
    hub = _hub()
    _docked_mid_session(hub)
    hub._apply_map_data(MAP_DATA)  # first map push after a restart-like state
    assert hub.session_path_segments


# ---------------------------------------------------------------------------
# scene / payload plumbing
# ---------------------------------------------------------------------------


def test_extract_cleaning_path_points_filters_types() -> None:
    points = extract_cleaning_path_points(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (900, 900, "PATH_POINT_TYPE_RETURN"),
                (100, 100, "PATH_POINT_TYPE_CLEANING"),
            ]
        )
    )
    assert points == [
        {"x": 0, "y": 0, "type": "PATH_POINT_TYPE_CLEANING"},
        {"x": 100, "y": 100, "type": "PATH_POINT_TYPE_CLEANING"},
    ]


def test_extract_cleaning_path_runs_splits_on_a_transit() -> None:
    # Two mowing stretches with a return/transit hop between them: the mower
    # drove out to (9000, 9000) and back, but that leg is a non-cleaning point
    # and is dropped. The two stretches must stay separate runs so nothing
    # bridges the gap with a phantom diagonal.
    runs = extract_cleaning_path_runs(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (100, 0, "PATH_POINT_TYPE_CLEANING"),
                (9000, 9000, "PATH_POINT_TYPE_RETURN"),
                (200, 0, "PATH_POINT_TYPE_CLEANING"),
                (300, 0, "PATH_POINT_TYPE_CLEANING"),
            ]
        )
    )
    assert [[(p["x"], p["y"]) for p in run] for run in runs] == [
        [(0, 0), (100, 0)],
        [(200, 0), (300, 0)],
    ]
    # Concatenating the runs reproduces the flat cleaning-only filter exactly.
    concatenated = [point for run in runs for point in run]
    assert concatenated == extract_cleaning_path_points(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (100, 0, "PATH_POINT_TYPE_CLEANING"),
                (9000, 9000, "PATH_POINT_TYPE_RETURN"),
                (200, 0, "PATH_POINT_TYPE_CLEANING"),
                (300, 0, "PATH_POINT_TYPE_CLEANING"),
            ]
        )
    )


def test_uninterrupted_mowing_is_a_single_run() -> None:
    runs = extract_cleaning_path_runs(_path(_clean((0, 0), (1, 0), (2, 0))))
    assert len(runs) == 1


def test_build_scene_splits_current_and_history_into_runs() -> None:
    transit_path = _path(
        [
            (0, 0, "PATH_POINT_TYPE_CLEANING"),
            (5000, 0, "PATH_POINT_TYPE_CLEANING"),
            (9000, 9000, "PATH_POINT_TYPE_RETURN"),
            (0, 2000, "PATH_POINT_TYPE_CLEANING"),
            (5000, 2000, "PATH_POINT_TYPE_CLEANING"),
        ]
    )
    scene = build_scene(MAP_DATA, transit_path, transit_path, False)
    assert len(scene["current_path_runs"]) == 2
    assert len(scene["history_path_runs"]) == 2
    # The flat lists are unchanged (still the union of every mowing point).
    assert len(scene["current_path_points"]) == 4
    assert len(scene["history_path_points"]) == 4


def test_build_scene_drops_runs_on_a_map_mismatch() -> None:
    # A path belonging to a different map is dropped whole — runs included.
    scene = build_scene(
        MAP_DATA,
        _path(_clean((0, 0), (1, 0)), path_id=9, map_id=2),
        {},
        False,
    )
    assert scene["current_path_runs"] == []
    assert scene["current_path_points"] == []
    assert scene["path_map_mismatch"] is True


def test_build_scene_carries_session_segments() -> None:
    segment = [{"x": 0.0, "y": 0.0}, {"x": 1000.0, "y": 0.0}]
    scene = build_scene(
        MAP_DATA,
        {},
        {},
        False,
        session_path_segments=[
            segment,
            [{"x": 5.0, "y": 5.0}],  # too short — dropped
            "junk",  # not a list — dropped
        ],
    )
    assert scene["session_path_segments"] == [segment]
    assert scene["scene_counts"]["session_path_segments"] == 1
    assert scene["scene_counts"]["session_path_points"] == 2
    assert "session_path" in scene["rendered_layers"]
    assert scene["rendered_layers"].index("session_path") < scene[
        "rendered_layers"
    ].index("path")
    # the segment participates in the scene's fit bounds
    assert scene["bounds"] is not None
    assert scene["bounds"][2] >= 1000.0

    metadata = build_render_metadata(scene, MAP_DATA, {}, {})
    assert metadata["session_path_summary"] == {
        "segment_count": 1,
        "point_count": 2,
    }


def test_build_scene_defaults_to_no_session_segments() -> None:
    scene = build_scene(MAP_DATA, {}, {}, False)
    assert scene["session_path_segments"] == []
    assert "session_path" not in scene["rendered_layers"]


def test_card_payload_breaks_current_path_between_runs() -> None:
    hub = _hub()
    hub._apply_map_data(MAP_DATA)
    _start_session(hub)
    hub._apply_path_data(
        _path(
            [
                (0, 0, "PATH_POINT_TYPE_CLEANING"),
                (5000, 0, "PATH_POINT_TYPE_CLEANING"),
                (9000, 9000, "PATH_POINT_TYPE_RETURN"),
                (0, 2000, "PATH_POINT_TYPE_CLEANING"),
                (5000, 2000, "PATH_POINT_TYPE_CLEANING"),
            ]
        )
    )

    current = build_scene_payload(hub)["current_path"]
    # Exactly one run break ([]), and the mow points on either side of it are
    # the two stretches — the transit gap is never bridged.
    assert current.count([]) == 1
    break_at = current.index([])
    assert current[:break_at] == [[0, 0], [5000, 0]]
    assert current[break_at + 1 :] == [[0, 2000], [5000, 2000]]


def test_card_payload_includes_session_paths() -> None:
    hub = _hub()
    hub._apply_map_data(MAP_DATA)
    _docked_mid_session(hub)

    payload = build_scene_payload(hub)
    assert payload["session_paths"] == [
        [[0, 0], [5000, 0], [5000, 1000], [0, 1000]]
    ]
    # paths never widen the fit-to-view bounds
    assert payload["bounds"] == [0, 0, 10000, 8000]


# ---------------------------------------------------------------------------
# camera render / legend
# ---------------------------------------------------------------------------


def _render(camera: TerraMowMapCamera) -> bytes:
    return asyncio.run(camera.async_camera_image())


def test_camera_renders_session_segments() -> None:
    hub = _hub()
    camera = TerraMowMapCamera(hub.basic_data, hub.hass, show_coverage=True)
    hub._map_data = MAP_DATA
    hub._coverage_segments = [
        [{"x": 0.0, "y": 0.0}, {"x": 5000.0, "y": 0.0}, {"x": 5000.0, "y": 1000.0}],
        # collapses to a single pixel — skipped by both draw layers
        [{"x": 200.0, "y": 200.0}, {"x": 200.0, "y": 200.0}],
    ]
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)

    scene = camera._build_scene()
    assert scene["scene_counts"]["session_path_segments"] == 2

    # segments alone light up the path and coverage legend entries
    labels = [label for _, label in camera._renderer._legend_entries(scene)]
    assert camera._renderer._t("path") in labels
    assert camera._renderer._t("coverage") in labels


def test_draw_coverage_without_transformer_is_noop() -> None:
    hub = _hub()
    camera = TerraMowMapCamera(hub.basic_data, hub.hass, show_coverage=True)
    camera._renderer._transformer = None
    image = MagicMock()
    camera._renderer._draw_coverage(
        image, {"session_path_segments": [], "path_points": []}
    )
    image.paste.assert_not_called()
