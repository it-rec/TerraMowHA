"""Safety checks between mower-reported map geometry and live poses."""

from __future__ import annotations

import math
from typing import Any

from .map_scene import build_scene

SAFETY_BOUNDARY_TOLERANCE_MM = 100.0
SAFETY_MAX_SEGMENT_MM = 10_000.0
SAFETY_MAX_SAMPLE_GAP_SECONDS = 15.0

Point = tuple[float, float]


def pose_point(pose: Any) -> Point | None:
    """Return a finite point from a raw pose without inventing coordinates."""
    if not isinstance(pose, dict):
        return None
    x = pose.get("x")
    y = pose.get("y")
    if (
        not isinstance(x, (int, float))
        or isinstance(x, bool)
        or not isinstance(y, (int, float))
        or isinstance(y, bool)
        or not math.isfinite(float(x))
        or not math.isfinite(float(y))
    ):
        return None
    return (float(x), float(y))


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    """Shortest Euclidean distance from a point to a finite segment."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.dist(point, start)
    position = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / length_sq,
        ),
    )
    projected = (start[0] + position * dx, start[1] + position * dy)
    return math.dist(point, projected)


def _on_boundary(point: Point, polygon: list[Point], tolerance_mm: float) -> bool:
    """Whether a point is on or within tolerance of a polygon edge."""
    return any(
        _distance_to_segment(point, start, end) <= tolerance_mm
        for start, end in zip(polygon, polygon[1:] + polygon[:1], strict=True)
    )


def _inside(point: Point, polygon: list[Point]) -> bool:
    """Ray-casting containment, with boundary handled separately."""
    inside = False
    x, y = point
    for (x1, y1), (x2, y2) in zip(
        polygon, polygon[1:] + polygon[:1], strict=True
    ):
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
    return inside


def _orientation(a: Point, b: Point, c: Point) -> float:
    """Signed orientation of three points."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_crossing(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Whether two segments cross through each other, excluding touches."""
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    if 0.0 in (first, second, third, fourth):
        return False
    return ((first > 0) != (second > 0)) and ((third > 0) != (fourth > 0))


def _scene_polygons(value: Any) -> list[list[Point]]:
    """Keep valid polygons from the already-normalized renderer scene."""
    if not isinstance(value, list):
        return []
    return [
        [(float(point[0]), float(point[1])) for point in polygon]
        for polygon in value
        if isinstance(polygon, list) and len(polygon) >= 3
    ]


def evaluate_pose(
    map_data: dict[str, Any],
    previous: Point | None,
    current: Point,
    *,
    allow_segment: bool,
    tolerance_mm: float = SAFETY_BOUNDARY_TOLERANCE_MM,
) -> list[dict[str, Any]]:
    """Return directly observed breaches for one pose update.

    Polygon incidents use the current reported point. Virtual-wall incidents
    require a proper crossing between two sufficiently close pose samples.
    Points on an edge or inside the tolerance band are deliberately neutral.
    """
    scene = build_scene(map_data, {}, {}, False)
    detections: list[dict[str, Any]] = []

    for kind in ("forbidden_zones", "physical_forbidden_zones"):
        for index, polygon in enumerate(_scene_polygons(scene.get(kind))):
            if not _on_boundary(current, polygon, tolerance_mm) and _inside(
                current, polygon
            ):
                detections.append(
                    {
                        "kind": "no_go_area",
                        "geometry_id": f"{kind}:{index}",
                    }
                )

    allowed = [
        [(float(x), float(y)) for x, y in region.get("boundary", [])]
        for region in scene.get("regions", [])
        if isinstance(region, dict) and len(region.get("boundary", [])) >= 3
    ]
    if allowed and not any(
        _on_boundary(current, polygon, tolerance_mm) or _inside(current, polygon)
        for polygon in allowed
    ):
        detections.append(
            {"kind": "outer_boundary", "geometry_id": "allowed_regions"}
        )

    if previous is not None and allow_segment:
        for index, wall in enumerate(scene.get("virtual_walls", [])):
            points = [(float(x), float(y)) for x, y in wall]
            for segment_index, (start, end) in enumerate(
                zip(points, points[1:], strict=False)
            ):
                if _proper_crossing(previous, current, start, end):
                    detections.append(
                        {
                            "kind": "virtual_wall",
                            "geometry_id": f"virtual_walls:{index}:{segment_index}",
                        }
                    )
    return detections


def segment_is_observable(
    previous: Point | None,
    current: Point,
    elapsed_seconds: float | None,
) -> bool:
    """Whether two reported poses are close enough to connect honestly."""
    return (
        previous is not None
        and elapsed_seconds is not None
        and 0 <= elapsed_seconds <= SAFETY_MAX_SAMPLE_GAP_SECONDS
        and math.dist(previous, current) <= SAFETY_MAX_SEGMENT_MM
    )
