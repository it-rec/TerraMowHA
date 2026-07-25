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
    MAX_SESSION_PATH_SEGMENTS,
    TerraMowHub,
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


def test_archive_is_capped() -> None:
    hub = _hub()
    _start_session(hub)
    for i in range(MAX_SESSION_PATH_SEGMENTS + 1):
        hub._apply_path_data(
            _path(_clean((i, 0), (i, 1000)), path_id=100 + i)
        )
        hub._apply_path_data(_path([], path_id=100 + i))
    assert len(hub.session_path_segments) == MAX_SESSION_PATH_SEGMENTS
    # the oldest segment fell off the front
    assert hub.session_path_segments[0][0] == {"x": 1.0, "y": 0.0}


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
