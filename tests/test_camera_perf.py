"""Camera rendering performance behaviors.

Covers the lazy hub-callback registration, rebuild coalescing, the render
generation counter, battery-source gating, the empty/unchanged map-data skip,
the cached placeholder and the bbox-cropped composite overlays.
"""

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# HA's camera component imports turbojpeg, which the test harness lacks.
sys.modules.setdefault("turbojpeg", MagicMock())

from PIL import Image, ImageDraw  # noqa: E402

from custom_components.terramow import TerraMowBasicData  # noqa: E402
from custom_components.terramow.camera import (  # noqa: E402
    BATTERY_STATUS_DP,
    TerraMowMapCamera,
)
from custom_components.terramow.hub import TerraMowHub  # noqa: E402
from custom_components.terramow.map_render import (  # noqa: E402
    _load_font,
    render_placeholder,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _poly(*pts):
    return {"points": [{"x": x, "y": y} for x, y in pts]}


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(host="192.0.2.170", password="secret")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    # run "executor" jobs inline so the render pipeline works synchronously
    hub.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    return hub


def _camera(hub, **kwargs) -> TerraMowMapCamera:
    return TerraMowMapCamera(hub.basic_data, hub.hass, **kwargs)


def _render(camera) -> bytes:
    return asyncio.run(camera.async_camera_image())


SMALL_MAP = {
    "id": 1,
    "name": "Garten",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 100,
    "height": 80,
    "resolution": 0.05,
    "origin": {"x": -2.0, "y": -2.0},
    "station_pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
    "regions": [
        {
            "id": 100,
            "boundary": _poly((0, 0), (3, 0), (3, 2), (0, 2)),
            "sub_regions": [],
        }
    ],
}


# ---------------------------------------------------------------------------
# lazy hub-callback registration (registry-disabled entities render nothing)
# ---------------------------------------------------------------------------


def test_constructor_does_not_register_hub_callbacks() -> None:
    hub = _hub()
    camera = _camera(hub)
    # A disabled-by-default entity is constructed but never added to hass; it
    # must not receive (and render on) map/path/pose pushes.
    assert camera._on_map_info not in hub.map_callbacks
    assert camera._on_pose not in hub.pose_callbacks


def test_added_to_hass_registers_hub_callbacks() -> None:
    hub = _hub()
    camera = _camera(hub)
    asyncio.run(camera.async_added_to_hass())
    assert camera._on_map_info in hub.map_callbacks
    assert camera._on_path_data in hub.path_callbacks
    assert camera._on_history_path_data in hub.history_path_callbacks
    assert camera._on_pose in hub.pose_callbacks
    assert camera._on_battery_status in hub.callbacks[BATTERY_STATUS_DP]
    # a second (clean-mode) camera registers alongside the first
    clean = _camera(hub, clean_mode=True)
    asyncio.run(clean.async_added_to_hass())
    assert clean._on_battery_status in hub.callbacks[BATTERY_STATUS_DP]


def test_removal_deregisters_all_hub_callbacks() -> None:
    hub = _hub()
    camera = _camera(hub)
    asyncio.run(camera.async_added_to_hass())
    # removing the entity (which runs the async_on_remove callbacks) must
    # deregister every hub callback so a removed camera stops being invoked
    camera._call_on_remove_callbacks()
    assert camera._on_map_info not in hub.map_callbacks
    assert camera._on_path_data not in hub.path_callbacks
    assert camera._on_history_path_data not in hub.history_path_callbacks
    assert camera._on_pose not in hub.pose_callbacks
    assert camera._on_battery_status not in hub.callbacks[BATTERY_STATUS_DP]


def test_added_to_hass_without_lawn_mower() -> None:
    hub = _hub()
    orphan = TerraMowMapCamera(
        TerraMowBasicData(host="192.0.2.171", password="secret"), hub.hass
    )
    # no lawn mower -> nothing to register, must not raise
    asyncio.run(orphan.async_added_to_hass())
    assert orphan._on_map_info not in hub.map_callbacks


def test_camera_image_rebuilds_lazily_without_snapshot() -> None:
    hub = _hub()
    camera = _camera(hub)
    # Data exists (e.g. replayed before the entity was enabled) but no
    # rebuild ran yet -> the first image request builds the snapshot.
    camera._map_data = SMALL_MAP
    assert camera._render_snapshot is None
    assert _render(camera).startswith(PNG_MAGIC)
    assert camera._render_snapshot is not None


def test_camera_image_rebuilds_when_marked_stale() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = SMALL_MAP
    assert _render(camera).startswith(PNG_MAGIC)  # builds the first snapshot

    # A later source push only marks the static layers stale (no proactive
    # render). Because the first snapshot was just built, an immediate frame
    # request is inside STATIC_REBUILD_MIN_INTERVAL and reuses it (a streamed
    # live view must not re-render the expensive image on every frame).
    camera._mark_static_dirty()
    assert camera._static_dirty is True
    assert camera._render_snapshot is not None
    with patch.object(
        camera, "_rebuild_static_image", wraps=camera._rebuild_static_image
    ) as rebuild:
        assert _render(camera).startswith(PNG_MAGIC)
        assert rebuild.call_count == 0
    assert camera._static_dirty is True  # still pending a rebuild

    # Once the throttle interval has elapsed, the next request rebuilds and
    # clears the stale mark.
    camera._last_static_rebuild -= 3600.0
    with patch.object(
        camera, "_rebuild_static_image", wraps=camera._rebuild_static_image
    ) as rebuild:
        assert _render(camera).startswith(PNG_MAGIC)
        assert rebuild.call_count == 1
    assert camera._static_dirty is False


def test_streaming_frames_during_mow_throttle_static_rebuilds() -> None:
    # A live view streams async_camera_image at ~2 fps while path pushes keep
    # marking the static layers stale; the expensive supersampled render must
    # fire at most once per STATIC_REBUILD_MIN_INTERVAL, not on every frame.
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = SMALL_MAP
    _render(camera)  # first frame builds the snapshot

    with patch.object(
        camera, "_rebuild_static_image", wraps=camera._rebuild_static_image
    ) as rebuild:
        # 20 streamed frames, each preceded by a fresh path push (as during an
        # active mow), all inside one throttle window
        for _ in range(20):
            camera._mark_static_dirty()
            assert _render(camera).startswith(PNG_MAGIC)
        assert rebuild.call_count == 0  # all served from the reused snapshot

        # the window elapses -> the next frame refreshes the static image once
        camera._last_static_rebuild -= 3600.0
        camera._mark_static_dirty()
        assert _render(camera).startswith(PNG_MAGIC)
        assert rebuild.call_count == 1


def test_should_rebuild_static_gates() -> None:
    hub = _hub()
    camera = _camera(hub)
    # No data at all -> never rebuild (the request serves the placeholder).
    assert camera._should_rebuild_static() is False
    assert _render(camera).startswith(PNG_MAGIC)

    # Data present, no snapshot yet -> rebuild.
    camera._map_data = SMALL_MAP
    assert camera._should_rebuild_static() is True
    _render(camera)  # builds the snapshot, clears the dirty flag

    # Snapshot present and not stale -> no rebuild.
    assert camera._static_dirty is False
    assert camera._should_rebuild_static() is False


def test_first_frame_always_renders_despite_throttle() -> None:
    # Opening the camera must never serve a blank frame even if a rebuild
    # "just happened" on the clock: no snapshot yet always forces a render.
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = SMALL_MAP
    camera._last_static_rebuild = 1e12  # pretend a rebuild just ran
    assert camera._render_snapshot is None
    with patch.object(
        camera, "_rebuild_static_image", wraps=camera._rebuild_static_image
    ) as rebuild:
        assert _render(camera).startswith(PNG_MAGIC)
        assert rebuild.call_count == 1
    assert camera._render_snapshot is not None


# ---------------------------------------------------------------------------
# rebuild coalescing
# ---------------------------------------------------------------------------


def test_concurrent_rebuild_requests_share_one_render() -> None:
    hub = _hub()
    camera = _camera(hub)
    camera._map_data = SMALL_MAP
    calls: list[int] = []

    async def _burst() -> None:
        with patch.object(
            camera, "_rebuild_static_image", side_effect=lambda: calls.append(1)
        ):
            # a reconnect burst: map + path + history callbacks land together
            await asyncio.gather(
                camera._async_rebuild(),
                camera._async_rebuild(),
                camera._async_rebuild(),
            )

    asyncio.run(_burst())
    assert len(calls) == 1


def test_rebuild_runs_again_when_dirtied_mid_render() -> None:
    hub = _hub()
    camera = _camera(hub)

    calls: list[int] = []

    def _rebuild_and_dirty() -> None:
        calls.append(1)
        if len(calls) == 1:
            # a new update arrives while the first render is in flight
            camera._rebuild_dirty = True

    with patch.object(camera, "_rebuild_static_image", _rebuild_and_dirty):
        asyncio.run(camera._async_rebuild())
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# map-data gating: empty or unchanged pushes don't trigger rebuilds
# ---------------------------------------------------------------------------


def test_on_map_info_skips_empty_and_unchanged_map_data() -> None:
    hub = _hub()
    camera = _camera(hub)
    # Rendering is lazy now: a map push only marks the static layers stale
    # (the render happens on the next image request), so the gating asserts on
    # _mark_static_dirty rather than on a proactive rebuild.
    with patch.object(camera, "_mark_static_dirty") as mark:
        # old-firmware push: map/current/info fires while map_data stays empty
        hub._map_data = {}
        asyncio.run(camera._on_map_info({"id": 1}))
        assert mark.call_count == 0
        # first real map data -> marked stale
        hub._map_data = dict(SMALL_MAP)
        asyncio.run(camera._on_map_info({"id": 1}))
        assert mark.call_count == 1
        # the same dict pushed again -> unchanged, skipped
        asyncio.run(camera._on_map_info({"id": 1}))
        assert mark.call_count == 1
        # a fresh dict (new HTTP fetch) -> marked stale
        hub._map_data = dict(SMALL_MAP)
        asyncio.run(camera._on_map_info({"id": 1}))
        assert mark.call_count == 2
        # map_data dropping back to empty is a change -> marked stale
        hub._map_data = {}
        asyncio.run(camera._on_map_info({"id": 1}))
        assert mark.call_count == 3


# ---------------------------------------------------------------------------
# battery-source gating
# ---------------------------------------------------------------------------


def test_battery_status_only_invalidates_on_source_change() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))

    # first battery message establishes the displayed source ("unavailable")
    asyncio.run(camera._on_battery_status("{}"))
    png = _render(camera)
    assert camera._cached_png is png

    # an unchanged keepalive must keep the cached PNG
    asyncio.run(camera._on_battery_status("{}"))
    assert camera._cached_png is png

    # charger connect with a docked zero pose flips the source -> invalidated
    camera._pose = {"x": 0.0, "y": 0.0, "yaw": 0.0}
    asyncio.run(hub.on_battery_status(json.dumps({"charger_connected": True})))
    asyncio.run(camera._on_battery_status("{}"))
    assert camera._cached_png is None


# ---------------------------------------------------------------------------
# pose gating: identical keepalive poses keep the cached PNG
# ---------------------------------------------------------------------------


def test_unchanged_pose_keeps_cached_png() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))

    asyncio.run(camera._on_pose({"x": 1.0, "y": 2.0, "yaw": 0.5}))
    png = _render(camera)
    assert camera._cached_png is png

    # a docked mower pushes the same pose at ~2 Hz; the cache must survive
    asyncio.run(camera._on_pose({"x": 1.0, "y": 2.0, "yaw": 0.5}))
    assert camera._cached_png is png

    # an actual movement invalidates
    asyncio.run(camera._on_pose({"x": 1.1, "y": 2.0, "yaw": 0.5}))
    assert camera._cached_png is None


# ---------------------------------------------------------------------------
# render generation counter
# ---------------------------------------------------------------------------


def test_stale_render_does_not_repopulate_cache() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._async_rebuild())  # lazy: build the snapshot explicitly

    # a pose update invalidates the cache while this render is in flight
    def _invalidate(*_args) -> None:
        camera._invalidate_png_cache()

    with patch.object(camera._renderer, "_draw_robot", side_effect=_invalidate):
        stale = camera._render_final_image()
    assert stale.startswith(PNG_MAGIC)
    assert camera._cached_png is None

    # the next (current-generation) render caches again
    fresh = camera._render_final_image()
    assert camera._cached_png is fresh


# ---------------------------------------------------------------------------
# static scene checkpoint cache
# ---------------------------------------------------------------------------


def _path(points) -> dict:
    return {
        "id": 5,
        "map_id": 1,
        "type": "PATH_TYPE_CLEAN",
        "points": [
            {"position": {"x": x, "y": y}, "type": "PATH_POINT_TYPE_CLEANING"}
            for x, y in points
        ],
    }


def test_warm_checkpoint_render_matches_cold_render_bytes() -> None:
    # The checkpoint replay must be pixel-identical to a full cold redraw.
    path = _path([(0.2, 0.2), (1.5, 0.8), (2.5, 1.5)])
    with patch("custom_components.terramow.camera.dt_util") as dt:
        dt.now.return_value.strftime.return_value = "12:00"

        # warm: map first (checkpoint stored), then a path push (replayed)
        hub_a = _hub()
        cam_a = _camera(hub_a)
        hub_a._map_data = SMALL_MAP
        asyncio.run(cam_a._on_map_info({"id": 1}))
        asyncio.run(cam_a._on_path_data(path))
        warm = _render(cam_a)

        # cold: identical data rendered in one pass on a fresh camera
        hub_b = _hub()
        cam_b = _camera(hub_b)
        cam_b._map_data = SMALL_MAP
        cam_b._path_data = path
        cold = _render(cam_b)

    assert warm == cold


def test_checkpoint_skips_static_redraw_until_fit_or_map_changes() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._async_rebuild())  # lazy: render builds the checkpoint
    renderer = camera._renderer
    assert renderer._static_checkpoint is not None

    with patch.object(
        renderer, "_draw_scene_static", wraps=renderer._draw_scene_static
    ) as static:
        # an in-bounds path push keeps the fit -> checkpoint replay
        asyncio.run(camera._on_path_data(_path([(0.5, 0.5), (1.0, 1.0)])))
        asyncio.run(camera._async_rebuild())
        assert static.call_count == 0
        # a point outside the map extent changes the fit -> full redraw
        asyncio.run(camera._on_path_data(_path([(0.5, 0.5), (50.0, 50.0)])))
        asyncio.run(camera._async_rebuild())
        assert static.call_count == 1

    # a new map dict (fresh HTTP fetch) misses on identity
    hub._map_data = dict(SMALL_MAP)
    with patch.object(
        renderer, "_draw_scene_static", wraps=renderer._draw_scene_static
    ) as static:
        asyncio.run(camera._on_map_info({"id": 1}))
        asyncio.run(camera._async_rebuild())
        assert static.call_count == 1


def test_checkpoint_cleared_when_scene_empties() -> None:
    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._async_rebuild())  # lazy: render builds the checkpoint
    assert camera._renderer._static_checkpoint is not None
    # all data gone -> reset() must release the supersampled canvas
    camera._map_data = {}
    camera._path_data = {}
    camera._history_path_data = {}
    camera._rebuild_static_image()
    assert camera._renderer._static_checkpoint is None


# ---------------------------------------------------------------------------
# scene path cache
# ---------------------------------------------------------------------------


def test_scene_path_cache_hits_on_same_dict_and_reextracts_on_new() -> None:
    from custom_components.terramow.map_scene import ScenePathCache, build_scene

    history = _path([(0.1, 0.1), (0.2, 0.2)])
    current = _path([(0.5, 0.5)])
    cache = ScenePathCache()

    first = build_scene(SMALL_MAP, current, history, False, cache=cache)
    # a new current-path dict with the unchanged history dict: the history
    # extraction is served from the cache (identical list objects)...
    second = build_scene(SMALL_MAP, _path([(0.5, 0.5), (0.6, 0.6)]), history, False, cache=cache)
    assert second["history_path_points"] is first["history_path_points"]
    # ...while the current path was re-extracted
    assert len(second["current_path_points"]) == 2

    # a replaced history dict re-extracts
    third = build_scene(SMALL_MAP, current, dict(history), False, cache=cache)
    assert third["history_path_points"] is not first["history_path_points"]
    assert third["history_path_points"] == first["history_path_points"]

    # cached and uncached scenes are equal for identical inputs
    uncached = build_scene(SMALL_MAP, current, history, False)
    cached = build_scene(SMALL_MAP, current, history, False, cache=ScenePathCache())
    assert cached == uncached


def test_camera_rebuild_uses_scene_cache_across_path_pushes() -> None:
    import custom_components.terramow.map_scene as map_scene_module

    hub = _hub()
    camera = _camera(hub)
    hub._map_data = SMALL_MAP
    asyncio.run(camera._on_map_info({"id": 1}))
    asyncio.run(camera._on_history_path_data(_path([(0.1, 0.1), (0.9, 0.9)])))
    asyncio.run(camera._async_rebuild())  # initial render populates the scene cache

    with patch.object(
        map_scene_module,
        "_extract_path_points",
        wraps=map_scene_module._extract_path_points,
    ) as extract:
        # a current-path push re-extracts only the changed source; the
        # unchanged history dict is served from the camera's scene cache
        asyncio.run(camera._on_path_data(_path([(0.5, 0.5)])))
        asyncio.run(camera._async_rebuild())
        assert extract.call_count == 1


# ---------------------------------------------------------------------------
# cached placeholder
# ---------------------------------------------------------------------------


def test_placeholder_png_is_cached_per_text_and_palette() -> None:
    first = render_placeholder("Cache me")
    assert first.startswith(PNG_MAGIC)
    # repeated waiting-for-data polls reuse the encoded PNG object
    assert render_placeholder("Cache me") is first
    assert render_placeholder("Different text") is not first


# ---------------------------------------------------------------------------
# bbox-cropped composite overlays
# ---------------------------------------------------------------------------


def test_composite_polygon_fill_matches_full_canvas_overlay() -> None:
    hub = _hub()
    camera = _camera(hub)
    pixels = [(5, 5), (40, 8), (30, 50)]
    fill = (255, 0, 0, 60)

    cropped = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
    camera._renderer._composite_polygon_fill(cropped, pixels, fill)

    # reference: the old full-canvas overlay compositing
    reference = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
    overlay = Image.new("RGBA", reference.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay, "RGBA").polygon(pixels, fill=fill)
    reference.alpha_composite(overlay)

    assert cropped.tobytes() == reference.tobytes()


def test_apply_hatch_matches_full_canvas_overlay() -> None:
    hub = _hub()
    camera = _camera(hub)
    pixels = [(6, 6), (50, 10), (40, 52), (8, 44)]
    color = (255, 120, 70, 88)
    spacing = 7

    cropped = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
    camera._renderer._apply_hatch(cropped, pixels, color, spacing=spacing)

    # reference: the old full-canvas mask/overlay hatch
    reference = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
    mask = Image.new("L", reference.size, 0)
    ImageDraw.Draw(mask).polygon(pixels, fill=255)
    overlay = Image.new("RGBA", reference.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    min_x = min(p[0] for p in pixels)
    max_x = max(p[0] for p in pixels)
    min_y = min(p[1] for p in pixels)
    max_y = max(p[1] for p in pixels)
    start = min_x - (max_y - min_y) - spacing
    end = max_x + (max_y - min_y) + spacing
    for offset in range(int(start), int(end), spacing):
        overlay_draw.line(
            [
                (offset, max_y + spacing),
                (offset + (max_y - min_y) + spacing, min_y - spacing),
            ],
            fill=color,
            width=1,
        )
    reference.alpha_composite(
        Image.composite(overlay, Image.new("RGBA", overlay.size), mask)
    )

    assert cropped.tobytes() == reference.tobytes()


def test_composite_helpers_skip_off_canvas_and_empty_shapes() -> None:
    hub = _hub()
    camera = _camera(hub)
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 255))
    before = image.tobytes()

    # a shape entirely off the canvas yields no overlay box
    assert camera._renderer._overlay_bbox(image, [(-20, -20), (-5, -5)], 1) is None
    camera._renderer._composite_polygon_fill(
        image, [(-20, -20), (-5, -20), (-5, -5)], (255, 0, 0, 128)
    )
    camera._renderer._apply_hatch(image, [(-20, -20), (-5, -20), (-5, -5)], (255, 0, 0, 128))
    # an empty point list is a no-op
    camera._renderer._composite_draw(image, [], lambda draw, shifted: None)

    assert image.tobytes() == before


# ---------------------------------------------------------------------------
# chip width without a scratch image
# ---------------------------------------------------------------------------


def test_chip_width_matches_textbbox_measurement() -> None:
    hub = _hub()
    camera = _camera(hub)
    text = "Map #1 · Garten"
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = draw.textbbox((0, 0), text, font=_load_font(15, bold=True))
    assert camera._renderer._chip_width(text) == int(box[2] - box[0] + 24)


# ---------------------------------------------------------------------------
# recorder-excluded attributes
# ---------------------------------------------------------------------------


def test_volatile_attributes_are_unrecorded() -> None:
    unrecorded = TerraMowMapCamera._unrecorded_attributes
    assert isinstance(unrecorded, frozenset)
    for key in (
        "current_pose",
        "display_pose",
        "calibration_points",
        "present_top_level_fields",
        "scene_counts",
    ):
        assert key in unrecorded
    # user-facing configuration attributes stay recorded
    assert "map_theme" not in unrecorded
    assert "coverage_enabled" not in unrecorded
