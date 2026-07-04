"""Extra camera render coverage: draw branches for every feature type.

Renders scenes that exercise the empty-map card, all marker/zone/tunnel draws,
order badges, the move-target and origin markers, the live-pose robot (battery
disconnected, no yaw) and a long mixed-type path.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.130", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _camera(hub, **kwargs) -> TerraMowMapCamera:
    return TerraMowMapCamera(hub.basic_data, hub.hass, **kwargs)


def _render(camera) -> bytes:
    return asyncio.run(camera.async_camera_image())


# ---------------------------------------------------------------------------
# empty map card
# ---------------------------------------------------------------------------


def test_render_empty_map_card() -> None:
    hub = _hub()
    camera = _camera(hub)
    # a map with a state but no geometry -> the empty-map card path
    hub._map_data = {"id": 1, "map_state": "MAP_STATE_INCOMPLETE"}
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# every feature type in one scene
# ---------------------------------------------------------------------------


MEGA_MAP = {
    "id": 1,
    "name": "Garten",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 100,
    "height": 80,
    "resolution": 0.05,
    "origin": {"x": -2.0, "y": -2.0},
    "station_pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
    "total_area": 2560,
    "map_view_rotate_angle": 0,
    "regions": [
        {
            "id": 100,
            "name": "Haupt",
            "boundary": _poly((0, 0), (4, 0), (4, 3), (0, 3)),
            "obstacles": [{"ellipse": {"center": {"x": 1, "y": 1}, "radius_x": 0.3, "radius_y": 0.3}}],
            "sub_regions": [
                {
                    "id": 7,
                    "name": "Vorne",
                    "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                    "center": {"x": 1, "y": 1},
                    "is_selected_for_mow": True,
                    "selected_for_mow_order": 1,
                },
                {
                    "id": 8,
                    "name": "Hinten",
                    "boundary": _poly((2, 0), (4, 0), (4, 2), (2, 2)),
                    "center": {"x": 3, "y": 1},
                    "selected_for_mow_order": 2,
                },
            ],
        },
    ],
    "obstacles": [_poly((3.2, 2.2), (3.5, 2.2), (3.5, 2.5))],
    "forbidden_zones": [_poly((0.2, 2.2), (0.8, 2.2), (0.8, 2.8))],
    "physical_forbidden_zones": [_poly((1.2, 2.2), (1.8, 2.2), (1.8, 2.8))],
    "pass_through_zones": [_poly((2.2, 2.2), (2.8, 2.2), (2.8, 2.8))],
    "required_zones": [_poly((0.2, 0.2), (0.6, 0.2), (0.6, 0.6))],
    "virtual_walls": [_poly((0, 2.5), (4, 2.5))],
    "cross_boundary_tunnels": [{"line": _poly((1, 1), (2, 2))}],
    "virtual_cross_boundary_tunnels": [{"line": _poly((0.5, 0.5), (1.5, 1.5))}],
    "cross_boundary_markers": [_poly((1, 3), (1.2, 3), (1.1, 3.2))],
    "trapped_points": [_poly((2, 1), (2.2, 1), (2.1, 1.2))],
    "maintenance_points": [_poly((3, 1), (3.2, 1), (3.1, 1.2))],
    "clean_info": {
        "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
        "select_region": {"region_id": [7]},
        "move_to_target_point": {"target_point": {"x": 2.5, "y": 2.5}},
    },
    "mow_param": {"mow_height": {"value": 45}},
}


def test_render_mega_scene_all_features() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)

    scene = camera._build_scene()
    assert scene["physical_forbidden_zones"]
    assert scene["pass_through_zones"]
    assert scene["required_zones"]
    assert scene["virtual_cross_boundary_tunnels"]
    assert scene["maintenance_points"]
    assert scene["move_target_point"] is not None

    # rendered_layers is populated in the attributes after a render
    attrs = camera.extra_state_attributes
    assert "rendered_layers" in attrs


# ---------------------------------------------------------------------------
# robot: live pose without yaw + battery disconnected
# ---------------------------------------------------------------------------


def test_render_robot_live_pose_without_yaw() -> None:
    hub = _hub()
    camera = _camera(hub)
    # battery explicitly disconnected -> not the dock fallback
    asyncio.run(hub.on_battery_status(json.dumps({"charger_connected": False})))
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    # a non-zero pose with no yaw -> the live_pose path with yaw defaulted to 0
    asyncio.run(camera._on_pose({"x": 1.5, "y": 1.5}))

    state = camera._get_display_robot_state()
    assert state["source"] == "live_pose"
    assert _render(camera).startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# long mixed-type path
# ---------------------------------------------------------------------------


def test_render_long_mixed_path() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))

    points = []
    for i in range(40):
        x = 0.1 * i
        ptype = "PATH_POINT_TYPE_CLEANING" if i % 5 else "PATH_POINT_TYPE_TRANSIT"
        points.append({"position": {"x": x, "y": 0.5 + 0.02 * i}, "type": ptype})
    asyncio.run(camera._on_path_data({"id": 5, "map_id": 1, "type": "PATH_TYPE_CLEAN", "points": points}))

    assert _render(camera).startswith(PNG_MAGIC)
    scene = camera._build_scene()
    assert scene["current_path_points"]
