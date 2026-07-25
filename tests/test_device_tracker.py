"""Tests for the GPS-anchored device tracker.

The projection is the interesting part: the mower's pose is millimetres in a
screen-style map frame, and turning that into latitude/longitude has to get
the axis directions right or the mower ends up mirrored across the lawn.
These tests pin each cardinal direction, plus the throttle that keeps a 2 Hz
pose stream out of the recorder.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    CONF_GPS_HEADING,
    CONF_GPS_LATITUDE,
    CONF_GPS_LONGITUDE,
)
from custom_components.terramow.device_tracker import (
    METERS_PER_DEGREE_LATITUDE,
    TerraMowDeviceTracker,
    async_setup_entry as tracker_setup,
    project_pose,
)
from custom_components.terramow.hub import TerraMowHub

HOST = "192.0.2.10"

# The anchor: a base station at 10 000 / 20 000 mm in the map frame.
STATION = {"x": 10000.0, "y": 20000.0}
ANCHOR_LAT = 52.0
ANCHOR_LON = 13.0

# One degree of latitude, and of longitude at the anchor, in metres.
LAT_M = METERS_PER_DEGREE_LATITUDE


def _project(dx_mm: float, dy_mm: float, heading: float = 0.0) -> tuple[float, float]:
    result = project_pose(
        {"x": STATION["x"] + dx_mm, "y": STATION["y"] + dy_mm},
        STATION,
        anchor_latitude=ANCHOR_LAT,
        anchor_longitude=ANCHOR_LON,
        heading=heading,
    )
    assert result is not None
    return result


def _meters_north(latitude: float) -> float:
    return (latitude - ANCHOR_LAT) * LAT_M


def _meters_east(longitude: float) -> float:
    import math

    return (
        (longitude - ANCHOR_LON) * LAT_M * math.cos(math.radians(ANCHOR_LAT))
    )


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------


def test_at_the_station_the_position_is_the_anchor() -> None:
    assert _project(0, 0) == (ANCHOR_LAT, ANCHOR_LON)


def test_map_north_up_maps_x_east_and_y_south() -> None:
    """With the map's top pointing north: +X is east, +Y (down) is south."""
    latitude, longitude = _project(5000, 0)  # 5 m along +X
    assert _meters_east(longitude) == pytest.approx(5.0, abs=1e-6)
    assert _meters_north(latitude) == pytest.approx(0.0, abs=1e-9)

    latitude, longitude = _project(0, 5000)  # 5 m along +Y (down the map)
    assert _meters_north(latitude) == pytest.approx(-5.0, abs=1e-6)
    assert _meters_east(longitude) == pytest.approx(0.0, abs=1e-9)


def test_map_rotated_east_rotates_the_projection() -> None:
    """Map top pointing east: +X (right on the map) now points south."""
    latitude, longitude = _project(5000, 0, heading=90.0)
    assert _meters_north(latitude) == pytest.approx(-5.0, abs=1e-6)
    assert _meters_east(longitude) == pytest.approx(0.0, abs=1e-6)

    # And -Y (up the map) points east.
    latitude, longitude = _project(0, -5000, heading=90.0)
    assert _meters_east(longitude) == pytest.approx(5.0, abs=1e-6)


def test_distance_is_preserved_under_rotation() -> None:
    import math

    for heading in (0.0, 37.0, 90.0, 180.0, 271.5, 360.0):
        latitude, longitude = _project(3000, 4000, heading=heading)
        distance = math.hypot(_meters_east(longitude), _meters_north(latitude))
        assert distance == pytest.approx(5.0, abs=1e-6)


def test_projection_needs_a_station_and_usable_numbers() -> None:
    assert project_pose(
        {"x": 1, "y": 2},
        None,
        anchor_latitude=ANCHOR_LAT,
        anchor_longitude=ANCHOR_LON,
        heading=0,
    ) is None
    assert project_pose(
        {"x": 1, "y": 2},
        "not a dict",  # type: ignore[arg-type]
        anchor_latitude=ANCHOR_LAT,
        anchor_longitude=ANCHOR_LON,
        heading=0,
    ) is None
    assert project_pose(
        {"y": 2},  # no x
        STATION,
        anchor_latitude=ANCHOR_LAT,
        anchor_longitude=ANCHOR_LON,
        heading=0,
    ) is None
    assert project_pose(
        {"x": "abc", "y": 2},
        STATION,
        anchor_latitude=ANCHOR_LAT,
        anchor_longitude=ANCHOR_LON,
        heading=0,
    ) is None


def test_polar_anchor_does_not_divide_by_zero() -> None:
    result = project_pose(
        {"x": 1000.0, "y": 0.0},
        {"x": 0.0, "y": 0.0},
        anchor_latitude=90.0,
        anchor_longitude=13.0,
        heading=0.0,
    )
    assert result is not None
    # The longitude is left at the anchor rather than exploding.
    assert result[1] == 13.0


# ---------------------------------------------------------------------------
# entity
# ---------------------------------------------------------------------------


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub._map_data = {"id": 1, "station_pose": dict(STATION)}
    return hub


def _tracker(hub: TerraMowHub, heading: float = 0.0) -> TerraMowDeviceTracker:
    return TerraMowDeviceTracker(
        hub.basic_data,
        hub.hass,
        latitude=ANCHOR_LAT,
        longitude=ANCHOR_LON,
        heading=heading,
    )


async def test_setup_skips_the_tracker_without_an_anchor(hub: TerraMowHub) -> None:
    added: list[Any] = []
    entry = SimpleNamespace(entry_id="e1", runtime_data=hub.basic_data, options={})
    await tracker_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]
    assert added == []

    # A half-configured anchor is no anchor either.
    entry = SimpleNamespace(
        entry_id="e1",
        runtime_data=hub.basic_data,
        options={CONF_GPS_LATITUDE: ANCHOR_LAT},
    )
    await tracker_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]
    assert added == []


async def test_setup_creates_the_tracker_with_an_anchor(hub: TerraMowHub) -> None:
    added: list[Any] = []
    entry = SimpleNamespace(
        entry_id="e1",
        runtime_data=hub.basic_data,
        options={
            CONF_GPS_LATITUDE: ANCHOR_LAT,
            CONF_GPS_LONGITUDE: ANCHOR_LON,
            CONF_GPS_HEADING: 45.0,
        },
    )
    await tracker_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]

    assert len(added) == 1
    tracker = added[0]
    assert tracker.source_type is SourceType.GPS
    assert tracker.extra_state_attributes["map_heading"] == 45.0


async def test_tracker_reports_no_position_before_a_pose(hub: TerraMowHub) -> None:
    tracker = _tracker(hub)
    assert tracker.latitude is None
    assert tracker.longitude is None


async def test_tracker_follows_the_pose(hub: TerraMowHub) -> None:
    tracker = _tracker(hub)
    await tracker._on_pose({"x": STATION["x"] + 5000, "y": STATION["y"]})

    assert tracker.latitude is not None and tracker.longitude is not None
    assert _meters_east(tracker.longitude) == pytest.approx(5.0, abs=1e-6)


async def test_tracker_ignores_poses_it_cannot_project(hub: TerraMowHub) -> None:
    hub._map_data = {"id": 1}  # no station pose yet
    tracker = _tracker(hub)
    await tracker._on_pose({"x": 1.0, "y": 2.0})
    assert tracker.latitude is None


async def test_tracker_without_a_hub_is_a_no_op(hub: TerraMowHub) -> None:
    tracker = _tracker(hub)
    hub.basic_data.lawn_mower = None
    await tracker._on_pose({"x": 1.0, "y": 2.0})
    assert tracker.latitude is None


async def test_small_moves_do_not_write_state(hub: TerraMowHub) -> None:
    """A 2 Hz pose stream must not fill the recorder with jitter."""
    tracker = _tracker(hub)
    await tracker._on_pose({"x": STATION["x"], "y": STATION["y"]})
    first = tracker.latitude

    # 10 cm — below the movement threshold, and well inside the interval.
    await tracker._on_pose({"x": STATION["x"] + 100, "y": STATION["y"]})
    assert tracker.latitude == first
    assert tracker.longitude is not None
    assert _meters_east(tracker.longitude) == pytest.approx(0.0, abs=1e-9)

    # 2 m — past the threshold, so the new fix is published.
    await tracker._on_pose({"x": STATION["x"] + 2000, "y": STATION["y"]})
    assert _meters_east(tracker.longitude) == pytest.approx(2.0, abs=1e-6)


async def test_a_stale_fix_is_published_after_the_interval(
    hub: TerraMowHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _tracker(hub)
    await tracker._on_pose({"x": STATION["x"], "y": STATION["y"]})

    published_at = tracker._published_at
    assert published_at is not None
    monkeypatch.setattr(
        "custom_components.terramow.device_tracker.time.monotonic",
        lambda: published_at + 11.0,
    )
    await tracker._on_pose({"x": STATION["x"] + 100, "y": STATION["y"]})

    assert tracker.longitude is not None
    assert _meters_east(tracker.longitude) == pytest.approx(0.1, abs=1e-6)


async def test_added_to_hass_subscribes_and_unsubscribes(hub: TerraMowHub) -> None:
    tracker = _tracker(hub)
    tracker.entity_id = "device_tracker.terramow_position"
    await tracker.async_added_to_hass()
    assert hub.pose_callbacks, "no pose subscription"

    # Run what the entity platform runs on removal: a leaked subscription
    # would keep pushing 2 Hz poses into a dead entity.
    for unsubscribe in list(tracker._on_remove or []):
        unsubscribe()
    assert not hub.pose_callbacks, "the subscription outlived the entity"


async def test_added_to_hass_without_a_hub_registers_nothing(
    hass: HomeAssistant,
) -> None:
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    tracker = TerraMowDeviceTracker(
        basic_data, hass, latitude=ANCHOR_LAT, longitude=ANCHOR_LON, heading=0.0
    )
    tracker.entity_id = "device_tracker.terramow_position"
    await tracker.async_added_to_hass()


async def test_pose_stream_reaches_the_tracker(hub: TerraMowHub) -> None:
    """End to end: an MQTT pose message moves the entity."""
    tracker = _tracker(hub)
    tracker.entity_id = "device_tracker.terramow_position"
    tracker.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    await tracker.async_added_to_hass()

    hub.on_mqtt_message(
        None,
        None,
        SimpleNamespace(
            topic="pose/current",
            payload=json.dumps(
                {"x": STATION["x"], "y": STATION["y"] - 3000, "yaw": 0}
            ).encode(),
        ),
    )
    await hub.hass.async_block_till_done()

    assert tracker.latitude is not None
    assert _meters_north(tracker.latitude) == pytest.approx(3.0, abs=1e-6)
