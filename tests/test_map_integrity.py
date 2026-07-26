"""Map-integrity monitoring from successive device-reported map bodies."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    Mission,
    SubMission,
    TerraMowHub,
)
from custom_components.terramow.map_integrity import (
    _points,
    changed_geometry_layers,
    geometry_digest,
    snapshot_map_geometry,
)


def _poly(*points: tuple[float, float]) -> dict[str, object]:
    return {"points": [{"x": x, "y": y} for x, y in points]}


def _map(map_id: int = 1) -> dict[str, object]:
    return {
        "id": map_id,
        "map_state": "MAP_STATE_COMPLETE",
        "station_pose": {"x": 0, "y": 0},
        "regions": [
            {
                "id": 10,
                "boundary": _poly((0, 0), (1000, 0), (1000, 1000), (0, 1000)),
                "sub_regions": [
                    {
                        "id": 11,
                        "boundary": _poly(
                            (0, 0), (500, 0), (500, 1000), (0, 1000)
                        ),
                    }
                ],
            }
        ],
        "forbidden_zones": [_poly((100, 100), (200, 100), (200, 200))],
        "physical_forbidden_zones": [
            _poly((300, 100), (400, 100), (400, 200))
        ],
        "pass_through_zones": [_poly((450, 0), (550, 0), (550, 100))],
        "required_zones": [_poly((600, 600), (700, 600), (700, 700))],
        "obstacles": [_poly((800, 800), (850, 800), (850, 850))],
        "virtual_walls": [_poly((0, 500), (1000, 500))],
        "cross_boundary_tunnels": [
            {
                "polygon": _poly((450, 450), (550, 450), (550, 550)),
                "line": _poly((450, 500), (550, 500)),
            }
        ],
        "virtual_cross_boundary_tunnels": [
            {"line": _poly((250, 0), (250, 100))}
        ],
    }


def _hub() -> TerraMowHub:
    hass = MagicMock()
    hass.bus = MagicMock()
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.214", password="secret"),
        hass,
    )


def test_snapshot_is_stable_for_invalid_and_reordered_geometry() -> None:
    data = _map()
    data["regions"].append(  # type: ignore[union-attr]
        {
            "id": None,
            "boundary": _poly((0, 0), (0, 100), (100, 100)),
            "sub_regions": [
                {
                    "id": None,
                    "boundary": _poly((0, 0), (0, 50), (50, 50)),
                }
            ],
        }
    )
    data["virtual_walls"].append({"points": [{"x": True, "y": 2}]})  # type: ignore[union-attr]
    snapshot = snapshot_map_geometry(data)
    assert snapshot["map_id"] == 1
    assert snapshot["station"] == [0.0, 0.0]
    assert [zone["key"] for zone in snapshot["zones"]] == [
        "region:1",
        "region:10",
        "sub:10:11",
        "sub:1:0",
    ]
    assert len(snapshot["tunnel_polygons"]) == 1
    assert len(snapshot["tunnel_lines"]) == 2
    assert geometry_digest(snapshot) == geometry_digest(deepcopy(snapshot))

    reordered = _map()
    reordered["regions"][0]["boundary"]["points"].reverse()  # type: ignore[index]
    reordered["forbidden_zones"].reverse()  # type: ignore[union-attr]
    moved = reordered["station_pose"]  # type: ignore[assignment]
    moved["x"] = 10  # type: ignore[index]
    assert changed_geometry_layers(
        snapshot_map_geometry(_map()), snapshot_map_geometry(reordered)
    ) == []


def test_changed_geometry_layers_classifies_every_layer() -> None:
    original = snapshot_map_geometry(_map())
    changed = _map()
    changed["station_pose"]["x"] = 100  # type: ignore[index]
    changed["regions"][0]["sub_regions"][0]["boundary"] = _poly(  # type: ignore[index]
        (0, 0), (400, 0), (400, 1000), (0, 1000)
    )
    changed["forbidden_zones"] = []
    changed["physical_forbidden_zones"] = []
    changed["pass_through_zones"] = []
    changed["required_zones"] = []
    changed["obstacles"] = []
    changed["virtual_walls"] = []
    changed["cross_boundary_tunnels"] = []
    changed["virtual_cross_boundary_tunnels"] = []
    assert changed_geometry_layers(original, snapshot_map_geometry(changed)) == [
        "station",
        "zones",
        "forbidden_zones",
        "physical_forbidden_zones",
        "pass_through_zones",
        "required_zones",
        "obstacles",
        "virtual_walls",
        "tunnel_lines",
        "tunnel_polygons",
    ]


def test_changed_geometry_layers_handles_missing_and_malformed_snapshots() -> None:
    snapshot = snapshot_map_geometry(_map())
    no_station = deepcopy(snapshot)
    no_station["station"] = None
    assert changed_geometry_layers(snapshot, no_station) == ["station"]
    assert changed_geometry_layers(no_station, no_station) == []

    malformed = deepcopy(snapshot)
    malformed["zones"] = ["bad"]
    malformed["forbidden_zones"] = "bad"
    assert changed_geometry_layers(snapshot, malformed) == [
        "zones",
        "forbidden_zones",
    ]

    assert _points(None) == []
    assert _points([[0, 0], [float("nan"), 1], [True, 1], [1]]) == [[0.0, 0.0]]

    different_lengths = deepcopy(snapshot)
    different_lengths["virtual_walls"][0].pop()
    assert changed_geometry_layers(snapshot, different_lengths) == ["virtual_walls"]

    unmatched = deepcopy(snapshot)
    unmatched["forbidden_zones"][0][0][0] += 100
    assert changed_geometry_layers(snapshot, unmatched) == ["forbidden_zones"]

    empty_zone = deepcopy(snapshot)
    empty_zone["zones"][0]["boundary"] = []
    assert changed_geometry_layers(empty_zone, deepcopy(empty_zone)) == []


def test_hub_creates_compares_and_alerts_on_live_changes() -> None:
    hub = _hub()
    first = _map()
    hub._apply_map_data(first)
    assert hub.map_integrity_state["status"] == "baseline_created"

    hub._apply_map_data(deepcopy(first))
    assert hub.map_integrity_state["status"] == "unchanged"

    changed = _map()
    changed["station_pose"]["x"] = 100  # type: ignore[index]
    hub._apply_map_data(changed)
    assert hub.map_integrity_state["status"] == "unexpected_change"
    assert hub.map_integrity_state["changed_layers"] == ["station"]
    hub.hass.bus.fire.assert_called_once()
    assert hub.hass.bus.fire.call_args.args[0] == "terramow_map_integrity"

    switched = _map(2)
    hub._apply_map_data(switched)
    assert hub.map_integrity_state["status"] == "expected_change"
    assert hub.map_integrity_state["reason"] == "map_switched"


def test_hub_suppresses_incomplete_and_reported_map_operations() -> None:
    hub = _hub()
    incomplete = _map()
    incomplete["map_state"] = "MAP_STATE_INCOMPLETE"
    hub._apply_map_data(incomplete)
    assert hub.map_integrity_state["reason"] == "map_not_complete"
    assert hub._map_integrity_baseline is None

    # The dp_117 state is used when the HTTP body omits map_state.
    hub._map_status = {"map_state": "MAP_STATE_INCOMPLETE"}
    without_state = _map()
    without_state.pop("map_state")
    hub._apply_map_data(without_state)
    assert hub._map_integrity_baseline is None

    hub._map_status = {}
    hub._apply_map_data(without_state)
    assert hub.map_integrity_state["status"] == "baseline_created"

    hub.mission = Mission.MISSION_BACKUP_MAP
    changed = _map()
    changed["station_pose"]["x"] = 100  # type: ignore[index]
    hub._apply_map_data(changed)
    assert hub.map_integrity_state["status"] == "expected_change"
    assert hub.map_integrity_state["reason"] == "MISSION_BACKUP_MAP"
    hub.hass.bus.fire.assert_not_called()

    hub.mission = Mission.MISSION_IDLE
    hub._map_status = {"is_backing_up_map": True}
    changed["station_pose"]["x"] = 200  # type: ignore[index]
    hub._apply_map_data(changed)
    assert hub.map_integrity_state["reason"] == "is_backing_up_map"

    hub._map_status = {}
    hub.sub_mission = SubMission.SUB_MISSION_SAVING_MAP
    changed["station_pose"]["x"] = 300  # type: ignore[index]
    hub._apply_map_data(changed)
    assert hub.map_integrity_state["reason"] == "SUB_MISSION_SAVING_MAP"

    save_data = hub._get_map_integrity_store().async_save.call_args.args[0]
    assert save_data["baseline"] == hub._map_integrity_baseline


async def test_restored_baseline_requires_one_live_revalidation(
    mock_session_path_store: list[MagicMock],
) -> None:
    hub = _hub()
    stored = snapshot_map_geometry(_map())
    store = hub._get_map_integrity_store()
    store.async_load = AsyncMock(return_value={"baseline": stored})
    await hub.async_restore_map_integrity()
    assert hub.map_integrity_state["status"] == "restored_unverified"

    changed = _map()
    changed["station_pose"]["x"] = 100  # type: ignore[index]
    hub._apply_map_data(changed)
    assert hub.map_integrity_state["status"] == "baseline_replaced"
    assert hub.map_integrity_state["changed_layers"] == ["station"]
    hub.hass.bus.fire.assert_not_called()

    hub._map_integrity_store = None
    empty_store = hub._get_map_integrity_store()
    empty_store.async_load = AsyncMock(return_value={"baseline": "bad"})
    await hub.async_restore_map_integrity()

    hub._map_integrity_store = None
    failing_store = hub._get_map_integrity_store()
    failing_store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_map_integrity()
    assert mock_session_path_store


async def test_matching_restored_baseline_is_revalidated() -> None:
    hub = _hub()
    store = hub._get_map_integrity_store()
    store.async_load = AsyncMock(
        return_value={"baseline": snapshot_map_geometry(_map())}
    )
    await hub.async_restore_map_integrity()
    hub._apply_map_data(_map())
    assert hub.map_integrity_state["status"] == "baseline_revalidated"
