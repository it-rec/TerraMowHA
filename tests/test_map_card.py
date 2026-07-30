"""Tests for the interactive map card backend (``map_card.py``).

Covers the global setup (static card resource + WebSocket command
registration), the ``terramow/map/subscribe`` feed (initial snapshot,
debounced scene pushes, live/docked robot pose events, error paths) and
the payload builders.
"""

from __future__ import annotations

import asyncio
import gc
import json
import math
import weakref
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import map_card
from custom_components.terramow.const import CONF_SERIAL, DOMAIN, POSE_TOPIC
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.map_card import (
    CARD_URL_PATH,
    WS_SUBSCRIBE_MAP,
    build_robot_payload,
    build_scene_payload,
    build_status_payload,
)


@pytest.fixture(autouse=True)
def _clear_hub_caches() -> Any:
    """Reset the module-level per-hub caches between tests.

    The caches are weak-keyed, so a collected hub drops its entry on its own;
    this only keeps tests deterministic while a test still holds its hub alive
    in a local variable."""
    map_card._HUB_SCENE_CACHES.clear()
    map_card._HUB_COVERAGE_CACHES.clear()
    map_card._HUB_BUILD_TASKS.clear()
    yield
    map_card._HUB_SCENE_CACHES.clear()
    map_card._HUB_COVERAGE_CACHES.clear()
    map_card._HUB_BUILD_TASKS.clear()


HOST = "192.0.2.10"
SERIAL = "MP511MAP01"

MAP_DATA: dict[str, Any] = {
    "id": 1,
    "name": "Garden",
    "map_state": "MAP_STATE_COMPLETE",
    "width": 100,
    "height": 80,
    "resolution": 100,
    "origin": {"x": 0, "y": 0},
    "has_station": True,
    "station_pose": {"x": 1200, "y": 3400, "theta": 1570},
    "total_area": 250_000_000,
    "regions": [
        {
            "id": 1,
            "name": "Main",
            "boundary": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 10000, "y": 0},
                    {"x": 10000, "y": 8000},
                    {"x": 0, "y": 8000},
                ]
            },
            "edge_segments": [
                {"points": [{"x": 0, "y": 0}, {"x": 10000, "y": 0}]}
            ],
            "sub_regions": [
                {
                    "id": 7,
                    "name": "Front lawn",
                    "boundary": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 5000, "y": 0},
                            {"x": 5000, "y": 8000},
                            {"x": 0, "y": 8000},
                        ]
                    },
                    "inner_boundarys": [
                        {
                            "points": [
                                {"x": 1000, "y": 1000},
                                {"x": 1500, "y": 1000},
                                {"x": 1500, "y": 1500},
                            ]
                        }
                    ],
                    "center": {"x": 2500, "y": 4000},
                    "is_selected_for_mow": True,
                },
            ],
        }
    ],
    "forbidden_zones": [
        {
            "polygon": {
                "points": [
                    {"x": 6000, "y": 6000},
                    {"x": 7000, "y": 6000},
                    {"x": 7000, "y": 7000},
                ]
            }
        }
    ],
    "cross_boundary_tunnels": [
        {
            "polygon": {
                "points": [
                    {"x": 8000, "y": 1000},
                    {"x": 8500, "y": 1000},
                    {"x": 8500, "y": 1500},
                ]
            }
        }
    ],
    "virtual_walls": [
        {"line": {"points": [{"x": 9000, "y": 500}, {"x": 9500, "y": 500}]}}
    ],
    "clean_info": {
        "move_to_target_point": {"target_point": {"x": 4000, "y": 4200}}
    },
}

# A degenerate sub-region (no boundary → no center) rides along in the map
# to exercise the payload's optional-geometry branches.
MAP_DATA["regions"][0]["sub_regions"].append({"id": 8, "boundary": {}})

PATH_DATA: dict[str, Any] = {
    "id": 101,
    "map_id": 1,
    "type": "NAVIGATION_PATH_TYPE_REALTIME",
    "points": [
        {"position": {"x": 100, "y": 200}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 300, "y": 400}, "type": "PATH_POINT_TYPE_CLEANING"},
        {"position": {"x": 900, "y": 900}, "type": "PATH_POINT_TYPE_RETURN"},
    ],
}


def _fake_hub_start(self: TerraMowHub) -> None:
    """Start the hub without network: mock client, real callback wiring."""
    client = MagicMock()
    client.is_connected.return_value = True
    client.publish.return_value = MagicMock(rc=0)
    self.mqtt_client = client
    self.register_all_callbacks()


async def setup_terramow(hass: HomeAssistant) -> MockConfigEntry:
    """Set the integration up for real and return the loaded config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_PASSWORD: "secret", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.terramow.validate_input",
            return_value={"title": f"TerraMow ({HOST})"},
        ),
        patch.object(TerraMowHub, "start", _fake_hub_start),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _lawn_mower_entity_id(hass: HomeAssistant) -> str:
    unique_id = f"lawn_mower.terramow@{SERIAL}"
    entity_id = er.async_get(hass).async_get_entity_id(
        "lawn_mower", DOMAIN, unique_id
    )
    assert entity_id is not None
    return entity_id


async def _drain(client: Any, quiet: float = 0.15) -> None:
    """Swallow queued feed events until the connection goes quiet."""
    while True:
        try:
            async with asyncio.timeout(quiet):
                await client.receive_json()
        except TimeoutError:
            return


async def test_setup_registers_card_and_command(
    hass: HomeAssistant, hass_client: Any
) -> None:
    """Setup serves the card JS over HTTP and registers the WS command."""
    # Simulate a loaded frontend so the card auto-registers in the app shell
    hass.config.components.add("frontend")
    extra_module_urls: set[str] = set()
    hass.data["frontend_extra_module_url"] = extra_module_urls

    await setup_terramow(hass)

    assert WS_SUBSCRIBE_MAP in hass.data["websocket_api"]
    assert any(url.startswith(CARD_URL_PATH) for url in extra_module_urls)

    client = await hass_client()
    resp = await client.get(CARD_URL_PATH)
    assert resp.status == 200
    body = await resp.text()
    assert "terramow-map-card" in body

    # Idempotent across additional entries
    await map_card.async_setup_map_card(hass)


async def test_subscribe_snapshot_and_updates(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """Subscribing yields a snapshot; map/path/pose pushes stream events."""
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 0)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": WS_SUBSCRIBE_MAP,
            "entity_id": _lawn_mower_entity_id(hass),
        }
    )
    result = await client.receive_json()
    assert result["success"]

    # The initial snapshot (scene) and the initial robot event both arrive.
    # The scene build now runs off the event loop, so the synchronous robot
    # event may lead it; accept either order.
    initial: dict[str, Any] = {}
    for _ in range(2):
        event = (await client.receive_json())["event"]
        initial[event["type"]] = event
    assert set(initial) == {"scene", "robot"}
    scene = initial["scene"]["scene"]
    assert scene["map_name"] == "Garden"
    assert scene["station"] == {"x": 1200, "y": 3400, "theta": 1.57}
    assert len(scene["regions"]) == 1
    sub = scene["regions"][0]["sub_regions"][0]
    assert sub["id"] == 7
    assert sub["selected"] is True
    assert sub["center"] == [2500, 4000]
    assert len(scene["forbidden_zones"]) == 1
    assert len(scene["tunnels"]) == 1
    assert len(scene["virtual_walls"]) == 1
    assert scene["move_target"] == [4000, 4200]
    assert scene["cutting_width"] == 320
    # Only the CLEANING points survive into the card path
    assert scene["current_path"] == [[100, 200], [300, 400]]
    assert scene["bounds"] is not None

    assert initial["robot"]["robot"] is None

    await _drain(client)

    # A live pose push streams a robot event
    msg = SimpleNamespace(
        topic=POSE_TOPIC,
        payload=json.dumps({"x": 4000, "y": 2000, "yaw": 1.0}).encode(),
    )
    hub.on_mqtt_message(None, None, msg)
    await hass.async_block_till_done()
    robot_event = await client.receive_json()
    robot = robot_event["event"]["robot"]
    assert robot == {"x": 4000.0, "y": 2000.0, "yaw": 1.0, "source": "live_pose"}

    # A map update streams a (debounced) scene event
    hub._apply_map_data({**MAP_DATA, "name": "Garden 2"})
    await hass.async_block_till_done()
    scene_event = await client.receive_json()
    assert scene_event["event"]["scene"]["map_name"] == "Garden 2"


async def test_robot_dock_fallback(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """An all-zero pose plus a connected charger parks the robot at the dock."""
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 0)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(MAP_DATA)
    hub._pose = {"x": 0, "y": 0, "yaw": 0}
    hub._battery_status = {"charger_connected": True}

    robot = build_robot_payload(hub)
    assert robot is not None
    assert robot["source"] == "dock_fallback"
    assert robot["x"] == 1200.0
    assert robot["y"] == 3400.0
    # Docked robot faces away from the station (theta + pi, normalized)
    assert robot["yaw"] is not None
    assert math.isclose(
        robot["yaw"], math.atan2(math.sin(1.57 + math.pi), math.cos(1.57 + math.pi))
    )

    # Without a charger connection there is no display pose at all
    hub._battery_status = {"charger_connected": False}
    assert build_robot_payload(hub) is None

    # A malformed station pose cannot serve as the fallback either
    hub._battery_status = {"charger_connected": True}
    hub._map_data = {**MAP_DATA, "station_pose": {"x": "bad", "y": 3400}}
    assert build_robot_payload(hub) is None


async def test_subscribe_unknown_entity(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Subscribing with a foreign or unknown entity fails cleanly."""
    await setup_terramow(hass)
    client = await hass_ws_client(hass)

    await client.send_json(
        {"id": 1, "type": WS_SUBSCRIBE_MAP, "entity_id": "lawn_mower.nope"}
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "not_found"

    # A TerraMow entity whose config entry never loaded has no hub either
    stale_entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.99"})
    stale_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", DOMAIN, "stale-uid", config_entry=stale_entry
    )
    await client.send_json(
        {"id": 2, "type": WS_SUBSCRIBE_MAP, "entity_id": stale.entity_id}
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "not_found"


async def test_subscribe_any_terramow_entity(
    hass: HomeAssistant, hass_ws_client: Any
) -> None:
    """Any entity of the config entry resolves to the same hub feed."""
    await setup_terramow(hass)
    registry = er.async_get(hass)
    sensor_id = next(
        entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == DOMAIN and entry.domain == "sensor"
    )

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": WS_SUBSCRIBE_MAP, "entity_id": sensor_id}
    )
    result = await client.receive_json()
    assert result["success"]

    # Unsubscribing tears the feed down without errors (skip the feed's
    # initial snapshot events queued between result and unsubscribe reply)
    await client.send_json(
        {"id": 2, "type": "unsubscribe_events", "subscription": 1}
    )
    while True:
        result = await client.receive_json()
        if result.get("id") == 2:
            break
    assert result["success"]


async def test_status_payload(hass: HomeAssistant) -> None:
    """Battery and job status serialize for the HUD chips."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    # Fresh: everything idle -> no chips, and status (all-idle) collapses to None
    assert build_status_payload(hub) == {
        "battery": None,
        "work": None,
        "status": None,
        "errors": None,
        "preflight": {},
    }

    # An active dp_116 fault surfaces on the card with readable catalog text.
    await hub.on_error_list(json.dumps({"error_list": [{"code": 909}, {"code": 7}]}))
    assert build_status_payload(hub)["errors"] == [
        {"code": 909, "text": "Mower stuck"},
        {"code": 7, "text": "Error 7"},
    ]
    await hub.on_error_list(json.dumps({"error_list": []}))
    assert build_status_payload(hub)["errors"] is None

    hub._battery_level = 87
    hub._battery_status = {"charger_connected": True}
    hub._current_work_data = {
        "total_area": 1000,
        "clean_area": 250,
        "work_duration": 600,
    }
    payload = build_status_payload(hub)
    assert payload["battery"] == {"level": 87, "charging": True}
    assert payload["work"] == {"progress": 25.0, "area_m2": 25.0, "duration_s": 600}

    # Work data without any numeric fields yields no work chip payload
    hub._current_work_data = {"type": "WORK_TYPE_NORMAL"}
    assert build_status_payload(hub)["work"] is None


async def test_status_payload_mission_info(hass: HomeAssistant) -> None:
    """Non-idle mission fields (#205) reach the HUD payload; idle ones don't."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    # An active mow, returned to base for the night
    await hub.on_mission_status(
        json.dumps(
            {
                "mission": "MISSION_GLOBAL_CLEAN",
                "sub_mission": "SUB_MISSION_RETURN_TO_BASE",
                "state": "MISSION_STATE_RUNNING",
                "back_to_station_reason": "BACK_TO_STATION_REASON_NIGHT_TIME",
            }
        )
    )
    assert build_status_payload(hub)["status"] == {
        "mission": "MISSION_GLOBAL_CLEAN",
        "sub_mission": "SUB_MISSION_RETURN_TO_BASE",
        "state": "MISSION_STATE_RUNNING",
        "back_to_station_reason": "BACK_TO_STATION_REASON_NIGHT_TIME",
    }

    # A NONE reason is treated as absent
    await hub.on_mission_status(
        json.dumps({"back_to_station_reason": "BACK_TO_STATION_REASON_NONE"})
    )
    assert (
        "back_to_station_reason" not in build_status_payload(hub)["status"]
    )


async def test_paths_append_delta(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """Growing paths stream as appends; rewrites fall back to a full scene."""
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 0)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": WS_SUBSCRIBE_MAP,
            "entity_id": _lawn_mower_entity_id(hass),
        }
    )
    result = await client.receive_json()
    assert result["success"]
    await _drain(client)

    # Path grows at the tail → only the new points travel
    extended = {
        **PATH_DATA,
        "points": [
            *PATH_DATA["points"],
            {"position": {"x": 500, "y": 600}, "type": "PATH_POINT_TYPE_CLEANING"},
        ],
    }
    hub._apply_path_data(extended)
    await hass.async_block_till_done()
    event = await client.receive_json()
    assert event["event"]["type"] == "paths_append"
    # PATH_DATA ends on a RETURN transit, so the new cleaning point starts a
    # fresh run: the append leads with the [] run-break sentinel — the card
    # lifts the pen instead of bridging the transit with a phantom line.
    assert event["event"]["current_path_append"] == [[], [500, 600]]
    assert event["event"]["history_path_append"] == []

    # Unchanged data → no push at all
    hub._apply_path_data(extended)
    await hass.async_block_till_done()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.3):
            await client.receive_json()

    # Path rewritten from scratch → full scene again
    rewritten = {
        **PATH_DATA,
        "points": [
            {"position": {"x": 7, "y": 8}, "type": "PATH_POINT_TYPE_CLEANING"}
        ],
    }
    hub._apply_path_data(rewritten)
    await hass.async_block_till_done()
    event = await client.receive_json()
    assert event["event"]["type"] == "scene"
    assert event["event"]["scene"]["current_path"] == [[7, 8]]


async def test_wifi_heatmap_payload_and_delta(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """The heatmap rides the scene once and the append channel afterwards."""
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 0)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    # No samples yet -> the payload slot exists but is None
    assert build_scene_payload(hub)["wifi_heatmap"] is None

    hub._wifi_cells = {(2, 3): 87.6}
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": WS_SUBSCRIBE_MAP,
            "entity_id": _lawn_mower_entity_id(hass),
        }
    )
    assert (await client.receive_json())["success"]
    events: dict[str, Any] = {}
    for _ in range(2):
        event = (await client.receive_json())["event"]
        events[event["type"]] = event
    # The initial scene carries the heatmap (values rounded to whole %)
    assert events["scene"]["scene"]["wifi_heatmap"] == {
        "cell_mm": 1500,
        "cells": [[2, 3, 88]],
    }
    await _drain(client)

    # Heatmap change + path growth -> the append event carries the whole map
    hub._wifi_cells[(4, 5)] = 42.0
    extended = {
        **PATH_DATA,
        "points": [
            *PATH_DATA["points"],
            {"position": {"x": 500, "y": 600}, "type": "PATH_POINT_TYPE_CLEANING"},
        ],
    }
    hub._apply_path_data(extended)
    await hass.async_block_till_done()
    event = (await client.receive_json())["event"]
    assert event["type"] == "paths_append"
    assert event["wifi_heatmap"]["cells"] == [[2, 3, 88], [4, 5, 42]]

    # Path grows again, heatmap unchanged -> no wifi key in the event
    extended2 = {
        **extended,
        "points": [
            *extended["points"],
            {"position": {"x": 700, "y": 800}, "type": "PATH_POINT_TYPE_CLEANING"},
        ],
    }
    hub._apply_path_data(extended2)
    await hass.async_block_till_done()
    event = (await client.receive_json())["event"]
    assert event["type"] == "paths_append"
    assert "wifi_heatmap" not in event

    # Heatmap-only change (paths untouched) -> an append event still goes out
    hub._wifi_cells[(6, 7)] = 55.0
    hub._apply_path_data(extended2)
    await hass.async_block_till_done()
    event = (await client.receive_json())["event"]
    assert event["type"] == "paths_append"
    assert event["current_path_append"] == []
    assert len(event["wifi_heatmap"]["cells"]) == 3


async def test_bounds_stable_while_path_grows(hass: HomeAssistant) -> None:
    """Bounds cover static geometry only, so a growing path can't move them."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)
    bounds_before = build_scene_payload(hub)["bounds"]

    outside = {
        **PATH_DATA,
        "points": [
            *PATH_DATA["points"],
            {
                "position": {"x": 99999, "y": 99999},
                "type": "PATH_POINT_TYPE_CLEANING",
            },
        ],
    }
    hub._apply_path_data(outside)
    assert build_scene_payload(hub)["bounds"] == bounds_before


async def test_content_bounds_excludes_map_extent(hass: HomeAssistant) -> None:
    """content_bounds hugs the drawn geometry, not the wider scanned extent."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    # A scanned grid far larger than the lawn: 500x500 cells at 100mm each
    # => extent reaches 50 000mm, while the regions top out near 10 000mm.
    oversized = {**MAP_DATA, "width": 500, "height": 500}
    hub._apply_map_data(oversized)
    hub._apply_path_data(PATH_DATA)

    payload = build_scene_payload(hub)
    bounds = payload["bounds"]
    content = payload["content_bounds"]
    assert bounds is not None and content is not None
    # The full bounds stretch to the extent corner; the content bounds do not.
    assert bounds[2] == 50000 and bounds[3] == 50000
    assert content[2] < bounds[2] and content[3] < bounds[3]
    # Every drawn point still fits inside the content box.
    assert content[2] >= 10000 and content[3] >= 8000


async def test_unsubscribe_cancels_pending_scene_push(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """Unsubscribing with a debounced push in flight cancels the timer."""
    # Large debounce: the timer is guaranteed to still be pending at stop()
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 30)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": WS_SUBSCRIBE_MAP,
            "entity_id": _lawn_mower_entity_id(hass),
        }
    )
    result = await client.receive_json()
    assert result["success"]
    await _drain(client)

    # Queue a scene push (default debounce keeps its timer pending) and
    # unsubscribe before it fires.
    hub._apply_map_data(MAP_DATA)
    await hass.async_block_till_done()
    await client.send_json(
        {"id": 2, "type": "unsubscribe_events", "subscription": 1}
    )
    while True:
        result = await client.receive_json()
        if result.get("id") == 2:
            break
    assert result["success"]


async def test_resubscribe_pushes_cached_scene_immediately(
    hass: HomeAssistant, hass_ws_client: Any, monkeypatch: Any
) -> None:
    """A second subscription paints the last scene at once (before rebuild)."""
    monkeypatch.setattr(map_card, "SCENE_PUSH_DEBOUNCE", 0)
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)
    await hass.async_block_till_done()

    # First subscription: cold cache -> the background build populates it.
    client1 = await hass_ws_client(hass)
    await client1.send_json(
        {"id": 1, "type": WS_SUBSCRIBE_MAP, "entity_id": _lawn_mower_entity_id(hass)}
    )
    assert (await client1.receive_json())["success"]
    await hass.async_block_till_done()
    assert hub in map_card._HUB_SCENE_CACHES

    # Second subscription: the very first event is the cached scene, emitted
    # synchronously from start() before any executor rebuild runs.
    client2 = await hass_ws_client(hass)
    await client2.send_json(
        {"id": 2, "type": WS_SUBSCRIBE_MAP, "entity_id": _lawn_mower_entity_id(hass)}
    )
    assert (await client2.receive_json())["success"]
    types = set()
    for _ in range(2):
        types.add((await client2.receive_json())["event"]["type"])
    assert "scene" in types


async def test_stop_cancels_inflight_build_task(hass: HomeAssistant) -> None:
    """Stopping a feed with a scene build still running cancels that task."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    feed = map_card._MapFeed(hass, MagicMock(), 1, hub)
    task = MagicMock()
    feed._build_task = task
    feed.stop()

    task.cancel.assert_called_once()
    assert feed._build_task is None


async def test_shared_scene_build_dedupes_across_feeds(
    hass: HomeAssistant, monkeypatch: Any
) -> None:
    """Feeds of the same hub share one executor build, not one each."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)

    calls = {"n": 0}
    real = map_card.build_scene_payload

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(map_card, "build_scene_payload", counting)

    feed_a = map_card._MapFeed(hass, MagicMock(), 1, hub)
    feed_b = map_card._MapFeed(hass, MagicMock(), 2, hub)

    payload_a, payload_b = await asyncio.gather(
        feed_a._shared_scene_build(), feed_b._shared_scene_build()
    )
    assert calls["n"] == 1  # one build shared by both feeds
    assert payload_a is payload_b
    assert map_card._HUB_SCENE_CACHES[hub] is payload_a

    # The previous task has finished, so a later request builds afresh.
    await feed_a._shared_scene_build()
    assert calls["n"] == 2


async def test_scene_cache_reuses_path_extraction(
    hass: HomeAssistant, monkeypatch: Any
) -> None:
    """A per-feed ScenePathCache skips re-extracting unchanged path sources."""
    from custom_components.terramow import map_scene

    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)

    calls = {"n": 0}
    real = map_scene._extract_path_points

    def counting(path_data: Any) -> Any:
        calls["n"] += 1
        return real(path_data)

    monkeypatch.setattr(map_scene, "_extract_path_points", counting)

    cache = map_card.ScenePathCache()
    first = build_scene_payload(hub, None, cache)
    assert calls["n"] == 2  # current + history extracted once each

    # Nothing changed: both source dicts hit the cache, no re-extraction.
    again = build_scene_payload(hub, None, cache)
    assert calls["n"] == 2
    assert again["current_path"] == first["current_path"]

    # A new current-path source re-extracts only the current path; the
    # unchanged history source stays cached.
    hub._apply_path_data(
        {
            **PATH_DATA,
            "points": [
                *PATH_DATA["points"],
                {"position": {"x": 9, "y": 9}, "type": "PATH_POINT_TYPE_CLEANING"},
            ],
        }
    )
    build_scene_payload(hub, None, cache)
    assert calls["n"] == 3


async def test_empty_scene_payload(hass: HomeAssistant) -> None:
    """With no map data yet, the payload is well-formed and empty."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    payload = build_scene_payload(hub)
    assert payload["map_name"] is None
    assert payload["bounds"] is None
    assert payload["content_bounds"] is None
    assert payload["regions"] == []
    assert payload["station"] is None
    assert payload["current_path"] == []
    assert payload["main_direction_angle"] is None
    # the staleness flag is always forwarded (default False) so the card's
    # "map refreshing" chip has a value to read
    assert payload["path_map_mismatch"] is False


async def test_map_name_falls_back_to_map_id_when_unnamed(
    hass: HomeAssistant,
) -> None:
    """An unnamed map still gets a chip name ('Map #<id>'), so the card's
    map/area chip renders instead of being hidden entirely (issue #212)."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    # a named map keeps its name
    hub._apply_map_data({**MAP_DATA, "name": "Garden"})
    assert build_scene_payload(hub)["map_name"] == "Garden"

    # an empty name falls back to "Map #<id>"
    hub._apply_map_data({**MAP_DATA, "name": ""})
    assert build_scene_payload(hub)["map_name"] == "Map #1"


async def test_payload_carries_main_direction_angle(hass: HomeAssistant) -> None:
    """The configured stripe direction reaches the card payload in degrees."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(
        {
            **MAP_DATA,
            "mow_param": {
                "global_param": {
                    "main_direction_angle_config": {"current_angle": 135}
                }
            },
        }
    )
    assert build_scene_payload(hub)["main_direction_angle"] == 135


async def test_main_direction_angle_tolerates_malformed_blocks(
    hass: HomeAssistant,
) -> None:
    """Missing or malformed mow_param structures resolve to None, not errors."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    for mow_param in (
        "not-a-dict",
        {"global_param": "not-a-dict"},
        {"global_param": {"main_direction_angle_config": "not-a-dict"}},
    ):
        hub._apply_map_data({**MAP_DATA, "mow_param": mow_param})
        assert build_scene_payload(hub)["main_direction_angle"] is None


async def test_zone_direction_angles_override_global(hass: HomeAssistant) -> None:
    """Zones with custom params carry their own stripe angle; SINGLE mode
    prefers the configured angle over the (stale) current_angle."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    def _cfg(**config: Any) -> dict[str, Any]:
        return {"region_param": {"main_direction_angle_config": config}}

    hub._apply_map_data(
        {
            **MAP_DATA,
            "mow_param": {
                "global_param": {
                    "main_direction_angle_config": {
                        "mode": "MAIN_DIRECTION_MODE_SINGLE",
                        "single_mode_config": {"angle": 180},
                        "current_angle": 90,
                    }
                },
                "regions": [
                    # SINGLE mode: configured angle wins over stale current.
                    {
                        "id": 7,
                        **_cfg(
                            mode="MAIN_DIRECTION_MODE_SINGLE",
                            single_mode_config={"angle": -90},
                            current_angle=90,
                        ),
                    },
                    # Non-single mode: current_angle is the live value.
                    {
                        "id": 8,
                        **_cfg(
                            mode="MAIN_DIRECTION_MODE_AUTO_ROTATE",
                            current_angle=45,
                        ),
                    },
                    # SINGLE with a malformed/empty single config falls back.
                    {
                        "id": 5,
                        **_cfg(
                            mode="MAIN_DIRECTION_MODE_SINGLE",
                            single_mode_config="junk",
                            current_angle=30,
                        ),
                    },
                    {
                        "id": 6,
                        **_cfg(
                            mode="MAIN_DIRECTION_MODE_SINGLE",
                            single_mode_config={},
                            current_angle=20,
                        ),
                    },
                    # Malformed entries are skipped, never crash the payload.
                    "junk",
                    {"id": None, **_cfg(current_angle=10)},
                    {"id": 9, "region_param": "junk"},
                ],
            },
        }
    )
    payload = build_scene_payload(hub)
    # Global SINGLE mode also prefers the configured angle.
    assert payload["main_direction_angle"] == 180
    subs = {
        sub["id"]: sub
        for region in payload["regions"]
        for sub in region["sub_regions"]
    }
    assert subs[7]["direction_angle"] == -90
    assert subs[8]["direction_angle"] == 45


async def test_payload_carries_zone_and_global_settings(
    hass: HomeAssistant,
) -> None:
    """Per-zone mow settings and the global block reach the card payload."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    hub._apply_map_data(
        {
            **MAP_DATA,
            "mow_param": {
                "global_param": {
                    "mow_height": 75,
                    "mow_speed": "MOW_SPEED_TYPE_MEDIUM",
                    "mow_spacing": 120,
                },
                "regions": [
                    {
                        "id": 7,
                        "region_param": {
                            "mow_height": 60,
                            "blade_disk_speed": "BLADE_DISK_SPEED_TYPE_HIGH",
                        },
                    },
                    # Malformed entries never crash the payload.
                    "junk",
                    {"id": None, "region_param": {"mow_height": 1}},
                    {"id": 9, "region_param": "junk"},
                ],
            },
        }
    )
    payload = build_scene_payload(hub)
    assert payload["mow_params"]["mow_height"] == 75
    assert payload["mow_params"]["mow_speed"] == "MOW_SPEED_TYPE_MEDIUM"
    subs = {
        sub["id"]: sub
        for region in payload["regions"]
        for sub in region["sub_regions"]
    }
    # Zone 7 has custom params; zone 8 runs on the global block.
    assert subs[7]["params"]["mow_height"] == 60
    assert subs[7]["params"]["blade_disk_speed"] == "BLADE_DISK_SPEED_TYPE_HIGH"
    assert subs[8]["params"] is None


class _FakeResources:
    """Storage-mode Lovelace resource collection double."""

    def __init__(self, items: list[dict[str, Any]], loaded: bool = True) -> None:
        self.items = items
        self.loaded = loaded
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    async def async_load(self) -> None:
        self.load_called = True

    def async_items(self) -> list[dict[str, Any]]:
        return self.items

    async def async_create_item(self, data: dict[str, Any]) -> None:
        self.created.append(data)

    async def async_update_item(self, item_id: str, data: dict[str, Any]) -> None:
        self.updated.append((item_id, data))


_CARD_URL = f"{map_card.CARD_URL_PATH}?v={map_card.CARD_VERSION}"


async def test_lovelace_resource_created(hass: HomeAssistant) -> None:
    """Storage mode: the card is registered as a classic-js resource."""
    resources = _FakeResources([], loaded=False)
    hass.data["lovelace"] = SimpleNamespace(resources=resources)

    await setup_terramow(hass)

    assert resources.load_called
    assert resources.loaded is True
    assert resources.created == [{"res_type": "js", "url": _CARD_URL}]


async def test_lovelace_resource_updated_on_new_version(
    hass: HomeAssistant,
) -> None:
    """A stale cache-buster from an older version is updated in place."""
    resources = _FakeResources(
        [
            {"id": "other", "url": "/hacsfiles/some-card.js"},
            {
                "id": "ours",
                "url": f"{map_card.CARD_URL_PATH}?v=0.9.9",
                "type": "js",
            },
        ]
    )
    # pre-2024.8 dict layout
    hass.data["lovelace"] = {"resources": resources}

    await setup_terramow(hass)

    assert resources.created == []
    assert resources.updated == [("ours", {"res_type": "js", "url": _CARD_URL})]


async def test_lovelace_resource_heals_module_type(
    hass: HomeAssistant,
) -> None:
    """A "module" entry from <= 1.19.x is flipped to js (#140)."""
    resources = _FakeResources([{"id": "ours", "url": _CARD_URL, "type": "module"}])
    hass.data["lovelace"] = SimpleNamespace(resources=resources)

    await setup_terramow(hass)

    assert resources.created == []
    assert resources.updated == [
        ("ours", {"res_type": "js", "url": _CARD_URL})
    ]
    # Regression guard: "js" (classic script) is the type that reliably
    # re-executes from browser cache on both HA 2026.6 and 2026.7+ (#140).
    assert map_card.CARD_RESOURCE_TYPE == "js"


async def test_lovelace_resource_already_current(hass: HomeAssistant) -> None:
    """A current resource entry is left untouched."""
    resources = _FakeResources(
        [{"id": "ours", "url": _CARD_URL, "type": "js"}]
    )
    hass.data["lovelace"] = SimpleNamespace(resources=resources)

    await setup_terramow(hass)

    assert resources.created == []
    assert resources.updated == []


async def test_lovelace_yaml_mode_skipped(hass: HomeAssistant) -> None:
    """YAML resource mode has no writable collection and is skipped."""
    hass.data["lovelace"] = SimpleNamespace(resources=object())
    entry = await setup_terramow(hass)
    assert entry.runtime_data.lawn_mower is not None


async def test_lovelace_resource_error_does_not_break_setup(
    hass: HomeAssistant, caplog: Any
) -> None:
    """A Lovelace API hiccup is logged but never fails entry setup."""

    class _Broken(_FakeResources):
        def async_items(self) -> list[dict[str, Any]]:
            raise RuntimeError("lovelace internals changed")

    hass.data["lovelace"] = SimpleNamespace(resources=_Broken([]))
    entry = await setup_terramow(hass)

    assert entry.runtime_data.lawn_mower is not None
    assert "Could not register the map card Lovelace resource" in caplog.text


async def test_lovelace_resource_retries_after_start(hass: HomeAssistant) -> None:
    """When lovelace is not up yet during boot, registration retries on start."""
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState

    hass.set_state(CoreState.not_running)
    await setup_terramow(hass)

    # lovelace comes up before HA finishes starting
    resources = _FakeResources([])
    hass.data["lovelace"] = SimpleNamespace(resources=resources)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert resources.created == [{"res_type": "js", "url": _CARD_URL}]


def test_zone_coverage_ratios_covers_bbox_and_skip_branches() -> None:
    """One mowed edge inside a zone, one far outside (bounding-box rejected)."""
    scene = {
        "session_path_segments": [
            [{"x": 100, "y": 100}, {"x": 300, "y": 300}],
            [{"x": 50000, "y": 50000}, {"x": 60000, "y": 60000}],
        ],
        "regions": [
            {
                "sub_regions": [
                    {"id": 7, "boundary": [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]},
                    # a valid zone far away: every edge is bbox-rejected -> 0 %
                    {
                        "id": 9,
                        "boundary": [
                            (20000, 0),
                            (21000, 0),
                            (21000, 1000),
                            (20000, 1000),
                        ],
                    },
                    {"id": None, "boundary": [(0, 0), (1, 0), (1, 1)]},  # id None
                    {"id": 8, "boundary": [(0, 0), (1, 1)]},  # < 3 vertices
                    {"id": 11, "boundary": [(0, 0), (10, 0), (20, 0)]},  # area 0
                ]
            }
        ],
    }
    ratios = map_card._zone_coverage_ratios(scene)
    # only the zone with a mowed edge inside it gets a positive coverage ratio
    assert set(ratios) == {7}
    assert 0.0 < ratios[7] <= 1.0


def test_zone_coverage_ratios_edge_in_bbox_but_outside_polygon() -> None:
    """A mowed edge whose midpoint clears the bbox but misses the polygon."""
    scene = {
        # midpoint (800, 800): inside the triangle's 0..1000 bounding box but
        # outside the triangle itself (x + y > 1000) -> point_in_polygon False
        "session_path_segments": [[{"x": 700, "y": 900}, {"x": 900, "y": 700}]],
        "regions": [
            {
                "sub_regions": [
                    {
                        "id": 7,
                        "boundary": [(0, 0), (1000, 0), (0, 1000)],
                    },
                ]
            }
        ],
    }
    # bbox passes, polygon rejects -> no zone earns coverage
    assert map_card._zone_coverage_ratios(scene) == {}


def test_zone_coverage_ratios_empty_inputs() -> None:
    assert (
        map_card._zone_coverage_ratios({"session_path_segments": [], "regions": []})
        == {}
    )
    # a single-point segment yields no drawable edges
    assert (
        map_card._zone_coverage_ratios(
            {"session_path_segments": [[{"x": 1, "y": 1}]], "regions": []}
        )
        == {}
    )


async def test_zone_coverage_recompute_is_throttled(hass: HomeAssistant) -> None:
    """The per-hub cache recomputes the coverage at most once per interval."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)

    # A shared cache: two builds within the interval recompute coverage once.
    cache: dict[str, Any] = {}
    with patch.object(
        map_card, "_zone_coverage_ratios", wraps=map_card._zone_coverage_ratios
    ) as zc:
        build_scene_payload(hub, cache)
        build_scene_payload(hub, cache)
        assert zc.call_count == 1
    # Without a cache every build recomputes.
    with patch.object(
        map_card, "_zone_coverage_ratios", wraps=map_card._zone_coverage_ratios
    ) as zc:
        build_scene_payload(hub)
        build_scene_payload(hub)
        assert zc.call_count == 2


async def test_hub_caches_are_released_with_their_hub(hass: HomeAssistant) -> None:
    """A collected hub takes its cache entries with it.

    The per-hub caches used to be keyed by ``id(hub)`` and were never pruned,
    so every config-entry reload stranded a full scene payload for the lifetime
    of the process — and, because CPython reuses id() values, a new hub could
    inherit the previous hub's cached scene. Weak keys make the entries live
    exactly as long as the hub does.
    """
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)

    # Populate all three caches for this hub.
    feed = map_card._MapFeed(hass, MagicMock(), 1, hub)
    map_card._HUB_SCENE_CACHES[hub] = build_scene_payload(hub, feed._coverage_cache)
    assert hub in map_card._HUB_SCENE_CACHES
    assert hub in map_card._HUB_COVERAGE_CACHES

    hub_ref = weakref.ref(hub)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Home Assistant clears entry.runtime_data on unload; drop the references
    # this test still holds and collect.
    del hub, feed
    gc.collect()

    assert hub_ref() is None, "the hub itself outlived the config entry"
    assert len(map_card._HUB_SCENE_CACHES) == 0
    assert len(map_card._HUB_COVERAGE_CACHES) == 0


async def test_unchanged_robot_event_is_not_pushed(hass: HomeAssistant) -> None:
    """A repeated pose report costs no WebSocket message.

    The pose arrives at ~2 Hz even while the mower sits docked, and dp_108/8/113
    report on their own schedule; without this gate every open card received two
    identical events a second forever.
    """
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)

    connection = MagicMock()
    feed = map_card._MapFeed(hass, connection, 1, hub)

    pose = {"x": 1000.0, "y": 2000.0, "yaw": 0.5}
    hub._pose = pose
    feed._push_robot()
    assert connection.send_message.call_count == 1

    # The same pose reported again — nothing to redraw, nothing to send.
    feed._push_robot()
    feed._push_robot()
    assert connection.send_message.call_count == 1

    # A moved mower pushes again.
    hub._pose = {"x": 1100.0, "y": 2000.0, "yaw": 0.5}
    feed._push_robot()
    assert connection.send_message.call_count == 2

    # So does an unchanged pose whose HUD chips changed (battery level).
    hub._battery_level = 42
    feed._push_robot()
    assert connection.send_message.call_count == 3


async def test_geometry_digest_tracks_geometry_not_paths(
    hass: HomeAssistant,
) -> None:
    """The digest ignores the streamed channels and follows everything else."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)

    first = build_scene_payload(hub)

    # A growing path must NOT change the digest — that is what keeps a mowing
    # tick a tail-append delta instead of a full scene push.
    grown = dict(PATH_DATA)
    grown["points"] = [
        *PATH_DATA["points"],
        {"position": {"x": 1500, "y": 1600}, "type": "PATH_POINT_TYPE_CLEANING"},
    ]
    hub._apply_path_data(grown)
    second = build_scene_payload(hub)
    assert second["current_path"] != first["current_path"]
    assert second[map_card.GEOMETRY_REV_KEY] == first[map_card.GEOMETRY_REV_KEY]

    # A changed zone name is geometry: the digest moves.
    renamed = json.loads(json.dumps(MAP_DATA))
    renamed["regions"][0]["sub_regions"][0]["name"] = "Back lawn"
    hub._apply_map_data(renamed)
    third = build_scene_payload(hub)
    assert third[map_card.GEOMETRY_REV_KEY] != first[map_card.GEOMETRY_REV_KEY]


async def test_geometry_digest_is_stable_across_equal_payloads(
    hass: HomeAssistant,
) -> None:
    """Two builds of an unchanged scene agree, so no full push is emitted."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None
    hub._apply_map_data(MAP_DATA)
    hub._apply_path_data(PATH_DATA)

    assert (
        build_scene_payload(hub)[map_card.GEOMETRY_REV_KEY]
        == build_scene_payload(hub)[map_card.GEOMETRY_REV_KEY]
    )
