"""Measured selective-mission preflight history."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import MissionState, TerraMowHub
from custom_components.terramow.mission_preflight import (
    PREFLIGHT_MAX_AGE_SECONDS,
    PREFLIGHT_MAX_RECORDS,
    MissionPreflightTracker,
    mow_settings_signature,
    zone_geometry_signature,
)


def _map(map_id: int = 1) -> dict[str, object]:
    return {
        "id": map_id,
        "regions": [
            {
                "sub_regions": [
                    {
                        "id": 2,
                        "boundary": {
                            "points": [
                                {"x": 0, "y": 0},
                                {"x": 1, "y": 0},
                                {"x": 1, "y": 1},
                            ]
                        },
                    },
                    {"id": 3, "boundary": {"points": [{"x": 2, "y": 2}]}},
                ]
            }
        ],
    }


def _hub() -> TerraMowHub:
    return TerraMowHub(
        TerraMowBasicData(host="192.0.2.217", password="secret"),
        MagicMock(),
    )


def test_signatures_require_exact_reported_zones_and_settings() -> None:
    assert zone_geometry_signature(_map(), [2]) is not None
    assert zone_geometry_signature(_map(), [99]) is None
    assert zone_geometry_signature({"regions": ["bad"]}, [2]) is None
    assert zone_geometry_signature({"regions": [{"sub_regions": ["bad"]}]}, [2]) is None
    assert mow_settings_signature({"mow_speed_type": "low", "other": 1}) == (
        '{"mow_speed_type":"low"}'
    )


def test_fresh_install_and_completed_observation_estimate() -> None:
    tracker = MissionPreflightTracker()
    now = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    started_at = now.timestamp() - 3600
    assert tracker.estimate(
        region_ids=[2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=80,
        sunset={"hour": 20, "minute": 0},
        now=now,
    ) == {"available": False, "sample_count": 0, "source": "live"}

    assert tracker.begin(
        region_ids=[2, 2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=80,
        charger_connected=False,
        now=started_at,
    )
    tracker.observe(
        battery_level=70,
        charger_connected=True,
        completed=False,
        aborted=False,
        work={},
        map_id=1,
        geometry="g",
        settings={},
        now=started_at + 300,
    )
    tracker.observe(
        battery_level=65,
        charger_connected=False,
        completed=True,
        aborted=False,
        work={"work_duration": 3600},
        map_id=1,
        geometry="g",
        settings={},
        now=now.timestamp(),
    )
    estimate = tracker.estimate(
        region_ids=[2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=50,
        sunset={"hour": 12, "minute": 30},
        now=now,
    )
    assert estimate["duration_seconds"] == 3600
    assert estimate["battery_percent"] == 15
    assert estimate["battery_margin_percent"] == 35
    assert estimate["recharge_legs"] == 1
    assert estimate["daylight_warning"] is True
    assert estimate["confidence"] == "low"


def test_incomplete_ambiguous_and_invalid_sessions_are_excluded() -> None:
    tracker = MissionPreflightTracker()
    assert not tracker.begin(
        region_ids=[],
        map_id=1,
        geometry=None,
        settings={},
        battery_level=None,
        charger_connected=False,
        now=0,
    )
    assert tracker.begin(
        region_ids=[2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=None,
        charger_connected=False,
        now=0,
    )
    tracker.observe(
        battery_level=None,
        charger_connected=False,
        completed=False,
        aborted=True,
        work={},
        map_id=1,
        geometry="g",
        settings={},
        now=1,
    )
    assert tracker.records == []

    for duration, geometry in ((0, "g"), (10, "changed")):
        tracker.begin(
            region_ids=[2],
            map_id=1,
            geometry="g",
            settings={},
            battery_level=50,
            charger_connected=False,
            now=0,
        )
        tracker.observe(
            battery_level=40,
            charger_connected=False,
            completed=True,
            aborted=False,
            work={"work_duration": duration},
            map_id=1,
            geometry=geometry,
            settings={},
            now=10,
        )
    assert tracker.records == []


def test_restore_expiry_cap_revalidation_and_invalid_sunset() -> None:
    tracker = MissionPreflightTracker()
    record = {
        "ended_at": PREFLIGHT_MAX_AGE_SECONDS + 1,
        "region_ids": [2],
        "map_id": 1,
        "geometry": "g",
        "settings": "{}",
        "duration_seconds": 60,
        "battery_used": 1,
        "recharge_legs": 0,
    }
    tracker.restore(
        {
            "records": [
                {"ended_at": 0},
                *[dict(record, ended_at=record["ended_at"] + i) for i in range(40)],
                "bad",
            ]
        },
        PREFLIGHT_MAX_AGE_SECONDS + 10,
    )
    assert len(tracker.dump()["records"]) == PREFLIGHT_MAX_RECORDS
    assert tracker.source == "restored"
    tracker.revalidate()
    assert tracker.source == "revalidated"
    tracker.revalidate()
    tracker.restore(None, 0)

    result = tracker.estimate(
        region_ids=[2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=None,
        sunset={"hour": 99, "minute": 0},
        now=datetime.fromtimestamp(PREFLIGHT_MAX_AGE_SECONDS + 10, tz=UTC),
    )
    assert result["daylight_warning"] is None
    assert result["battery_margin_percent"] is None


def test_estimate_ignores_malformed_sunset_fields() -> None:
    tracker = MissionPreflightTracker()
    tracker.restore(
        {
            "records": [
                {
                    "ended_at": 100.0,
                    "region_ids": [2],
                    "map_id": 1,
                    "geometry": "g",
                    "settings": "{}",
                    "duration_seconds": 60,
                    "battery_used": 1,
                    "recharge_legs": 0,
                }
            ]
        },
        100.0,
    )
    # hour/minute must both be ints; a malformed sunset keeps the warning unknown
    result = tracker.estimate(
        region_ids=[2],
        map_id=1,
        geometry="g",
        settings={},
        battery_level=50,
        sunset={"hour": "seven", "minute": 30},
        now=datetime.fromtimestamp(200.0, tz=UTC),
    )
    assert result["daylight_warning"] is None


async def test_hub_starts_measures_restores_and_catalogs() -> None:
    hub = _hub()
    hub._map_data = _map()
    hub._battery_level = 80
    hub.async_publish_with_ack = AsyncMock()
    with patch("custom_components.terramow.hub.dt_util.utcnow") as utcnow:
        utcnow.return_value.timestamp.return_value = 2_000_000_000
        await hub.async_start_select_region_clean([2])
    assert hub._mission_preflight.active is not None

    hub._battery_level = 70
    hub._current_work_data = {"work_duration": 600}
    hub.mission_state = MissionState.MISSION_STATE_COMPLETE
    with patch("custom_components.terramow.hub.dt_util.utcnow") as utcnow:
        utcnow.return_value.timestamp.return_value = 2_000_000_600
        hub._observe_mission_preflight()
    assert len(hub._mission_preflight.records) == 1
    assert hub.mission_preflight_catalog["2"]["available"] is True

    store = hub._get_preflight_store()
    store.async_load = AsyncMock(return_value=hub._mission_preflight.dump())
    await hub.async_restore_mission_preflight()
    assert hub._mission_preflight.source == "restored"
    # a different map must not revalidate the parked records
    mismatched = _map()
    mismatched["id"] = 999
    hub._apply_map_data(mismatched)
    assert hub._mission_preflight.source == "restored"
    hub._apply_map_data(_map())
    assert hub._mission_preflight.source == "revalidated"
    callback = store.async_delay_save.call_args.args[0]
    assert len(callback()["records"]) == 1

    store.async_load = AsyncMock(side_effect=OSError("broken"))
    await hub.async_restore_mission_preflight()
