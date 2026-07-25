"""Tests for the fault-hotspot layer.

A stuck mower is reported as an error code and nothing else — the app tells
you it happened, never where. These tests pin the pairing of the dp_116 error
list with the pose stream, and the merging that turns three stalls at the
same root into one marker with a count instead of three near-identical dots.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    FAULT_HOTSPOT_MERGE_MM,
    MAX_FAULT_HOTSPOTS,
    TerraMowHub,
)
from custom_components.terramow.map_card import build_scene_payload

HOST = "192.0.2.10"


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub._map_data = {"id": 3, "regions": []}
    hub._get_fault_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_delay_save=MagicMock())
    )
    return hub


async def _fault(hub: TerraMowHub, *codes: int) -> None:
    await hub.on_error_list(
        json.dumps({"error_list": [{"code": code} for code in codes]})
    )


def _at(hub: TerraMowHub, x: float, y: float) -> None:
    hub._pose = {"x": x, "y": y}


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------


async def test_a_fault_records_where_the_mower_stood(hub: TerraMowHub) -> None:
    _at(hub, 1000, 2000)
    await _fault(hub, 903)

    assert hub.fault_hotspots == [
        {
            "x": 1000.0,
            "y": 2000.0,
            "code": 903,
            "count": 1,
            "last_seen": hub.fault_hotspots[0]["last_seen"],
        }
    ]


async def test_a_persisting_fault_is_recorded_once(hub: TerraMowHub) -> None:
    """dp_116 repeats while the fault lasts; one stall is one marker."""
    _at(hub, 1000, 2000)
    await _fault(hub, 903)
    _at(hub, 1010, 2010)
    await _fault(hub, 903)  # same list, still present
    await _fault(hub, 903)

    assert len(hub.fault_hotspots) == 1
    assert hub.fault_hotspots[0]["count"] == 1


async def test_a_fault_that_clears_and_returns_counts_again(
    hub: TerraMowHub,
) -> None:
    _at(hub, 1000, 2000)
    await _fault(hub, 903)
    await _fault(hub)  # cleared
    _at(hub, 1200, 2100)  # back at roughly the same spot
    await _fault(hub, 903)

    assert len(hub.fault_hotspots) == 1
    spot = hub.fault_hotspots[0]
    assert spot["count"] == 2
    # The marker settles on the running mean of the two positions.
    assert 1000 < spot["x"] < 1200


async def test_faults_further_apart_stay_separate(hub: TerraMowHub) -> None:
    _at(hub, 0, 0)
    await _fault(hub, 903)
    await _fault(hub)
    _at(hub, FAULT_HOTSPOT_MERGE_MM * 3, 0)
    await _fault(hub, 903)

    assert len(hub.fault_hotspots) == 2


async def test_different_codes_at_one_spot_stay_separate(hub: TerraMowHub) -> None:
    """"Stuck here" and "lifted here" are different problems."""
    _at(hub, 500, 500)
    await _fault(hub, 903, 201)

    assert sorted(spot["code"] for spot in hub.fault_hotspots) == [201, 903]


async def test_a_fault_without_a_pose_is_not_a_hotspot(hub: TerraMowHub) -> None:
    """A location we never learned must not be invented as the origin."""
    await _fault(hub, 903)
    assert hub.fault_hotspots == []

    hub._pose = {"x": "abc", "y": True}
    await _fault(hub, 904)
    assert hub.fault_hotspots == []


async def test_malformed_error_entries_are_skipped(hub: TerraMowHub) -> None:
    _at(hub, 100, 100)
    await hub.on_error_list(json.dumps({"error_list": ["nope", {"code": 903}]}))
    assert [spot["code"] for spot in hub.fault_hotspots] == [903]


async def test_the_list_is_bounded(hub: TerraMowHub) -> None:
    for index in range(MAX_FAULT_HOTSPOTS + 10):
        _at(hub, index * FAULT_HOTSPOT_MERGE_MM * 3, 0)
        await _fault(hub, 900 + index)
        await _fault(hub)

    assert len(hub.fault_hotspots) == MAX_FAULT_HOTSPOTS
    # The oldest are the ones dropped.
    assert hub.fault_hotspots[0]["code"] == 910


# ---------------------------------------------------------------------------
# reset boundaries and persistence
# ---------------------------------------------------------------------------


async def test_a_new_map_clears_the_hotspots(hub: TerraMowHub) -> None:
    """The coordinates are map-frame: elsewhere they mark nothing real."""
    _at(hub, 1000, 1000)
    await _fault(hub, 903)
    assert hub.fault_hotspots

    hub._apply_map_data({"id": 4, "regions": []})
    assert hub.fault_hotspots == []


async def test_the_same_map_keeps_them(hub: TerraMowHub) -> None:
    _at(hub, 1000, 1000)
    await _fault(hub, 903)
    hub._apply_map_data({"id": 3, "regions": []})
    assert len(hub.fault_hotspots) == 1


async def test_hotspots_survive_a_restart(hub: TerraMowHub) -> None:
    _at(hub, 1000, 1000)
    await _fault(hub, 903)
    saved = hub._fault_save_data()
    assert saved["map_id"] == 3

    fresh = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hub.hass)
    fresh._get_fault_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(saved))
    )
    await fresh.async_restore_fault_hotspots()
    assert fresh.fault_hotspots == hub.fault_hotspots
    assert fresh._fault_map_id == 3


async def test_restore_skips_junk_and_survives_a_broken_store(
    hub: TerraMowHub,
) -> None:
    stored = {
        "map_id": 3,
        "hotspots": ["nope", {"x": 1}, {"x": 1, "y": 2, "code": 903, "count": 1}],
    }
    hub._get_fault_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(stored))
    )
    await hub.async_restore_fault_hotspots()
    assert len(hub.fault_hotspots) == 1

    hub._fault_hotspots = []
    hub._get_fault_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning({"hotspots": "nope"}))
    )
    await hub.async_restore_fault_hotspots()
    assert hub.fault_hotspots == []

    async def _boom() -> None:
        raise OSError("disk gone")

    hub._get_fault_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_boom)
    )
    await hub.async_restore_fault_hotspots()  # logs, never blocks setup


async def test_the_store_is_created_once(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    store = hub._get_fault_store()
    assert store is hub._get_fault_store()


def _returning(value: Any) -> Any:
    async def _load() -> Any:
        return value

    return _load


# ---------------------------------------------------------------------------
# card payload
# ---------------------------------------------------------------------------


async def test_the_payload_omits_hotspots_until_there_are_any(
    hub: TerraMowHub,
) -> None:
    assert build_scene_payload(hub)["fault_hotspots"] is None


async def test_the_payload_carries_the_hotspots(hub: TerraMowHub) -> None:
    _at(hub, 1234.56, 2000)
    await _fault(hub, 903)

    (spot,) = build_scene_payload(hub)["fault_hotspots"]
    assert spot["x"] == 1234.6  # rounded for the wire
    assert spot["code"] == 903
    assert spot["count"] == 1
    assert spot["last_seen"]
