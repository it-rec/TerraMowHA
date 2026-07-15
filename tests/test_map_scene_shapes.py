"""Parametric no-go-zone shapes (circle / rectangle / ellipse) and the
geometry-diagnostics attribute.

Regression context: issue #155 — the device draws no-go zones as polygons,
rectangles, circles or ellipses, but only the polygon form carries a vertex
list. The other three arrive as centre/size/radius descriptors that the old
extractor dropped, so they never rendered on the camera or the card (both go
through ``build_scene``). These tests pin the additive extraction and the
self-diagnosing report that surfaces any still-unhandled encoding.
"""

import math

from custom_components.terramow.map_scene import (  # noqa: E402
    _circle_points,
    _extract_polygons,
    _rect_points,
    build_render_metadata,
    build_scene,
    zone_geometry_diagnostics,
)


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


def _fz_count(item):
    """forbidden_zones count end-to-end through build_scene."""
    scene = build_scene({"id": 1, "forbidden_zones": [item]}, {}, {}, False)
    return scene["scene_counts"]["forbidden_zones"]


# ---------------------------------------------------------------------------
# regression: the working polygon / nested-ellipse paths are unchanged
# ---------------------------------------------------------------------------


def test_polygon_forms_still_render() -> None:
    assert len(_extract_polygons(_poly((0, 0), (1, 0), (1, 1)))) == 1
    assert len(_extract_polygons({"boundary": _poly((0, 0), (2, 0), (2, 2))})) == 1
    assert len(_extract_polygons({"polygon": _poly((0, 0), (2, 0), (2, 2), (0, 2))})) == 1
    assert _fz_count(_poly((0, 0), (10, 0), (10, 10), (0, 10))) == 1


def test_nested_ellipse_unchanged_and_not_double_counted() -> None:
    item = {"ellipse": {"center": {"x": 3, "y": 3}, "radius_x": 0.5, "radius_y": 0.5}}
    polygons = _extract_polygons(item)
    assert len(polygons) == 1  # exactly one, item-level parametric did not also fire
    assert len(polygons[0]) == 36


def test_polygon_with_stray_radius_is_not_double_counted() -> None:
    # An item that already yields a polygon must never also gain a parametric
    # shape from the ``if not polygons`` fallback.
    item = {**_poly((0, 0), (2, 0), (2, 2), (0, 2)), "radius": 5}
    assert len(_extract_polygons(item)) == 1


# ---------------------------------------------------------------------------
# new: parametric shapes now render
# ---------------------------------------------------------------------------


def test_item_level_ellipse_now_renders() -> None:
    # No "ellipse" wrapper — previously dropped, now rendered.
    item = {"center": {"x": 5, "y": 5}, "radius_x": 3, "radius_y": 2}
    polygons = _extract_polygons(item)
    assert len(polygons) == 1 and len(polygons[0]) == 36
    assert _fz_count(item) == 1


def test_firmware_ellipse_semi_axes_now_render() -> None:
    # The real V1000 no-go ellipse encoding: an "ellipse" sub-object with
    # semi_major_axis / semi_minor_axis / rotation_angle and NO vertex list.
    item = {
        "id": 19,
        "is_polygon": False,
        "shape": "SHAPE_ELLIPSE",
        "ellipse": {
            "center": {"x": -13578, "y": -10382},
            "semi_major_axis": 1292,
            "semi_minor_axis": 888,
            "rotation_angle": 0,
        },
    }
    polygons = _extract_polygons(item)
    assert len(polygons) == 1 and len(polygons[0]) == 36
    # the sampled ring spans the full semi-axes about the centre
    xs = [p[0] for p in polygons[0]]
    ys = [p[1] for p in polygons[0]]
    assert round(max(xs) - min(xs)) == 2 * 1292
    assert round(max(ys) - min(ys)) == 2 * 888
    # and it reaches the card/camera end-to-end
    assert _fz_count(item) == 1


def test_circle_by_radius_variants() -> None:
    assert len(_circle_points({"center": {"x": 0, "y": 0}, "radius": 2})) == 36
    assert len(_circle_points({"center": {"x": 0, "y": 0}, "r": 2})) == 36
    assert len(_circle_points({"center": {"x": 0, "y": 0}, "diameter": 4})) == 36
    # center inferred from the dict itself
    assert len(_circle_points({"x": 1, "y": 1, "radius": 2})) == 36
    # degenerate / missing pieces -> no polygon
    assert _circle_points({"center": {"x": 0, "y": 0}, "radius": 0}) == []
    assert _circle_points({"radius": 2}) == []
    assert _circle_points("nope") == []
    # end-to-end through the zone extractor
    assert _fz_count({"center": {"x": 5, "y": 5}, "radius": 3}) == 1


def test_rectangle_and_square_forms() -> None:
    # centre + width/height
    rect = _rect_points({"center": {"x": 0, "y": 0}, "width": 4, "height": 2})
    assert len(rect) == 4
    # square via a single size
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "size": 3})) == 4
    # two opposite corners -> normalized winding
    assert _rect_points({"min": {"x": -1, "y": -1}, "max": {"x": 1, "y": 1}}) == [
        (-1.0, -1.0),
        (1.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
    ]
    # flat bbox scalars, even when given "backwards"
    assert _rect_points({"min_x": 1, "min_y": 1, "max_x": -1, "max_y": -1}) == [
        (-1.0, -1.0),
        (1.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
    ]
    # top_left / bottom_right
    assert len(_rect_points({"top_left": {"x": -1, "y": 1}, "bottom_right": {"x": 1, "y": -1}})) == 4
    # degenerate / unrecognized -> []
    assert _rect_points({"center": {"x": 0, "y": 0}, "width": 0, "height": 2}) == []
    assert _rect_points({"center": {"x": 0, "y": 0}}) == []
    assert _rect_points("nope") == []
    assert _fz_count({"center": {"x": 5, "y": 5}, "width": 4, "height": 4}) == 1


def test_rect_rotation_keeps_a_valid_quad() -> None:
    rot = _rect_points(
        {"center": {"x": 0, "y": 0}, "width": 2, "height": 2, "rotation": 45}
    )
    assert len(rot) == 4
    # a rotated unit square: every corner stays sqrt(2) from the centre
    for x, y in rot:
        assert abs(math.hypot(x, y) - math.sqrt(2)) < 1e-6


def test_rect_alias_and_edge_branches() -> None:
    # degenerate corner pair -> no polygon
    assert _rect_points({"min": {"x": 0, "y": 0}, "max": {"x": 0, "y": 5}}) == []
    # bottom_left / top_right corner pair
    assert len(_rect_points({"bottom_left": {"x": 0, "y": 0}, "top_right": {"x": 2, "y": 2}})) == 4
    # explicit half_width / half_height
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "half_width": 2, "half_height": 1})) == 4
    # size present but both half extents already set -> size is ignored
    assert (
        len(
            _rect_points(
                {"center": {"x": 0, "y": 0}, "half_width": 2, "half_height": 1, "size": 9}
            )
        )
        == 4
    )
    # a single axis mirrors onto the other (square) — both directions
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "width": 4})) == 4
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "height": 6})) == 4
    # centre taken from the dict itself (no "center" key)
    assert len(_rect_points({"x": 0, "y": 0, "width": 4, "height": 2})) == 4
    # rotation via "angle" and via a milli-radian "theta"
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "size": 2, "angle": 30})) == 4
    assert len(_rect_points({"center": {"x": 0, "y": 0}, "size": 2, "theta": 100000})) == 4
    # "rectangle" nested sub-object
    assert len(_extract_polygons({"rectangle": {"min": {"x": 0, "y": 0}, "max": {"x": 2, "y": 2}}})) == 1


def test_circle_center_from_nested_point() -> None:
    # centre recovered by recursively searching for a nested point
    assert len(_circle_points({"pts": [{"x": 1, "y": 1}], "radius": 2})) == 36


def test_nested_shape_subobjects_render() -> None:
    assert len(_extract_polygons({"circle": {"center": {"x": 0, "y": 0}, "radius": 1}})) == 1
    assert len(_extract_polygons({"rect": {"min": {"x": 0, "y": 0}, "max": {"x": 2, "y": 2}}})) == 1
    assert len(_extract_polygons({"bbox": {"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1}})) == 1
    assert len(_extract_polygons({"bounds": {"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1}})) == 1


def test_rectangle_wins_over_ellipse_on_width_height() -> None:
    # A bare centre + width/height renders as a 4-point rectangle, not a
    # 36-point inscribed ellipse (dispatcher order).
    polygons = _extract_polygons({"center": {"x": 0, "y": 0}, "width": 4, "height": 2})
    assert len(polygons) == 1 and len(polygons[0]) == 4


def test_scene_counts_increase_across_zone_collections() -> None:
    circle = {"center": {"x": 5, "y": 5}, "radius": 3}
    scene = build_scene(
        {
            "id": 1,
            "forbidden_zones": [circle],
            "physical_forbidden_zones": [circle],
            "pass_through_zones": [circle],
            "required_zones": [circle],
        },
        {},
        {},
        False,
    )
    counts = scene["scene_counts"]
    assert counts["forbidden_zones"] == 1
    assert counts["physical_forbidden_zones"] == 1
    assert counts["pass_through_zones"] == 1
    assert counts["required_zones"] == 1


# ---------------------------------------------------------------------------
# self-diagnosing geometry report
# ---------------------------------------------------------------------------


def test_diagnostic_reports_dropped_item_keys() -> None:
    map_data = {
        "id": 1,
        "forbidden_zones": [
            _poly((0, 0), (1, 0), (1, 1)),  # renders
            {"mystery_center": {"x": 1, "y": 1}, "mystery_r": 5},  # unknown shape
        ],
    }
    diag = zone_geometry_diagnostics(map_data)
    assert diag["forbidden_zones"] == {
        "raw_item_count": 2,
        "rendered_item_count": 1,
        "dropped_item_count": 1,
        "dropped_item_keys": ["mystery_center", "mystery_r"],
    }


def test_diagnostic_empty_when_everything_renders() -> None:
    map_data = {
        "id": 1,
        "forbidden_zones": [{"center": {"x": 5, "y": 5}, "radius": 3}],
        "physical_forbidden_zones": [_poly((0, 0), (1, 0), (1, 1))],
    }
    assert zone_geometry_diagnostics(map_data) == {}


def test_diagnostic_handles_non_dict_items_and_non_dict_input() -> None:
    diag = zone_geometry_diagnostics({"id": 1, "forbidden_zones": ["not-a-dict"]})
    assert diag["forbidden_zones"] == {
        "raw_item_count": 1,
        "rendered_item_count": 0,
        "dropped_item_count": 1,
        "dropped_item_keys": [],
    }
    # a non-dict map_data is treated as empty
    assert zone_geometry_diagnostics(None) == {}


def test_diagnostic_covers_tunnels() -> None:
    # a tunnel item that yields neither polygon nor polyline is reported
    diag = zone_geometry_diagnostics(
        {"id": 1, "cross_boundary_tunnels": [{"marker_id": 3}]}
    )
    assert diag["cross_boundary_tunnels"]["dropped_item_count"] == 1
    assert diag["cross_boundary_tunnels"]["dropped_item_keys"] == ["marker_id"]


def test_diagnostic_covers_walls_and_is_surfaced_in_metadata() -> None:
    # A wall carrying no extractable endpoints at all (the polyline extractor
    # is permissive and would otherwise recover any nested points).
    map_data = {
        "id": 1,
        "virtual_walls": [{"style": "dashed", "wall_id": 7}],
    }
    diag = zone_geometry_diagnostics(map_data)
    assert diag["virtual_walls"]["dropped_item_count"] == 1
    assert diag["virtual_walls"]["dropped_item_keys"] == ["style", "wall_id"]
    # and it is exposed through the camera's render metadata
    scene = build_scene(map_data, {}, {}, False)
    meta = build_render_metadata(scene, map_data, {}, {})
    assert meta["geometry_diagnostics"] == diag
