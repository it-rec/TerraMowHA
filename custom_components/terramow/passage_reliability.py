"""Evidence-based reliability for mower-reported passages."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any

from .map_scene import build_scene, point_in_polygon

PASSAGE_NEAR_MM = 500.0
PASSAGE_MAX_SAMPLE_GAP = 15.0
PASSAGE_MAX_TRAVERSAL_SECONDS = 120.0
PASSAGE_MAX_OBSERVATIONS = 20
PASSAGE_MAX_AGE_SECONDS = 180 * 24 * 3600
PASSAGE_MIN_CLASSIFICATION_SAMPLES = 3

Point = tuple[float, float]


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = dx * dx + dy * dy
    if length == 0:
        return math.dist(point, start)
    scale = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length),
    )
    return math.dist(point, (start[0] + scale * dx, start[1] + scale * dy))


def _zone_at(point: Point, zones: dict[int, list[Point]]) -> int | None:
    matches = [
        zone_id
        for zone_id, polygon in zones.items()
        if point_in_polygon(point, polygon)
    ]
    return matches[0] if len(matches) == 1 else None


def build_passage_graph(map_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build only edges whose reported line endpoints identify two zones."""
    scene = build_scene(map_data, {}, {}, False)
    zones: dict[int, list[Point]] = {}
    for region in scene["regions"]:
        for zone in region["sub_regions"]:
            if isinstance(zone.get("id"), int) and len(zone["boundary"]) >= 3:
                zones[zone["id"]] = list(zone["boundary"])
    edges: list[dict[str, Any]] = []
    for kind in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for tunnel_index, tunnel in enumerate(scene[kind]):
            for line_index, line in enumerate(tunnel["polylines"]):
                if len(line) < 2:
                    continue
                start_zone = _zone_at(line[0], zones)
                end_zone = _zone_at(line[-1], zones)
                if (
                    start_zone is None
                    or end_zone is None
                    or start_zone == end_zone
                ):
                    continue
                geometry = [[float(x), float(y)] for x, y in line]
                digest = hashlib.blake2b(
                    json.dumps(geometry, separators=(",", ":")).encode(),
                    digest_size=8,
                ).hexdigest()
                edges.append(
                    {
                        "id": f"{kind}:{tunnel_index}:{line_index}:{digest}",
                        "zones": sorted((start_zone, end_zone)),
                        "line": geometry,
                    }
                )
    return sorted(edges, key=lambda edge: edge["id"])


class PassageReliabilityTracker:
    """Assign only unambiguous observed transitions to deterministic edges."""

    def __init__(self) -> None:
        self.map_id: Any | None = None
        self.edges: list[dict[str, Any]] = []
        self.stats: dict[str, dict[str, Any]] = {}
        self._last_zone: int | None = None
        self._left_zone_at: float | None = None
        self._candidates: set[str] = set()
        self._previous_sample_at: float | None = None
        self.source = "live"

    def set_map(self, map_data: dict[str, Any]) -> None:
        """Reset changed geometry; revalidate exact restored edge ids."""
        edges = build_passage_graph(map_data)
        edge_ids = {edge["id"] for edge in edges}
        incoming_id = map_data.get("id")
        if self.map_id != incoming_id:
            self.stats = {}
        else:
            self.stats = {
                key: value for key, value in self.stats.items() if key in edge_ids
            }
        self.map_id = incoming_id
        self.edges = edges
        self._last_zone = None
        self._left_zone_at = None
        self._candidates = set()
        self._previous_sample_at = None
        if self.source == "restored" and any(key in edge_ids for key in self.stats):
            self.source = "revalidated"

    def _near_edges(self, point: Point) -> set[str]:
        nearby: set[str] = set()
        for edge in self.edges:
            line = [(float(x), float(y)) for x, y in edge["line"]]
            if any(
                _distance_to_segment(point, start, end) <= PASSAGE_NEAR_MM
                for start, end in zip(line, line[1:], strict=False)
            ):
                nearby.add(edge["id"])
        return nearby

    def _record(self, edge_id: str, kind: str, now: float, duration: float | None = None) -> None:
        stats = self.stats.setdefault(
            edge_id,
            {"successes": [], "retreats": [], "faults": []},
        )
        item = {"at": now}
        if duration is not None:
            item["duration_seconds"] = round(duration, 1)
        stats[kind].append(item)
        stats[kind] = stats[kind][-PASSAGE_MAX_OBSERVATIONS:]

    def observe_pose(
        self,
        *,
        point: Point,
        now: float,
        zone_id: int | None,
    ) -> None:
        """Consume an already validated pose and exact zone assignment."""
        if (
            self._previous_sample_at is not None
            and now - self._previous_sample_at > PASSAGE_MAX_SAMPLE_GAP
        ):
            self._last_zone = zone_id
            self._left_zone_at = None
            self._candidates = set()
        self._previous_sample_at = now
        nearby = self._near_edges(point)
        if zone_id is None:
            if self._last_zone is not None and self._left_zone_at is None:
                self._left_zone_at = now
            self._candidates.update(nearby)
            return
        if self._last_zone is None:
            self._last_zone = zone_id
            return
        if self._left_zone_at is None:
            self._last_zone = zone_id
            return
        elapsed = now - self._left_zone_at
        matching = [
            edge
            for edge in self.edges
            if edge["id"] in self._candidates
            and (
                self._last_zone in edge["zones"]
                if zone_id == self._last_zone
                else edge["zones"] == sorted((self._last_zone, zone_id))
            )
        ]
        if elapsed <= PASSAGE_MAX_TRAVERSAL_SECONDS and len(matching) == 1:
            kind = "retreats" if zone_id == self._last_zone else "successes"
            self._record(matching[0]["id"], kind, now, elapsed)
        self._last_zone = zone_id
        self._left_zone_at = None
        self._candidates = set()

    def observe_fault(self, point: Point, now: float) -> None:
        """Assign a fault only when exactly one passage is geometrically near."""
        nearby = self._near_edges(point)
        if len(nearby) == 1:
            self._record(next(iter(nearby)), "faults", now)

    def _expire(self, now: float) -> None:
        cutoff = now - PASSAGE_MAX_AGE_SECONDS
        for stats in self.stats.values():
            for kind in ("successes", "retreats", "faults"):
                stats[kind] = [
                    item
                    for item in stats.get(kind, [])
                    if isinstance(item.get("at"), (int, float)) and item["at"] >= cutoff
                ][-PASSAGE_MAX_OBSERVATIONS:]

    def diagnostics(self, now: float) -> list[dict[str, Any]]:
        """Return evidence and conservative unknown/healthy/degraded labels."""
        self._expire(now)
        result: list[dict[str, Any]] = []
        for edge in self.edges:
            stats = self.stats.get(
                edge["id"], {"successes": [], "retreats": [], "faults": []}
            )
            successes = len(stats["successes"])
            retreats = len(stats["retreats"])
            faults = len(stats["faults"])
            evidence = successes + retreats + faults
            classification = "unknown"
            if evidence >= PASSAGE_MIN_CLASSIFICATION_SAMPLES:
                classification = (
                    "degraded"
                    if (retreats + faults) / evidence >= 0.5
                    else "healthy"
                )
            durations = [
                item["duration_seconds"]
                for item in stats["successes"]
                if "duration_seconds" in item
            ]
            result.append(
                {
                    "id": edge["id"],
                    "zones": edge["zones"],
                    "classification": classification,
                    "successes": successes,
                    "retreats": retreats,
                    "nearby_faults": faults,
                    "median_duration_seconds": (
                        round(statistics.median(durations), 1) if durations else None
                    ),
                    "last_success": (
                        stats["successes"][-1]["at"] if stats["successes"] else None
                    ),
                    "source": self.source,
                }
            )
        return result

    def dump(self) -> dict[str, Any]:
        return {"map_id": self.map_id, "stats": self.stats}

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict) or not isinstance(data.get("stats"), dict):
            return
        self.map_id = data.get("map_id")
        self.stats = {
            key: value
            for key, value in data["stats"].items()
            if isinstance(key, str) and isinstance(value, dict)
        }
        self.source = "restored"
