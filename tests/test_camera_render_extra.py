"""Extra camera coverage: render a feature-rich map scene.

The base ``test_camera`` suite renders a simple map. This module feeds a scene
that also carries obstacles, forbidden zones, virtual walls, a selected
sub-region with inner boundaries and edge segments, a live robot pose and a
history path, so the region/obstacle/zone extraction and the corresponding
draw helpers are exercised end to end.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

# HA's camera component imports turbojpeg, which the test harness does not
# ship; a stub is enough for these tests.
sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.50", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    # run "executor" jobs inline so the render pipeline works synchronously
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


RICH_MAP = {
    "id": 1,
    "name": "Garten",
    "map_state": "MAP_STATE_COMPLETE",
    "resolution": 0.05,
    "origin": {"x": -2.0, "y": -2.0},
    "station_pose": {"x": 0.0, "y": 0.0, "theta": 250.0},
    "total_area": 2560,
    "map_view_rotate_angle": 15,
    "regions": [
        {
            "id": 100,
            "name": "Haupt",
            "boundary": _poly((0, 0), (4, 0), (4, 3), (0, 3)),
            "obstacles": [_poly((1.0, 1.0), (1.3, 1.0), (1.3, 1.3), (1.0, 1.3))],
            "sub_regions": [
                {
                    "id": 7,
                    "name": "Rasen vorne",
                    "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                    "inner_boundarys": [_poly((0.5, 0.5), (1.0, 0.5), (1.0, 1.0))],
                    "edge_segments": [_poly((0, 0), (2, 0))],
                    "center": {"x": 1.0, "y": 1.0},
                    "is_selected_for_mow": True,
                    "selected_for_mow_order": 1,
                },
                {
                    "id": 8,
                    "name": "Rasen hinten",
                    "boundary": _poly((2, 0), (4, 0), (4, 2), (2, 2)),
                    "center": {"x": 3.0, "y": 1.0},
                },
            ],
        },
    ],
    "obstacles": [_poly((3.0, 2.0), (3.4, 2.0), (3.4, 2.4), (3.0, 2.4))],
    "forbidden_zones": [_poly((0.2, 2.2), (0.8, 2.2), (0.8, 2.8), (0.2, 2.8))],
    "virtual_walls": [_poly((0, 2.5), (4, 2.5))],
    "clean_info": {
        "mode": "MAP_CLEAN_INFO_MODE_SELECT_REGION",
        "select_region": {"region_id": [7]},
    },
    "mow_param": {"mow_height": {"value": 45}},
}

CURRENT_PATH = {
    "id": 5,
    "map_id": 1,
    "type": "PATH_TYPE_CLEAN",
    "points": [
        {"position": {"x": 0.2, "y": 0.2}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 1.0, "y": 0.6}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 2.2, "y": 1.4}, "type": "PATH_POINT_TYPE_CLEANING"},
    ],
}

HISTORY_PATH = {
    "id": 4,
    "map_id": 1,
    "type": "PATH_TYPE_CLEAN",
    "points": [
        {"position": {"x": 0.1, "y": 0.1}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 0.5, "y": 0.4}, "type": "PATH_POINT_TYPE_CLEANING"},
    ],
}


def _camera(hub, **kwargs) -> TerraMowMapCamera:
    return TerraMowMapCamera(hub.basic_data, hub.hass, **kwargs)


def test_camera_renders_rich_scene_with_all_features() -> None:
    hub = _hub()
    camera = _camera(hub)

    # battery connected so the robot renders in its charging-aware state
    asyncio.run(hub.on_battery_status(json.dumps({"charger_connected": True})))

    hub._map_data = RICH_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data(HISTORY_PATH))
    asyncio.run(camera._on_path_data(CURRENT_PATH))
    asyncio.run(camera._on_pose({"x": 1.0, "y": 1.0, "yaw": 45}))

    image = asyncio.run(camera.async_camera_image())
    assert image.startswith(PNG_MAGIC)

    scene = camera._build_scene()
    counts = scene["scene_counts"]
    assert counts["regions"] == 1
    # region-level + map-level obstacles both extracted
    assert len(scene["obstacles"]) == 2
    assert len(scene["forbidden_zones"]) == 1
    assert len(scene["virtual_walls"]) == 1

    # the sub-region referenced by clean_info.select_region is marked selected
    sub_regions = scene["regions"][0]["sub_regions"]
    selected = {s["id"]: s["selected"] for s in sub_regions}
    assert selected[7] is True
    assert selected[8] is False


def test_camera_rich_scene_reports_layers_and_paths() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = RICH_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data(HISTORY_PATH))
    asyncio.run(camera._on_path_data(CURRENT_PATH))

    # render so extra_state_attributes reflects a real scene
    asyncio.run(camera.async_camera_image())
    attrs = camera.extra_state_attributes
    assert attrs["combined_path_summary"]["point_count"] == 5
    assert "rendered_layers" in attrs
