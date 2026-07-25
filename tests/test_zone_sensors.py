"""Tests for the per-zone "last mowed" sensors.

The value is an observation — the last pose the device reported inside a
zone's boundary — so the tests drive real poses through the hub and pin the
sampling interval, the map-change reset and the persistence round-trip.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.map_scene import (
    coverage_ratios_for_zones,
    zone_boundaries_from_map,
)
from custom_components.terramow.zone_sensor import (
    ZoneLastMowedSensor,
    async_setup_zone_sensors,
    zone_records,
)

HOST = "192.0.2.10"


def _square(x0: float, y0: float, size: float) -> list[dict[str, float]]:
    return [
        {"x": x0, "y": y0},
        {"x": x0 + size, "y": y0},
        {"x": x0 + size, "y": y0 + size},
        {"x": x0, "y": y0 + size},
    ]


MAP_DATA: dict[str, Any] = {
    "id": 7,
    "regions": [
        {
            "name": "Garden",
            "sub_regions": [
                {"id": 1, "name": "Terrace", "boundary": _square(0, 0, 10000)},
                {"id": 2, "name": "", "boundary": _square(20000, 0, 10000)},
            ],
        }
    ],
}


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub._map_data = json.loads(json.dumps(MAP_DATA))
    hub._get_session_path_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_delay_save=MagicMock())
    )
    return hub


def _pose(hub: TerraMowHub, x: float, y: float) -> None:
    hub._sample_zone_presence({"x": x, "y": y})


# ---------------------------------------------------------------------------
# hub sampling
# ---------------------------------------------------------------------------


async def test_a_pose_inside_a_zone_stamps_it(hub: TerraMowHub) -> None:
    _pose(hub, 5000, 5000)
    assert set(hub.zone_last_seen) == {1}
    assert dt_util.parse_datetime(hub.zone_last_seen[1]) is not None


async def test_a_pose_outside_every_zone_stamps_nothing(hub: TerraMowHub) -> None:
    _pose(hub, 15000, 5000)  # between the two squares
    assert hub.zone_last_seen == {}


async def test_sampling_is_throttled(hub: TerraMowHub) -> None:
    """A 2 Hz pose stream must not re-run point-in-polygon every frame."""
    _pose(hub, 5000, 5000)
    first = hub.zone_last_seen[1]

    _pose(hub, 25000, 5000)  # immediately after: inside zone 2, but skipped
    assert set(hub.zone_last_seen) == {1}
    assert hub.zone_last_seen[1] == first

    hub._zone_sampled_at = None  # interval elapsed
    _pose(hub, 25000, 5000)
    assert set(hub.zone_last_seen) == {1, 2}


async def test_unusable_poses_are_ignored(hub: TerraMowHub) -> None:
    hub._sample_zone_presence("not a dict")  # type: ignore[arg-type]
    hub._sample_zone_presence({"x": "abc", "y": 1})
    hub._sample_zone_presence({"x": True, "y": 1})
    hub._sample_zone_presence({"y": 1})
    assert hub.zone_last_seen == {}


async def test_malformed_regions_do_not_break_the_lookup(hub: TerraMowHub) -> None:
    hub._map_data = {
        "id": 7,
        "regions": [
            "not a dict",
            {"sub_regions": ["not a dict", {"id": "x", "boundary": []}]},
            {"sub_regions": [{"id": 9, "boundary": [{"x": 1, "y": 1}]}]},  # < 3 pts
            {"sub_regions": [{"id": 10, "boundary": [{"x": None, "y": 1}] * 3}]},
        ],
    }
    _pose(hub, 1, 1)
    assert hub.zone_last_seen == {}


async def test_a_new_map_drops_the_stamps(hub: TerraMowHub) -> None:
    """Zone ids belong to a map; keeping them would date zones that are gone."""
    _pose(hub, 5000, 5000)
    assert hub.zone_last_seen

    hub._apply_map_data({"id": 8, "regions": []})
    assert hub.zone_last_seen == {}


async def test_a_restored_map_mismatch_drops_the_stamps(hub: TerraMowHub) -> None:
    hub._zone_last_seen = {1: "2026-07-25T10:00:00+00:00"}
    hub._restored_map_id = 7
    hub._apply_map_data({"id": 99, "regions": []})
    assert hub.zone_last_seen == {}


async def test_stamps_are_persisted_and_restored(hub: TerraMowHub) -> None:
    _pose(hub, 5000, 5000)
    saved = hub._session_path_save_data()
    assert saved["zone_last_seen"] == {"1": hub.zone_last_seen[1]}

    fresh = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hub.hass)
    fresh._get_session_path_store = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(async_load=_returning(saved))
    )
    await fresh.async_restore_session_paths()
    assert fresh.zone_last_seen == {1: saved["zone_last_seen"]["1"]}
    # Restored stamps stay tied to the map they were taken on.
    assert fresh._restored_map_id == 7


async def test_restore_ignores_junk_stamp_entries(hub: TerraMowHub) -> None:
    stored = {
        "map_id": 7,
        "zone_last_seen": {"1": "2026-07-25T10:00:00+00:00", "x": "y", "2": 5},
    }
    hub._get_session_path_store = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(async_load=_returning(stored))
    )
    await hub.async_restore_session_paths()
    assert hub.zone_last_seen == {1: "2026-07-25T10:00:00+00:00"}


def _returning(value: Any) -> Any:
    async def _load() -> Any:
        return value

    return _load


# ---------------------------------------------------------------------------
# entity creation
# ---------------------------------------------------------------------------


def test_zone_records_names_fall_back() -> None:
    assert zone_records(MAP_DATA) == [(1, "Terrace"), (2, "Garden")]
    # No parent name either: the id is the last resort.
    assert zone_records(
        {"regions": [{"sub_regions": [{"id": 3, "boundary": []}]}]}
    ) == [(3, "#3")]
    # Junk is skipped rather than crashing platform setup.
    assert zone_records({"regions": ["x", {"sub_regions": ["y", {"id": True}]}]}) == []
    assert zone_records({}) == []


async def test_sensors_are_created_from_the_map(hub: TerraMowHub) -> None:
    added: list[Any] = []
    async_setup_zone_sensors(hub.hass, hub.basic_data, added.extend)
    await hub.hass.async_block_till_done()

    # register_map_callback replays the cached map, but only once map_info is
    # set — feed it the way the hub does.
    await hub._notify_map_callbacks(MAP_DATA) if hasattr(
        hub, "_notify_map_callbacks"
    ) else None
    for callback in list(hub.map_callbacks):
        await callback(MAP_DATA)

    assert sorted(sensor.zone_id for sensor in added) == [1, 2]
    assert added[0]._attr_translation_placeholders == {"zone": "Terrace"}


async def test_sensors_are_not_duplicated_on_a_map_refresh(
    hub: TerraMowHub,
) -> None:
    added: list[Any] = []
    async_setup_zone_sensors(hub.hass, hub.basic_data, added.extend)
    for callback in list(hub.map_callbacks):
        await callback(MAP_DATA)
        await callback(MAP_DATA)
    assert len(added) == 2


async def test_setup_without_a_hub_registers_nothing(hass: HomeAssistant) -> None:
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    added: list[Any] = []
    async_setup_zone_sensors(hass, basic_data, added.extend)
    assert added == []


# ---------------------------------------------------------------------------
# entity behaviour
# ---------------------------------------------------------------------------


def _sensor(hub: TerraMowHub, zone_id: int = 1) -> ZoneLastMowedSensor:
    return ZoneLastMowedSensor(hub.basic_data, hub.hass, zone_id, "Terrace")


async def test_sensor_reports_the_stamp(hub: TerraMowHub) -> None:
    sensor = _sensor(hub)
    assert sensor.native_value is None

    _pose(hub, 5000, 5000)
    value = sensor.native_value
    assert value is not None
    assert value.isoformat() == hub.zone_last_seen[1]


async def test_sensor_exposes_the_cycle_coverage(hub: TerraMowHub) -> None:
    sensor = _sensor(hub)
    assert sensor.extra_state_attributes["cycle_coverage"] is None

    # A track straight across zone 1.
    hub._coverage_segments = [[{"x": 0, "y": 5000}, {"x": 10000, "y": 5000}]]
    attributes = sensor.extra_state_attributes
    assert attributes["zone_id"] == 1
    assert attributes["cycle_coverage"] is not None
    assert 0 < attributes["cycle_coverage"] <= 1


async def test_sensor_without_a_hub(hub: TerraMowHub) -> None:
    sensor = _sensor(hub)
    hub.basic_data.lawn_mower = None
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {"zone_id": 1}


async def test_sensor_writes_state_only_when_the_stamp_moves(
    hub: TerraMowHub,
) -> None:
    sensor = _sensor(hub)
    sensor.entity_id = "sensor.terramow_terrace_last_mowed"
    sensor.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

    await sensor._on_pose({})  # no stamp yet -> nothing changed
    assert sensor.async_write_ha_state.call_count == 0

    _pose(hub, 5000, 5000)
    await sensor._on_pose({})
    assert sensor.async_write_ha_state.call_count == 1

    await sensor._on_pose({})  # same stamp -> no second write
    assert sensor.async_write_ha_state.call_count == 1


async def test_sensor_subscribes_to_the_pose_stream(hub: TerraMowHub) -> None:
    sensor = _sensor(hub)
    sensor.entity_id = "sensor.terramow_terrace_last_mowed"
    await sensor.async_added_to_hass()
    assert hub.pose_callbacks

    for unsubscribe in list(sensor._on_remove or []):
        unsubscribe()
    assert not hub.pose_callbacks


async def test_sensor_added_without_a_hub(hass: HomeAssistant) -> None:
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    sensor = ZoneLastMowedSensor(basic_data, hass, 1, "Terrace")
    sensor.entity_id = "sensor.terramow_terrace_last_mowed"
    await sensor.async_added_to_hass()


# ---------------------------------------------------------------------------
# shared coverage maths
# ---------------------------------------------------------------------------


def test_zone_boundaries_from_map_skips_unusable_geometry() -> None:
    assert [zone_id for zone_id, _ in zone_boundaries_from_map(MAP_DATA)] == [1, 2]
    assert zone_boundaries_from_map({"regions": ["x"]}) == []
    assert zone_boundaries_from_map({"regions": [{"sub_regions": ["x"]}]}) == []
    assert zone_boundaries_from_map(
        {"regions": [{"sub_regions": [{"id": 1, "boundary": [{"x": "a", "y": 1}]}]}]}
    ) == []
    assert zone_boundaries_from_map(
        {"regions": [{"sub_regions": [{"id": True, "boundary": []}]}]}
    ) == []


def test_coverage_ratios_need_zones_and_segments() -> None:
    zones = zone_boundaries_from_map(MAP_DATA)
    assert coverage_ratios_for_zones(zones, [], 200.0) == {}
    assert coverage_ratios_for_zones([], [[{"x": 0, "y": 0}]], 200.0) == {}
    # A segment with a single point yields no edges.
    assert coverage_ratios_for_zones(zones, [[{"x": 0, "y": 0}]], 200.0) == {}


def test_coverage_ratio_is_capped_at_one() -> None:
    zones = zone_boundaries_from_map(MAP_DATA)
    # Many passes over the same small zone: the raw product exceeds the area.
    segments = [
        [{"x": 0, "y": y}, {"x": 10000, "y": y}] for y in range(0, 10000, 200)
    ]
    ratios = coverage_ratios_for_zones(zones, segments, 500.0)
    assert ratios[1] == 1.0


def test_degenerate_zones_are_skipped() -> None:
    zones = [(1, [(0.0, 0.0), (1.0, 0.0)]), (2, [(0.0, 0.0)] * 3)]
    segments = [[{"x": 0, "y": 0}, {"x": 1, "y": 0}]]
    assert coverage_ratios_for_zones(zones, segments, 200.0) == {}
