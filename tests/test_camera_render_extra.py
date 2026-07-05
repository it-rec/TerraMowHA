"""Extra camera coverage: render a feature-rich map scene.

The base ``test_camera`` suite renders a simple map. This module feeds a scene
that also carries obstacles, forbidden zones, virtual walls, a selected
sub-region with inner boundaries and edge segments, a live robot pose and a
history path, so the region/obstacle/zone extraction and the corresponding
draw helpers are exercised end to end.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

# HA's camera component imports turbojpeg, which the test harness does not
# ship; a stub is enough for these tests.
sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.50", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    # run "executor" jobs inline so the render pipeline works synchronously
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


RICH_MAP = {
    "id": 1,
    "name": "Garten",
    "map_state": "MAP_STATE_COMPLETE",
    "resolution": 0.05,
    "origin": {"x": -2.0, "y": -2.0},
    "station_pose": {"x": 0.0, "y": 0.0, "theta": 250.0},
    "total_area": 2560,
    "map_view_rotate_angle": 15,
    "regions": [
        {
            "id": 100,
            "name": "Haupt",
            "boundary": _poly((0, 0), (4, 0), (4, 3), (0, 3)),
            "obstacles": [_poly((1.0, 1.0), (1.3, 1.0), (1.3, 1.3), (1.0, 1.3))],
            "sub_regions": [
                {
                    "id": 7,
                    "name": "Rasen vorne",
                    "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                    "inner_boundarys": [_poly((0.5, 0.5), (1.0, 0.5), (1.0, 1.0))],
                    "edge_segments": [_poly((0, 0), (2, 0))],
                    "center": {"x": 1.0, "y": 1.0},
                    "is_selected_for_mow": True,
                    "selected_for_mow_order": 1,
                },
                {
                    "id": 8,
                    "name": "Rasen hinten",
                    "boundary": _poly((2, 0), (4, 0), (4, 2), (2, 2)),
                    "center": {"x": 3.0, "y": 1.0},
                },
            ],
        },
    ],
    "obstacles": [_poly((3.0, 2.0), (3.4, 2.0), (3.4, 2.4), (3.0, 2.4))],
    "forbidden_zones": [_poly((0.2, 2.2), (0.8, 2.2), (0.8, 2.8), (0.2, 2.8))],
    "virtual_walls": [_poly((0, 2.5), (4, 2.5))],
    "clean_info": {
        "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
        "select_region": {"region_id": [7]},
    },
    "mow_param": {"mow_height": {"value": 45}},
}

CURRENT_PATH = {
    "id": 5,
    "map_id": 1,
    "type": "PATH_TYPE_CLEAN",
    "points": [
        {"position": {"x": 0.2, "y": 0.2}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 1.0, "y": 0.6}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 2.2, "y": 1.4}, "type": "PATH_POINT_TYPE_CLEANING"},
    ],
}

HISTORY_PATH = {
    "id": 4,
    "map_id": 1,
    "type": "PATH_TYPE_CLEAN",
    "points": [
        {"position": {"x": 0.1, "y": 0.1}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 0.5, "y": 0.4}, "type": "PATH_POINT_TYPE_CLEANING"},
    ],
}


def _camera(hub, **kwargs) -> TerraMowMapCamera:
    return TerraMowMapCamera(hub.basic_data, hub.hass, **kwargs)


def test_camera_renders_rich_scene_with_all_features() -> None:
    hub = _hub()
    camera = _camera(hub)

    # battery connected so the robot renders in its charging-aware state
    asyncio.run(hub.on_battery_status(json.dumps({"charger_connected": True})))

    hub._map_data = RICH_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data(HISTORY_PATH))
    asyncio.run(camera._on_path_data(CURRENT_PATH))
    asyncio.run(camera._on_pose({"x": 1.0, "y": 1.0, "yaw": 45}))

    image = asyncio.run(camera.async_camera_image())
    assert image.startswith(PNG_MAGIC)

    scene = camera._build_scene()
    counts = scene["scene_counts"]
    assert counts["regions"] == 1
    # region-level + map-level obstacles both extracted
    assert len(scene["obstacles"]) == 2
    assert len(scene["forbidden_zones"]) == 1
    assert len(scene["virtual_walls"]) == 1

    # the sub-region referenced by clean_info.select_region is marked selected
    sub_regions = scene["regions"][0]["sub_regions"]
    selected = {s["id"]: s["selected"] for s in sub_regions}
    assert selected[7] is True
    assert selected[8] is False


def test_camera_rich_scene_reports_layers_and_paths() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = RICH_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data(HISTORY_PATH))
    asyncio.run(camera._on_path_data(CURRENT_PATH))

    # render so extra_state_attributes reflects a real scene
    asyncio.run(camera.async_camera_image())
    attrs = camera.extra_state_attributes
    assert attrs["combined_path_summary"]["point_count"] == 5
    assert "rendered_layers" in attrs


# ===========================================================================
# Final line/branch coverage: font fallback, helper edge branches, every
# ``_build_scene`` skip path, the private draw helpers reached with degenerate
# geometry, the robot-image reuse pass and the summary-panel overflow break.
# ===========================================================================

import time  # noqa: E402
from unittest.mock import patch  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from custom_components.terramow.camera import (  # noqa: E402
    _collect_recursive_points,
    _enum_label,
    _extract_all_map_points,
    _extract_marker_points,
    _load_font,
    _simplify_path_pixels,
)


def _render(camera) -> bytes:
    return asyncio.run(camera.async_camera_image())


def _draw_ctx():
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image, "RGBA")


def _cleaning(x, y):
    return {"position": {"x": x, "y": y}, "type": "PATH_POINT_TYPE_CLEANING"}


# ---------------------------------------------------------------------------
# module-level helper edge branches
# ---------------------------------------------------------------------------


def test_load_font_falls_back_to_default() -> None:
    # When every TrueType candidate path fails to load, the bundled default is
    # used. Only reject the on-disk path lookups so ``load_default`` (which also
    # goes through ``truetype`` with a file object) still works.
    real_truetype = ImageFont.truetype

    def _reject_paths(font=None, *args, **kwargs):
        if isinstance(font, str):
            raise OSError
        return real_truetype(font, *args, **kwargs)

    with patch(
        "custom_components.terramow.camera.ImageFont.truetype",
        side_effect=_reject_paths,
    ):
        font = _load_font(997, bold=True)
    assert isinstance(font, (ImageFont.ImageFont, ImageFont.FreeTypeFont))


def test_collect_recursive_skips_non_container_list_values() -> None:
    # A list whose members are plain scalars exercises the "not a container"
    # branch of the list-iteration loop.
    assert _collect_recursive_points([1, "x", 2.5]) == []


def test_extract_marker_points_skips_featureless_item() -> None:
    # An item with no extractable points contributes no marker.
    assert _extract_marker_points([{}]) == []


def test_extract_marker_points_centroid_none() -> None:
    # Defensive branch: a featureful item whose centroid resolves to None is
    # dropped (forced via patch since a non-empty point list always has one).
    with patch(
        "custom_components.terramow.camera._polygon_centroid", return_value=None
    ):
        assert _extract_marker_points([_poly((0, 0), (2, 0), (2, 2))]) == []


def test_simplify_path_pixels_close_middle_and_equal_endpoint() -> None:
    # A near-degenerate closed loop: the single middle point is within the
    # min-segment gap (skipped) and the endpoint equals the kept start point.
    assert _simplify_path_pixels([(0, 0), (1, 0), (0, 0)], 0.5, 5.0) == [(0, 0)]


def test_enum_label_without_known_prefix() -> None:
    # A non-empty string matching none of the prefixes falls straight through.
    assert _enum_label("custom_value") == "Custom Value"


def test_extract_all_map_points_missing_station_and_non_dict_clean_info() -> None:
    points = _extract_all_map_points(
        {
            "width": 10,
            "height": 10,
            "resolution": 0.1,
            "origin": {"x": 0, "y": 0},
            "regions": [
                {"boundary": _poly((0, 0), (2, 0), (2, 2)), "sub_regions": [], "obstacles": []}
            ],
            # no station_pose -> skip; clean_info is not a dict -> skip
            "clean_info": "nope",
        }
    )
    assert points


def test_extract_all_map_points_non_dict_clean_subsections() -> None:
    points = _extract_all_map_points(
        {
            "width": 10,
            "height": 10,
            "resolution": 0.1,
            "origin": {"x": 0, "y": 0},
            "station_pose": {"x": 0, "y": 0, "theta": 0},
            "clean_info": {"draw_region": "x", "move_to_target_point": "y"},
        }
    )
    assert points


# ---------------------------------------------------------------------------
# robot-state helpers
# ---------------------------------------------------------------------------


def test_get_battery_connected_without_lawn_mower() -> None:
    hub = _hub()
    orphan = TerraMowMapCamera(
        TerraMowBasicData(host="192.0.2.201", password="secret"), hub.hass
    )
    assert orphan._get_battery_connected() is None


def test_get_battery_connected_non_dict_status() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._battery_status = None  # property returns a non-dict
    assert camera._get_battery_connected() is None


def test_get_live_robot_pose_missing_coordinates() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._pose = {"x": None, "y": 1.0, "yaw": 0.0}
    assert camera._get_live_robot_pose() is None


def test_dock_fallback_without_station_theta() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._battery_status = {"charger_connected": True}
    camera._map_data = {"station_pose": {"x": 0.0, "y": 0.0, "theta": 0}}
    camera._pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
    # Defensive branch: station angle resolving to None leaves robot yaw unset.
    with patch(
        "custom_components.terramow.camera._coerce_angle_radians", return_value=None
    ):
        state = camera._get_display_robot_state()
    assert state["source"] == "dock_fallback"
    assert state["display_pose"]["yaw"] is None


# ---------------------------------------------------------------------------
# orphaned camera: callbacks without a lawn mower + throttled pose
# ---------------------------------------------------------------------------


def test_orphan_camera_callbacks_and_empty_payloads() -> None:
    hub = _hub()
    orphan = TerraMowMapCamera(
        TerraMowBasicData(host="192.0.2.202", password="secret"), hub.hass
    )
    # No lawn mower -> map_data stays empty; the "empty everything" rebuild path
    # sets the static image to None.
    asyncio.run(orphan._on_map_info({"id": 1}))
    assert orphan._static_image is None
    # Empty path payloads skip the one-shot debug logging branch.
    asyncio.run(orphan._on_path_data({}))
    asyncio.run(orphan._on_history_path_data({}))
    asyncio.run(orphan._on_battery_status("{}"))
    assert orphan._cached_png is None
    # Nothing to render -> the placeholder PNG.
    assert _render(orphan).startswith(PNG_MAGIC)


def test_on_pose_throttles_rapid_updates() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._last_pose_state_update = time.monotonic()
    asyncio.run(camera._on_pose({"x": 1.0, "y": 1.0, "yaw": 0.0}))
    assert camera._pose["x"] == 1.0


# ---------------------------------------------------------------------------
# _build_scene skip branches
# ---------------------------------------------------------------------------


def test_build_scene_history_points_without_map_id() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {"map_state": "MAP_STATE_COMPLETE"}  # no id
    camera._path_data = {}
    camera._history_path_data = {"points": [_cleaning(0.0, 0.0)]}  # no map_id
    scene = camera._build_scene()
    assert scene["history_path_points"]
    assert scene["path_map_mismatch"] is False


def test_build_scene_non_dict_clean_and_mow_param() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "clean_info": "nope",
        "mow_param": "nope",
    }
    scene = camera._build_scene()
    assert scene["draw_region_polygons"] == []
    assert scene["move_target_point"] is None


def test_build_scene_select_region_variants() -> None:
    hub = _hub()
    camera = _camera(hub)
    # select_region is not a dict -> skipped
    camera._map_data = {"id": 1, "clean_info": {"select_region": "nope"}}
    assert camera._build_scene()["regions"] == []
    # region_id list holds an un-coercible value alongside a valid one
    camera._map_data = {
        "id": 1,
        "clean_info": {"select_region": {"region_id": ["bad", 5]}},
        "regions": [
            {
                "id": 5,
                "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                "sub_regions": [{"id": 5, "boundary": _poly((0, 0), (1, 0), (1, 1))}],
            }
        ],
    }
    scene = camera._build_scene()
    assert scene["regions"][0]["sub_regions"][0]["selected"] is True


def test_build_scene_clean_info_subsections_non_dict() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "clean_info": {"draw_region": "x", "move_to_target_point": "y"},
    }
    scene = camera._build_scene()
    assert scene["draw_region_polygons"] == []
    assert scene["move_target_point"] is None


def test_build_scene_draw_region_small_polygon() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "clean_info": {
            "draw_region": {"regions": [_poly((0, 0), (1, 0))]},  # <3 points
            "move_to_target_point": {},
        },
    }
    scene = camera._build_scene()
    assert scene["draw_region_polygons"] == []


def test_build_scene_skips_non_dict_region_and_subregion() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "regions": [
            "not-a-dict",
            {
                "id": 1,
                "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                "sub_regions": [
                    "not-a-dict",
                    {"id": 9},  # no boundary -> centroid stays None
                ],
            },
        ],
    }
    scene = camera._build_scene()
    assert len(scene["regions"]) == 1
    assert scene["regions"][0]["sub_regions"][0]["center"] is None


# ---------------------------------------------------------------------------
# render scenes exercising the remaining draw branches
# ---------------------------------------------------------------------------


MAP_DRAW = {
    "id": 1,
    "name": "Zeichnung",
    "map_state": "MAP_STATE_COMPLETE",
    # no station_pose / origin -> station/origin draw skipped
    "has_bird_view": True,
    "bird_view_index": 2,
    "enable_advanced_edge_cutting": True,
    "is_boundary_locked": True,
    "is_able_to_run_build_map": True,
    "has_backup": True,
    "backup_info_list": [{"id": 1}],
    "regions": [
        "not-a-dict",
        {
            "id": 10,
            "boundary": _poly((0, 0), (6, 0), (6, 6), (0, 6)),
            "edge_segments": [_poly((0, 0), (6, 0)), _poly((0, 0))],  # valid + <2
            "obstacles": [
                {"ellipse": {"center": {"x": 1, "y": 1}, "radius_x": 0.3, "radius_y": 0.3}}
            ],
            "sub_regions": [
                "not-a-dict",
                {
                    "id": 7,
                    "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                    "center": {"x": 1, "y": 1},
                    "inner_boundarys": [
                        _poly((0.2, 0.2), (0.8, 0.2), (0.8, 0.8)),
                        _poly((0.3, 0.3), (0.4, 0.3)),  # <3 -> skipped
                    ],
                    "edge_segments": [_poly((0, 0), (2, 0)), _poly((0, 0))],  # valid + <2
                },
                {"id": 8, "boundary": _poly((3, 3), (4, 3))},  # boundary <3 -> skipped in draw
            ],
        },
        {
            "id": 11,
            "boundary": _poly((5, 5), (6, 5)),  # region boundary <3 -> outline skipped
            "edge_segments": [_poly((5, 5), (6, 6))],
            "sub_regions": [],
        },
    ],
    "mow_param": {"regions": [{"id": 7}]},  # sub-region 7 gains the custom-param badge
    "cross_boundary_tunnels": [{"polygon": _poly((1, 1), (2, 1), (2, 2))}],
}


def test_render_draw_map_covers_edge_and_badge_branches() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DRAW
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)

    scene = camera._build_scene()
    # region 10 edge + region 11 short boundary both survive into the scene
    assert scene["regions"][0]["edge_lines"]
    assert len(scene["regions"][1]["boundary"]) == 2
    # custom-param flag drives the badge draw
    assert scene["regions"][0]["sub_regions"][0]["has_custom_param"] is True
    # tunnel carries a polygon (not just a polyline)
    assert scene["cross_boundary_tunnels"][0]["polygons"]


def test_render_map_with_non_dict_metadata_sections() -> None:
    hub = _hub()
    # clean-mode skips the summary panel, which assumes clean_info is a dict;
    # here we only care about the metadata + scene fallbacks for non-dict fields.
    camera = _camera(hub, clean_mode=True)
    hub._map_data = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "clean_info": "nope",
        "mow_param": "nope",
        "backup_info_list": "nope",
        "regions": [
            {"id": 1, "boundary": _poly((0, 0), (4, 0), (4, 4), (0, 4)), "sub_regions": []}
        ],
    }
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)
    # the render metadata falls back to empty summaries for the non-dict sections
    attrs = camera.extra_state_attributes
    assert attrs["clean_info_summary"] == {}
    assert attrs["mow_param_summary"] == {}
    assert attrs["backup_summary"] == {}


def test_render_clean_mode_empty_map_card() -> None:
    hub = _hub()
    camera = _camera(hub, clean_mode=True)
    # metadata only, no geometry -> the empty-map card without map chips
    hub._map_data = {"id": 1, "map_state": "MAP_STATE_INCOMPLETE"}
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)


def test_render_collapsing_path_layer() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DRAW
    asyncio.run(camera._on_map_info({"id": 1}))
    # two coincident cleaning points collapse to a single pixel after simplify
    asyncio.run(
        camera._on_path_data(
            {
                "id": 5,
                "map_id": 1,
                "type": "PATH_TYPE_CLEAN",
                "points": [_cleaning(1.0, 1.0), _cleaning(1.0, 1.0)],
            }
        )
    )
    assert _render(camera).startswith(PNG_MAGIC)


def test_render_reuses_robot_image_on_second_pass() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DRAW
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_pose({"x": 1.5, "y": 1.5, "yaw": 0.5}))
    assert _render(camera).startswith(PNG_MAGIC)
    assert camera._robot_image is not None
    # invalidate only the PNG cache; the cached robot sprite must be reused
    camera._cached_png = None
    assert _render(camera).startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# private draw helpers reached directly with degenerate input
# ---------------------------------------------------------------------------


def test_draw_helpers_degenerate_inputs() -> None:
    hub = _hub()
    camera = _camera(hub)
    image, draw = _draw_ctx()

    # transformer is None -> _draw_scene / _draw_station return immediately
    scene = camera._build_scene()
    camera._draw_scene(image, scene)
    camera._draw_station(image, {"x": 0.0, "y": 0.0, "theta": 0})

    # polygon helpers with too-few points or a fully transparent fill
    camera._draw_polygon_pixels(
        image, draw, [(0, 0), (1, 1)], (0, 0, 0, 255), (0, 0, 0, 255), 1
    )
    camera._draw_polygon_pixels(
        image, draw, [(0, 0), (10, 0), (10, 10)], (0, 0, 0, 0), (0, 0, 0, 255), 1
    )
    camera._draw_polygon(image, draw, None, [(0, 0), (1, 1)], (0, 0, 0, 0), (0, 0, 0, 255), 1)

    # polyline / dashed / hatch degenerate paths
    camera._draw_polyline(draw, None, [(0.0, 0.0)], (0, 0, 0, 255), 1)
    camera._draw_dashed_polyline(draw, [(0, 0)], (0, 0, 0, 255), 1, 4, 4)
    camera._draw_dashed_polyline(draw, [(5, 5), (5, 5), (20, 5)], (0, 0, 0, 255), 1, 4, 4)
    camera._apply_hatch(image, [(0, 0), (10, 0)], (0, 0, 0, 255))

    # marker with an unknown kind -> the fallback dot
    camera._draw_marker(draw, (40, 40), (0, 0, 0, 255), "circle")

    # path stroke: too-few points, then the dashed variant
    camera._draw_path_stroke(draw, [(0, 0)], (0, 0, 0, 255), 4, (0, 0, 0, 128), 8)
    camera._draw_path_stroke(
        draw, [(0, 0), (30, 30)], (0, 0, 0, 255), 4, (0, 0, 0, 128), 8, dash=6, gap=4
    )
    assert image.mode == "RGBA"


def test_draw_helpers_requiring_transformer() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DRAW
    asyncio.run(camera._on_map_info({"id": 1}))
    _render(camera)  # establishes camera._transformer
    image, draw = _draw_ctx()

    # three coincident points collapse to a single pixel after simplify, so the
    # path layer / segment bail out on the post-simplify length guard
    coincident = [{"x": 1.0, "y": 1.0}, {"x": 1.0, "y": 1.0}, {"x": 1.0, "y": 1.0}]
    camera._draw_path_layer(image, coincident, "current")
    camera._draw_path_segment(draw, coincident)
    # a station pose that carries no theta -> yaw defaults to zero
    camera._draw_station(image, {"x": 1.0, "y": 1.0})
    assert camera._transformer is not None


def test_draw_summary_panel_breaks_on_overflowing_chips() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {"id": 1, "name": "X", "map_state": "MAP_STATE_COMPLETE"}
    image = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
    # oversized counts make the first count chip overflow the panel and break.
    huge = 10 ** 400
    scene = {
        "scene_counts": {
            "regions": huge,
            "sub_regions": huge,
            "forbidden_zones": huge,
            "physical_forbidden_zones": huge,
            "pass_through_zones": huge,
            "cross_boundary_tunnels": huge,
            "virtual_cross_boundary_tunnels": huge,
        }
    }
    camera._draw_summary_panel(image, scene)
    assert image.mode == "RGBA"
