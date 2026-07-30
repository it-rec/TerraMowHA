"""Passage graph and evidence-based reliability."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.terramow.passage_reliability as passage_reliability
from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.passage_reliability import (
    PASSAGE_MAX_AGE_SECONDS,
    PassageReliabilityTracker,
    _distance_to_segment,
    build_passage_graph,
)


def _poly(*points: tuple[float, float]) -> dict[str, object]:
    return {"points": [{"x": x, "y": y} for x, y in points]}


def _map(map_id: int = 1, *, duplicate: bool = False) -> dict[str, object]:
    tunnel = {"line": _poly((500, 500), (2500, 500))}
    return {
        "id": map_id,
        "regions": [
            {
                "sub_regions": [
                    {
                        "id": 1,
                        "boundary": _poly(
                            (0, 0), (1000, 0), (1000, 1000), (0, 1000)
                        ),
                    },
                    {
                        "id": 2,
                        "boundary": _poly(
                            (2000, 0), (3000, 0), (3000, 1000), (2000, 1000)
                        ),
                    },
                    {
                        "id": 3,
                        "boundary": _poly(
                            (4000, 0), (5000, 0), (5000, 1000), (4000, 1000)
                        ),
                    },
                ]
            }
        ],
        "cross_boundary_tunnels": [tunnel, *([tunnel] if duplicate else [])],
    }


def _hub() -> TerraMowHub:
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.219", password="secret"),
        MagicMock(),
    )


def test_graph_is_deterministic_and_keeps_disconnected_zones() -> None:
    graph = build_passage_graph(_map())
    assert len(graph) == 1
    assert graph[0]["zones"] == [1, 2]
    assert build_passage_graph(_map()) == graph
    assert _distance_to_segment((3, 4), (0, 0), (0, 0)) == 5


def test_graph_rejects_incomplete_and_unverifiable_geometry() -> None:
    map_data = _map()
    sub_regions = map_data["regions"][0]["sub_regions"]
    sub_regions.extend(
        [
            {"id": "not-a-zone", "boundary": _poly((0, 0), (1, 0), (1, 1))},
            {"id": 4, "boundary": _poly((0, 0), (1, 0))},
        ]
    )
    map_data["cross_boundary_tunnels"].extend(
        [
            {"line": _poly((500, 500))},
            {"line": _poly((500, 500), (750, 500))},
            {"line": _poly((500, 500), (6000, 500))},
        ]
    )

    graph = build_passage_graph(map_data)

    assert len(graph) == 1
    assert graph[0]["zones"] == [1, 2]


def test_graph_rejects_short_normalized_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        passage_reliability,
        "build_scene",
        lambda *_args: {
            "regions": [],
            "cross_boundary_tunnels": [{"polylines": [[(0.0, 0.0)]]}],
            "virtual_cross_boundary_tunnels": [],
        },
    )

    assert build_passage_graph({}) == []


def test_near_edge_checks_every_reported_segment() -> None:
    map_data = _map()
    map_data["cross_boundary_tunnels"] = [
        {"line": _poly((500, 500), (1500, 1500), (2500, 500))}
    ]
    tracker = PassageReliabilityTracker()
    tracker.set_map(map_data)

    assert tracker._near_edges((2400, 600)) == {tracker.edges[0]["id"]}
    assert tracker._near_edges((10000, 10000)) == set()


def test_success_retreat_fault_and_conservative_classification() -> None:
    tracker = PassageReliabilityTracker()
    tracker.set_map(_map())
    edge_id = tracker.edges[0]["id"]

    tracker.observe_pose(point=(500, 500), now=0, zone_id=1)
    tracker.observe_pose(point=(1500, 500), now=1, zone_id=None)
    tracker.observe_pose(point=(2500, 500), now=2, zone_id=2)
    tracker.observe_pose(point=(1500, 500), now=3, zone_id=None)
    tracker.observe_pose(point=(2500, 500), now=4, zone_id=2)
    tracker.observe_fault((1500, 500), 5)

    result = tracker.diagnostics(5)[0]
    assert result["classification"] == "degraded"
    assert result["successes"] == 1
    assert result["retreats"] == 1
    assert result["nearby_faults"] == 1
    assert result["median_duration_seconds"] == 1
    assert result["last_success"] == 2
    assert tracker.stats[edge_id]

    # Lack of use alone is never degraded.
    fresh = PassageReliabilityTracker()
    fresh.set_map(_map())
    assert fresh.diagnostics(0)[0]["classification"] == "unknown"


def test_sparse_and_ambiguous_evidence_is_not_assigned() -> None:
    tracker = PassageReliabilityTracker()
    tracker.set_map(_map())
    tracker.observe_pose(point=(500, 500), now=-2, zone_id=1)
    tracker.observe_pose(point=(2500, 500), now=-1, zone_id=2)
    tracker.observe_pose(point=(500, 500), now=0, zone_id=1)
    tracker.observe_pose(point=(1500, 500), now=20, zone_id=None)
    tracker.observe_pose(point=(2500, 500), now=21, zone_id=2)
    assert tracker.stats == {}

    ambiguous = PassageReliabilityTracker()
    ambiguous.set_map(_map(duplicate=True))
    ambiguous.observe_fault((1500, 500), 1)
    assert ambiguous.stats == {}


def test_overlong_continuous_traversal_is_not_assigned() -> None:
    tracker = PassageReliabilityTracker()
    tracker.set_map(_map())
    tracker.observe_pose(point=(500, 500), now=0, zone_id=1)
    for now in range(1, 122, 10):
        tracker.observe_pose(point=(1500, 500), now=now, zone_id=None)
    tracker.observe_pose(point=(2500, 500), now=122, zone_id=2)

    assert tracker.stats == {}


def test_healthy_expiry_restore_revalidation_and_map_reset() -> None:
    tracker = PassageReliabilityTracker()
    tracker.set_map(_map())
    edge_id = tracker.edges[0]["id"]
    tracker.stats[edge_id] = {
        "successes": [
            {"at": PASSAGE_MAX_AGE_SECONDS + index, "duration_seconds": 2}
            for index in range(3)
        ],
        "retreats": [],
        "faults": [],
    }
    assert tracker.diagnostics(PASSAGE_MAX_AGE_SECONDS + 3)[0][
        "classification"
    ] == "healthy"
    saved = tracker.dump()

    restored = PassageReliabilityTracker()
    restored.restore(saved)
    assert restored.source == "restored"
    restored.set_map(_map())
    assert restored.source == "revalidated"
    restored.set_map(_map(2))
    assert restored.stats == {}
    restored.restore(None)


async def test_hub_samples_faults_and_restores() -> None:
    hub = _hub()
    hub._apply_map_data(_map())
    hub._sample_passage_reliability({"x": 500, "y": 500})
    hub._sample_passage_reliability({"x": 1500, "y": 500})
    hub._sample_passage_reliability({"x": 2500, "y": 500})
    hub._pose = {"x": 1500, "y": 500}
    hub._record_passage_fault()
    assert hub.passage_reliability[0]["successes"] == 1
    callback = hub._get_passage_store().async_delay_save.call_args.args[0]
    assert callback()["stats"]

    store = hub._get_passage_store()
    store.async_load = AsyncMock(return_value=callback())
    await hub.async_restore_passage_reliability()
    assert hub._passage_reliability.source == "restored"
    store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_passage_reliability()


def test_invalid_hub_pose_is_ignored() -> None:
    hub = _hub()
    hub._sample_passage_reliability({"x": True, "y": 1})
    hub._record_passage_fault()
    assert hub.passage_reliability == []
