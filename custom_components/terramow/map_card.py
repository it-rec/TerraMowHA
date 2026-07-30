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

import asyncio
import hashlib
import json
import logging
import math
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

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
from .error_codes import describe_error
from .hub import MOW_COUNT_CELL_MM, WIFI_CELL_MM, TerraMowHub
from .map_render import CUTTING_WIDTH_MM
from .map_scene import (
    ScenePathCache,
    build_scene,
    coerce_angle_radians,
    coverage_ratios_for_zones,
    normalize_angle_radians,
)

_LOGGER = logging.getLogger(__name__)

# Bump when frontend/terramow-map-card.js changes; busts browser caches via
# the ?v= query on the auto-registered resource URL (and re-fires the
# resource-update path on existing installs).
CARD_VERSION = "1.31.0"

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

# The two payload keys that stream as tail-appends; excluded from the
# geometry digest so a growing path is a delta, not a full scene push.
_PATH_KEYS = ("current_path", "history_path")

# Where the digest rides in the scene payload. Present on the wire too — a
# 32-character string the card ignores — so a cached scene replayed to a new
# subscription carries its fingerprint with it.
GEOMETRY_REV_KEY = "geometry_rev"

# Map/path/history pushes can land in a burst (one mowing tick updates all
# three channels); collapse them into a single scene push.
SCENE_PUSH_DEBOUNCE = 0.2
# The per-zone mowed-% is O(edges x zones) and changes slowly; during active
# mowing, recomputing it on every path push dominates CPU. Reuse the last result
# for this long (path + robot still update live) so a viewed card stays cheap.
COVERAGE_RECOMPUTE_INTERVAL = 12.0

# Per-hub caches shared across every card subscription of one mower.
#
# All three are keyed by the hub OBJECT in a WeakKeyDictionary, not by id(hub).
# id() keys leaked: nothing ever removed an entry, so every config-entry reload
# stranded a full scene payload (megabytes on a large lawn) for the lifetime of
# the Home Assistant process. Worse, CPython reuses id() values once an object
# is collected, so a freshly created hub could inherit the previous hub's cached
# scene and make a card paint the wrong map. Weak keys fix both: an entry is
# dropped as soon as its hub is collected, and an object key cannot be aliased.

# Throttles the expensive per-zone coverage math (O(edges x zones)) so that
# re-opening the map dashboard — or viewing it on several devices at once —
# reuses the last computed result instead of recomputing it from scratch.
_HUB_COVERAGE_CACHES: WeakKeyDictionary[TerraMowHub, dict[str, Any]] = (
    WeakKeyDictionary()
)

# Last fully-built scene payload per hub. A fresh subscription (initial load, or
# a mobile view-swipe that recreates the card element) pushes this immediately
# so the card paints the known map at once, instead of blanking to "Waiting for
# mower data…" while the heavy build_scene_payload runs in the executor. The
# background rebuild that follows sends a delta (or a fresh scene) moments later.
_HUB_SCENE_CACHES: WeakKeyDictionary[TerraMowHub, dict[str, Any]] = (
    WeakKeyDictionary()
)

# In-flight scene build per hub. When several cards view the same mower, their
# feeds get the same source callbacks at the same tick and would each run the
# heavy build_scene_payload in the executor — identical work N times over. They
# now share one build task per hub (each feed still emits its own delta), so N
# simultaneous viewers cost one build, not N. The entry holds a finished task
# between builds and is replaced on the next one.
_HUB_BUILD_TASKS: WeakKeyDictionary[TerraMowHub, asyncio.Task[dict[str, Any]]] = (
    WeakKeyDictionary()
)

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


def _path_pts_runs(runs: list[list[dict[str, Any]]]) -> list[list[int]]:
    """Flatten mowing runs into one point list with break sentinels.

    Each run is a contiguous mowing stretch; an empty ``[]`` element separates
    two runs so the card lifts the pen there instead of drawing a straight
    diagonal across the transit leg that was filtered out between them. Keeping
    a single flat list (rather than a list of runs) preserves the tail-append
    delta protocol the card uses to stream a growing path cheaply.
    """
    flat: list[list[int]] = []
    for run in runs:
        if flat:
            flat.append([])  # run break — pen up
        flat.extend(_path_pts(run))
    return flat


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


def _zone_coverage_ratios(scene: dict[str, Any]) -> dict[int, float]:
    """Per-zone mowed fraction from the cycle coverage segments (#197).

    Thin wrapper: the maths lives in map_scene so the card and the per-zone
    sensors cannot drift apart. The scene already carries each zone's
    boundary as tuples, so no re-extraction is needed here.
    """
    zones = [
        (sub["id"], sub["boundary"])
        for region in scene["regions"]
        for sub in region["sub_regions"]
        if sub["id"] is not None
    ]
    return coverage_ratios_for_zones(
        zones, scene["session_path_segments"], CUTTING_WIDTH_MM
    )


def build_scene_payload(
    hub: TerraMowHub,
    coverage_cache: dict[str, Any] | None = None,
    scene_cache: ScenePathCache | None = None,
) -> dict[str, Any]:
    """Serialize the drawable scene for the card.

    ``coverage_cache`` (a per-subscription dict) throttles the expensive
    per-zone coverage math: it is recomputed at most every
    COVERAGE_RECOMPUTE_INTERVAL seconds and otherwise reused, so a card viewed
    during active mowing doesn't recompute it on every path push.

    ``scene_cache`` (a per-subscription :class:`ScenePathCache`) skips
    re-extracting path point lists whose source dict is unchanged — during
    mowing the history path in particular is re-fetched rarely, so every push
    would otherwise re-parse its full O(N) point list.
    """
    map_data = hub.map_data
    scene = build_scene(
        map_data,
        hub.path_data,
        hub.history_path_data,
        False,
        cache=scene_cache,
        # Cycle coverage (superset of the session archive) feeds the
        # existing "mowed area" renderer (issue #202, approach B).
        session_path_segments=hub.coverage_segments,
    )

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
    now = time.monotonic()
    if (
        coverage_cache is not None
        and coverage_cache.get("value") is not None
        and now - coverage_cache.get("time", 0.0) < COVERAGE_RECOMPUTE_INTERVAL
    ):
        zone_coverage = coverage_cache["value"]
    else:
        zone_coverage = _zone_coverage_ratios(scene)
        if coverage_cache is not None:
            coverage_cache["value"] = zone_coverage
            coverage_cache["time"] = now
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
                        # Mowed fraction of this zone in the running cycle
                        # (None until the coverage touches it, issue #197).
                        "coverage": zone_coverage.get(sub["id"]),
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
        "current_path": _path_pts_runs(scene["current_path_runs"]),
        "history_path": _path_pts_runs(scene["history_path_runs"]),
        # Mow tracks from earlier in the running session, archived by the hub
        # across a mid-session recharge dock (issue #214). One polyline per
        # segment so the card never draws a connector across the dock gap.
        "session_paths": [
            _path_pts(segment) for segment in scene["session_path_segments"]
        ],
        # Self-sampled Wi-Fi heatmap (issue #200): coarse grid of the mower's
        # own dp_109 signal %, accumulated by the hub while it drives. None
        # until the first sample exists. Excluded from the delta-detection
        # geometry in _emit_scene (it changes on every mowing tick).
        "wifi_heatmap": (
            {
                "cell_mm": WIFI_CELL_MM,
                "cells": [
                    [gx, gy, int(round(value))]
                    for (gx, gy), value in hub.wifi_map_cells.items()
                ],
            }
            if hub.wifi_map_cells
            else None
        ),
        # Where faults happened (issue #171 follow-up): the pose the mower
        # reported when each error code appeared, merged per spot so repeat
        # offenders read as one marker with a count. None until the first
        # fault is recorded.
        "fault_hotspots": (
            [
                {
                    "x": round(spot["x"], 1),
                    "y": round(spot["y"], 1),
                    "code": spot["code"],
                    "count": spot["count"],
                    "last_seen": spot["last_seen"],
                }
                for spot in hub.fault_hotspots
            ]
            or None
        ),
        # Season heatmap: how many finished cycles reached each cell. Stacking
        # cycles is what makes a patch the mower keeps skipping visible — any
        # single cycle looks fine. None until a cycle has finished. Rides the
        # geometry channel on purpose: unlike the Wi-Fi grid it changes only
        # at the end of a cycle, so a full push then costs nothing.
        "mow_counts": (
            {
                "cell_mm": MOW_COUNT_CELL_MM,
                "max": max(hub.mow_counts.values()),
                "cells": [
                    [gx, gy, count] for (gx, gy), count in hub.mow_counts.items()
                ],
            }
            if hub.mow_counts
            else None
        ),
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
    # Computed last, over everything above it, so _emit_scene can compare a
    # string instead of deep-walking the geometry on the event loop.
    payload[GEOMETRY_REV_KEY] = _geometry_digest(payload)
    return payload


def _geometry_digest(payload: dict[str, Any]) -> str:
    """Fingerprint the payload's non-path, non-heatmap content.

    ``_emit_scene`` decides between a full scene push and a tail-append delta
    by asking whether anything outside the two path lists and the Wi-Fi heatmap
    changed. That used to be a deep equality check over the whole geometry —
    every polygon of every zone — run on the event loop, once per subscribed
    feed, on every scene build.

    Computing one digest here instead moves that walk into the executor build
    (where the payload is assembled anyway) and shares it across every feed of
    the hub, leaving each feed a string comparison.
    """
    geometry = {
        key: value
        for key, value in payload.items()
        if key not in _PATH_KEYS and key != "wifi_heatmap"
    }
    encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(encoded.encode(), digest_size=16).hexdigest()


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
    outcome = hub.session_outcome
    if isinstance(work_data, dict) and work_data:
        if outcome == "completed":
            # Session over: show the completion, not the stale counters —
            # mirrors the session sensors' snap/reset (issues #204/#207).
            work["progress"] = 100.0
        elif outcome is None:
            total_area = work_data.get("total_area") or 0
            clean_area = work_data.get("clean_area") or 0
            if total_area > 0:
                work["progress"] = round(
                    min(100.0 * clean_area / total_area, 100.0), 1
                )
            if clean_area:
                # clean_area is in units of 0.1 m²
                work["area_m2"] = round(float(clean_area) / 10, 1)
            if work_data.get("work_duration") is not None:
                work["duration_s"] = work_data.get("work_duration")
        # aborted: no job chip — the counters reset with the session sensors

    # Mission info for the HUD (issue #205): raw enum values, only the
    # non-idle ones (the card prettifies them). Uses the decayed display_*
    # so a stale SAVING_MAP/RUNNING doesn't linger (issue #142).
    status: dict[str, Any] = {}
    if hub.mission.value != "MISSION_IDLE":
        status["mission"] = hub.mission.value
    if hub.display_sub_mission.value != "SUB_MISSION_IDLE":
        status["sub_mission"] = hub.display_sub_mission.value
    if hub.display_mission_state.value != "MISSION_STATE_IDLE":
        status["state"] = hub.display_mission_state.value
    reason = hub.back_to_station_reason
    if reason and reason != "BACK_TO_STATION_REASON_NONE":
        status["back_to_station_reason"] = reason

    # Active faults (dp_116) with readable text, so the card can surface the
    # error on the map itself instead of only in the Active-errors sensor
    # (issue #171). Empty when there's no fault.
    errors = [
        {"code": code, "text": describe_error(code)}
        for code in hub.active_error_codes
    ]

    return {
        "battery": battery or None,
        "work": work or None,
        "status": status or None,
        "errors": errors or None,
        "preflight": hub.mission_preflight_catalog,
    }


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
        # Digest of the last pushed geometry (see GEOMETRY_REV_KEY) rather than
        # the geometry itself: comparing it is a string compare instead of a
        # deep walk of every polygon on the event loop.
        self._last_geometry_rev: str | None = None
        self._last_paths: dict[str, list[list[int]]] = {}
        self._last_wifi: dict[str, Any] | None = None
        # Last robot/status event pushed, so unchanged repeats are dropped.
        self._last_robot_event: dict[str, Any] | None = None
        # Scene building is CPU-heavy (polygon coverage math); it runs in an
        # executor thread. These coalesce overlapping rebuilds so a burst of
        # source callbacks never stacks up more than one pending build.
        self._build_task: asyncio.Task[None] | None = None
        self._rebuild_pending = False
        # Throttles the expensive per-zone coverage recompute across pushes, and
        # is shared per hub so re-opening the card (or another device viewing it)
        # reuses the last result instead of recomputing it from scratch.
        self._coverage_cache = _HUB_COVERAGE_CACHES.setdefault(hub, {})
        # Reuse path point extraction across pushes: the history path source is
        # re-fetched rarely, so re-parsing its full point list on every mowing
        # tick is wasted work (identity-keyed, so a new source dict re-parses).
        self._scene_cache = ScenePathCache()

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
            self.hub.register_callback(152, self._on_pose),
            self.hub.register_callback(155, self._on_pose),
        ]
        # Paint instantly from the last known scene (if any card has rendered
        # this hub before), then schedule the authoritative rebuild which sends
        # a delta or a fresh scene once it completes.
        cached = _HUB_SCENE_CACHES.get(self.hub)
        if cached is not None:
            self._emit_scene(cached)
        self._schedule_scene_build()
        self._push_robot()

    @callback
    def stop(self) -> None:
        """Tear the subscription down."""
        if self._scene_timer is not None:
            self._scene_timer.cancel()
            self._scene_timer = None
        if self._build_task is not None:
            self._build_task.cancel()
            self._build_task = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    # Hub callbacks arrive on the event loop; path/history callbacks must be
    # coroutine functions (the hub wraps them in async_create_task).
    async def _on_scene_source(self, _data: Any) -> None:
        if self._scene_timer is not None:
            self._scene_timer.cancel()
        self._scene_timer = self.hass.loop.call_later(
            SCENE_PUSH_DEBOUNCE, self._schedule_scene_build
        )

    async def _on_pose(self, _data: Any) -> None:
        self._push_robot()

    @callback
    def _schedule_scene_build(self) -> None:
        # Debounce fired: start a build unless one is already running, in which
        # case just flag that another is needed once it finishes. Coalescing
        # keeps a storm of map/path callbacks from stacking up 3-5 s builds.
        self._scene_timer = None
        if self._build_task is not None and not self._build_task.done():
            self._rebuild_pending = True
            return
        self._build_task = self.hass.async_create_task(self._build_and_push())

    async def _build_and_push(self) -> None:
        try:
            while True:
                self._rebuild_pending = False
                try:
                    payload = await self._shared_scene_build()
                except Exception:  # pragma: no cover - defensive
                    _LOGGER.exception("Failed to build map card scene")
                    return
                self._emit_scene(payload)
                if not self._rebuild_pending:
                    return
        finally:
            self._build_task = None

    async def _shared_scene_build(self) -> dict[str, Any]:
        """Await one build shared across every feed of this hub.

        The first feed to ask starts the executor build; feeds that ask while
        it is running await the same task instead of launching their own. Each
        still emits its own delta from the shared payload.
        """
        task = _HUB_BUILD_TASKS.get(self.hub)
        if task is None or task.done():
            task = self.hass.async_create_task(self._run_scene_build())
            _HUB_BUILD_TASKS[self.hub] = task
        return await task

    async def _run_scene_build(self) -> dict[str, Any]:
        # The heavy polygon / zone-coverage math runs off the event loop so the
        # WebSocket + HTTP stack stays responsive.
        payload = await self.hass.async_add_executor_job(
            build_scene_payload,
            self.hub,
            self._coverage_cache,
            self._scene_cache,
        )
        # Remember the freshest full scene so the next subscription can paint it
        # immediately (see start()).
        _HUB_SCENE_CACHES[self.hub] = payload
        return payload

    @callback
    def _emit_scene(self, payload: dict[str, Any]) -> None:
        # Delta detection: during mowing the only thing that usually changes
        # is the path growing at the tail. Sending just the appended points
        # keeps the per-update payload tiny on large lawns.
        paths = {key: payload[key] for key in _PATH_KEYS}
        # The Wi-Fi heatmap changes on nearly every mowing tick, so it rides
        # its own delta channel (like the paths) — including it in the
        # geometry comparison would turn every append push into a full scene.
        wifi = payload.get("wifi_heatmap")
        # The digest was computed once, in the executor, over exactly the keys
        # excluded here; comparing it beats deep-walking the geometry per feed
        # on the event loop (see _geometry_digest).
        geometry_rev = payload[GEOMETRY_REV_KEY]
        if self._last_geometry_rev == geometry_rev:
            appends: dict[str, Any] = {}
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
                if wifi != self._last_wifi:
                    # Small payload (a few hundred triplets), sent whole.
                    appends["wifi_heatmap"] = wifi
                    self._last_wifi = wifi
                if any(value for value in appends.values()):
                    self.connection.send_message(
                        event_message(
                            self.msg_id, {"type": "paths_append", **appends}
                        )
                    )
                return  # nothing changed at all — push nothing

        self._last_geometry_rev = geometry_rev
        self._last_paths = paths
        self._last_wifi = wifi
        self.connection.send_message(
            event_message(self.msg_id, {"type": "scene", "scene": payload})
        )

    @callback
    def _push_robot(self) -> None:
        """Push the robot pose and HUD chips, skipping unchanged repeats.

        The sources behind this event — the realtime pose plus dp_108/8/113 —
        report on their own schedule regardless of whether anything moved: the
        pose arrives at ~2 Hz even while the mower sits docked. Sending the
        resulting event unconditionally meant every open card received two
        WebSocket messages a second forever, each re-rendering the same pose
        and the same chips. Only a changed event is worth a push; the camera
        entity has always gated its pose handling the same way.
        """
        event = {
            "type": "robot",
            "robot": build_robot_payload(self.hub),
            **build_status_payload(self.hub),
        }
        if event == self._last_robot_event:
            return
        self._last_robot_event = event
        self.connection.send_message(event_message(self.msg_id, event))


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
