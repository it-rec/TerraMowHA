"""TerraMow map scene building.

Protocol-parsing / geometry layer of the map camera: pure functions that
coerce and extract points, polygons and paths from the ha_map_v1 / ha_path_v1
protocol dicts, simplify polylines for display, and organize everything into
a drawable scene plus its render metadata. No PIL here — the drawing lives in
map_render.py, and the entity plumbing in camera.py.
"""

from __future__ import annotations

import math
from typing import Any

HANDLED_MAP_FIELDS = {
    "id",
    "name",
    "width",
    "height",
    "resolution",
    "origin",
    "has_station",
    "station_pose",
    "regions",
    "obstacles",
    "forbidden_zones",
    "virtual_walls",
    "physical_forbidden_zones",
    "cross_boundary_markers",
    "total_area",
    "map_state",
    "cross_boundary_tunnels",
    "trapped_points",
    "has_bird_view",
    "bird_view_index",
    "clean_info",
    "mow_param",
    "has_backup",
    "required_zones",
    "file_size",
    "virtual_cross_boundary_tunnels",
    "type",
    "pass_through_zones",
    "backup_info_list",
    "map_view_rotate_angle",
    "maintenance_points",
    "is_boundary_locked",
    "enable_advanced_edge_cutting",
    "is_able_to_run_build_map",
}
HANDLED_PATH_FIELDS = {"id", "map_id", "type", "points"}


def coerce_float(value: Any) -> float | None:
    """Convert the input to a float where possible."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def coerce_int(value: Any) -> int | None:
    """Convert the input to an int where possible."""
    number = coerce_float(value)
    if number is None:
        return None
    return int(number)


def point_tuple(obj: Any) -> tuple[float, float] | None:
    """Extract a Point from an object."""
    if not isinstance(obj, dict):
        return None
    x = coerce_float(obj.get("x"))
    y = coerce_float(obj.get("y"))
    if x is None or y is None:
        return None
    return (x, y)


def pose_tuple(obj: Any) -> dict[str, float] | None:
    """Extract a Pose from an object."""
    point = point_tuple(obj)
    if point is None:
        return None
    theta = coerce_float(obj.get("theta"))
    yaw = coerce_float(obj.get("yaw"))
    return {
        "x": point[0],
        "y": point[1],
        # Fall back to yaw, then to 0.0 so the pose always carries a concrete
        # angle; a missing theta must not propagate None into the rotation math.
        "theta": theta if theta is not None else (yaw if yaw is not None else 0.0),
    }


def _polygon_points(polygon: dict[str, Any] | None) -> list[tuple[float, float]]:
    """Extract the point list from a Polygon object."""
    if not isinstance(polygon, dict):
        return []
    raw = polygon.get("points")
    if not isinstance(raw, list):
        return []
    points: list[tuple[float, float]] = []
    for item in raw:
        point = point_tuple(item)
        if point is not None:
            points.append(point)
    return points


def _line_points(line: Any) -> list[tuple[float, float]]:
    """Extract the point list from a Line or any linear structure."""
    if isinstance(line, dict):
        direct = _polygon_points(line)
        if len(direct) >= 2:
            return direct
        candidates: list[tuple[float, float]] = []
        for key in (
            "start",
            "end",
            "start_point",
            "end_point",
            "point1",
            "point2",
            "from",
            "to",
        ):
            point = point_tuple(line.get(key))
            if point is not None:
                candidates.append(point)
        if len(candidates) >= 2:
            return candidates
    return _collect_recursive_points(line, limit=8)


def _collect_recursive_points(data: Any, limit: int = 64) -> list[tuple[float, float]]:
    """Recursively collect points from an arbitrary object."""
    points: list[tuple[float, float]] = []
    stack = [data]
    while stack and len(points) < limit:
        item = stack.pop()
        point = point_tuple(item)
        if point is not None:
            points.append(point)
        if isinstance(item, dict):
            for value in item.values():
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
    return _dedupe_points(points)


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Deduplicate points by coordinate."""
    seen: set[tuple[int, int]] = set()
    result: list[tuple[float, float]] = []
    for point in points:
        key = (int(round(point[0] * 1000)), int(round(point[1] * 1000)))
        if key in seen:
            continue
        seen.add(key)
        result.append(point)
    return result


def _ellipse_points(ellipse: Any, segments: int = 36) -> list[tuple[float, float]]:
    """Approximate an Ellipse as a set of polygon points."""
    if not isinstance(ellipse, dict):
        return []

    center = point_tuple(ellipse.get("center"))
    if center is None:
        center = point_tuple(ellipse)
    if center is None:
        points = _collect_recursive_points(ellipse, limit=8)
        center = points[0] if points else None
    if center is None:
        return []

    radius_x = coerce_float(ellipse.get("radius_x"))
    radius_y = coerce_float(ellipse.get("radius_y"))
    if radius_x is None:
        radius_x = coerce_float(ellipse.get("rx"))
    if radius_y is None:
        radius_y = coerce_float(ellipse.get("ry"))
    if radius_x is None:
        width = coerce_float(ellipse.get("width"))
        if width is not None:
            radius_x = width / 2
    if radius_y is None:
        height = coerce_float(ellipse.get("height"))
        if height is not None:
            radius_y = height / 2
    if radius_x is None:
        radius_x = coerce_float(ellipse.get("major_radius"))
    if radius_y is None:
        radius_y = coerce_float(ellipse.get("minor_radius"))
    if radius_x is None:
        radius_x = coerce_float(ellipse.get("a"))
    if radius_y is None:
        radius_y = coerce_float(ellipse.get("b"))
    if radius_x is None and radius_y is not None:
        radius_x = radius_y
    if radius_y is None and radius_x is not None:
        radius_y = radius_x
    if radius_x is None or radius_y is None or radius_x <= 0 or radius_y <= 0:
        return []

    rotation = coerce_float(ellipse.get("rotation"))
    if rotation is None:
        rotation = coerce_float(ellipse.get("angle"))
    if rotation is None:
        rotation = coerce_float(ellipse.get("theta"))
        if rotation is not None and abs(rotation) > math.pi * 4:
            rotation = rotation / 1000.0
            rotation = math.degrees(rotation)
    rotation_rad = math.radians(rotation or 0.0)
    cos_a = math.cos(rotation_rad)
    sin_a = math.sin(rotation_rad)

    result: list[tuple[float, float]] = []
    cx, cy = center
    for index in range(segments):
        angle = 2 * math.pi * index / segments
        local_x = radius_x * math.cos(angle)
        local_y = radius_y * math.sin(angle)
        point_x = cx + local_x * cos_a - local_y * sin_a
        point_y = cy + local_x * sin_a + local_y * cos_a
        result.append((point_x, point_y))
    return result


def _extract_polygons(item: Any) -> list[list[tuple[float, float]]]:
    """Extract the list of polygons from an object."""
    polygons: list[list[tuple[float, float]]] = []
    if not isinstance(item, dict):
        return polygons

    direct = _polygon_points(item)
    if len(direct) >= 3:
        polygons.append(direct)

    for key in ("boundary", "polygon"):
        points = _polygon_points(item.get(key))
        if len(points) >= 3:
            polygons.append(points)

    ellipse = item.get("ellipse")
    ellipse_points = _ellipse_points(ellipse)
    if len(ellipse_points) >= 3:
        polygons.append(ellipse_points)

    return polygons


def _extract_polylines(item: Any) -> list[list[tuple[float, float]]]:
    """Extract the list of polylines from an object."""
    polylines: list[list[tuple[float, float]]] = []
    if not isinstance(item, dict):
        return polylines
    for key in ("line", "polyline", "center_line"):
        points = _line_points(item.get(key))
        if len(points) >= 2:
            polylines.append(points)
    if not polylines:
        direct = _line_points(item)
        if len(direct) >= 2:
            polylines.append(direct)
    return polylines


def _feature_points(item: Any) -> list[tuple[float, float]]:
    """Extract all points of a spatial object."""
    points: list[tuple[float, float]] = []
    for polygon in _extract_polygons(item):
        points.extend(polygon)
    for polyline in _extract_polylines(item):
        points.extend(polyline)
    point = point_tuple(item)
    if point is not None:
        points.append(point)
    pose = pose_tuple(item)
    if pose is not None:
        points.append((pose["x"], pose["y"]))
    return _dedupe_points(points)


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Compute a simple centroid."""
    if not points:
        return None
    x = sum(point[0] for point in points) / len(points)
    y = sum(point[1] for point in points) / len(points)
    return (x, y)


def _extract_marker_points(items: list[Any]) -> list[tuple[float, float]]:
    """Extract center points from a collection of objects."""
    markers: list[tuple[float, float]] = []
    for item in items:
        points = _feature_points(item)
        if points:
            marker = _polygon_centroid(points)
            if marker is not None:
                markers.append(marker)
    return _dedupe_points(markers)


def _extract_path_points(path_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the PathPoint list from ha_path_v1."""
    raw = path_data.get("points")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        position = point_tuple(item.get("position"))
        if position is None:
            continue
        result.append(
            {
                "x": position[0],
                "y": position[1],
                "type": item.get("type", ""),
            }
        )
    return result


def _path_map_id(path_data: dict[str, Any]) -> int | None:
    """Extract the map ID that the path belongs to."""
    if not isinstance(path_data, dict):
        return None
    return coerce_int(path_data.get("map_id"))


def _path_point_key(point: dict[str, Any]) -> tuple[int, int, str]:
    """Build a deduplication key for a path point."""
    return (
        int(round(point["x"] * 1000)),
        int(round(point["y"] * 1000)),
        str(point.get("type", "")),
    )


def _merge_path_points(
    history_points: list[dict[str, Any]],
    current_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Concatenate path points with the history path first and the current path last."""
    if not history_points:
        return list(current_points)
    if not current_points:
        return list(history_points)
    if _path_point_key(history_points[-1]) == _path_point_key(current_points[0]):
        return [*history_points, *current_points[1:]]
    return [*history_points, *current_points]


def _filter_cleaning_path_points(path_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only mowing path points."""
    return [point for point in path_points if point.get("type") == "PATH_POINT_TYPE_CLEANING"]


def _pixel_distance(point_a: tuple[int, int], point_b: tuple[int, int]) -> float:
    """Compute the distance between two pixel points."""
    return math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1])


def _point_line_distance(
    point: tuple[int, int],
    line_start: tuple[int, int],
    line_end: tuple[int, int],
) -> float:
    """Compute the perpendicular distance from a point to a line segment."""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def _rdp_simplify_pixels(points: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    """Simplify a pixel polyline using the RDP algorithm.

    Iterative (explicit stack) rather than recursive so a very long mowing
    session — tens of thousands of points — can't exceed Python's recursion
    limit.
    """
    count = len(points)
    if count <= 2:
        return list(points)

    # keep[i] marks whether points[i] survives simplification.
    keep = [False] * count
    keep[0] = keep[count - 1] = True
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        start = points[first]
        end = points[last]
        max_distance = 0.0
        max_index = first
        for index in range(first + 1, last):
            distance = _point_line_distance(points[index], start, end)
            if distance > max_distance:
                max_distance = distance
                max_index = index
        if max_distance > epsilon:
            keep[max_index] = True
            stack.append((first, max_index))
            stack.append((max_index, last))

    return [point for point, kept in zip(points, keep, strict=True) if kept]


def simplify_path_pixels(
    pixels: list[tuple[int, int]],
    epsilon: float,
    min_segment: float,
) -> list[tuple[int, int]]:
    """Simplify path pixels for display purposes."""
    if len(pixels) <= 2:
        return list(pixels)

    deduped = [pixels[0]]
    for point in pixels[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    if len(deduped) <= 2:
        return deduped

    simplified = _rdp_simplify_pixels(deduped, epsilon)
    if len(simplified) <= 2:
        return simplified

    filtered = [simplified[0]]
    for point in simplified[1:-1]:
        if _pixel_distance(filtered[-1], point) >= min_segment:
            filtered.append(point)
    if simplified[-1] != filtered[-1]:
        filtered.append(simplified[-1])
    return filtered


def _extract_map_extent(map_data: dict[str, Any]) -> list[tuple[float, float]]:
    """Derive the map's outer bounding box from width/height/resolution/origin."""
    width = coerce_float(map_data.get("width"))
    height = coerce_float(map_data.get("height"))
    resolution = coerce_float(map_data.get("resolution"))
    origin = point_tuple(map_data.get("origin"))
    if width is None or height is None or resolution is None or origin is None:
        return []
    origin_x, origin_y = origin
    max_x = origin_x + width * resolution
    max_y = origin_y + height * resolution
    return [
        (origin_x, origin_y),
        (max_x, origin_y),
        (max_x, max_y),
        (origin_x, max_y),
    ]


def coerce_angle_radians(value: Any, milli_radian: bool = False) -> float | None:
    """Convert an angle to radians."""
    number = coerce_float(value)
    if number is None:
        return None
    if milli_radian:
        return number / 1000.0
    return number


def normalize_angle_radians(value: float) -> float:
    """Normalize radians to the range [-pi, pi)."""
    return math.atan2(math.sin(value), math.cos(value))


def build_scene(
    map_data: dict[str, Any],
    path_data: dict[str, Any],
    history_path_data: dict[str, Any],
    show_coverage: bool,
) -> dict[str, Any]:
    """Organize the raw protocol data into a drawable scene."""
    map_data = map_data if isinstance(map_data, dict) else {}
    path_data = path_data if isinstance(path_data, dict) else {}
    history_path_data = history_path_data if isinstance(history_path_data, dict) else {}
    clean_info = map_data.get("clean_info", {})
    mow_param = map_data.get("mow_param", {})
    current_map_id = coerce_int(map_data.get("id"))
    raw_current_path_points = _extract_path_points(path_data)
    raw_history_path_points = _extract_path_points(history_path_data)
    current_path_points = _filter_cleaning_path_points(raw_current_path_points)
    history_path_points = _filter_cleaning_path_points(raw_history_path_points)
    current_path_map_id = _path_map_id(path_data)
    history_path_map_id = _path_map_id(history_path_data)
    target_map_id = current_map_id
    if target_map_id is None:
        if current_path_points and current_path_map_id is not None:
            target_map_id = current_path_map_id
        elif history_path_points and history_path_map_id is not None:
            target_map_id = history_path_map_id

    path_map_mismatch = False
    if target_map_id is not None and current_path_map_id is not None and current_path_map_id != target_map_id:
        current_path_points = []
        path_map_mismatch = True
    if target_map_id is not None and history_path_map_id is not None and history_path_map_id != target_map_id:
        history_path_points = []
        path_map_mismatch = True

    combined_path_points = _merge_path_points(history_path_points, current_path_points)
    display_path_data = path_data if current_path_points else history_path_data if history_path_points else path_data
    selected_ids: set[int] = set()
    if isinstance(clean_info, dict):
        select_region = clean_info.get("select_region", {})
        if isinstance(select_region, dict):
            for region_id in select_region.get("region_id", []):
                integer = coerce_int(region_id)
                if integer is not None:
                    selected_ids.add(integer)

    region_param_ids: set[int] = set()
    if isinstance(mow_param, dict):
        for item in mow_param.get("regions", []):
            if not isinstance(item, dict):
                continue
            region_id = coerce_int(item.get("id"))
            if region_id is not None:
                region_param_ids.add(region_id)

    scene: dict[str, Any] = {
        "rotation_deg": coerce_float(map_data.get("map_view_rotate_angle")) or 0.0,
        "map_extent": _extract_map_extent(map_data),
        "origin": point_tuple(map_data.get("origin")),
        "station_pose": pose_tuple(map_data.get("station_pose")),
        "path_points": combined_path_points,
        "current_path_points": current_path_points,
        "history_path_points": history_path_points,
        "filtered_non_cleaning_point_count": {
            "current": len(raw_current_path_points) - len(current_path_points),
            "history": len(raw_history_path_points) - len(history_path_points),
        },
        "path_display_id": display_path_data.get("id"),
        "path_display_type": display_path_data.get("type"),
        "path_map_mismatch": path_map_mismatch,
        "regions": [],
        "forbidden_zones": [],
        "physical_forbidden_zones": [],
        "pass_through_zones": [],
        "required_zones": [],
        "obstacles": [],
        "virtual_walls": [],
        "cross_boundary_tunnels": [],
        "virtual_cross_boundary_tunnels": [],
        "cross_boundary_markers": _extract_marker_points(map_data.get("cross_boundary_markers", [])),
        "trapped_points": _extract_marker_points(map_data.get("trapped_points", [])),
        "maintenance_points": _extract_marker_points(map_data.get("maintenance_points", [])),
        "draw_region_polygons": [],
        "move_target_point": None,
    }

    all_points: list[tuple[float, float]] = []
    all_points.extend(scene["map_extent"])

    if scene["origin"] is not None:
        all_points.append(scene["origin"])
    if scene["station_pose"] is not None:
        all_points.append((scene["station_pose"]["x"], scene["station_pose"]["y"]))

    for region in map_data.get("regions", []):
        if not isinstance(region, dict):
            continue
        region_boundary = _polygon_points(region.get("boundary"))
        region_record: dict[str, Any] = {
            "id": coerce_int(region.get("id")),
            "name": region.get("name"),
            "boundary": region_boundary,
            "sub_regions": [],
            "edge_lines": [],
        }
        all_points.extend(region_boundary)

        for edge_segment in region.get("edge_segments", []):
            edge_line = _line_points(edge_segment)
            if len(edge_line) >= 2:
                region_record["edge_lines"].append(edge_line)
                all_points.extend(edge_line)

        for obstacle in region.get("obstacles", []):
            obstacle_polygons = _extract_polygons(obstacle)
            for polygon in obstacle_polygons:
                scene["obstacles"].append(polygon)
                all_points.extend(polygon)

        for sub_region in region.get("sub_regions", []):
            if not isinstance(sub_region, dict):
                continue
            sub_boundary = _polygon_points(sub_region.get("boundary"))
            inner_boundaries: list[list[tuple[float, float]]] = []
            for inner in sub_region.get("inner_boundarys", []):
                points = _polygon_points(inner)
                if len(points) >= 3:
                    inner_boundaries.append(points)
                    all_points.extend(points)

            edge_lines: list[list[tuple[float, float]]] = []
            for key in ("edge_segments", "boudary_polyline_descriptions"):
                for edge_segment in sub_region.get(key, []):
                    points = _line_points(edge_segment)
                    if len(points) >= 2:
                        edge_lines.append(points)
                        all_points.extend(points)

            center = point_tuple(sub_region.get("center"))
            if center is None and sub_boundary:
                center = _polygon_centroid(sub_boundary)
            sub_id = coerce_int(sub_region.get("id"))
            selected = bool(sub_region.get("is_selected_for_mow")) or (
                sub_id in selected_ids if sub_id is not None else False
            )
            region_record["sub_regions"].append(
                {
                    "id": sub_id,
                    "name": sub_region.get("name"),
                    "boundary": sub_boundary,
                    "center": center,
                    "selected": selected,
                    "order": coerce_int(sub_region.get("selected_for_mow_order")),
                    "has_custom_param": sub_id in region_param_ids if sub_id is not None else False,
                    "inner_boundaries": inner_boundaries,
                    "edge_lines": edge_lines,
                }
            )
            all_points.extend(sub_boundary)
            if center is not None:
                all_points.append(center)

        scene["regions"].append(region_record)

    for key in ("forbidden_zones", "physical_forbidden_zones", "pass_through_zones", "required_zones"):
        for item in map_data.get(key, []):
            for polygon in _extract_polygons(item):
                scene[key].append(polygon)
                all_points.extend(polygon)

    for obstacle in map_data.get("obstacles", []):
        for polygon in _extract_polygons(obstacle):
            scene["obstacles"].append(polygon)
            all_points.extend(polygon)

    for wall in map_data.get("virtual_walls", []):
        for line in _extract_polylines(wall):
            scene["virtual_walls"].append(line)
            all_points.extend(line)

    for key in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for item in map_data.get(key, []):
            polygons = _extract_polygons(item)
            polylines = _extract_polylines(item)
            scene[key].append({"polygons": polygons, "polylines": polylines})
            for polygon in polygons:
                all_points.extend(polygon)
            for polyline in polylines:
                all_points.extend(polyline)

    if isinstance(clean_info, dict):
        draw_region = clean_info.get("draw_region", {})
        if isinstance(draw_region, dict):
            for polygon in draw_region.get("regions", []):
                points = _polygon_points(polygon)
                if len(points) >= 3:
                    scene["draw_region_polygons"].append(points)
                    all_points.extend(points)
        move_to_target = clean_info.get("move_to_target_point", {})
        if isinstance(move_to_target, dict):
            scene["move_target_point"] = point_tuple(move_to_target.get("target_point"))
            if scene["move_target_point"] is not None:
                all_points.append(scene["move_target_point"])

    for path_point in scene["path_points"]:
        all_points.append((path_point["x"], path_point["y"]))

    scene["all_points"] = _dedupe_points(all_points)
    scene["scene_counts"] = {
        "regions": len(scene["regions"]),
        "sub_regions": sum(len(region["sub_regions"]) for region in scene["regions"]),
        "forbidden_zones": len(scene["forbidden_zones"]),
        "physical_forbidden_zones": len(scene["physical_forbidden_zones"]),
        "pass_through_zones": len(scene["pass_through_zones"]),
        "required_zones": len(scene["required_zones"]),
        "obstacles": len(scene["obstacles"]),
        "virtual_walls": len(scene["virtual_walls"]),
        "cross_boundary_tunnels": len(scene["cross_boundary_tunnels"]),
        "virtual_cross_boundary_tunnels": len(scene["virtual_cross_boundary_tunnels"]),
        "cross_boundary_markers": len(scene["cross_boundary_markers"]),
        "trapped_points": len(scene["trapped_points"]),
        "maintenance_points": len(scene["maintenance_points"]),
        "path_points": len(scene["path_points"]),
        "current_path_points": len(scene["current_path_points"]),
        "history_path_points": len(scene["history_path_points"]),
        "filtered_non_cleaning_path_points": (
            scene["filtered_non_cleaning_point_count"]["current"]
            + scene["filtered_non_cleaning_point_count"]["history"]
        ),
    }
    scene["rendered_layers"] = [
        "map_extent",
        "regions",
        "sub_regions",
        "pass_through_zones",
        "required_zones",
        "forbidden_zones",
        "physical_forbidden_zones",
        "obstacles",
        "virtual_walls",
        "cross_boundary_tunnels",
        "virtual_cross_boundary_tunnels",
        "cross_boundary_markers",
        "trapped_points",
        "maintenance_points",
        "path",
        "station_pose",
        "move_target",
        "summary_hud",
    ]
    if show_coverage:
        scene["rendered_layers"].insert(
            scene["rendered_layers"].index("path"), "coverage"
        )
    return scene


def build_render_metadata(
    scene: dict[str, Any],
    map_data: dict[str, Any],
    path_data: dict[str, Any],
    history_path_data: dict[str, Any],
) -> dict[str, Any]:
    """Build the entity attributes."""
    map_data = map_data if isinstance(map_data, dict) else {}
    path_data = path_data if isinstance(path_data, dict) else {}
    history_path_data = history_path_data if isinstance(history_path_data, dict) else {}
    clean_info = map_data.get("clean_info", {})
    mow_param = map_data.get("mow_param", {})
    backup_info = map_data.get("backup_info_list", [])

    if isinstance(clean_info, dict):
        clean_summary = {
            "mode": clean_info.get("mode"),
            "selected_region_count": len(
                clean_info.get("select_region", {}).get("region_id", [])
            )
            if isinstance(clean_info.get("select_region"), dict)
            else 0,
            "draw_region_count": len(clean_info.get("draw_region", {}).get("regions", []))
            if isinstance(clean_info.get("draw_region"), dict)
            else 0,
            "has_target_point": bool(
                isinstance(clean_info.get("move_to_target_point"), dict)
                and clean_info["move_to_target_point"].get("target_point")
            ),
        }
    else:
        clean_summary = {}

    if isinstance(mow_param, dict):
        global_param = mow_param.get("global_param", {})
        mow_summary = {
            "region_param_count": len(mow_param.get("regions", []))
            if isinstance(mow_param.get("regions"), list)
            else 0,
            "mow_height": global_param.get("mow_height")
            if isinstance(global_param, dict)
            else None,
            "mow_speed": global_param.get("mow_speed")
            if isinstance(global_param, dict)
            else None,
            "main_direction_angle": (
                global_param.get("main_direction_angle_config", {}).get("current_angle")
                if isinstance(global_param, dict)
                and isinstance(global_param.get("main_direction_angle_config"), dict)
                else None
            ),
            "enable_thorough_corner_cutting": mow_param.get(
                "enable_thorough_corner_cutting"
            ),
            "high_grass_edge_trim_mode": (
                mow_param.get("high_grass_edge_trim_mode", {}).get("mode")
                if isinstance(mow_param.get("high_grass_edge_trim_mode"), dict)
                else None
            ),
        }
    else:
        mow_summary = {}

    if isinstance(backup_info, list):
        backup_summary = {
            "has_backup": map_data.get("has_backup", False),
            "backup_count": len(backup_info),
            "file_size": map_data.get("file_size"),
        }
    else:
        backup_summary = {}

    return {
        "present_top_level_fields": {
            "map": sorted(map_data.keys()),
            "path": {
                "current": sorted(path_data.keys()),
                "history": sorted(history_path_data.keys()),
            },
        },
        "scene_counts": scene.get("scene_counts", {}),
        "rendered_layers": scene.get("rendered_layers", []),
        "unrendered_fields": {
            "map": sorted(set(map_data.keys()) - HANDLED_MAP_FIELDS),
            "path": {
                "current": sorted(set(path_data.keys()) - HANDLED_PATH_FIELDS),
                "history": sorted(set(history_path_data.keys()) - HANDLED_PATH_FIELDS),
            },
        },
        "clean_info_summary": clean_summary,
        "mow_param_summary": mow_summary,
        "backup_summary": backup_summary,
        "path_summary": {
            "id": scene.get("path_display_id"),
            "map_id": path_data.get("map_id") if scene.get("current_path_points") else history_path_data.get("map_id"),
            "type": scene.get("path_display_type"),
            "point_count": len(scene.get("path_points", [])),
        },
        "current_path_summary": {
            "id": path_data.get("id"),
            "map_id": path_data.get("map_id"),
            "type": path_data.get("type"),
            "point_count": len(scene.get("current_path_points", [])),
        },
        "history_path_summary": {
            "id": history_path_data.get("id"),
            "map_id": history_path_data.get("map_id"),
            "type": history_path_data.get("type"),
            "point_count": len(scene.get("history_path_points", [])),
        },
        "combined_path_summary": {
            "point_count": len(scene.get("path_points", [])),
            "history_path_available": bool(history_path_data),
            "path_map_mismatch": scene.get("path_map_mismatch", False),
        },
        "filtered_non_cleaning_point_count": scene.get("filtered_non_cleaning_point_count", {}),
        "rotation_angle": scene.get("rotation_deg", 0.0),
        "map_name": map_data.get("name"),
        "map_state": map_data.get("map_state"),
    }
