"""Tests for the interactive map card backend (``map_card.py``).

Covers the global setup (static card resource + WebSocket command
registration), the ``terramow/map/subscribe`` feed (initial snapshot,
debounced scene pushes, live/docked robot pose events, error paths) and
the payload builders.
"""

from __future__ import annotations

import asyncio
import json
import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

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
)

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
}

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
    # Simulate a loaded frontend so the card auto-registers as a module
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

    scene_event = await client.receive_json()
    assert scene_event["event"]["type"] == "scene"
    scene = scene_event["event"]["scene"]
    assert scene["map_name"] == "Garden"
    assert scene["station"] == {"x": 1200, "y": 3400, "theta": 1.57}
    assert len(scene["regions"]) == 1
    sub = scene["regions"][0]["sub_regions"][0]
    assert sub["id"] == 7
    assert sub["selected"] is True
    assert sub["center"] == [2500, 4000]
    assert len(scene["forbidden_zones"]) == 1
    assert len(scene["tunnels"]) == 1
    # Only the CLEANING points survive into the card path
    assert scene["current_path"] == [[100, 200], [300, 400]]
    assert scene["bounds"] is not None

    robot_event = await client.receive_json()
    assert robot_event["event"]["type"] == "robot"
    assert robot_event["event"]["robot"] is None

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


async def test_empty_scene_payload(hass: HomeAssistant) -> None:
    """With no map data yet, the payload is well-formed and empty."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    assert hub is not None

    payload = build_scene_payload(hub)
    assert payload["map_name"] is None
    assert payload["bounds"] is None
    assert payload["regions"] == []
    assert payload["station"] is None
    assert payload["current_path"] == []


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
    """Storage mode: the card is registered as a module resource."""
    resources = _FakeResources([], loaded=False)
    hass.data["lovelace"] = SimpleNamespace(resources=resources)

    await setup_terramow(hass)

    assert resources.load_called
    assert resources.loaded is True
    assert resources.created == [{"res_type": "module", "url": _CARD_URL}]


async def test_lovelace_resource_updated_on_new_version(
    hass: HomeAssistant,
) -> None:
    """A stale cache-buster from an older version is updated in place."""
    resources = _FakeResources(
        [
            {"id": "other", "url": "/hacsfiles/some-card.js"},
            {"id": "ours", "url": f"{map_card.CARD_URL_PATH}?v=0.9.9"},
        ]
    )
    # pre-2024.8 dict layout
    hass.data["lovelace"] = {"resources": resources}

    await setup_terramow(hass)

    assert resources.created == []
    assert resources.updated == [("ours", {"url": _CARD_URL})]


async def test_lovelace_resource_already_current(hass: HomeAssistant) -> None:
    """A current resource entry is left untouched."""
    resources = _FakeResources([{"id": "ours", "url": _CARD_URL}])
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
