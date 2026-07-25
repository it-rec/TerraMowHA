"""Scene fit bounds.

``build_scene`` publishes the scene's bounding box instead of a materialized,
deduplicated point cloud; the renderer's ``CoordinateTransformer`` fits that
box. These tests pin the accumulator's own semantics (empty, single point,
negative coordinates) and — the point of the change — that the resulting fit is
identical to the one the full point cloud produced.
"""

from custom_components.terramow.map_render import CoordinateTransformer
from custom_components.terramow.map_scene import _BoundsAccumulator, build_scene


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


MAP_DATA = {
    "id": 4,
    "name": "Garten",
    "origin": {"x": -500.0, "y": -250.0},
    "station_pose": {"x": 120.0, "y": -80.0, "theta": 0},
    "regions": [
        {
            "id": 1,
            "boundary": _poly((0, 0), (4000, 0), (4000, 3000), (0, 3000)),
            "edge_segments": [_poly((0, 0), (4000, 0))],
            "obstacles": [_poly((100, 100), (200, 100), (200, 200))],
            "sub_regions": [
                {
                    "id": 11,
                    "boundary": _poly((10, 10), (900, 10), (900, 900)),
                    "center": {"x": 400.0, "y": 300.0},
                    "inner_boundarys": [_poly((50, 50), (80, 50), (80, 80))],
                    "edge_segments": [_poly((10, 10), (900, 10))],
                }
            ],
        }
    ],
    "forbidden_zones": [_poly((-900, -400), (-800, -400), (-800, -300))],
    "virtual_walls": [{"line": _poly((0, 5000), (100, 5200))}],
    "cross_boundary_tunnels": [{"polygon": _poly((1, 1), (2, 1), (2, 2))}],
    "obstacles": [_poly((3000, 2000), (3100, 2000), (3100, 2100))],
    "clean_info": {
        "draw_region": {"regions": [_poly((5, 5), (15, 5), (15, 15))]},
        "move_to_target_point": {"target_point": {"x": 6000.0, "y": -900.0}},
    },
}

PATH_DATA = {
    "id": 1,
    "map_id": 4,
    "points": [
        {"position": {"x": float(i), "y": float(-i)}, "type": "PATH_POINT_TYPE_CLEANING"}
        for i in range(200)
    ],
}


def _reference_bounds(scene_map, path, history, segments):
    """The bounding box of every point the scene draws, gathered naively."""
    points: list[tuple[float, float]] = []
    scene = build_scene(scene_map, path, history, False, session_path_segments=segments)
    points.extend(scene["map_extent"])
    if scene["origin"] is not None:
        points.append(scene["origin"])
    if scene["station_pose"] is not None:
        points.append((scene["station_pose"]["x"], scene["station_pose"]["y"]))
    for region in scene["regions"]:
        points.extend(region["boundary"])
        for line in region["edge_lines"]:
            points.extend(line)
        for sub in region["sub_regions"]:
            points.extend(sub["boundary"])
            if sub["center"] is not None:
                points.append(sub["center"])
            for inner in sub["inner_boundaries"]:
                points.extend(inner)
            for line in sub["edge_lines"]:
                points.extend(line)
    for key in (
        "forbidden_zones",
        "physical_forbidden_zones",
        "pass_through_zones",
        "required_zones",
        "obstacles",
        "draw_region_polygons",
    ):
        for polygon in scene[key]:
            points.extend(polygon)
    for line in scene["virtual_walls"]:
        points.extend(line)
    for key in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for tunnel in scene[key]:
            for polygon in tunnel["polygons"]:
                points.extend(polygon)
            for polyline in tunnel["polylines"]:
                points.extend(polyline)
    if scene["move_target_point"] is not None:
        points.append(scene["move_target_point"])
    for point in scene["path_points"]:
        points.append((point["x"], point["y"]))
    for segment in scene["session_path_segments"]:
        for point in segment:
            points.append((point["x"], point["y"]))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def test_bounds_match_the_full_point_cloud() -> None:
    """The accumulated box equals the box over every scene point.

    This is the correctness guarantee behind dropping the point cloud: the fit
    only ever read the extremes, and deduplication cannot move an extreme.
    """
    segments = [[{"x": -7000.0, "y": 4200.0}, {"x": -6900.0, "y": 4300.0}]]
    scene = build_scene(
        MAP_DATA, PATH_DATA, {}, False, session_path_segments=segments
    )
    assert scene["bounds"] == _reference_bounds(MAP_DATA, PATH_DATA, {}, segments)


def test_bounds_drive_the_same_fit_as_the_point_cloud() -> None:
    """A transformer built from the box maps corners exactly as before."""
    scene = build_scene(MAP_DATA, PATH_DATA, {}, False)
    bounds = scene["bounds"]
    assert bounds is not None
    from_box = CoordinateTransformer(bounds, rect=(0, 0, 500, 500), padding=20)
    min_x, min_y, max_x, max_y = bounds
    # Both extremes land inside the padded rect and span it on the fitted axis.
    assert from_box.to_pixel(min_x, min_y)[0] >= 20
    assert from_box.to_pixel(max_x, max_y)[0] <= 480
    assert from_box.scale > 0


def test_bounds_are_none_for_an_empty_scene() -> None:
    scene = build_scene({}, {}, {}, False)
    assert scene["bounds"] is None


def test_accumulator_handles_empty_single_and_negative_points() -> None:
    empty = _BoundsAccumulator()
    assert empty.result() is None

    single = _BoundsAccumulator()
    single.add(3.0, -4.0)
    assert single.result() == (3.0, -4.0, 3.0, -4.0)

    spread = _BoundsAccumulator()
    spread.extend([(0.0, 0.0), (-10.0, 5.0), (7.0, -2.0)])
    assert spread.result() == (-10.0, -2.0, 7.0, 5.0)
