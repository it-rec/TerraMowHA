"""Safety-breach detection from reported map geometry and poses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    SAFETY_HISTORY_MAXLEN,
    SAFETY_WARNING_TIMEOUT,
    Mission,
    SubMission,
    TerraMowHub,
)
from custom_components.terramow.map_safety import (
    _distance_to_segment,
    _scene_polygons,
    evaluate_pose,
    pose_point,
    segment_is_observable,
)


def _poly(*points: tuple[float, float]) -> dict[str, object]:
    return {"points": [{"x": x, "y": y} for x, y in points]}


def _map(map_id: int = 1) -> dict[str, object]:
    return {
        "id": map_id,
        "regions": [
            {
                "id": 10,
                "boundary": _poly((0, 0), (1000, 0), (1000, 1000), (0, 1000)),
            }
        ],
        "forbidden_zones": [
            _poly((300, 300), (700, 300), (700, 700), (300, 700))
        ],
        "physical_forbidden_zones": [
            _poly((100, 100), (200, 100), (200, 200), (100, 200))
        ],
        "virtual_walls": [_poly((500, 0), (500, 1000))],
    }


def _hub() -> TerraMowHub:
    hass = MagicMock()
    hass.bus = MagicMock()
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.215", password="secret"),
        hass,
    )


def test_pose_validation_and_observable_segments() -> None:
    assert pose_point({"x": 1, "y": 2}) == (1.0, 2.0)
    assert pose_point(None) is None
    assert pose_point({"x": True, "y": 2}) is None
    assert pose_point({"x": float("nan"), "y": 2}) is None
    assert not segment_is_observable(None, (0, 0), None)
    assert not segment_is_observable((0, 0), (0, 0), -1)
    assert not segment_is_observable((0, 0), (0, 0), 16)
    assert not segment_is_observable((0, 0), (10_001, 0), 1)
    assert segment_is_observable((0, 0), (1, 1), 1)
    assert _distance_to_segment((3, 4), (0, 0), (0, 0)) == 5
    assert _scene_polygons(None) == []


def test_polygon_entry_outer_exit_wall_crossing_and_edges() -> None:
    data = _map()
    assert evaluate_pose(data, None, (500, 500), allow_segment=False) == [
        {"kind": "no_go_area", "geometry_id": "forbidden_zones:0"}
    ]
    assert evaluate_pose(
        data, None, (150, 150), allow_segment=False, tolerance_mm=10
    ) == [
        {"kind": "no_go_area", "geometry_id": "physical_forbidden_zones:0"}
    ]
    assert evaluate_pose(data, None, (1200, 500), allow_segment=False) == [
        {"kind": "outer_boundary", "geometry_id": "allowed_regions"}
    ]
    assert evaluate_pose(data, None, (300, 500), allow_segment=False) == []
    assert evaluate_pose(
        data, (250, 250), (750, 250), allow_segment=True
    ) == [{"kind": "virtual_wall", "geometry_id": "virtual_walls:0:0"}]
    # Merely touching an endpoint and a disallowed telemetry segment are neutral.
    assert evaluate_pose(data, (250, 0), (500, 0), allow_segment=True) == []
    assert evaluate_pose(data, (250, 250), (750, 250), allow_segment=False) == []
    assert evaluate_pose({"regions": []}, None, (99, 99), allow_segment=False) == []


def test_hub_confirms_deduplicates_closes_and_marks_gaps() -> None:
    hub = _hub()
    hub._apply_map_data(_map())
    hub.mission = Mission.MISSION_GLOBAL_CLEAN
    hub.sub_mission = SubMission.SUB_MISSION_REMOTE_CONTROL

    with patch(
        "custom_components.terramow.hub.time.monotonic",
        side_effect=[1, 1, 2, 2, 3, 4],
    ):
        hub._sample_safety_pose({"x": 500, "y": 500})
        assert hub.safety_breach_state["status"] == "clear"
        hub._sample_safety_pose({"x": 500, "y": 500})
        assert hub.safety_breach_state["status"] == "breach"
        hub._sample_safety_pose({"x": 500, "y": 500})
        hub._sample_safety_pose({"x": 250, "y": 250})

    assert len(hub.safety_breach_state["history"]) == 1
    assert hub.safety_breach_state["status"] == "clear"
    record = hub.safety_breach_state["history"][0]
    assert record["mission"] == "MISSION_GLOBAL_CLEAN"
    assert record["sub_mission"] == "SUB_MISSION_REMOTE_CONTROL"
    hub.hass.bus.fire.assert_called_once()

    hub._safety_previous = ((250, 250), 0)
    with patch("custom_components.terramow.hub.time.monotonic", return_value=20):
        hub._sample_safety_pose({"x": 750, "y": 250})
    assert hub.safety_breach_state["status"] == "indeterminate"
    assert len(hub.safety_breach_state["history"]) == 1


def test_wall_event_is_immediate_and_live_warning_expires() -> None:
    hub = _hub()
    hub._apply_map_data(_map())
    hub._safety_previous = ((250, 250), 1)
    with patch("custom_components.terramow.hub.time.monotonic", return_value=2):
        hub._sample_safety_pose({"x": 750, "y": 250})
        assert hub.safety_breach_state["status"] == "breach"
    with patch(
        "custom_components.terramow.hub.time.monotonic",
        return_value=2 + SAFETY_WARNING_TIMEOUT + 1,
    ):
        assert hub.safety_breach_state["status"] == "clear"


def test_map_switch_clears_history_and_save_is_capped() -> None:
    hub = _hub()
    hub._apply_map_data(_map())
    hub._safety_history = [{"index": index} for index in range(30)]
    save = hub._safety_save_data()
    assert len(save["history"]) == SAFETY_HISTORY_MAXLEN

    hub._apply_map_data(_map(2))
    assert hub.safety_breach_state["history"] == []
    callback = hub._get_safety_store().async_delay_save.call_args.args[0]
    assert callback()["map_id"] == 2


async def test_restore_is_historical_and_invalid_payloads_are_ignored() -> None:
    hub = _hub()
    store = hub._get_safety_store()
    store.async_load = AsyncMock(
        return_value={"map_id": 1, "history": [{"kind": "no_go_area"}] * 25}
    )
    await hub.async_restore_safety_history()
    assert len(hub.safety_breach_state["history"]) == SAFETY_HISTORY_MAXLEN
    assert {item["source"] for item in hub.safety_breach_state["history"]} == {
        "restored"
    }
    assert hub.safety_breach_state["active"] == []

    store.async_load = AsyncMock(return_value={"history": "bad"})
    await hub.async_restore_safety_history()
    store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_safety_history()


def test_invalid_pose_or_missing_map_is_ignored() -> None:
    hub = _hub()
    hub._sample_safety_pose({"x": 1})
    hub._map_data = _map()
    hub._sample_safety_pose({"x": False, "y": 2})
    assert hub.safety_breach_state["status"] == "unknown"
