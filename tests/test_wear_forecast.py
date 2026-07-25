"""Tests for the measured-rate service forecasts.

The point of these sensors is that they refuse to guess: the rate comes from
two readings the device sent, and until there are two far enough apart the
sensors say nothing. These tests pin every refusal as carefully as the
arithmetic.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
)
from custom_components.terramow.hub import WEAR_MIN_WINDOW_SECONDS, TerraMowHub
from custom_components.terramow.sensor import (
    BaseStationWearForecastSensor,
    BladeWearForecastSensor,
)

HOST = "192.0.2.10"


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_delay_save=MagicMock())
    )
    return hub


def _anchor(hub: TerraMowHub, key: str, *, age_hours: float, value: int) -> None:
    """Plant an anchor of a given age, as a previous run would have left it."""
    stamp = dt_util.utcnow() - timedelta(hours=age_hours)
    hub._wear_anchors[key] = (stamp.isoformat(), value)


# ---------------------------------------------------------------------------
# anchors
# ---------------------------------------------------------------------------


async def test_the_first_reading_becomes_the_anchor(hub: TerraMowHub) -> None:
    await hub.on_blade_time(json.dumps({"int_value": 600}))
    assert hub.wear_window("blade") == {
        "observed_since": hub._wear_anchors["blade"][0],
        "observed_from_minutes": 600,
    }


async def test_later_readings_keep_the_oldest_anchor(hub: TerraMowHub) -> None:
    """A longer window is a better rate, so the anchor is not refreshed."""
    await hub.on_blade_time(json.dumps({"int_value": 600}))
    first = hub._wear_anchors["blade"]

    await hub.on_blade_time(json.dumps({"int_value": 900}))
    assert hub._wear_anchors["blade"] == first


async def test_a_counter_reset_starts_a_new_window(hub: TerraMowHub) -> None:
    """Extrapolating across a reset would use a rate that never happened."""
    await hub.on_blade_time(json.dumps({"int_value": 900}))
    await hub.on_blade_time(json.dumps({"int_value": 0}))  # reset button pressed
    assert hub._wear_anchors["blade"][1] == 0


async def test_both_counters_are_tracked_separately(hub: TerraMowHub) -> None:
    await hub.on_blade_time(json.dumps({"int_value": 100}))
    await hub.on_base_station_time(json.dumps({"int_value": 200}))
    assert hub._wear_anchors["blade"][1] == 100
    assert hub._wear_anchors["base_station"][1] == 200


async def test_unusable_counter_payloads_are_ignored(hub: TerraMowHub) -> None:
    await hub.on_blade_time(json.dumps({"int_value": True}))
    await hub.on_blade_time(json.dumps({"other": 1}))
    await hub.on_blade_time("[1]")
    assert hub.wear_window("blade") is None


# ---------------------------------------------------------------------------
# the forecast itself
# ---------------------------------------------------------------------------


async def test_no_forecast_without_an_anchor(hub: TerraMowHub) -> None:
    assert hub.wear_forecast("blade", 600, BLADE_MAINTENANCE_CYCLE_MINUTES) is None


async def test_no_forecast_inside_the_minimum_window(hub: TerraMowHub) -> None:
    """Hours of observation must not become a date months out."""
    _anchor(hub, "blade", age_hours=1, value=0)
    assert hub.wear_forecast("blade", 60, BLADE_MAINTENANCE_CYCLE_MINUTES) is None


async def test_no_forecast_while_the_counter_has_not_moved(
    hub: TerraMowHub,
) -> None:
    _anchor(hub, "blade", age_hours=48, value=600)
    assert hub.wear_forecast("blade", 600, BLADE_MAINTENANCE_CYCLE_MINUTES) is None


async def test_no_forecast_once_the_interval_is_already_past(
    hub: TerraMowHub,
) -> None:
    """"Due now" is what the maintenance entities already say."""
    _anchor(hub, "blade", age_hours=48, value=0)
    assert (
        hub.wear_forecast(
            "blade",
            BLADE_MAINTENANCE_CYCLE_MINUTES,
            BLADE_MAINTENANCE_CYCLE_MINUTES,
        )
        is None
    )


async def test_no_forecast_from_an_unparsable_anchor(hub: TerraMowHub) -> None:
    hub._wear_anchors["blade"] = ("not a timestamp", 0)
    assert hub.wear_forecast("blade", 600, BLADE_MAINTENANCE_CYCLE_MINUTES) is None


async def test_the_forecast_extrapolates_the_observed_rate(
    hub: TerraMowHub,
) -> None:
    """10 counter-minutes per observed hour, 100 to go -> 10 hours out."""
    _anchor(hub, "blade", age_hours=100, value=0)
    forecast = hub.wear_forecast("blade", 1000, 1100)

    assert forecast is not None
    hours_out = (forecast - dt_util.utcnow()).total_seconds() / 3600
    assert hours_out == pytest.approx(10.0, abs=0.05)


async def test_a_slower_mower_gets_a_later_date(hub: TerraMowHub) -> None:
    _anchor(hub, "base_station", age_hours=48, value=0)
    fast = hub.wear_forecast("base_station", 2000, BASE_STATION_MAINTENANCE_CYCLE_MINUTES)
    _anchor(hub, "base_station", age_hours=48, value=0)
    slow = hub.wear_forecast("base_station", 500, BASE_STATION_MAINTENANCE_CYCLE_MINUTES)

    assert fast is not None and slow is not None
    assert slow > fast


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


async def test_anchors_survive_a_restart(hub: TerraMowHub) -> None:
    """Without this the window would restart on every reload and never mature."""
    _anchor(hub, "blade", age_hours=100, value=42)
    saved = hub._wear_save_data()
    assert saved == {"anchors": {"blade": [hub._wear_anchors["blade"][0], 42]}}

    fresh = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hub.hass)
    fresh._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(saved))
    )
    await fresh.async_restore_wear_anchors()
    assert fresh._wear_anchors == hub._wear_anchors


async def test_restore_skips_junk_entries(hub: TerraMowHub) -> None:
    stored = {
        "anchors": {
            "blade": ["2026-07-01T00:00:00+00:00", 10],
            "bad_shape": ["only one"],
            "bad_value": ["2026-07-01T00:00:00+00:00", "x"],
            "bad_bool": ["2026-07-01T00:00:00+00:00", True],
            "not_a_list": "nope",
        }
    }
    hub._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(stored))
    )
    await hub.async_restore_wear_anchors()
    assert set(hub._wear_anchors) == {"blade"}


async def test_restore_tolerates_an_empty_or_broken_store(
    hub: TerraMowHub,
) -> None:
    hub._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning(None))
    )
    await hub.async_restore_wear_anchors()
    assert hub._wear_anchors == {}

    hub._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_returning({"anchors": "nope"}))
    )
    await hub.async_restore_wear_anchors()
    assert hub._wear_anchors == {}

    async def _boom() -> None:
        raise OSError("disk gone")

    hub._get_wear_store = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(async_load=_boom)
    )
    await hub.async_restore_wear_anchors()  # logs, never blocks setup


async def test_the_store_is_created_once(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    store = hub._get_wear_store()
    assert store is hub._get_wear_store()


def _returning(value: Any) -> Any:
    async def _load() -> Any:
        return value

    return _load


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------


async def test_blade_sensor_reports_the_forecast(hub: TerraMowHub) -> None:
    sensor = BladeWearForecastSensor(hub.basic_data, hub.hass)
    assert sensor.native_value is None

    await hub.on_blade_time(json.dumps({"int_value": 0}))
    _anchor(hub, "blade", age_hours=WEAR_MIN_WINDOW_SECONDS / 3600 + 1, value=0)
    await hub.on_blade_time(json.dumps({"int_value": 1200}))

    value = sensor.native_value
    assert value is not None and value > dt_util.utcnow()
    attributes = sensor.extra_state_attributes
    assert attributes["used_minutes"] == 1200
    assert attributes["recommended_cycle"] == BLADE_MAINTENANCE_CYCLE_MINUTES
    assert "observed_since" in attributes


async def test_base_station_sensor_uses_its_own_counter(hub: TerraMowHub) -> None:
    sensor = BaseStationWearForecastSensor(hub.basic_data, hub.hass)
    _anchor(hub, "base_station", age_hours=48, value=0)
    await hub.on_base_station_time(json.dumps({"int_value": 3000}))

    assert sensor.native_value is not None
    assert (
        sensor.extra_state_attributes["recommended_cycle"]
        == BASE_STATION_MAINTENANCE_CYCLE_MINUTES
    )


async def test_sensor_without_usable_data(hub: TerraMowHub) -> None:
    sensor = BladeWearForecastSensor(hub.basic_data, hub.hass)

    await hub.on_blade_time(json.dumps({"other": 1}))
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["used_minutes"] is None

    await hub.on_blade_time("[1, 2]")
    assert sensor.native_value is None


async def test_sensor_without_a_hub(hub: TerraMowHub) -> None:
    sensor = BladeWearForecastSensor(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
