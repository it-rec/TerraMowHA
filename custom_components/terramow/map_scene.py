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
    # The TerraMow firmware reports ellipse no-go zones as semi-axes (already
    # a radius, not a diameter): {"center", "semi_major_axis", "semi_minor_axis",
    # "rotation_angle"}. Confirmed against a real V1000 map export.
    if radius_x is None:
        radius_x = coerce_float(ellipse.get("semi_major_axis"))
    if radius_y is None:
        radius_y = coerce_float(ellipse.get("semi_minor_axis"))
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
        rotation = coerce_float(ellipse.get("rotation_angle"))
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


def _axis_aligned_rect(
    x0: float, y0: float, x1: float, y1: float
) -> list[tuple[float, float]]:
    """Four corners of an axis-aligned rectangle from two opposite corners.

    Normalizes the corner order so the result is always a valid,
    non-self-intersecting quad regardless of which diagonal the device gave;
    a degenerate (zero-extent) rectangle yields no polygon.
    """
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)
    top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
    if right - left <= 0 or bottom - top <= 0:
        return []
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def _rotated_rect(
    center: tuple[float, float],
    half_width: float,
    half_height: float,
    rotation_deg: float,
) -> list[tuple[float, float]]:
    """Four corners of a rectangle centered at ``center``, optionally rotated.

    Corners keep a fixed winding, so rotation can never turn the quad into a
    self-intersecting bow-tie.
    """
    rotation_rad = math.radians(rotation_deg)
    cos_a = math.cos(rotation_rad)
    sin_a = math.sin(rotation_rad)
    cx, cy = center
    local = [
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    ]
    return [
        (cx + lx * cos_a - ly * sin_a, cy + lx * sin_a + ly * cos_a)
        for lx, ly in local
    ]


def _rect_rotation(rect: dict[str, Any]) -> float:
    """Resolve a rectangle's rotation in degrees (mirrors the ellipse cascade)."""
    rotation = coerce_float(rect.get("rotation"))
    if rotation is None:
        rotation = coerce_float(rect.get("angle"))
    if rotation is None:
        theta = coerce_float(rect.get("theta"))
        if theta is not None and abs(theta) > math.pi * 4:
            theta = math.degrees(theta / 1000.0)
        rotation = theta
    return rotation or 0.0


def _rect_points(rect: Any) -> list[tuple[float, float]]:
    """Approximate a rectangle / square descriptor as four polygon points.

    Handles the common parametric encodings a no-go zone can arrive in when it
    is not a vertex list: two opposite corners (``top_left``/``bottom_right``,
    ``min``/``max`` or the flat ``min_x``/``min_y``/``max_x``/``max_y``
    scalars), or a ``center`` plus a size (``width``/``height``, ``w``/``h``,
    ``size_x``/``size_y``, ``half_width``/``half_height`` or a single square
    ``size``/``side``) with an optional rotation. Returns [] when nothing
    resolves, so a non-rectangle item is left for the other shape parsers.
    """
    if not isinstance(rect, dict):
        return []

    for lo_key, hi_key in (
        ("top_left", "bottom_right"),
        ("bottom_left", "top_right"),
        ("min", "max"),
    ):
        lo = point_tuple(rect.get(lo_key))
        hi = point_tuple(rect.get(hi_key))
        if lo is not None and hi is not None:
            return _axis_aligned_rect(lo[0], lo[1], hi[0], hi[1])

    min_x = coerce_float(rect.get("min_x"))
    min_y = coerce_float(rect.get("min_y"))
    max_x = coerce_float(rect.get("max_x"))
    max_y = coerce_float(rect.get("max_y"))
    if min_x is not None and min_y is not None and max_x is not None and max_y is not None:
        return _axis_aligned_rect(min_x, min_y, max_x, max_y)

    half_width = coerce_float(rect.get("half_width"))
    if half_width is None:
        width = coerce_float(rect.get("width"))
        if width is None:
            width = coerce_float(rect.get("w"))
        if width is None:
            width = coerce_float(rect.get("size_x"))
        if width is not None:
            half_width = width / 2
    half_height = coerce_float(rect.get("half_height"))
    if half_height is None:
        height = coerce_float(rect.get("height"))
        if height is None:
            height = coerce_float(rect.get("h"))
        if height is None:
            height = coerce_float(rect.get("size_y"))
        if height is not None:
            half_height = height / 2
    side = coerce_float(rect.get("size"))
    if side is None:
        side = coerce_float(rect.get("side"))
    if side is not None:
        if half_width is None:
            half_width = side / 2
        if half_height is None:
            half_height = side / 2
    # A square may specify only one axis; mirror it onto the other.
    if half_width is None and half_height is not None:
        half_width = half_height
    if half_height is None and half_width is not None:
        half_height = half_width

    center = point_tuple(rect.get("center"))
    if center is None:
        center = point_tuple(rect)
    if (
        center is not None
        and half_width is not None
        and half_height is not None
        and half_width > 0
        and half_height > 0
    ):
        return _rotated_rect(center, half_width, half_height, _rect_rotation(rect))

    return []


def _circle_points(circle: Any, segments: int = 36) -> list[tuple[float, float]]:
    """Approximate a circle descriptor (``center`` + ``radius``) as points.

    A circle is an ellipse with equal radii; this reads the single-radius
    encodings the ellipse parser does not (``radius`` / ``r`` / ``diameter``)
    and delegates the sampling to :func:`_ellipse_points`, leaving that tested
    helper untouched.
    """
    if not isinstance(circle, dict):
        return []
    radius = coerce_float(circle.get("radius"))
    if radius is None:
        radius = coerce_float(circle.get("r"))
    if radius is None:
        diameter = coerce_float(circle.get("diameter"))
        if diameter is not None:
            radius = diameter / 2
    if radius is None or radius <= 0:
        return []
    center = point_tuple(circle.get("center"))
    if center is None:
        center = point_tuple(circle)
    if center is None:
        points = _collect_recursive_points(circle, limit=8)
        center = points[0] if points else None
    if center is None:
        return []
    return _ellipse_points(
        {
            "center": {"x": center[0], "y": center[1]},
            "radius_x": radius,
            "radius_y": radius,
        },
        segments,
    )


def _parametric_shape_points(obj: Any) -> list[tuple[float, float]]:
    """Points for a parametric shape descriptor (rectangle, circle or ellipse).

    First match wins: a rectangle is tried before the ellipse/circle forms so
    a ``center`` + ``width``/``height`` descriptor renders as a rectangle
    rather than an inscribed ellipse (an ellipse is expected to carry
    ``radius_x``/``radius_y`` or live under an ``ellipse`` key). Returns [] for
    anything that is not a recognizable parametric shape.
    """
    rect = _rect_points(obj)
    if len(rect) >= 3:
        return rect
    circle = _circle_points(obj)
    if len(circle) >= 3:
        return circle
    ellipse = _ellipse_points(obj)
    if len(ellipse) >= 3:
        return ellipse
    return []


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

    # A parametric shape may be nested under its own key, mirroring the
    # existing "ellipse" handling. These keys were previously ignored, so
    # appending them cannot change the output for any input handled before.
    for key in ("circle", "rect", "rectangle", "bbox", "bounds"):
        shape_points = _parametric_shape_points(item.get(key))
        if len(shape_points) >= 3:
            polygons.append(shape_points)

    # Finally, the item itself may be a bare parametric descriptor (a circle,
    # ellipse or rectangle no-go zone carrying no vertex list). Gated on "no
    # polygon found yet" so a real polygon / nested-ellipse item is never also
    # re-derived as a curve — the working paths above stay byte-for-byte.
    if not polygons:
        shape_points = _parametric_shape_points(item)
        if len(shape_points) >= 3:
            polygons.append(shape_points)

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


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Unsigned polygon area (shoelace); 0.0 for degenerate input (#197)."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def point_in_polygon(
    point: tuple[float, float], polygon: list[tuple[float, float]]
) -> bool:
    """Ray-casting point-in-polygon test (used for zone coverage, #197)."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


class _BoundsAccumulator:
    """Running axis-aligned bounding box over a stream of points.

    ``build_scene`` used to collect every scene point — including each of the
    tens of thousands of path points of a long mow — into one list and run it
    through :func:`_dedupe_points` before handing it to the renderer's
    ``CoordinateTransformer``, which only ever reads the extremes. The dedupe
    cost two ``int(round())`` calls plus a set insert per point (~12 ms per
    rebuild at 20 000 points, ~43 ms at 60 000, several times that on a small
    HA host) and the transformer then walked the result four more times.
    Folding each point into the running extremes instead is a single pass and
    yields the same box: deduplication can never change a min or a max.
    """

    __slots__ = ("max_x", "max_y", "min_x", "min_y")

    def __init__(self) -> None:
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf

    def add(self, x: float, y: float) -> None:
        """Fold a single point into the box."""
        if x < self.min_x:
            self.min_x = x
        if x > self.max_x:
            self.max_x = x
        if y < self.min_y:
            self.min_y = y
        if y > self.max_y:
            self.max_y = y

    def extend(self, points: list[tuple[float, float]]) -> None:
        """Fold a list of ``(x, y)`` tuples into the box."""
        for x, y in points:
            self.add(x, y)

    def result(self) -> tuple[float, float, float, float] | None:
        """The box as ``(min_x, min_y, max_x, max_y)``, or None when empty."""
        if self.min_x > self.max_x:
            return None
        return (self.min_x, self.min_y, self.max_x, self.max_y)


def coverage_ratios_for_zones(
    zones: list[tuple[int, list[tuple[float, float]]]],
    segments: list[list[dict[str, Any]]],
    cutting_width_mm: float,
) -> dict[int, float]:
    """Per-zone mowed fraction from mow-track segments (#197).

    Approximation: a segment edge counts for the zone its midpoint lies in;
    covered area is edge length x cutting width, capped at the zone area
    (stripe overlap and edge laps push the raw product past 100 %).

    Shared by the map card (which passes the zones it already built for the
    scene) and the per-zone sensors (which pass the raw map regions), so the
    number a user sees on the card and in an entity cannot drift apart.
    """
    if not segments or not zones:
        return {}
    # Precompute each edge's midpoint + length ONCE (was recomputed per zone).
    edges: list[tuple[float, float, float]] = []
    for segment in segments:
        pts = [(point["x"], point["y"]) for point in segment]
        for a, b in zip(pts, pts[1:], strict=False):
            edges.append((
                (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.dist(a, b),
            ))
    if not edges:
        return {}
    ratios: dict[int, float] = {}
    for zone_id, boundary in zones:
        if len(boundary) < 3:
            continue
        area = polygon_area(boundary)
        if area <= 0:
            continue
        # Cheap bounding-box reject before the O(V) point-in-polygon test:
        # on a multi-zone lawn most edges fall outside most zones, so this
        # turns the O(edges x zones x verts) hot loop into roughly O(edges).
        xs = [p[0] for p in boundary]
        ys = [p[1] for p in boundary]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        covered = 0.0
        for mx, my, length in edges:
            if mx < min_x or mx > max_x or my < min_y or my > max_y:
                continue
            if point_in_polygon((mx, my), boundary):
                covered += length
        if covered > 0:
            ratios[zone_id] = round(min(1.0, covered * cutting_width_mm / area), 3)
    return ratios


def zone_boundaries_from_map(
    map_data: dict[str, Any],
) -> list[tuple[int, list[tuple[float, float]]]]:
    """Extract (zone id, boundary) pairs straight from a raw map payload."""
    zones: list[tuple[int, list[tuple[float, float]]]] = []
    for region in map_data.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for sub in region.get("sub_regions") or []:
            if not isinstance(sub, dict):
                continue
            zone_id = sub.get("id")
            if not isinstance(zone_id, int) or isinstance(zone_id, bool):
                continue
            boundary = [
                (float(point["x"]), float(point["y"]))
                for point in sub.get("boundary") or []
                if isinstance(point, dict)
                and isinstance(point.get("x"), (int, float))
                and isinstance(point.get("y"), (int, float))
            ]
            if len(boundary) >= 3:
                zones.append((zone_id, boundary))
    return zones


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


def _split_cleaning_runs(
    path_points: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split extracted path points into contiguous mowing runs.

    Keeps only ``PATH_POINT_TYPE_CLEANING`` points but, unlike
    ``_filter_cleaning_path_points``, returns one sub-list per uninterrupted
    mowing stretch: a run is broken wherever a non-cleaning point — a
    return-to-dock or a transit hop between areas — sits between two mowing
    points. Rendering each run on its own stops the map from bridging that gap
    with a straight diagonal the mower never drove: the real transit route was
    discarded together with the non-cleaning points, so the two mowing
    stretches must not be joined into one polyline.

    Concatenating the returned runs yields exactly
    ``_filter_cleaning_path_points(path_points)``.
    """
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for point in path_points:
        if point.get("type") == "PATH_POINT_TYPE_CLEANING":
            current.append(point)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def extract_cleaning_path_points(path_data: dict[str, Any]) -> list[dict[str, Any]]:
    """The mowing-only path points of an ha_path_v1 payload."""
    return _filter_cleaning_path_points(_extract_path_points(path_data))


def extract_cleaning_path_runs(
    path_data: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    """The mowing-only path of an ha_path_v1 payload, split into runs.

    One sub-list per uninterrupted mowing stretch (see ``_split_cleaning_runs``)
    so a transit between two areas is never archived as a single segment that
    would draw a phantom diagonal across the gap.
    """
    return _split_cleaning_runs(_extract_path_points(path_data))


class ScenePathCache:
    """Identity-keyed cache of extracted path points for one camera entity.

    The hub replaces the ha_path_v1 dicts wholesale and never mutates them,
    so ``source is cached_source`` proves the extraction inputs are
    unchanged (the strong reference to the source rules out ``id()`` reuse).
    The history path in particular survives many current-path pushes, whose
    rebuilds would otherwise re-extract its O(N) point list every time.
    """

    def __init__(self) -> None:
        self._entries: dict[
            str,
            tuple[
                dict[str, Any],
                list[dict[str, Any]],
                list[dict[str, Any]],
                list[list[dict[str, Any]]],
            ],
        ] = {}

    def extract(
        self, key: str, path_data: dict[str, Any]
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[list[dict[str, Any]]],
    ]:
        """Return the (raw, cleaning-only, cleaning-runs) lists for ``path_data``."""
        entry = self._entries.get(key)
        if entry is not None and entry[0] is path_data:
            return entry[1], entry[2], entry[3]
        raw = _extract_path_points(path_data)
        cleaning = _filter_cleaning_path_points(raw)
        runs = _split_cleaning_runs(raw)
        self._entries[key] = (path_data, raw, cleaning, runs)
        return raw, cleaning, runs


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
    cache: ScenePathCache | None = None,
    session_path_segments: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Organize the raw protocol data into a drawable scene.

    Stays a pure function by default; a caller that rebuilds repeatedly
    (the camera) may pass its ``ScenePathCache`` to skip re-extracting
    path point lists whose source dict is unchanged.

    ``session_path_segments`` are the hub's archived mow tracks from earlier
    in the running session — the firmware clears the realtime path when the
    mower docks mid-session to recharge (issue #214), and these keep the
    already-mowed track drawable until the session actually finishes.
    """
    map_data = map_data if isinstance(map_data, dict) else {}
    path_data = path_data if isinstance(path_data, dict) else {}
    history_path_data = history_path_data if isinstance(history_path_data, dict) else {}
    session_segments = [
        segment
        for segment in (session_path_segments or [])
        if isinstance(segment, list) and len(segment) >= 2
    ]
    clean_info = map_data.get("clean_info", {})
    mow_param = map_data.get("mow_param", {})
    current_map_id = coerce_int(map_data.get("id"))
    if cache is None:
        raw_current_path_points = _extract_path_points(path_data)
        raw_history_path_points = _extract_path_points(history_path_data)
        current_path_points = _filter_cleaning_path_points(raw_current_path_points)
        history_path_points = _filter_cleaning_path_points(raw_history_path_points)
        current_path_runs = _split_cleaning_runs(raw_current_path_points)
        history_path_runs = _split_cleaning_runs(raw_history_path_points)
    else:
        raw_current_path_points, current_path_points, current_path_runs = (
            cache.extract("current", path_data)
        )
        raw_history_path_points, history_path_points, history_path_runs = (
            cache.extract("history", history_path_data)
        )
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
        current_path_runs = []
        path_map_mismatch = True
    if target_map_id is not None and history_path_map_id is not None and history_path_map_id != target_map_id:
        history_path_points = []
        history_path_runs = []
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
        # The mow path split into contiguous cleaning runs (one polyline each).
        # Rendering per run avoids bridging a straight diagonal across the
        # transit points that were filtered out between two mowing stretches.
        "current_path_runs": current_path_runs,
        "history_path_runs": history_path_runs,
        "session_path_segments": session_segments,
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

    bounds = _BoundsAccumulator()
    bounds.extend(scene["map_extent"])

    if scene["origin"] is not None:
        bounds.add(*scene["origin"])
    if scene["station_pose"] is not None:
        bounds.add(scene["station_pose"]["x"], scene["station_pose"]["y"])

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
        bounds.extend(region_boundary)

        for edge_segment in region.get("edge_segments", []):
            edge_line = _line_points(edge_segment)
            if len(edge_line) >= 2:
                region_record["edge_lines"].append(edge_line)
                bounds.extend(edge_line)

        for obstacle in region.get("obstacles", []):
            obstacle_polygons = _extract_polygons(obstacle)
            for polygon in obstacle_polygons:
                scene["obstacles"].append(polygon)
                bounds.extend(polygon)

        for sub_region in region.get("sub_regions", []):
            if not isinstance(sub_region, dict):
                continue
            sub_boundary = _polygon_points(sub_region.get("boundary"))
            inner_boundaries: list[list[tuple[float, float]]] = []
            for inner in sub_region.get("inner_boundarys", []):
                points = _polygon_points(inner)
                if len(points) >= 3:
                    inner_boundaries.append(points)
                    bounds.extend(points)

            edge_lines: list[list[tuple[float, float]]] = []
            for key in ("edge_segments", "boudary_polyline_descriptions"):
                for edge_segment in sub_region.get(key, []):
                    points = _line_points(edge_segment)
                    if len(points) >= 2:
                        edge_lines.append(points)
                        bounds.extend(points)

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
            bounds.extend(sub_boundary)
            if center is not None:
                bounds.add(*center)

        scene["regions"].append(region_record)

    for key in ("forbidden_zones", "physical_forbidden_zones", "pass_through_zones", "required_zones"):
        for item in map_data.get(key, []):
            for polygon in _extract_polygons(item):
                scene[key].append(polygon)
                bounds.extend(polygon)

    for obstacle in map_data.get("obstacles", []):
        for polygon in _extract_polygons(obstacle):
            scene["obstacles"].append(polygon)
            bounds.extend(polygon)

    for wall in map_data.get("virtual_walls", []):
        for line in _extract_polylines(wall):
            scene["virtual_walls"].append(line)
            bounds.extend(line)

    for key in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for item in map_data.get(key, []):
            polygons = _extract_polygons(item)
            polylines = _extract_polylines(item)
            scene[key].append({"polygons": polygons, "polylines": polylines})
            for polygon in polygons:
                bounds.extend(polygon)
            for polyline in polylines:
                bounds.extend(polyline)

    if isinstance(clean_info, dict):
        draw_region = clean_info.get("draw_region", {})
        if isinstance(draw_region, dict):
            for polygon in draw_region.get("regions", []):
                points = _polygon_points(polygon)
                if len(points) >= 3:
                    scene["draw_region_polygons"].append(points)
                    bounds.extend(points)
        move_to_target = clean_info.get("move_to_target_point", {})
        if isinstance(move_to_target, dict):
            scene["move_target_point"] = point_tuple(move_to_target.get("target_point"))
            if scene["move_target_point"] is not None:
                bounds.add(*scene["move_target_point"])

    for path_point in scene["path_points"]:
        bounds.add(path_point["x"], path_point["y"])
    for segment in scene["session_path_segments"]:
        for path_point in segment:
            bounds.add(path_point["x"], path_point["y"])

    # The renderer fits the scene to this box; see _BoundsAccumulator for why
    # it replaced the fully materialized (and deduplicated) point list.
    scene["bounds"] = bounds.result()
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
        "session_path_segments": len(scene["session_path_segments"]),
        "session_path_points": sum(
            len(segment) for segment in scene["session_path_segments"]
        ),
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
    if scene["session_path_segments"]:
        scene["rendered_layers"].insert(
            scene["rendered_layers"].index("path"), "session_path"
        )
    return scene


# Zone collections whose items are geometry descriptors; the diagnostic below
# reports any whose shape the extractor could not turn into something drawable.
_POLYGON_ZONE_KEYS = (
    "forbidden_zones",
    "physical_forbidden_zones",
    "pass_through_zones",
    "required_zones",
    "obstacles",
)
_TUNNEL_ZONE_KEYS = ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels")


def _item_yields_geometry(key: str, item: Any) -> bool:
    """Whether ``item`` produced any drawable geometry for collection ``key``.

    Mirrors how ``build_scene`` extracts each collection: polylines for
    virtual walls, either shape for tunnels, polygons for everything else.
    """
    if key == "virtual_walls":
        return bool(_extract_polylines(item))
    if key in _TUNNEL_ZONE_KEYS:
        return bool(_extract_polygons(item) or _extract_polylines(item))
    return bool(_extract_polygons(item))


def zone_geometry_diagnostics(map_data: dict[str, Any]) -> dict[str, Any]:
    """Report zone items whose shape produced no drawable geometry.

    Answers "why isn't my no-go zone showing?" without a full map capture: for
    every zone collection that has at least one item the extractor could not
    render, it reports how many items were present, how many rendered, and the
    sorted union of the JSON keys on the dropped items. A shape the extractor
    does not yet understand (e.g. a circle/rectangle whose real field names
    differ from those handled here) surfaces with its actual field names —
    exactly what is needed to teach the extractor that encoding. Coordinates
    are never included, only key names. Empty when every zone renders.
    """
    map_data = map_data if isinstance(map_data, dict) else {}
    diagnostics: dict[str, Any] = {}
    for key in (*_POLYGON_ZONE_KEYS, "virtual_walls", *_TUNNEL_ZONE_KEYS):
        items = map_data.get(key)
        if not isinstance(items, list) or not items:
            continue
        rendered = 0
        dropped_keys: set[str] = set()
        for item in items:
            if _item_yields_geometry(key, item):
                rendered += 1
            elif isinstance(item, dict):
                dropped_keys.update(str(inner_key) for inner_key in item)
        dropped = len(items) - rendered
        if dropped <= 0:
            continue
        diagnostics[key] = {
            "raw_item_count": len(items),
            "rendered_item_count": rendered,
            "dropped_item_count": dropped,
            "dropped_item_keys": sorted(dropped_keys),
        }
    return diagnostics


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
        # Zone items whose shape produced no drawable geometry, with the JSON
        # keys of the dropped items — self-reports a device shape encoding the
        # extractor does not yet understand. Empty when everything renders.
        "geometry_diagnostics": zone_geometry_diagnostics(map_data),
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
        # Mow tracks archived from earlier in the running session, kept across
        # a mid-session recharge dock (issue #214).
        "session_path_summary": {
            "segment_count": len(scene.get("session_path_segments", [])),
            "point_count": sum(
                len(segment) for segment in scene.get("session_path_segments", [])
            ),
        },
        "filtered_non_cleaning_point_count": scene.get("filtered_non_cleaning_point_count", {}),
        "rotation_angle": scene.get("rotation_deg", 0.0),
        "map_name": map_data.get("name"),
        "map_state": map_data.get("map_state"),
    }
