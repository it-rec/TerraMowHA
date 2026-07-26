"""Measured battery-health aggregation and hub integration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.battery_health import (
    BATTERY_HEALTH_MAX_AGE_SECONDS,
    BATTERY_HEALTH_MAX_RECORDS,
    BatteryHealthTracker,
    _number,
    settings_signature,
)
from custom_components.terramow.hub import Mission, TerraMowHub


def _observe(
    tracker: BatteryHealthTracker,
    level: int,
    area: float,
    duration: float,
    now: float,
    *,
    mowing: bool = True,
    charging: bool = False,
    map_id: int = 1,
    speed: str = "medium",
) -> None:
    tracker.observe(
        level=level,
        charger_connected=charging,
        is_mowing=mowing,
        work={"clean_area": area, "work_duration": duration},
        map_id=map_id,
        settings={"mow_speed_type": speed, "unrelated": now},
        now=now,
    )


def _hub() -> TerraMowHub:
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.216", password="secret"),
        MagicMock(),
    )


def test_number_and_settings_signature_are_defensive() -> None:
    assert _number(1) == 1
    assert _number(True) is None
    assert _number("1") is None
    assert _number(float("nan")) is None
    assert _number(float("inf")) is None
    assert settings_signature(
        {"mow_speed_type": "low", "unrelated": 1, "mow_spacing": 100}
    ) == '{"mow_spacing":100,"mow_speed_type":"low"}'


def test_discharge_metrics_and_relative_trend() -> None:
    tracker = BatteryHealthTracker()
    _observe(tracker, 100, 0, 0, 0)
    for index, level in enumerate((90, 80, 70), start=1):
        _observe(tracker, level, index * 100, index * 600, index * 600)
    for index, level in enumerate((60, 50, 40), start=4):
        area = 300 + (index - 3) * 50
        _observe(tracker, level, area, index * 600, index * 600)

    metrics = tracker.metrics(
        map_id=1, settings={"mow_speed_type": "medium"}, now=4000
    )
    assert metrics["discharge_samples"] == 6
    assert metrics["area_m2_per_10_percent"] == 7.5
    assert metrics["mowing_minutes_per_10_percent"] == 10
    assert metrics["area_efficiency_trend_percent"] == -50
    assert metrics["confidence"] == "medium"
    assert metrics["observation_start"] == 600
    assert metrics["observation_end"] == 3600

    # A map or relevant setting change is not silently pooled.
    assert (
        tracker.metrics(map_id=2, settings={"mow_speed_type": "medium"}, now=4000)[
            "area_m2_per_10_percent"
        ]
        is None
    )
    assert (
        tracker.metrics(map_id=1, settings={"mow_speed_type": "low"}, now=4000)[
            "discharge_samples"
        ]
        == 0
    )

    zero_baseline = BatteryHealthTracker()
    zero_baseline.restore(
        {
            "discharge_records": [
                {
                    "ended_at": index,
                    "map_id": 1,
                    "settings": "{}",
                    "drop": 10,
                    "area_m2": 0,
                    "duration_seconds": 60,
                }
                for index in range(6)
            ],
            "charge_records": [],
        },
        6,
    )
    assert zero_baseline.metrics(map_id=1, settings={}, now=6)[
        "area_efficiency_trend_percent"
    ] is None


def test_partial_incomparable_and_invalid_windows_are_classified() -> None:
    tracker = BatteryHealthTracker()
    _observe(tracker, 90, 10, 10, 0)
    _observe(tracker, 88, 20, 20, 10, mowing=False)
    assert tracker.partial_discharges == 1

    _observe(tracker, 80, 20, 20, 20)
    _observe(tracker, 81, 30, 30, 30)
    _observe(tracker, 70, 40, 40, 40, speed="low")
    _observe(tracker, 60, 30, 30, 50, speed="low")
    assert tracker.partial_discharges == 3
    assert tracker.discharge_records == []

    tracker.observe(
        level=None,
        charger_connected=False,
        is_mowing=True,
        work={},
        map_id=1,
        settings={},
        now=60,
    )
    tracker.observe(
        level=101,
        charger_connected=False,
        is_mowing=True,
        work={},
        map_id=1,
        settings={},
        now=60,
    )


def test_charge_window_interruption_and_metrics() -> None:
    tracker = BatteryHealthTracker()
    _observe(tracker, 20, 0, 0, 0, mowing=False, charging=True)
    _observe(tracker, 80, 0, 0, 3600, mowing=False, charging=True)
    metrics = tracker.metrics(map_id=1, settings={}, now=3600)
    assert metrics["charge_20_80_minutes"] == 60
    assert metrics["charge_percent_per_hour"] == 60
    assert metrics["charge_samples"] == 1

    _observe(tracker, 15, 0, 0, 4000, mowing=False, charging=True)
    _observe(tracker, 30, 0, 0, 4100, mowing=False, charging=False)
    assert tracker.interrupted_charges == 1

    # A non-positive elapsed window is discarded instead of guessed.
    _observe(tracker, 20, 0, 0, 5000, mowing=False, charging=True)
    _observe(tracker, 80, 0, 0, 5000, mowing=False, charging=True)
    assert len(tracker.charge_records) == 1


def test_restore_expiry_caps_sources_and_reset() -> None:
    tracker = BatteryHealthTracker()
    fresh = {
        "ended_at": BATTERY_HEALTH_MAX_AGE_SECONDS + 1,
        "map_id": 1,
        "settings": "{}",
        "drop": 10,
        "area_m2": 1,
        "duration_seconds": 60,
    }
    tracker.restore(
        {
            "discharge_records": [
                {"ended_at": 0},
                *[dict(fresh, ended_at=fresh["ended_at"] + index) for index in range(40)],
                "bad",
            ],
            "charge_records": "bad",
            "partial_discharges": 2,
            "interrupted_charges": 3,
        },
        BATTERY_HEALTH_MAX_AGE_SECONDS + 10,
    )
    assert len(tracker.discharge_records) == BATTERY_HEALTH_MAX_RECORDS
    assert tracker.metrics(map_id=1, settings={}, now=BATTERY_HEALTH_MAX_AGE_SECONDS + 10)[
        "source"
    ] == "restored"

    _observe(
        tracker,
        50,
        0,
        0,
        BATTERY_HEALTH_MAX_AGE_SECONDS + 11,
        mowing=False,
    )
    assert tracker.metrics(
        map_id=1, settings={}, now=BATTERY_HEALTH_MAX_AGE_SECONDS + 11
    )["source"] == "revalidated"
    _observe(
        tracker,
        49,
        0,
        0,
        BATTERY_HEALTH_MAX_AGE_SECONDS + 12,
        mowing=False,
    )
    assert tracker.metrics(
        map_id=1, settings={}, now=BATTERY_HEALTH_MAX_AGE_SECONDS + 12
    )["source"] == "live"

    dumped = tracker.dump()
    assert len(dumped["discharge_records"]) == BATTERY_HEALTH_MAX_RECORDS
    tracker.reset()
    assert tracker.metrics(map_id=1, settings={}, now=1)["confidence"] == "unavailable"
    tracker.restore(None, 1)


async def test_hub_feeds_persists_restores_and_resets_aggregates() -> None:
    hub = _hub()
    hub._map_data = {"id": 1}
    hub._global_params = {"mow_speed_type": "medium"}
    hub.mission = Mission.MISSION_GLOBAL_CLEAN
    with patch("custom_components.terramow.hub.dt_util.utcnow") as now:
        # a controllable clock: other trackers hooked into the same dp
        # handlers may sample the time too, so a finite list would exhaust
        clock = {"now": 2_000_000_000}
        now.return_value.timestamp.side_effect = lambda: clock["now"]
        await hub.on_battery_level('{"int_value": 100}')
        await hub.on_current_work_data(
            json.dumps({"clean_area": 0, "work_duration": 0})
        )
        clock["now"] = 2_000_000_600
        await hub.on_battery_level('{"int_value": 90}')
        await hub.on_current_work_data(
            json.dumps({"clean_area": 100, "work_duration": 600})
        )
    assert hub.battery_health_metrics["discharge_samples"] == 1
    store = hub._get_battery_health_store()
    callback = store.async_delay_save.call_args.args[0]
    assert len(callback()["discharge_records"]) == 1

    store.async_load = AsyncMock(return_value=callback())
    await hub.async_restore_battery_health()
    assert hub.battery_health_metrics["source"] == "restored"
    store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_battery_health()
    store.async_save = AsyncMock()
    await hub.async_reset_battery_health()
    store.async_save.assert_awaited_once()


async def test_hub_ignores_invalid_battery_payloads() -> None:
    hub = _hub()
    await hub.on_battery_level("bad")
    await hub.on_battery_level('{"int_value": true}')
    await hub.on_battery_status("bad")
    assert hub.battery_level is None
