"""Tests for the season heatmap (how often each patch has been mowed).

The coverage layer answers "did this cycle cover the lawn". Stacking finished
cycles answers the more useful question — which patches the mower keeps
missing — and that only works if a cycle counts once per cell no matter how
many times it drove through.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import (
    MAX_MOW_COUNT_CELLS,
    MOW_COUNT_CELL_MM,
    TerraMowHub,
)
from custom_components.terramow.map_card import build_scene_payload

HOST = "192.0.2.10"


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub._map_data = {"id": 5, "regions": []}
    hub._get_mow_count_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_delay_save=MagicMock())
    )
    hub._get_session_path_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_delay_save=MagicMock())
    )
    return hub


def _track(*points: tuple[float, float]) -> list[list[dict[str, float]]]:
    return [[{"x": x, "y": y} for x, y in points]]


async def _finish_cycle(hub: TerraMowHub) -> None:
    """Drive the dp_107 frame that ends a cycle."""
    await hub.on_mission_status(
        json.dumps(
            {
                "mission": "MISSION_GLOBAL_CLEAN",
                "sub_mission": "SUB_MISSION_IDLE",
                "state": "MISSION_STATE_COMPLETE",
            }
        )
    )


# ---------------------------------------------------------------------------
# accumulation
# ---------------------------------------------------------------------------


async def test_nothing_is_counted_before_a_cycle_ends(hub: TerraMowHub) -> None:
    hub._coverage_segments = _track((0, 0), (1000, 0))
    assert hub.mow_counts == {}


async def test_a_finished_cycle_counts_its_cells(hub: TerraMowHub) -> None:
    hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
    hub._coverage_segments = _track((0, 0), (MOW_COUNT_CELL_MM, 0))
    await _finish_cycle(hub)

    assert hub.mow_counts == {(0, 0): 1, (1, 0): 1}


async def test_a_cycle_counts_each_cell_once(hub: TerraMowHub) -> None:
    """Driving through a cell five times is still one cycle reaching it."""
    hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
    hub._coverage_segments = [
        [{"x": 0.0, "y": 0.0} for _ in range(5)],
        [{"x": 10.0, "y": 10.0}],
    ]
    await _finish_cycle(hub)

    assert hub.mow_counts == {(0, 0): 1}


async def test_cycles_stack(hub: TerraMowHub) -> None:
    """The missed patch is the one whose count falls behind."""
    for _ in range(3):
        hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
        hub._coverage_segments = _track((0, 0))
        await _finish_cycle(hub)
    # A fourth cycle also reaches the neighbouring cell.
    hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
    hub._coverage_segments = _track((0, 0), (MOW_COUNT_CELL_MM * 4, 0))
    await _finish_cycle(hub)

    assert hub.mow_counts[(0, 0)] == 4
    assert hub.mow_counts[(4, 0)] == 1


async def test_an_empty_or_unusable_track_counts_nothing(hub: TerraMowHub) -> None:
    hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
    hub._coverage_segments = [[{"x": "a", "y": 1}, {"x": True, "y": 2}, {}]]
    await _finish_cycle(hub)
    assert hub.mow_counts == {}


async def test_the_grid_is_bounded(hub: TerraMowHub) -> None:
    hub._mow_counts = {
        (index, 0): 1 for index in range(MAX_MOW_COUNT_CELLS + 50)
    }
    hub._active_mow_mission = "MISSION_GLOBAL_CLEAN"
    hub._coverage_segments = _track((0, 0))
    await _finish_cycle(hub)

    assert len(hub.mow_counts) == MAX_MOW_COUNT_CELLS


# ---------------------------------------------------------------------------
# reset boundaries and persistence
# ---------------------------------------------------------------------------


async def test_a_new_map_clears_the_counts(hub: TerraMowHub) -> None:
    hub._mow_counts = {(0, 0): 3}
    hub._mow_count_map_id = 5

    hub._apply_map_data({"id": 6, "regions": []})
    assert hub.mow_counts == {}


async def test_the_same_map_keeps_them(hub: TerraMowHub) -> None:
    hub._mow_counts = {(0, 0): 3}
    hub._mow_count_map_id = 5
    hub._apply_map_data({"id": 5, "regions": []})
    assert hub.mow_counts == {(0, 0): 3}


async def test_counts_survive_a_restart(hub: TerraMowHub) -> None:
    hub._mow_counts = {(1, 2): 4}
    hub._mow_count_map_id = 5
    saved = hub._mow_count_save_data()
    assert saved == {"map_id": 5, "cells": {"1,2": 4}}

    fresh = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hub.hass)
    fresh._get_mow_count_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(saved))
    )
    await fresh.async_restore_mow_counts()
    assert fresh.mow_counts == {(1, 2): 4}
    assert fresh._mow_count_map_id == 5


async def test_restore_skips_junk_and_survives_a_broken_store(
    hub: TerraMowHub,
) -> None:
    stored = {
        "map_id": 5,
        "cells": {"1,2": 4, "bad": 1, "3,4": "x", "5,6": 0},
    }
    hub._get_mow_count_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(stored))
    )
    await hub.async_restore_mow_counts()
    assert hub.mow_counts == {(1, 2): 4}

    hub._get_mow_count_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning({"cells": "nope"}))
    )
    await hub.async_restore_mow_counts()
    assert hub.mow_counts == {(1, 2): 4}  # untouched by a malformed payload

    async def _boom() -> None:
        raise OSError("disk gone")

    hub._get_mow_count_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_boom)
    )
    await hub.async_restore_mow_counts()  # logs, never blocks setup


async def test_the_store_is_created_once(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    store = hub._get_mow_count_store()
    assert store is hub._get_mow_count_store()


def _returning(value: Any) -> Any:
    async def _load() -> Any:
        return value

    return _load


# ---------------------------------------------------------------------------
# card payload
# ---------------------------------------------------------------------------


async def test_the_payload_omits_the_heatmap_until_a_cycle_finished(
    hub: TerraMowHub,
) -> None:
    assert build_scene_payload(hub)["mow_counts"] is None


async def test_the_payload_carries_the_grid_and_its_maximum(
    hub: TerraMowHub,
) -> None:
    hub._mow_counts = {(0, 0): 4, (1, 0): 1}

    grid = build_scene_payload(hub)["mow_counts"]
    assert grid["cell_mm"] == MOW_COUNT_CELL_MM
    # The card scales its ramp against the maximum, so it has to ship.
    assert grid["max"] == 4
    assert sorted(grid["cells"]) == [[0, 0, 4], [1, 0, 1]]
