"""Map-geometry snapshots and tolerant comparisons.

The mower periodically serves the complete map body.  This module turns the
spatial parts of two such reports into comparable, JSON-serializable snapshots
without assigning meaning to undocumented fields.  Comparisons tolerate small
coordinate jitter and point-order changes, but report structural changes by
layer.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .map_scene import build_scene

MAP_INTEGRITY_TOLERANCE_MM = 25.0

_POLYGON_KEYS = (
    "forbidden_zones",
    "physical_forbidden_zones",
    "pass_through_zones",
    "required_zones",
    "obstacles",
)


def _points(points: Any) -> list[list[float]]:
    """Return finite ``[x, y]`` points from parsed scene geometry."""
    result: list[list[float]] = []
    if not isinstance(points, list):
        return result
    for point in points:
        if (
            isinstance(point, (list, tuple))
            and len(point) == 2
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in point
            )
        ):
            result.append([float(point[0]), float(point[1])])
    return result


def snapshot_map_geometry(map_data: dict[str, Any]) -> dict[str, Any]:
    """Extract the map layers used by the integrity monitor.

    Only geometry already understood by the renderer is included.  An
    unsupported device shape therefore remains visible through the existing
    geometry diagnostics instead of being guessed here.
    """
    scene = build_scene(map_data, {}, {}, False)
    zones: list[dict[str, Any]] = []
    for region_index, region in enumerate(scene["regions"]):
        region_id = region.get("id")
        zones.append(
            {
                "key": f"region:{region_id if region_id is not None else region_index}",
                "boundary": _points(region.get("boundary")),
            }
        )
        for sub_index, sub_region in enumerate(region.get("sub_regions", [])):
            sub_id = sub_region.get("id")
            zones.append(
                {
                    "key": (
                        f"sub:{region_id if region_id is not None else region_index}:"
                        f"{sub_id if sub_id is not None else sub_index}"
                    ),
                    "boundary": _points(sub_region.get("boundary")),
                }
            )

    station = scene.get("station_pose")
    snapshot: dict[str, Any] = {
        "map_id": map_data.get("id"),
        "station": (
            [float(station["x"]), float(station["y"])]
            if isinstance(station, dict)
            and isinstance(station.get("x"), (int, float))
            and isinstance(station.get("y"), (int, float))
            else None
        ),
        "zones": sorted(zones, key=lambda item: item["key"]),
        "virtual_walls": [
            _points(line) for line in scene["virtual_walls"] if len(_points(line)) >= 2
        ],
    }
    for key in _POLYGON_KEYS:
        snapshot[key] = [
            _points(polygon)
            for polygon in scene[key]
            if len(_points(polygon)) >= 3
        ]

    tunnel_polygons: list[list[list[float]]] = []
    tunnel_lines: list[list[list[float]]] = []
    for key in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for tunnel in scene[key]:
            tunnel_polygons.extend(
                _points(polygon)
                for polygon in tunnel["polygons"]
                if len(_points(polygon)) >= 3
            )
            tunnel_lines.extend(
                _points(line)
                for line in tunnel["polylines"]
                if len(_points(line)) >= 2
            )
    snapshot["tunnel_polygons"] = tunnel_polygons
    snapshot["tunnel_lines"] = tunnel_lines
    return snapshot


def geometry_digest(snapshot: dict[str, Any]) -> str:
    """Stable compact identity for diagnostics and event correlation."""
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(encoded.encode(), digest_size=16).hexdigest()


def _sequence_close(
    left: list[list[float]],
    right: list[list[float]],
    tolerance_mm: float,
    *,
    cyclic: bool,
) -> bool:
    """Compare a line or polygon independently of direction/start vertex."""
    if len(left) != len(right):
        return False
    if not left:
        return True

    candidates: list[list[list[float]]] = [right, list(reversed(right))]
    if cyclic:
        candidates = [
            candidate[offset:] + candidate[:offset]
            for candidate in candidates
            for offset in range(len(candidate))
        ]
    return any(
        all(math.dist(a, b) <= tolerance_mm for a, b in zip(left, candidate, strict=True))
        for candidate in candidates
    )


def _collection_close(
    left: Any,
    right: Any,
    tolerance_mm: float,
    *,
    cyclic: bool,
) -> bool:
    """Compare an unordered collection of polygons or lines."""
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    if len(left) != len(right):
        return False
    remaining = list(right)
    for feature in left:
        match = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if isinstance(feature, list)
                and isinstance(candidate, list)
                and _sequence_close(feature, candidate, tolerance_mm, cyclic=cyclic)
            ),
            None,
        )
        if match is None:
            return False
        remaining.pop(match)
    return True


def changed_geometry_layers(
    previous: dict[str, Any],
    current: dict[str, Any],
    tolerance_mm: float = MAP_INTEGRITY_TOLERANCE_MM,
) -> list[str]:
    """Return the spatial layers that materially changed."""
    changed: list[str] = []
    previous_station = previous.get("station")
    current_station = current.get("station")
    if previous_station is None or current_station is None:
        if previous_station != current_station:
            changed.append("station")
    elif math.dist(previous_station, current_station) > tolerance_mm:
        changed.append("station")

    previous_zones = {
        item["key"]: item["boundary"]
        for item in previous.get("zones", [])
        if isinstance(item, dict)
        and isinstance(item.get("key"), str)
        and isinstance(item.get("boundary"), list)
    }
    current_zones = {
        item["key"]: item["boundary"]
        for item in current.get("zones", [])
        if isinstance(item, dict)
        and isinstance(item.get("key"), str)
        and isinstance(item.get("boundary"), list)
    }
    if previous_zones.keys() != current_zones.keys() or any(
        not _sequence_close(
            boundary,
            current_zones[key],
            tolerance_mm,
            cyclic=True,
        )
        for key, boundary in previous_zones.items()
        if key in current_zones
    ):
        changed.append("zones")

    for key in _POLYGON_KEYS:
        if not _collection_close(
            previous.get(key),
            current.get(key),
            tolerance_mm,
            cyclic=True,
        ):
            changed.append(key)
    for key in ("virtual_walls", "tunnel_lines"):
        if not _collection_close(
            previous.get(key),
            current.get(key),
            tolerance_mm,
            cyclic=False,
        ):
            changed.append(key)
    if not _collection_close(
        previous.get("tunnel_polygons"),
        current.get("tunnel_polygons"),
        tolerance_mm,
        cyclic=True,
    ):
        changed.append("tunnel_polygons")
    return changed
