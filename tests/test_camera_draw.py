"""Extra camera render coverage: draw branches for every feature type.

Renders scenes that exercise the empty-map card, all marker/zone/tunnel draws,
order badges, the move-target and origin markers, the live-pose robot (battery
disconnected, no yaw) and a long mixed-type path.
"""

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import (  # noqa: E402
    TerraMowMapCamera,
    async_setup_entry,
)
from custom_components.terramow.const import CONF_MAP_RESOLUTION  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.130", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
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


# ---------------------------------------------------------------------------
# _build_scene: path/map-id inference, mismatch dropping, region params
# ---------------------------------------------------------------------------


def _cleaning(x, y):
    return {"position": {"x": x, "y": y}, "type": "PATH_POINT_TYPE_CLEANING"}


def test_build_scene_drops_current_path_on_map_mismatch() -> None:
    hub = _hub()
    camera = _camera(hub)
    # map has an id (target); mow_param.regions feeds region_param_ids
    camera._map_data = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "mow_param": {"regions": [{"id": 5}, "not-a-dict", {"id": None}]},
    }
    # current path belongs to a different map -> dropped as a mismatch
    camera._path_data = {"map_id": 2, "points": [_cleaning(0.0, 0.0)]}
    # history path matches the target map -> kept
    camera._history_path_data = {"map_id": 1, "points": [_cleaning(1.0, 1.0)]}

    scene = camera._build_scene()
    assert scene["path_map_mismatch"] is True
    assert scene["current_path_points"] == []
    assert scene["history_path_points"]


def test_build_scene_infers_target_map_from_current_path() -> None:
    hub = _hub()
    camera = _camera(hub)
    # map without an id -> target map is inferred from the current path
    camera._map_data = {"map_state": "MAP_STATE_COMPLETE"}
    camera._path_data = {"map_id": 3, "points": [_cleaning(0.0, 0.0)]}
    # history path on another map -> dropped once the target is known
    camera._history_path_data = {"map_id": 9, "points": [_cleaning(2.0, 2.0)]}

    scene = camera._build_scene()
    assert scene["current_path_points"]
    assert scene["history_path_points"] == []
    assert scene["path_map_mismatch"] is True


def test_build_scene_infers_target_map_from_history_path() -> None:
    hub = _hub()
    camera = _camera(hub)
    # map without an id, no current path -> target inferred from history path
    camera._map_data = {"map_state": "MAP_STATE_COMPLETE"}
    camera._path_data = {}
    camera._history_path_data = {"map_id": 4, "points": [_cleaning(0.0, 0.0)]}

    scene = camera._build_scene()
    assert scene["history_path_points"]
    assert scene["current_path_points"] == []


# ---------------------------------------------------------------------------
# camera platform setup
# ---------------------------------------------------------------------------


def test_camera_setup_creates_normal_and_clean_cameras() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(runtime_data=hub.basic_data, options={})
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    # one full-map camera + one clean-mode camera
    assert len(added) == 2
    assert any(cam._clean_mode for cam in added)
    assert any(not cam._clean_mode for cam in added)


def test_camera_setup_falls_back_on_invalid_resolution() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(
        runtime_data=hub.basic_data, options={CONF_MAP_RESOLUTION: "bogus"}
    )
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert len(added) == 2


def test_camera_setup_falls_back_on_invalid_theme() -> None:
    hub = _hub()
    added: list = []
    entry = SimpleNamespace(
        runtime_data=hub.basic_data, options={"map_theme": "bogus"}
    )
    asyncio.run(async_setup_entry(hub.hass, entry, added.extend))
    assert all(cam._theme == "light" for cam in added)


def test_calibration_points_none_before_first_render() -> None:
    hub = _hub()
    camera = _camera(hub)
    # never rendered -> no snapshot -> no calibration attribute
    assert camera._build_calibration_points() is None


def test_draw_coverage_noop_on_degenerate_path() -> None:
    hub = _hub()
    camera = _camera(hub, show_coverage=True)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    # two identical cleaning points collapse to a single pixel -> no swath drawn
    asyncio.run(
        camera._on_path_data(
            {
                "id": 5,
                "map_id": 1,
                "type": "PATH_TYPE_CLEAN",
                "points": [
                    {"position": {"x": 1.0, "y": 1.0}, "type": "PATH_POINT_TYPE_CLEANING"},
                    {"position": {"x": 1.0, "y": 1.0}, "type": "PATH_POINT_TYPE_CLEANING"},
                    {"position": {"x": 1.0, "y": 1.0}, "type": "PATH_POINT_TYPE_CLEANING"},
                ],
            }
        )
    )
    assert _render(camera).startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# _build_scene: region edges / obstacles / sub-region inner + centroid
# ---------------------------------------------------------------------------


def test_build_scene_region_edges_obstacles_and_subregion_details() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "regions": [
            {
                "id": 100,
                "boundary": _poly((0, 0), (4, 0), (4, 4), (0, 4)),
                "edge_segments": [_poly((0, 0), (4, 0))],
                "obstacles": [
                    {"ellipse": {"center": {"x": 1, "y": 1}, "radius_x": 0.3, "radius_y": 0.3}}
                ],
                "sub_regions": [
                    {
                        "id": 7,
                        "boundary": _poly((0, 0), (2, 0), (2, 2), (0, 2)),
                        "inner_boundarys": [_poly((0.2, 0.2), (0.8, 0.2), (0.8, 0.8))],
                        "edge_segments": [_poly((0, 0), (2, 0))],
                        # no explicit center -> centroid is derived from the boundary
                    }
                ],
            }
        ],
    }
    camera._path_data = {}
    camera._history_path_data = {}

    scene = camera._build_scene()
    assert scene["regions"]
    assert scene["obstacles"]
    assert scene["regions"][0]["edge_lines"]
    assert scene["regions"][0]["sub_regions"][0]["inner_boundaries"]


# ---------------------------------------------------------------------------
# clean-mode camera render (transparent background, no chrome)
# ---------------------------------------------------------------------------


def test_render_clean_mode_camera() -> None:
    hub = _hub()
    camera = _camera(hub, clean_mode=True)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)


def test_draw_path_segment_legacy_interface() -> None:
    from PIL import Image, ImageDraw

    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    _render(camera)  # a render establishes the coordinate transformer

    img = Image.new("RGBA", (100, 100))
    draw = ImageDraw.Draw(img)
    # a real 2-point segment draws a stroke; a too-short one is a no-op
    camera._draw_path_segment(draw, [{"x": 0.1, "y": 0.1}, {"x": 0.6, "y": 0.6}])
    camera._draw_path_segment(draw, [{"x": 0.1, "y": 0.1}])


# ---------------------------------------------------------------------------
# dark theme
# ---------------------------------------------------------------------------


def test_render_dark_theme() -> None:
    hub = _hub()
    camera = _camera(hub, theme="dark")
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)
    assert camera.extra_state_attributes["map_theme"] == "dark"


def test_invalid_theme_falls_back_to_light() -> None:
    hub = _hub()
    camera = _camera(hub, theme="bogus")
    assert camera._theme == "light"


def test_placeholder_uses_theme_before_data() -> None:
    hub = _hub()
    camera = _camera(hub, theme="dark")
    # no map data yet -> placeholder path, must not raise
    assert _render(camera).startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# coverage layer
# ---------------------------------------------------------------------------


def test_render_coverage_layer() -> None:
    hub = _hub()
    camera = _camera(hub, show_coverage=True)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))

    points = [
        {"position": {"x": 0.1 * i, "y": 0.5}, "type": "PATH_POINT_TYPE_CLEANING"}
        for i in range(20)
    ]
    asyncio.run(
        camera._on_path_data(
            {"id": 5, "map_id": 1, "type": "PATH_TYPE_CLEAN", "points": points}
        )
    )
    assert _render(camera).startswith(PNG_MAGIC)
    assert camera.extra_state_attributes["coverage_enabled"] is True
    assert "coverage" in camera.extra_state_attributes["rendered_layers"]


# ---------------------------------------------------------------------------
# calibration points for interactive map cards
# ---------------------------------------------------------------------------


def test_calibration_points_exposed() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    _render(camera)

    calibration = camera.extra_state_attributes["calibration_points"]
    assert len(calibration) == 3
    for point in calibration:
        assert set(point) == {"vacuum", "map"}
        assert set(point["vacuum"]) == {"x", "y"}
        assert set(point["map"]) == {"x", "y"}


def test_calibration_points_scale_with_output_resolution() -> None:
    hub = _hub()
    camera = _camera(hub, output_resolution=2048)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    _render(camera)

    calibration = camera.extra_state_attributes["calibration_points"]
    # map pixels are expressed in the output-resolution space (2048 = 2x 1024)
    assert max(p["map"]["x"] for p in calibration) > 1024


def test_no_calibration_points_without_geometry() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = {"id": 1, "map_state": "MAP_STATE_INCOMPLETE"}
    asyncio.run(camera._on_map_info({"id": 1}))
    assert "calibration_points" not in camera.extra_state_attributes


# ---------------------------------------------------------------------------
# robot / station icons scale with the map
# ---------------------------------------------------------------------------


def test_robot_icon_rebuilds_on_scale_change() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_pose({"x": 1.5, "y": 1.5, "yaw": 0.0}))
    _render(camera)
    length_a = camera._robot_image_length_px
    assert length_a is not None
    # a much larger map -> smaller robot-to-canvas ratio, icon is rebuilt
    big_map = dict(MEGA_MAP, width=4000, height=4000)
    hub._map_data = big_map
    asyncio.run(camera._on_map_info({"id": 1}))
    _render(camera)
    assert camera._robot_image_length_px is not None


# ---------------------------------------------------------------------------
# scale bar
# ---------------------------------------------------------------------------


def test_scale_bar_and_timestamp_rendered() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    assert _render(camera).startswith(PNG_MAGIC)
    # a rebuild stamps the update time and exposes it as an attribute
    assert camera._last_update_label is not None
    assert camera.extra_state_attributes["map_updated_at"] == camera._last_update_label


def test_scale_bar_choice_picks_round_distance() -> None:
    hub = _hub()
    camera = _camera(hub)
    # 0.1 px/mm -> 5000 mm bar spans 500 px (too wide), 2000 mm spans 200 px (fits)
    choice = camera._scale_bar_choice(0.1)
    assert choice is not None
    length_mm, length_px = choice
    assert length_mm == 2000
    assert length_px == 200


def test_scale_bar_suppressed_on_extreme_zoom() -> None:
    hub = _hub()
    camera = _camera(hub)
    # even the smallest 100 mm step would be far wider than the target
    assert camera._scale_bar_choice(100.0) is None
    # a degenerate transformer scale yields no bar
    assert camera._scale_bar_choice(0.0) is None
    # extremely zoomed out: every step fits but the bar collapses below 12 px
    assert camera._scale_bar_choice(0.0001) is None


def test_map_updated_at_absent_before_first_render() -> None:
    hub = _hub()
    camera = _camera(hub)
    # no rebuild yet -> no timestamp attribute
    assert "map_updated_at" not in camera.extra_state_attributes


# ---------------------------------------------------------------------------
# legend
# ---------------------------------------------------------------------------


def test_legend_lists_present_feature_types() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MEGA_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    scene = camera._build_scene()
    labels = [label for _, label in camera._legend_entries(scene)]
    # the mega map carries no-go, required, pass-through, tunnel and obstacles
    assert "No-go" in labels
    assert "Required" in labels
    assert "Tunnel" in labels


def test_legend_empty_without_features() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "width": 100,
        "height": 80,
        "resolution": 0.05,
        "origin": {"x": 0.0, "y": 0.0},
    }
    scene = camera._build_scene()
    assert camera._legend_entries(scene) == []


# ---------------------------------------------------------------------------
# realistic scale: scale bar + legend actually draw
# ---------------------------------------------------------------------------


# 400 x 320 cells @ 25 mm -> a 10 m x 8 m lawn in millimetre coordinates,
# giving a realistic pixels-per-mm scale where the scale bar is visible.
REALISTIC_MAP = {
    "id": 2,
    "name": "Lawn",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 400,
    "height": 320,
    "resolution": 25,
    "origin": {"x": 0.0, "y": 0.0},
    "station_pose": {"x": 500, "y": 500, "theta": 0},
    "regions": [
        {
            "id": 1,
            "boundary": _poly((0, 0), (10000, 0), (10000, 8000), (0, 8000)),
            "sub_regions": [],
        }
    ],
    "forbidden_zones": [_poly((1000, 1000), (2000, 1000), (2000, 2000))],
    "required_zones": [_poly((3000, 3000), (4000, 3000), (4000, 4000))],
    "pass_through_zones": [_poly((5000, 1000), (6000, 1000), (6000, 2000))],
    "cross_boundary_tunnels": [{"line": _poly((1000, 5000), (2000, 6000))}],
    "obstacles": [_poly((7000, 2000), (7500, 2000), (7500, 2500))],
}


def test_realistic_map_draws_scale_bar_and_legend() -> None:
    hub = _hub()
    camera = _camera(hub, show_coverage=True)
    hub._map_data = REALISTIC_MAP
    asyncio.run(camera._on_map_info({"id": 2}))
    points = [
        {"position": {"x": 500 * i, "y": 4000}, "type": "PATH_POINT_TYPE_CLEANING"}
        for i in range(15)
    ]
    asyncio.run(
        camera._on_path_data(
            {"id": 9, "map_id": 2, "type": "PATH_TYPE_CLEAN", "points": points}
        )
    )
    assert _render(camera).startswith(PNG_MAGIC)

    # the transformer scale is realistic -> a scale bar is chosen and drawn
    assert camera._transformer is not None
    assert camera._scale_bar_choice(camera._transformer.scale) is not None
    labels = [label for _, label in camera._legend_entries(camera._build_scene())]
    assert "Path" in labels
    assert "Coverage" in labels


def test_scale_bar_noop_without_transformer() -> None:
    from PIL import Image, ImageDraw

    hub = _hub()
    camera = _camera(hub)
    camera._transformer = None
    draw = ImageDraw.Draw(Image.new("RGBA", (100, 100)))
    # no transformer -> early return, no crash
    camera._draw_scale_bar(draw)
