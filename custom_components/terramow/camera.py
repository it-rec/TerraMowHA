"""TerraMow map camera entity.

Renders ha_map_v1 / ha_path_v1 / pose into a PNG map with a HUD overlay.

The pipeline is split across three modules: map_scene.py parses the protocol
data into a drawable scene, map_render.py draws it with PIL, and this module
owns the entities — hub callbacks, rebuild coalescing, the PNG cache and the
state attributes.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from PIL import Image

from . import TerraMowBasicData, TerraMowConfigEntry
from .const import (
    CONF_MAP_RESOLUTION,
    CONF_MAP_SHOW_COVERAGE,
    CONF_MAP_THEME,
    DEFAULT_MAP_RESOLUTION,
    DEFAULT_MAP_SHOW_COVERAGE,
    DEFAULT_MAP_THEME,
    MAP_RESOLUTION_OPTIONS,
    MAP_THEME_OPTIONS,
)
from .entity import TerraMowEntity
from .entity_utils import safe_write_ha_state
from .map_render import (
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MAP_PADDING,
    MAP_RECT,
    PALETTES,
    CoordinateTransformer,
    MapRenderer,
)
from .map_scene import (
    ScenePathCache,
    build_render_metadata,
    build_scene,
    coerce_angle_radians,
    coerce_float,
    normalize_angle_radians,
    pose_tuple,
)

# Push-based integration: no update throttling needed
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

BATTERY_STATUS_DP = 108


class TerraMowMapCamera(TerraMowEntity, Camera):
    """Map camera entity."""

    # Volatile (pose/battery-driven, changing every ~2 s) and bulky diagnostic
    # attributes; keep them out of the recorder database. The attributes stay
    # visible on the entity, they are just never written to history.
    _unrecorded_attributes = frozenset(
        {
            "current_pose",
            "display_pose",
            "robot_pose_source",
            "live_pose_valid",
            "battery_connected",
            "map_updated_at",
            "calibration_points",
            "present_top_level_fields",
            "unrendered_fields",
            "scene_counts",
            "rendered_layers",
            "clean_info_summary",
            "mow_param_summary",
            "backup_summary",
            "path_summary",
            "current_path_summary",
            "history_path_summary",
            "combined_path_summary",
            "filtered_non_cleaning_point_count",
        }
    )

    def __init__(
        self,
        basic_data: TerraMowBasicData,
        hass: HomeAssistant,
        *,
        clean_mode: bool = False,
        output_resolution: int = DEFAULT_MAP_RESOLUTION,
        theme: str = DEFAULT_MAP_THEME,
        show_coverage: bool = DEFAULT_MAP_SHOW_COVERAGE,
    ) -> None:
        super().__init__(basic_data, hass)
        self._clean_mode = clean_mode
        self._attr_translation_key = "map_camera_clean" if clean_mode else "map_camera"
        self._unique_id_suffix = "map_camera_clean" if clean_mode else "map_camera"
        # The clean-mode camera is a borderless dashboard-only variant of the
        # main map camera; keep it opt-in so a fresh install shows one camera.
        self._attr_entity_registry_enabled_default = not clean_mode
        self._map_rect: tuple[int, int, int, int] = (
            (0, 0, IMAGE_WIDTH, IMAGE_HEIGHT) if clean_mode else MAP_RECT
        )
        self._output_resolution = output_resolution
        self._theme = theme if theme in PALETTES else DEFAULT_MAP_THEME
        self._show_coverage = show_coverage
        # The renderer owns the drawing state: palette, HUD language table,
        # robot icon cache and the active coordinate transformer.
        config = getattr(hass, "config", None)
        language = getattr(config, "language", None)
        self._renderer = MapRenderer(
            theme=self._theme,
            language=language,
            clean_mode=clean_mode,
            show_coverage=show_coverage,
            output_resolution=output_resolution,
        )
        self._language = self._renderer.language
        # Wall-clock label (HA timezone) of the last static-layer rebuild, shown
        # in the HUD so a stale image is recognisable.
        self._last_update_label: str | None = None

        self._map_data: dict[str, Any] = {}
        self._path_data: dict[str, Any] = {}
        self._history_path_data: dict[str, Any] = {}
        self._pose: dict[str, Any] = {}
        # Skips re-extracting path point lists whose source dict is unchanged
        # across rebuilds (the history path survives every current-path push).
        self._scene_cache = ScenePathCache()

        # The finished static layers paired with the transformer they were
        # drawn with, published as one atomic reference. The final render reads
        # this so it never pairs a static image with a mismatched transformer.
        self._render_snapshot: tuple[Image.Image, CoordinateTransformer | None] | None = None
        # Serialize rebuilds so overlapping map/path/history updates don't race
        # on the renderer's drawing state (each rebuild runs in an executor).
        self._rebuild_lock = asyncio.Lock()
        # Rebuild coalescing: callbacks mark the scene dirty and share a single
        # pending rebuild task, so a burst of map/path/history updates (e.g.
        # after a reconnect) costs one extra render, not one per callback.
        self._rebuild_dirty = False
        self._rebuild_task: asyncio.Task[None] | None = None
        self._cached_png: bytes | None = None
        # Bumped on every cache invalidation; a render only publishes its PNG
        # if the generation it started with is still current, so a render that
        # began before a pose update can't repopulate the cache with stale data.
        self._render_generation = 0
        # The map_data dict the last rebuild rendered; identity-compared so
        # map/current/info pushes that leave map_data empty or unchanged
        # (old-firmware pushes) don't trigger pointless full rebuilds.
        self._last_rendered_map_data: dict[str, Any] | None = None
        # Displayed robot source at the last battery evaluation; battery
        # keepalives only invalidate the render when this actually changes.
        self._last_robot_source: str | None = None
        self._last_pose_state_update = 0.0
        self._render_metadata: dict[str, Any] = {}
        self._map_data_logged = False
        self._path_data_logged = False
        self._history_path_data_logged = False

    async def async_added_to_hass(self) -> None:
        """Register hub callbacks once the entity is actually added.

        Registering here instead of in ``__init__`` means a registry-disabled
        entity (the opt-in clean-mode camera) never receives map/path/pose
        pushes and never pays the full supersampled render cost.
        """
        await super().async_added_to_hass()
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower:
            # Hand each unsubscribe to async_on_remove so a removed/disabled
            # camera is deregistered from the hub instead of leaking.
            self.async_on_remove(lawn_mower.register_map_callback(self._on_map_info))
            self.async_on_remove(lawn_mower.register_path_callback(self._on_path_data))
            self.async_on_remove(
                lawn_mower.register_history_path_callback(self._on_history_path_data)
            )
            self.async_on_remove(lawn_mower.register_pose_callback(self._on_pose))
            self.async_on_remove(
                lawn_mower.register_callback(BATTERY_STATUS_DP, self._on_battery_status)
            )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return rendering metadata."""
        attributes = dict(self._render_metadata)
        robot_state = self._get_display_robot_state()
        rendered_layers = list(attributes.get("rendered_layers", []))
        if robot_state["display_pose"] is not None and "robot" not in rendered_layers:
            rendered_layers.append("robot")
        attributes["rendered_layers"] = rendered_layers
        attributes["map_theme"] = self._theme
        attributes["map_language"] = self._language
        attributes["coverage_enabled"] = self._show_coverage
        if self._last_update_label is not None:
            attributes["map_updated_at"] = self._last_update_label
        calibration = self._build_calibration_points()
        if calibration is not None:
            attributes["calibration_points"] = calibration
        attributes["robot_pose_source"] = robot_state["source"]
        attributes["live_pose_valid"] = robot_state["live_pose_valid"]
        attributes["battery_connected"] = robot_state["battery_connected"]
        if robot_state["display_pose"] is not None:
            attributes["display_pose"] = robot_state["display_pose"]
        if self._pose:
            attributes["current_pose"] = {
                "x": self._pose.get("x"),
                "y": self._pose.get("y"),
                "yaw": self._pose.get("yaw"),
                "timestamp_ms": self._pose.get("timestamp_ms"),
                "frame": self._pose.get("frame"),
            }
        return attributes

    def _build_calibration_points(self) -> list[dict[str, dict[str, int]]] | None:
        """Map-coordinate ↔ image-pixel calibration for interactive map cards.

        The format matches the ``calibration_source: camera`` attribute
        convention used by the Lovelace vacuum map cards: three non-collinear
        reference points, each pairing a device coordinate (mm) with the pixel
        it lands on in the rendered PNG.
        """
        snapshot = self._render_snapshot
        if snapshot is None:
            return None
        transformer = snapshot[1]
        if transformer is None or transformer.scale <= 0:
            return None
        left, top, right, bottom = self._map_rect
        padding = 0 if self._clean_mode else MAP_PADDING
        anchors = (
            (left + padding, top + padding),
            (right - padding, top + padding),
            (left + padding, bottom - padding),
        )
        factor = self._output_resolution / IMAGE_WIDTH
        points = []
        for px, py in anchors:
            map_x, map_y = transformer.to_map(px, py)
            points.append(
                {
                    "vacuum": {"x": int(round(map_x)), "y": int(round(map_y))},
                    "map": {"x": int(round(px * factor)), "y": int(round(py * factor))},
                }
            )
        return points

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        # Lazy initial render: if data arrived but no snapshot was built yet
        # (e.g. the entity was just enabled), build it on the first request.
        if self._render_snapshot is None and (
            self._map_data or self._path_data or self._history_path_data
        ):
            await self._async_rebuild()
        return await self.hass.async_add_executor_job(self._render_final_image)

    def _invalidate_png_cache(self) -> None:
        """Drop the cached PNG and retire any in-flight render."""
        self._render_generation += 1
        self._cached_png = None

    async def _async_rebuild(self) -> None:
        """Rebuild the static layers, coalescing concurrent requests.

        Every caller marks the scene dirty and joins the single pending
        rebuild task, which loops while the flag is set; a burst of callbacks
        therefore shares one rebuild plus at most one catch-up pass.
        """
        self._rebuild_dirty = True
        task = self._rebuild_task
        if task is None or task.done():
            task = asyncio.get_running_loop().create_task(self._async_rebuild_loop())
            self._rebuild_task = task
        await task

    async def _async_rebuild_loop(self) -> None:
        """Run rebuilds until the dirty flag stays clear."""
        async with self._rebuild_lock:
            while self._rebuild_dirty:
                self._rebuild_dirty = False
                await self.hass.async_add_executor_job(self._rebuild_static_image)
        self._invalidate_png_cache()
        safe_write_ha_state(self)

    async def _on_map_info(self, map_info: dict[str, Any]) -> None:
        """Callback for map info updates."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower:
            self._map_data = lawn_mower.map_data or {}
        if not self._map_data_logged and self._map_data:
            _LOGGER.debug("ha_map_v1 top-level keys: %s", list(self._map_data.keys()))
            self._map_data_logged = True
        # Old-firmware map/current/info pushes leave map_data empty, and
        # repeated pushes carry the same dict; neither can change the rendered
        # scene, so skip the full rebuild for them.
        if self._map_data is self._last_rendered_map_data or (
            not self._map_data and not self._last_rendered_map_data
        ):
            return
        self._last_rendered_map_data = self._map_data
        await self._async_rebuild()

    async def _on_path_data(self, path_data: dict[str, Any]) -> None:
        """Callback for path data updates."""
        self._path_data = path_data
        if not self._path_data_logged and path_data:
            _LOGGER.debug(
                "ha_path_v1 top-level keys: %s",
                list(path_data.keys()) if isinstance(path_data, dict) else type(path_data),
            )
            self._path_data_logged = True
        await self._async_rebuild()

    async def _on_history_path_data(self, path_data: dict[str, Any]) -> None:
        """Callback for history path data updates."""
        self._history_path_data = path_data
        if not self._history_path_data_logged and path_data:
            _LOGGER.debug(
                "ha_path_v1 history top-level keys: %s",
                list(path_data.keys()) if isinstance(path_data, dict) else type(path_data),
            )
            self._history_path_data_logged = True
        await self._async_rebuild()

    async def _on_pose(self, pose: dict[str, Any]) -> None:
        """Callback for pose updates.

        Pose arrives at ~2 Hz even while the mower sits docked; an unchanged
        pose renders a byte-identical frame, so only a changed one may drop
        the cached PNG (map/battery changes invalidate through their own
        callbacks).
        """
        pose_changed = pose != self._pose
        self._pose = pose
        if pose_changed:
            self._invalidate_png_cache()
        now = time.monotonic()
        if now - self._last_pose_state_update >= 2.0:
            self._last_pose_state_update = now
            safe_write_ha_state(self)

    async def _on_battery_status(self, _payload: str) -> None:
        """Clear the robot layer cache when a battery update changes the pose.

        Battery status arrives as a periodic keepalive; only a change in the
        displayed robot source (live pose vs. dock fallback vs. hidden) can
        alter the rendered image, so unchanged updates keep the cache.
        """
        source = str(self._get_display_robot_state()["source"])
        if source == self._last_robot_source:
            return
        self._last_robot_source = source
        self._invalidate_png_cache()
        safe_write_ha_state(self)

    def _get_battery_connected(self) -> bool | None:
        """Read whether the charger is currently connected."""
        lawn_mower = self.basic_data.lawn_mower
        if lawn_mower is None:
            return None
        battery_status = lawn_mower.battery_status
        if not isinstance(battery_status, dict):
            return None
        connected = battery_status.get("charger_connected")
        if connected is None:
            return None
        return bool(connected)

    def _get_live_robot_pose(self) -> dict[str, Any] | None:
        """Parse the live pose and flag whether it is an all-zero invalid pose."""
        if not isinstance(self._pose, dict) or not self._pose:
            return None
        x = coerce_float(self._pose.get("x"))
        y = coerce_float(self._pose.get("y"))
        raw_yaw = coerce_float(self._pose.get("yaw"))
        if x is None or y is None:
            return None
        return {
            "x": x,
            "y": y,
            "yaw": raw_yaw,
            "is_zero": raw_yaw is not None and x == 0.0 and y == 0.0 and raw_yaw == 0.0,
        }

    def _get_display_robot_state(self) -> dict[str, Any]:
        """Determine the final robot pose to display on the map."""
        battery_connected = self._get_battery_connected()
        live_pose = self._get_live_robot_pose()
        if live_pose is not None and not live_pose["is_zero"]:
            return {
                "source": "live_pose",
                "live_pose_valid": True,
                "battery_connected": battery_connected,
                "display_pose": {
                    "x": live_pose["x"],
                    "y": live_pose["y"],
                    "yaw": coerce_angle_radians(live_pose["yaw"]),
                },
            }

        station_pose = pose_tuple(self._map_data.get("station_pose"))
        if live_pose is not None and live_pose["is_zero"] and battery_connected is True and station_pose is not None:
            station_theta = coerce_angle_radians(station_pose.get("theta"), milli_radian=True)
            robot_yaw = None
            if station_theta is not None:
                robot_yaw = normalize_angle_radians(station_theta + math.pi)
            return {
                "source": "dock_fallback",
                "live_pose_valid": False,
                "battery_connected": battery_connected,
                "display_pose": {
                    "x": station_pose["x"],
                    "y": station_pose["y"],
                    "yaw": robot_yaw,
                },
            }

        return {
            "source": "unavailable",
            "live_pose_valid": False,
            "battery_connected": battery_connected,
            "display_pose": None,
        }

    def _build_scene(self) -> dict[str, Any]:
        """Organize the raw protocol data into a drawable scene."""
        return build_scene(
            self._map_data,
            self._path_data,
            self._history_path_data,
            self._show_coverage,
            cache=self._scene_cache,
        )

    def _rebuild_static_image(self) -> None:
        """Rebuild the static layers."""
        scene = self._build_scene()
        self._render_metadata = build_render_metadata(
            scene, self._map_data, self._path_data, self._history_path_data
        )

        if not self._map_data and not self._path_data and not self._history_path_data:
            self._renderer.reset()
            self._render_snapshot = None
            return

        self._last_update_label = dt_util.now().strftime("%H:%M")
        # The renderer draws every static layer and hands back the finished
        # image paired with the transformer it was drawn with, published as
        # one atomic reference (see _render_final_image).
        self._render_snapshot = self._renderer.render_static(
            scene, self._map_data, self._last_update_label
        )

    def _t(self, key: str) -> str:
        """Return the localized HUD label for a key (English-filled)."""
        return self._renderer._t(key)

    def _render_final_image(self) -> bytes:
        """Render the final image."""
        cached = self._cached_png
        if cached is not None:
            return cached
        # Remember the generation this render is based on; an invalidation
        # (pose/battery/rebuild) while we render bumps it, and the stale
        # result must then not repopulate the cache.
        generation = self._render_generation

        # Read the published (image, transformer) pair once so a rebuild
        # completing mid-render can't leave us drawing the robot with a
        # transformer that doesn't match the copied static image.
        snapshot = self._render_snapshot
        if snapshot is None:
            return self._renderer.placeholder_png()

        result = self._renderer.compose_frame(
            snapshot, self._get_display_robot_state()["display_pose"]
        )
        if generation == self._render_generation:
            self._cached_png = result
        return result


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TerraMowConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize the camera platform."""
    basic_data = config_entry.runtime_data
    resolution = config_entry.options.get(
        CONF_MAP_RESOLUTION, DEFAULT_MAP_RESOLUTION
    )
    if resolution not in MAP_RESOLUTION_OPTIONS:
        resolution = DEFAULT_MAP_RESOLUTION
    theme = config_entry.options.get(CONF_MAP_THEME, DEFAULT_MAP_THEME)
    if theme not in MAP_THEME_OPTIONS:
        theme = DEFAULT_MAP_THEME
    show_coverage = bool(
        config_entry.options.get(CONF_MAP_SHOW_COVERAGE, DEFAULT_MAP_SHOW_COVERAGE)
    )
    async_add_entities(
        [
            TerraMowMapCamera(
                basic_data,
                hass,
                output_resolution=resolution,
                theme=theme,
                show_coverage=show_coverage,
            ),
            TerraMowMapCamera(
                basic_data,
                hass,
                clean_mode=True,
                output_resolution=resolution,
                theme=theme,
                show_coverage=show_coverage,
            ),
        ]
    )
