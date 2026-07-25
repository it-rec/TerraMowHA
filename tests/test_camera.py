"""Tests for the map camera: geometry helpers, scene building, rendering."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

# HA's camera component imports turbojpeg, which the test harness does not
# ship; a stub is enough for these tests.
sys.modules.setdefault("turbojpeg", MagicMock())

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import TerraMowMapCamera  # noqa: E402
from custom_components.terramow.hub import TerraMowHub  # noqa: E402
from custom_components.terramow.map_render import (  # noqa: E402
    CoordinateTransformer,
    _truncate,
    render_placeholder,
)
from custom_components.terramow.map_scene import (  # noqa: E402
    _dedupe_points,
    _extract_map_extent,
    _extract_path_points,
    _path_map_id,
    _polygon_points,
    _rdp_simplify_pixels,
    coerce_float,
    coerce_int,
    point_tuple,
    pose_tuple,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    # run "executor" jobs inline so the render pipeline works synchronously
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def test_coordinate_transformer_scales_and_centers() -> None:
    transformer = CoordinateTransformer(
        (0.0, 0.0, 10.0, 10.0), rect=(0, 0, 120, 120), padding=10
    )
    assert transformer.to_pixel(0.0, 0.0) == (10, 10)
    assert transformer.to_pixel(10.0, 10.0) == (110, 110)
    assert transformer.to_pixels([(5.0, 5.0)]) == [(60, 60)]


def test_coordinate_transformer_without_points_is_identity_plus_padding() -> None:
    transformer = CoordinateTransformer(None, rect=(0, 0, 100, 100), padding=8)
    assert transformer.to_pixel(0.0, 0.0) == (8, 8)


def test_coercion_helpers() -> None:
    assert coerce_float("1.5") == 1.5
    assert coerce_float(None) is None
    assert coerce_float("abc") is None
    assert coerce_int("7") == 7
    assert coerce_int("x") is None


def test_point_pose_and_polygon_extraction() -> None:
    assert point_tuple({"x": 1, "y": 2}) == (1.0, 2.0)
    assert point_tuple({"x": 1}) is None
    assert point_tuple("nope") is None

    pose = pose_tuple({"x": 1, "y": 2, "theta": 0.5})
    assert pose == {"x": 1.0, "y": 2.0, "theta": 0.5}
    # yaw is accepted as a theta fallback
    assert pose_tuple({"x": 0, "y": 0, "yaw": 1.0})["theta"] == 1.0

    polygon = _polygon_points({"points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, "junk"]})
    assert polygon == [(0.0, 0.0), (1.0, 0.0)]
    assert _polygon_points(None) == []


def test_dedupe_points_keeps_order() -> None:
    assert _dedupe_points([(1.0, 1.0), (2.0, 2.0), (1.0, 1.0)]) == [
        (1.0, 1.0),
        (2.0, 2.0),
    ]


def test_extract_map_extent() -> None:
    extent = _extract_map_extent(
        {"width": 100, "height": 80, "resolution": 0.05, "origin": {"x": -2, "y": -1}}
    )
    assert extent == [(-2.0, -1.0), (3.0, -1.0), (3.0, 3.0), (-2.0, 3.0)]
    assert _extract_map_extent({"width": 100}) == []


def test_extract_path_points_and_map_id() -> None:
    path_data = {
        "map_id": 4,
        "points": [
            {"position": {"x": 1, "y": 2}, "type": "PATH_POINT_TYPE_CLEANING"},
            {"position": {"x": 9}},  # incomplete -> dropped
            "junk",
        ],
    }
    points = _extract_path_points(path_data)
    assert points == [{"x": 1.0, "y": 2.0, "type": "PATH_POINT_TYPE_CLEANING"}]
    assert _path_map_id(path_data) == 4
    assert _extract_path_points({"points": "no-list"}) == []


def test_rdp_simplify_drops_collinear_points() -> None:
    line = [(0, 0), (5, 0), (10, 0), (10, 10)]
    assert _rdp_simplify_pixels(line, epsilon=1.0) == [(0, 0), (10, 0), (10, 10)]


def test_truncate() -> None:
    assert _truncate("short", 10) == "short"
    assert len(_truncate("a-very-long-name", 8)) <= 8


def test_render_placeholder_returns_png() -> None:
    assert render_placeholder("Testing").startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# full render pipeline
# ---------------------------------------------------------------------------

MAP_DATA = {
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
            "boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 3, "y": 0},
                    {"x": 3, "y": 2},
                    {"x": 0, "y": 2},
                ]
            },
            "sub_regions": [
                {
                    "id": 7,
                    "name": "Rasen",
                    "boundary": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 3, "y": 0},
                            {"x": 3, "y": 2},
                            {"x": 0, "y": 2},
                        ]
                    },
                    "center": {"x": 1.5, "y": 1.0},
                }
            ],
        }
    ],
    "clean_info": {"mode": "MAP_CLEAN_INFO_MODE_GLOBAL"},
    "mow_param": {"mow_height": {"value": 45}},
}

PATH_DATA = {
    "id": 5,
    "map_id": 1,
    "type": "PATH_TYPE_CLEAN",
    "points": [
        {"position": {"x": 0.2, "y": 0.2}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 1.0, "y": 0.6}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 2.2, "y": 1.4}, "type": "PATH_POINT_TYPE_CLEANING"},
    ],
}


def _camera(hub, **kwargs) -> TerraMowMapCamera:
    return TerraMowMapCamera(hub.basic_data, hub.hass, **kwargs)


def _image(camera) -> bytes:
    return asyncio.run(camera.async_camera_image())


def test_camera_renders_placeholder_without_data() -> None:
    hub = _hub()
    camera = _camera(hub)
    assert _image(camera).startswith(PNG_MAGIC)


def test_camera_renders_map_with_path_and_pose() -> None:
    hub = _hub()
    camera = _camera(hub)

    hub._map_data = MAP_DATA
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_path_data(PATH_DATA))
    asyncio.run(camera._on_pose({"x": 1.0, "y": 1.0, "yaw": 45}))

    image = _image(camera)
    assert image.startswith(PNG_MAGIC)
    # a real map render is substantially bigger than the placeholder
    assert len(image) > len(render_placeholder())

    attrs = camera.extra_state_attributes
    assert attrs["combined_path_summary"]["point_count"] == 3
    assert "rendered_layers" in attrs


def test_camera_clean_mode_renders_and_uses_own_unique_id() -> None:
    hub = _hub()
    camera = _camera(hub, clean_mode=True)
    hub._map_data = MAP_DATA
    asyncio.run(camera._on_map_info({"id": 1}))

    assert _image(camera).startswith(PNG_MAGIC)
    assert camera.unique_id.endswith("map_camera_clean")

    default = _camera(hub)
    assert default.unique_id.endswith("map_camera")


def test_camera_render_is_cached_until_new_data() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DATA
    asyncio.run(camera._on_map_info({"id": 1}))

    first = _image(camera)
    assert _image(camera) is first  # cached PNG object reused

    asyncio.run(camera._on_path_data(PATH_DATA))
    assert _image(camera) is not first  # cache invalidated by new data


def test_camera_output_resolution_is_applied() -> None:
    import io

    from PIL import Image

    hub = _hub()
    camera = _camera(hub, output_resolution=400)
    hub._map_data = MAP_DATA
    asyncio.run(camera._on_map_info({"id": 1}))

    with Image.open(io.BytesIO(_image(camera))) as rendered:
        assert rendered.size == (400, 400)


def test_camera_ignores_path_for_other_map() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = MAP_DATA
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_path_data({**PATH_DATA, "map_id": 99}))

    scene = camera._build_scene()
    assert scene["path_map_mismatch"] is True
    assert scene["current_path_points"] == []
