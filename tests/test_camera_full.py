"""Thorough coverage for the camera module's pure helpers and render branches.

Unit-tests the geometry / path / formatting helpers and renders scenes that
exercise the marker / tunnel / wall / ellipse / rotation draw paths and the
dock-fallback robot state.
"""

import asyncio
import json
import math
import sys
from unittest.mock import AsyncMock, MagicMock

# HA's camera component imports turbojpeg, which the test harness lacks.
sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402
from custom_components.terramow.map_render import (  # noqa: E402
    _enum_label,
    _format_area,
    _format_file_size,
    _format_point,
    _format_size,
    _truncate,
    render_placeholder,
)
from custom_components.terramow.map_scene import (  # noqa: E402
    _collect_recursive_points,
    _dedupe_points,
    _ellipse_points,
    _extract_map_extent,
    _extract_marker_points,
    _extract_path_points,
    _extract_polygons,
    _extract_polylines,
    _feature_points,
    _filter_cleaning_path_points,
    _line_points,
    _merge_path_points,
    _path_map_id,
    _point_line_distance,
    _polygon_centroid,
    _polygon_points,
    _rdp_simplify_pixels,
    coerce_angle_radians,
    coerce_float,
    coerce_int,
    normalize_angle_radians,
    point_tuple,
    pose_tuple,
    simplify_path_pixels,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


# ---------------------------------------------------------------------------
# scalar / point helpers
# ---------------------------------------------------------------------------


def test_coerce_float_and_int() -> None:
    assert coerce_float("3.5") == 3.5
    assert coerce_float(None) is None
    assert coerce_float("nope") is None
    assert coerce_int("7") == 7
    assert coerce_int(None) is None
    assert coerce_int("bad") is None


def test_point_and_pose_tuple() -> None:
    assert point_tuple({"x": 1, "y": 2}) == (1.0, 2.0)
    assert point_tuple({"x": 1}) is None
    assert point_tuple(None) is None
    # theta falls back to yaw, then to 0.0
    assert pose_tuple({"x": 0, "y": 0, "yaw": 5})["theta"] == 5.0
    assert pose_tuple({"x": 0, "y": 0})["theta"] == 0.0
    assert pose_tuple(None) is None


def test_polygon_and_line_points() -> None:
    assert len(_polygon_points(_poly((0, 0), (1, 0), (1, 1)))) == 3
    assert _polygon_points(None) == []
    # a line via explicit points
    assert len(_line_points(_poly((0, 0), (1, 1)))) == 2
    # a line via start/end keys
    seg = {"start": {"x": 0, "y": 0}, "end": {"x": 2, "y": 2}}
    assert len(_line_points(seg)) == 2


def test_collect_recursive_and_dedupe() -> None:
    nested = {"a": {"x": 1, "y": 1}, "b": [{"x": 2, "y": 2}]}
    pts = _collect_recursive_points(nested)
    assert (1.0, 1.0) in pts and (2.0, 2.0) in pts
    assert _dedupe_points([(1.0, 1.0), (1.0, 1.0), (2.0, 2.0)]) == [(1.0, 1.0), (2.0, 2.0)]


def test_ellipse_points_variants() -> None:
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "radius_x": 1, "radius_y": 2})) == 36
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "width": 2, "height": 4})) == 36
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "a": 1, "b": 1, "rotation": 30})) == 36
    # missing radii -> no polygon
    assert _ellipse_points({"center": {"x": 0, "y": 0}}) == []
    assert _ellipse_points("nope") == []


def test_extract_polygons_and_polylines_and_features() -> None:
    item = {"boundary": _poly((0, 0), (1, 0), (1, 1))}
    assert len(_extract_polygons(item)) == 1
    assert _extract_polygons("x") == []
    wall = {"line": _poly((0, 0), (1, 1))}
    assert len(_extract_polylines(wall)) == 1
    assert _extract_polylines("x") == []
    assert _feature_points({"boundary": _poly((0, 0), (2, 0), (2, 2))})


def test_polygon_centroid_and_markers() -> None:
    assert _polygon_centroid([]) is None
    assert _polygon_centroid([(0.0, 0.0), (2.0, 0.0), (1.0, 3.0)]) == (1.0, 1.0)
    markers = _extract_marker_points([_poly((0, 0), (2, 0), (2, 2), (0, 2))])
    assert len(markers) == 1


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------


def test_extract_path_points_and_map_id() -> None:
    data = {
        "map_id": 3,
        "points": [
            {"position": {"x": 1, "y": 2}, "type": "PATH_POINT_TYPE_CLEANING"},
            {"position": None},          # skipped
            "not-a-dict",                # skipped
        ],
    }
    pts = _extract_path_points(data)
    assert len(pts) == 1 and pts[0]["type"] == "PATH_POINT_TYPE_CLEANING"
    assert _path_map_id(data) == 3
    assert _path_map_id("x") is None
    assert _extract_path_points({"points": "nope"}) == []


def test_merge_and_filter_path_points() -> None:
    a = [{"x": 0.0, "y": 0.0, "type": "PATH_POINT_TYPE_CLEANING"}]
    b = [{"x": 1.0, "y": 1.0, "type": "PATH_POINT_TYPE_TRANSIT"}]
    assert _merge_path_points([], b) == b
    assert _merge_path_points(a, []) == a
    merged = _merge_path_points(a, b)
    assert len(merged) == 2
    # dedupe join when last==first
    joined = _merge_path_points(a, a)
    assert len(joined) == 1
    assert _filter_cleaning_path_points(a + b) == a


def test_pixel_geometry_and_simplify() -> None:
    assert _point_line_distance((0, 1), (0, 0), (0, 0)) == 1.0  # degenerate segment
    assert _point_line_distance((0, 1), (0, 0), (2, 0)) == 1.0
    assert _rdp_simplify_pixels([(0, 0), (5, 0)], 1.0) == [(0, 0), (5, 0)]
    # collinear middle point is dropped
    assert _rdp_simplify_pixels([(0, 0), (1, 0), (2, 0)], 0.5) == [(0, 0), (2, 0)]
    assert simplify_path_pixels([(0, 0), (0, 0), (10, 0)], 1.0, 2.0)


# ---------------------------------------------------------------------------
# map extent / all points / formatting
# ---------------------------------------------------------------------------


def test_map_extent() -> None:
    extent = _extract_map_extent({"width": 100, "height": 80, "resolution": 0.05, "origin": {"x": 0, "y": 0}})
    assert len(extent) == 4
    assert _extract_map_extent({}) == []


def test_coerce_float_non_convertible_and_ellipse_without_center() -> None:
    # neither a number nor a convertible string -> None (final fallthrough)
    assert coerce_float([1, 2]) is None
    # a string that float() rejects -> None
    assert coerce_float("nan-ish!!") is None
    # an ellipse with radii but no resolvable centre yields no polygon
    assert _ellipse_points({"radius_x": 1, "radius_y": 1}) == []


def test_ellipse_points_key_fallbacks() -> None:
    # center inferred from the ellipse dict itself (no "center" key)
    assert len(_ellipse_points({"x": 0, "y": 0, "radius_x": 1, "radius_y": 1})) == 36
    # center found by recursively searching for a nested point
    assert len(
        _ellipse_points({"pts": [{"x": 1, "y": 1}], "radius_x": 1, "radius_y": 1})
    ) == 36
    # rx/ry aliases
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "rx": 1, "ry": 2})) == 36
    # major/minor aliases
    assert len(
        _ellipse_points({"center": {"x": 0, "y": 0}, "major_radius": 2, "minor_radius": 1})
    ) == 36
    # a single radius mirrors onto the missing axis (both directions)
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "radius_x": 2})) == 36
    assert len(_ellipse_points({"center": {"x": 0, "y": 0}, "radius_y": 2})) == 36
    # a large theta is read as milli-radians and converted to degrees
    assert len(
        _ellipse_points(
            {"center": {"x": 0, "y": 0}, "radius_x": 1, "radius_y": 1, "theta": 100000}
        )
    ) == 36


def test_feature_points_includes_bare_point_and_pose() -> None:
    # a bare point and a pose both contribute their coordinates
    assert _feature_points({"x": 1.0, "y": 2.0, "theta": 0.5})


def test_extract_polylines_direct_line_fallback() -> None:
    # no line/polyline/center_line key -> the item itself is treated as a line
    assert len(_extract_polylines(_poly((0, 0), (1, 1)))) == 1


def test_formatting_helpers() -> None:
    assert _enum_label("MAP_STATE_COMPLETE") == "Complete"
    assert _enum_label("") == "-"
    assert _truncate("abcdef", 4).endswith("…")
    assert _truncate("ab", 4) == "ab"
    assert _format_area(2560) == "256.0 m²"
    assert _format_area(None) == "-"
    assert _format_file_size(512) == "512B"
    assert _format_file_size(2048).endswith("KB")
    assert _format_file_size(5 * 1024 * 1024).endswith("MB")
    assert _format_point(None) == "-"
    assert _format_point((1.4, 2.6)) == "1, 3"
    assert _format_size({"width": 100, "height": 80, "resolution": 50}) == "100×80 @ 50mm"
    assert _format_size({}) == "-"


def test_angle_helpers() -> None:
    assert coerce_angle_radians(None) is None
    assert coerce_angle_radians(2000, milli_radian=True) == 2.0
    assert abs(normalize_angle_radians(3 * math.pi) - math.pi) < 1e-6 or \
        abs(normalize_angle_radians(3 * math.pi) + math.pi) < 1e-6


def test_render_placeholder_is_png() -> None:
    assert render_placeholder("Hi").startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# render branches: markers/tunnels/walls/rotation + dock fallback
# ---------------------------------------------------------------------------


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.90", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


MAP_WITH_MARKERS = {
    "id": 1,
    "map_state": "MAP_STATE_COMPLETE",
    "map_view_rotate_angle": 20,
    "station_pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
    "regions": [{"id": 1, "boundary": _poly((0, 0), (4, 0), (4, 4), (0, 4)), "sub_regions": []}],
    "virtual_walls": [_poly((0, 2), (4, 2))],
    "cross_boundary_tunnels": [{"line": _poly((1, 1), (2, 2))}],
    "forbidden_zones": [{"ellipse": {"center": {"x": 3, "y": 3}, "radius_x": 0.5, "radius_y": 0.5}}],
    "cross_boundary_markers": [_poly((1, 3), (1.2, 3), (1.1, 3.2))],
    "trapped_points": [_poly((2, 1), (2.2, 1), (2.1, 1.2))],
    "clean_info": {
        "mode": "MAP_CLEAN_INFO_MODE_DRAW_REGION",
        "draw_region": {"regions": [_poly((0.5, 0.5), (1.5, 0.5), (1.5, 1.5))]},
        "move_to_target_point": {"target_point": {"x": 2.5, "y": 2.5}},
    },
}


def test_render_scene_with_markers_walls_tunnels_rotation() -> None:
    hub = _hub()
    camera = TerraMowMapCamera(hub.basic_data, hub.hass)
    hub._map_data = MAP_WITH_MARKERS
    asyncio.run(camera._on_map_info({"id": 1}))
    assert asyncio.run(camera.async_camera_image()).startswith(PNG_MAGIC)

    scene = camera._build_scene()
    assert scene["rotation_deg"] == 20.0
    assert scene["virtual_walls"]
    assert scene["draw_region_polygons"]
    assert scene["move_target_point"] is not None


def test_render_dock_fallback_robot() -> None:
    hub = _hub()
    camera = TerraMowMapCamera(hub.basic_data, hub.hass)
    # charger connected + an all-zero live pose + a station -> dock fallback
    asyncio.run(hub.on_battery_status(json.dumps({"charger_connected": True})))
    hub._map_data = MAP_WITH_MARKERS
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_pose({"x": 0.0, "y": 0.0, "yaw": 0.0}))

    state = camera._get_display_robot_state()
    assert state["source"] == "dock_fallback"
    assert asyncio.run(camera.async_camera_image()).startswith(PNG_MAGIC)


def test_render_history_only_path() -> None:
    hub = _hub()
    camera = TerraMowMapCamera(hub.basic_data, hub.hass)
    hub._map_data = MAP_WITH_MARKERS
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data({
        "id": 9, "map_id": 1, "type": "PATH_TYPE_CLEAN",
        "points": [
            {"position": {"x": 0.2, "y": 0.2}, "type": "PATH_POINT_TYPE_CLEANING"},
            {"position": {"x": 1.0, "y": 1.0}, "type": "PATH_POINT_TYPE_CLEANING"},
        ],
    }))
    assert asyncio.run(camera.async_camera_image()).startswith(PNG_MAGIC)
    scene = camera._build_scene()
    assert scene["history_path_points"]
