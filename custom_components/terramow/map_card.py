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
from .map_scene import build_scene, coerce_angle_radians, normalize_angle_radians

_LOGGER = logging.getLogger(__name__)

# Bump when frontend/terramow-map-card.js changes; busts browser caches via
# the ?v= query on the auto-registered resource URL.
CARD_VERSION = "1.0.2"

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

    # res_type "js" on purpose: a module resource is deferred and executes
    # only after the dashboard has rendered, so the element is not defined
    # when the card is built ("Configuration error"); a classic script runs
    # before the render. The card file is written to work in both goals.
    url = f"{CARD_URL_PATH}?v={CARD_VERSION}"
    for item in resources.async_items():
        item_url = str(item.get("url", ""))
        if item_url.partition("?")[0] != CARD_URL_PATH:
            continue
        if item_url != url or item.get("type") != "js":
            # Stale cache-buster from an older version, or a broken deferred
            # "module" entry from <= 1.0.1 — self-heal in place.
            await resources.async_update_item(
                item["id"], {"res_type": "js", "url": url}
            )
            _LOGGER.info("Updated the map card Lovelace resource to %s", url)
        return
    await resources.async_create_item({"res_type": "js", "url": url})
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

    bounds: list[int] | None = None
    all_points = scene["all_points"]
    if all_points:
        xs = [point[0] for point in all_points]
        ys = [point[1] for point in all_points]
        bounds = [
            int(math.floor(min(xs))),
            int(math.floor(min(ys))),
            int(math.ceil(max(xs))),
            int(math.ceil(max(ys))),
        ]

    return {
        "map_id": map_data.get("id"),
        "map_name": map_data.get("name"),
        "map_state": map_data.get("map_state"),
        "total_area": map_data.get("total_area"),
        "map_extent": _poly(scene["map_extent"]),
        "bounds": bounds,
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

    @callback
    def start(self) -> None:
        """Register hub callbacks and push the initial snapshot."""
        self._unsubs = [
            self.hub.register_map_callback(self._on_scene_source),
            self.hub.register_path_callback(self._on_scene_source),
            self.hub.register_history_path_callback(self._on_scene_source),
            self.hub.register_pose_callback(self._on_pose),
            # dp_108 charger state feeds the docked fallback pose
            self.hub.register_callback(108, self._on_pose),
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
        self.connection.send_message(
            event_message(
                self.msg_id, {"type": "scene", "scene": payload}
            )
        )

    @callback
    def _push_robot(self) -> None:
        self.connection.send_message(
            event_message(
                self.msg_id, {"type": "robot", "robot": build_robot_payload(self.hub)}
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
