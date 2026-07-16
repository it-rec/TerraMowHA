"""Live map data feed and Lovelace card registration.

Backend half of the interactive map card (``frontend/terramow-map-card.js``):

- serves the card module over HTTP and auto-loads it on every dashboard via
  ``frontend.add_extra_js_url`` (no manual Lovelace resource needed),
- exposes a ``terramow/map/subscribe`` WebSocket command that pushes the
  structured map scene (regions, zones, forbidden areas, paths, station) and
  the live robot pose to subscribed cards.

The scene payload is built from the same :func:`map_scene.build_scene`
geometry the PNG camera renders, so the card and the camera always agree;
coordinates stay in the device's millimetre frame and the card does the
world-to-screen transform client-side (pan/zoom without re-fetching).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.components.websocket_api.messages import event_message
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .hub import TerraMowHub
from .map_render import CUTTING_WIDTH_MM
from .map_scene import build_scene, coerce_angle_radians, normalize_angle_radians

_LOGGER = logging.getLogger(__name__)

# Bump when frontend/terramow-map-card.js changes; busts browser caches via
# the ?v= query on the auto-registered resource URL (and re-fires the
# resource-update path on existing installs).
CARD_VERSION = "1.13.0"

# Register the card as a classic "js" resource, NOT an ES "module". A classic
# <script> re-executes on every page load -- even when the file is served from
# the browser cache -- so the custom element is reliably defined before the
# dashboard first renders. An ES "module" served from cache is NOT re-executed
# (the browser keeps its first evaluation in the module map), so on a cold or
# cached load the element can stay undefined and Home Assistant shows a
# permanent "Configuration error" -- the intermittent failure in issue #140.
# "js" is deprecated-but-functional on current Home Assistant and is the only
# type that loads reliably on both HA 2026.6 and 2026.7+.
CARD_RESOURCE_TYPE = "js"

CARD_URL_PATH = "/terramow-frontend/terramow-map-card.js"

WS_SUBSCRIBE_MAP = "terramow/map/subscribe"

# Map/path/history pushes can land in a burst (one mowing tick updates all
# three channels); collapse them into a single scene push.
SCENE_PUSH_DEBOUNCE = 0.2

_DATA_SETUP_DONE = f"{DOMAIN}_map_card_setup"


async def async_setup_map_card(hass: HomeAssistant) -> None:
    """Register the card resources and WebSocket API (idempotent)."""
    if hass.data.get(_DATA_SETUP_DONE):
        return
    hass.data[_DATA_SETUP_DONE] = True

    js_path = Path(__file__).parent / "frontend" / "terramow-map-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, str(js_path), cache_headers=True)]
    )
    # frontend is an after_dependency: always loaded on a real install
    # (default_config), absent in headless/test setups — then the card can
    # still be added manually as a Lovelace resource.
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, f"{CARD_URL_PATH}?v={CARD_VERSION}")
    await _async_try_register_lovelace_resource(hass)

    websocket_api.async_register_command(hass, ws_subscribe_map)


async def _async_try_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register the Lovelace resource, logging instead of raising."""
    try:
        await _async_register_lovelace_resource(hass)
    except Exception as err:  # never let a Lovelace API change break setup
        _LOGGER.warning("Could not register the map card Lovelace resource: %s", err)


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Ensure the card is registered as a Lovelace resource (storage mode).

    The extra-module list only reaches the browser through the app shell,
    which Home Assistant's service worker caches aggressively — right after
    installing the integration the card would stay unknown until a hard
    refresh. Lovelace resources are imported dynamically when a dashboard
    loads, so registering one (the same mechanism HACS uses for frontend
    plugins) makes the card available reliably. Duck-typed via ``hass.data``
    on purpose: no import of lovelace internals, and YAML resource mode
    (read-only collection) is skipped silently.
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None and not hass.is_running:
        # Config-entry setup can beat lovelace during a cold boot; retry once
        # everything is up instead of silently never registering.
        async def _register_when_started(_event: Event) -> None:
            await _async_try_register_lovelace_resource(hass)

        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, _register_when_started
        )
        return
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):  # pre-2024.8 layout
        resources = lovelace.get("resources")
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.debug(
            "Lovelace storage-mode resources unavailable (yaml mode or no "
            "lovelace); the card stays available via the extra-module list "
            "or a manual resource"
        )
        return
    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True

    # See CARD_RESOURCE_TYPE for why "js" (not "module").
    url = f"{CARD_URL_PATH}?v={CARD_VERSION}"
    for item in resources.async_items():
        item_url = str(item.get("url", ""))
        if item_url.partition("?")[0] != CARD_URL_PATH:
            continue
        if item_url != url or item.get("type") != CARD_RESOURCE_TYPE:
            # Stale cache-buster from an older version, or a "module" entry
            # from <= 1.19.x (unreliable from browser cache, issue #140) —
            # self-heal in place.
            await resources.async_update_item(
                item["id"], {"res_type": CARD_RESOURCE_TYPE, "url": url}
            )
            _LOGGER.info("Updated the map card Lovelace resource to %s", url)
        return
    await resources.async_create_item(
        {"res_type": CARD_RESOURCE_TYPE, "url": url}
    )
    _LOGGER.info("Registered the map card Lovelace resource %s", url)


def _pt(point: tuple[float, float]) -> list[int]:
    """Compact a millimetre point for JSON transport."""
    return [int(round(point[0])), int(round(point[1]))]


def _poly(points: list[tuple[float, float]]) -> list[list[int]]:
    return [_pt(point) for point in points]


def _polys(polygons: list[list[tuple[float, float]]]) -> list[list[list[int]]]:
    return [_poly(polygon) for polygon in polygons]


def _path_pts(points: list[dict[str, Any]]) -> list[list[int]]:
    return [[int(round(point["x"])), int(round(point["y"]))] for point in points]


def _direction_angle_from_config(config: Any) -> Any:
    """Resolve the effective stripe angle from a main_direction_angle_config.

    In SINGLE mode the configured ``single_mode_config.angle`` is the truth;
    the device's ``current_angle`` goes stale there (observed reporting 90
    while the configured angle was 180/-90). Other modes rotate through
    angles, so ``current_angle`` is the live value.
    """
    if not isinstance(config, dict):
        return None
    if config.get("mode") == "MAIN_DIRECTION_MODE_SINGLE":
        single = config.get("single_mode_config")
        if isinstance(single, dict) and single.get("angle") is not None:
            return single.get("angle")
    return config.get("current_angle")


def _main_direction_angle(map_data: dict[str, Any]) -> Any:
    """The global mowing-stripe direction in degrees, or None.

    Read defensively from the raw map data (``mow_param`` blocks may be
    missing or malformed while the device is still reporting).
    """
    mow_param = map_data.get("mow_param")
    if not isinstance(mow_param, dict):
        return None
    global_param = mow_param.get("global_param")
    if not isinstance(global_param, dict):
        return None
    return _direction_angle_from_config(
        global_param.get("main_direction_angle_config")
    )


# The per-zone mow settings surfaced in the card's zone-info panel; the same
# fields exist on the global param block and act as the fallback.
_ZONE_SETTING_FIELDS = (
    "mow_height",
    "mow_speed",
    "mow_spacing",
    "blade_disk_speed",
    "edge_cutting_distance",
)


def _zone_settings(map_data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Per-zone mow settings from the custom region params, keyed by zone id."""
    mow_param = map_data.get("mow_param")
    if not isinstance(mow_param, dict):
        return {}
    settings: dict[int, dict[str, Any]] = {}
    for item in mow_param.get("regions") or []:
        if not isinstance(item, dict):
            continue
        zone_id = item.get("id")
        param = item.get("region_param")
        if isinstance(zone_id, int) and isinstance(param, dict):
            settings[zone_id] = {
                key: param.get(key) for key in _ZONE_SETTING_FIELDS
            }
    return settings


def _global_settings(map_data: dict[str, Any]) -> dict[str, Any] | None:
    """The global mow settings block, or None while unreported/malformed."""
    mow_param = map_data.get("mow_param")
    if not isinstance(mow_param, dict):
        return None
    global_param = mow_param.get("global_param")
    if not isinstance(global_param, dict):
        return None
    return {key: global_param.get(key) for key in _ZONE_SETTING_FIELDS}


def _zone_direction_angles(map_data: dict[str, Any]) -> dict[int, Any]:
    """Per-zone stripe angles from the custom region params, keyed by zone id.

    Zones with custom parameters override the global direction (the map's
    ``mow_param.regions`` entries); zones without stay on the global angle.
    """
    mow_param = map_data.get("mow_param")
    if not isinstance(mow_param, dict):
        return {}
    angles: dict[int, Any] = {}
    for item in mow_param.get("regions") or []:
        if not isinstance(item, dict):
            continue
        zone_id = item.get("id")
        param = item.get("region_param")
        angle = _direction_angle_from_config(
            param.get("main_direction_angle_config")
            if isinstance(param, dict)
            else None
        )
        if isinstance(zone_id, int) and angle is not None:
            angles[zone_id] = angle
    return angles


def build_scene_payload(hub: TerraMowHub) -> dict[str, Any]:
    """Serialize the drawable scene for the card."""
    map_data = hub.map_data
    scene = build_scene(map_data, hub.path_data, hub.history_path_data, False)

    station: dict[str, Any] | None = None
    station_pose = scene["station_pose"]
    if station_pose is not None:
        station = {
            "x": int(round(station_pose["x"])),
            "y": int(round(station_pose["y"])),
            # station_pose.theta is milli-radians on the wire
            "theta": coerce_angle_radians(station_pose["theta"], milli_radian=True),
        }

    zone_angles = _zone_direction_angles(map_data)
    zone_settings = _zone_settings(map_data)
    regions: list[dict[str, Any]] = []
    for region in scene["regions"]:
        regions.append(
            {
                "id": region["id"],
                "name": region["name"],
                "boundary": _poly(region["boundary"]),
                "edge_lines": _polys(region["edge_lines"]),
                "sub_regions": [
                    {
                        "id": sub["id"],
                        "name": sub["name"],
                        "boundary": _poly(sub["boundary"]),
                        "center": _pt(sub["center"]) if sub["center"] else None,
                        "selected": sub["selected"],
                        "order": sub["order"],
                        "inner_boundaries": _polys(sub["inner_boundaries"]),
                        # Zone-specific stripe direction (custom params); the
                        # card falls back to the global main_direction_angle.
                        "direction_angle": zone_angles.get(sub["id"]),
                        # Zone-specific mow settings for the zone-info panel;
                        # None -> the zone runs on the global mow_params.
                        "params": zone_settings.get(sub["id"]),
                    }
                    for sub in region["sub_regions"]
                ],
            }
        )

    tunnels: list[dict[str, Any]] = []
    for key in ("cross_boundary_tunnels", "virtual_cross_boundary_tunnels"):
        for tunnel in scene[key]:
            tunnels.append(
                {
                    "polygons": _polys(tunnel["polygons"]),
                    "polylines": _polys(tunnel["polylines"]),
                }
            )

    payload: dict[str, Any] = {
        "map_id": map_data.get("id"),
        # Fall back to "Map #<id>" for unnamed maps, mirroring the PNG camera,
        # so the card's map/area chip still renders (else an empty name hides
        # the whole chip, area included).
        "map_name": (
            map_data.get("name")
            or (
                f"Map #{map_data['id']}"
                if map_data.get("id") is not None
                else None
            )
        ),
        "map_state": map_data.get("map_state"),
        "total_area": map_data.get("total_area"),
        # True when the reported path belongs to a different map than the one
        # being drawn (paths were dropped): the card shows a "map refreshing"
        # chip so the momentarily missing path isn't mistaken for a bug.
        "path_map_mismatch": scene["path_map_mismatch"],
        "cutting_width": CUTTING_WIDTH_MM,
        # Configured mowing-stripe direction in degrees (None when the device
        # has not reported mow params yet); the card draws it as a lane arrow.
        "main_direction_angle": _main_direction_angle(map_data),
        # Global mow settings; zones without custom params inherit these.
        "mow_params": _global_settings(map_data),
        "map_extent": _poly(scene["map_extent"]),
        "station": station,
        "regions": regions,
        "forbidden_zones": _polys(scene["forbidden_zones"]),
        "physical_forbidden_zones": _polys(scene["physical_forbidden_zones"]),
        "pass_through_zones": _polys(scene["pass_through_zones"]),
        "required_zones": _polys(scene["required_zones"]),
        "obstacles": _polys(scene["obstacles"]),
        "virtual_walls": _polys(scene["virtual_walls"]),
        "tunnels": tunnels,
        "draw_regions": _polys(scene["draw_region_polygons"]),
        "move_target": (
            _pt(scene["move_target_point"]) if scene["move_target_point"] else None
        ),
        "markers": {
            "cross_boundary": _poly(scene["cross_boundary_markers"]),
            "trapped": _poly(scene["trapped_points"]),
            "maintenance": _poly(scene["maintenance_points"]),
        },
        "current_path": _path_pts(scene["current_path_points"]),
        "history_path": _path_pts(scene["history_path_points"]),
    }
    # Bounds over the static geometry only — NOT the paths. A growing path
    # would otherwise shift the bounds on every mowing tick, defeating both
    # the paths_append delta and a stable fit-to-view on the card.
    payload["bounds"] = _geometry_bounds(payload, include_extent=True)
    # Tighter bounds over the drawn content only, excluding map_extent (the
    # full scanned occupancy grid, which the card never draws). Fitting the
    # view to this fills the card with the lawn instead of padding it out to
    # an invisible rectangle. Falls back to the full bounds when the scene
    # has nothing but the extent yet.
    payload["content_bounds"] = (
        _geometry_bounds(payload, include_extent=False) or payload["bounds"]
    )
    return payload


def _geometry_bounds(
    payload: dict[str, Any], *, include_extent: bool
) -> list[int] | None:
    """Bounding box [minx, miny, maxx, maxy] of the payload's geometry."""
    points = list(_iter_geometry_points(payload, include_extent=include_extent))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _iter_geometry_points(
    payload: dict[str, Any], *, include_extent: bool
) -> Iterator[list[int]]:
    """Yield every static-geometry point of a scene payload."""
    if include_extent:
        yield from payload["map_extent"]
    for region in payload["regions"]:
        yield from region["boundary"]
        for line in region["edge_lines"]:
            yield from line
        for sub in region["sub_regions"]:
            yield from sub["boundary"]
            if sub["center"]:
                yield sub["center"]
            for hole in sub["inner_boundaries"]:
                yield from hole
    for key in (
        "forbidden_zones",
        "physical_forbidden_zones",
        "pass_through_zones",
        "required_zones",
        "obstacles",
        "draw_regions",
    ):
        for polygon in payload[key]:
            yield from polygon
    for line in payload["virtual_walls"]:
        yield from line
    for tunnel in payload["tunnels"]:
        for polygon in tunnel["polygons"]:
            yield from polygon
        for line in tunnel["polylines"]:
            yield from line
    for marker_points in payload["markers"].values():
        yield from marker_points
    if payload["move_target"]:
        yield payload["move_target"]
    if payload["station"]:
        yield [payload["station"]["x"], payload["station"]["y"]]


def build_robot_payload(hub: TerraMowHub) -> dict[str, Any] | None:
    """Determine the robot pose to display (mirrors the camera's logic).

    A live pose wins unless it is the all-zero invalid pose; a charging
    robot with no live pose sits docked at the station, nose outward.
    """
    pose = hub.pose
    x = pose.get("x") if isinstance(pose, dict) else None
    y = pose.get("y") if isinstance(pose, dict) else None
    yaw = pose.get("yaw") if isinstance(pose, dict) else None
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        is_zero = x == 0.0 and y == 0.0 and yaw == 0.0
        if not is_zero:
            return {
                "x": float(x),
                "y": float(y),
                "yaw": coerce_angle_radians(yaw),
                "source": "live_pose",
            }

    battery_status = hub.battery_status
    charger_connected = (
        bool(battery_status.get("charger_connected"))
        if isinstance(battery_status, dict)
        else False
    )
    station_pose = hub.map_data.get("station_pose")
    if charger_connected and isinstance(station_pose, dict):
        sx = station_pose.get("x")
        sy = station_pose.get("y")
        if isinstance(sx, (int, float)) and isinstance(sy, (int, float)):
            theta = coerce_angle_radians(
                station_pose.get("theta"), milli_radian=True
            )
            return {
                "x": float(sx),
                "y": float(sy),
                "yaw": (
                    normalize_angle_radians(theta + math.pi)
                    if theta is not None
                    else None
                ),
                "source": "dock_fallback",
            }
    return None


def build_status_payload(hub: TerraMowHub) -> dict[str, Any]:
    """Battery and current-job status for the card's HUD chips."""
    battery: dict[str, Any] = {}
    if hub.battery_level is not None:
        battery["level"] = hub.battery_level
    battery_status = hub.battery_status
    if isinstance(battery_status, dict) and "charger_connected" in battery_status:
        battery["charging"] = bool(battery_status.get("charger_connected"))

    work: dict[str, Any] = {}
    work_data = hub.current_work_data
    if isinstance(work_data, dict) and work_data:
        total_area = work_data.get("total_area") or 0
        clean_area = work_data.get("clean_area") or 0
        if total_area > 0:
            work["progress"] = round(min(100.0 * clean_area / total_area, 100.0), 1)
        if clean_area:
            # clean_area is in units of 0.1 m²
            work["area_m2"] = round(float(clean_area) / 10, 1)
        if work_data.get("work_duration") is not None:
            work["duration_s"] = work_data.get("work_duration")

    return {"battery": battery or None, "work": work or None}


def _resolve_hub(hass: HomeAssistant, entity_id: str) -> TerraMowHub | None:
    """Find the hub owning ``entity_id`` (any TerraMow entity works)."""
    registry = er.async_get(hass)
    reg_entry = registry.async_get(entity_id)
    if (
        reg_entry is None
        or reg_entry.platform != DOMAIN
        or reg_entry.config_entry_id is None
    ):
        return None
    config_entry = hass.config_entries.async_get_entry(reg_entry.config_entry_id)
    basic_data = getattr(config_entry, "runtime_data", None)
    if basic_data is None:
        return None
    hub: TerraMowHub | None = basic_data.lawn_mower
    return hub


class _MapFeed:
    """One card subscription: hub callbacks in, WebSocket events out."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: ActiveConnection,
        msg_id: int,
        hub: TerraMowHub,
    ) -> None:
        self.hass = hass
        self.connection = connection
        self.msg_id = msg_id
        self.hub = hub
        self._unsubs: list[Any] = []
        self._scene_timer: Any | None = None
        # Last pushed scene, split for delta detection: everything except the
        # two path lists, and the path lists themselves.
        self._last_geometry: dict[str, Any] | None = None
        self._last_paths: dict[str, list[list[int]]] = {}

    @callback
    def start(self) -> None:
        """Register hub callbacks and push the initial snapshot."""
        self._unsubs = [
            self.hub.register_map_callback(self._on_scene_source),
            self.hub.register_path_callback(self._on_scene_source),
            self.hub.register_history_path_callback(self._on_scene_source),
            self.hub.register_pose_callback(self._on_pose),
            # dp_108 charger state feeds the docked fallback pose and the
            # battery chip; dp_8 the battery level; dp_113 the job progress
            self.hub.register_callback(108, self._on_pose),
            self.hub.register_callback(8, self._on_pose),
            self.hub.register_callback(113, self._on_pose),
        ]
        self._push_scene()
        self._push_robot()

    @callback
    def stop(self) -> None:
        """Tear the subscription down."""
        if self._scene_timer is not None:
            self._scene_timer.cancel()
            self._scene_timer = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    # Hub callbacks arrive on the event loop; path/history callbacks must be
    # coroutine functions (the hub wraps them in async_create_task).
    async def _on_scene_source(self, _data: Any) -> None:
        if self._scene_timer is not None:
            self._scene_timer.cancel()
        self._scene_timer = self.hass.loop.call_later(
            SCENE_PUSH_DEBOUNCE, self._push_scene
        )

    async def _on_pose(self, _data: Any) -> None:
        self._push_robot()

    @callback
    def _push_scene(self) -> None:
        self._scene_timer = None
        try:
            payload = build_scene_payload(self.hub)
        except Exception:  # pragma: no cover - defensive
            _LOGGER.exception("Failed to build map card scene")
            return

        # Delta detection: during mowing the only thing that usually changes
        # is the path growing at the tail. Sending just the appended points
        # keeps the per-update payload tiny on large lawns.
        paths = {
            "current_path": payload["current_path"],
            "history_path": payload["history_path"],
        }
        geometry = {
            key: value for key, value in payload.items() if key not in paths
        }
        if self._last_geometry == geometry:
            appends: dict[str, list[list[int]]] = {}
            is_delta = True
            for key, new_points in paths.items():
                old_points = self._last_paths.get(key, [])
                if (
                    len(new_points) >= len(old_points)
                    and new_points[: len(old_points)] == old_points
                ):
                    appends[f"{key}_append"] = new_points[len(old_points) :]
                else:  # path reset/rewritten — fall back to a full scene
                    is_delta = False
                    break
            if is_delta:
                self._last_paths = paths
                if any(appends.values()):
                    self.connection.send_message(
                        event_message(
                            self.msg_id, {"type": "paths_append", **appends}
                        )
                    )
                return  # nothing changed at all — push nothing

        self._last_geometry = geometry
        self._last_paths = paths
        self.connection.send_message(
            event_message(self.msg_id, {"type": "scene", "scene": payload})
        )

    @callback
    def _push_robot(self) -> None:
        self.connection.send_message(
            event_message(
                self.msg_id,
                {
                    "type": "robot",
                    "robot": build_robot_payload(self.hub),
                    **build_status_payload(self.hub),
                },
            )
        )


@websocket_command(
    {
        vol.Required("type"): WS_SUBSCRIBE_MAP,
        vol.Required("entity_id"): cv.entity_id,
    }
)
@callback
def ws_subscribe_map(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe a map card to live scene and robot pose updates."""
    hub = _resolve_hub(hass, msg["entity_id"])
    if hub is None:
        connection.send_error(
            msg["id"],
            ERR_NOT_FOUND,
            f"No TerraMow device for entity {msg['entity_id']}",
        )
        return

    feed = _MapFeed(hass, connection, msg["id"], hub)
    connection.subscriptions[msg["id"]] = feed.stop
    connection.send_result(msg["id"])
    feed.start()
