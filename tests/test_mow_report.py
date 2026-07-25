"""Tests for the mow-report image and the hub snapshot behind it.

The report exists because the device destroys the evidence: when a session
ends it zeroes the dp_113 counters, and the next session clears the cycle
coverage. These tests pin that the snapshot is taken while the data is still
there, that it describes one session, and that the rendered picture keeps
showing that session afterwards.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.image import (
    MowReportImage,
    async_setup_entry as image_setup,
)
from custom_components.terramow.map_render import _format_duration, render_mow_report
from custom_components.terramow.map_scene import build_scene

HOST = "192.0.2.10"

WORK_RUNNING = {
    "clean_area": 1234,  # 0.1 m² units -> 123.4 m²
    "total_area": 1500,
    "work_duration": 105,
    "type": "CLEAN_TYPE_GLOBAL",
}

MAP_DATA: dict[str, Any] = {
    "id": 7,
    "name": "Garden",
    "total_area": 1500,
    "resolution": 50,
    "origin": {"x": 0, "y": 0},
    "size": {"width": 200, "height": 200},
}


def _mission(mission: str, state: str) -> str:
    return json.dumps(
        {"mission": mission, "sub_mission": "SUB_MISSION_IDLE", "state": state}
    )


@pytest.fixture(name="hub")
async def hub_fixture(hass: HomeAssistant) -> TerraMowHub:
    """A hub mid-session: counters reported, coverage accumulated."""
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value = MagicMock(rc=0)
    hub._map_data = dict(MAP_DATA)
    hub._coverage_segments = [[{"x": 0, "y": 0}, {"x": 1000, "y": 1000}]]
    await hub.on_current_work_data(json.dumps(WORK_RUNNING))
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    )
    return hub


# ---------------------------------------------------------------------------
# hub snapshot
# ---------------------------------------------------------------------------


async def test_no_report_before_a_session_ends(hub: TerraMowHub) -> None:
    assert hub.last_mow_report is None


async def test_completion_captures_the_session_numbers(hub: TerraMowHub) -> None:
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )

    report = hub.last_mow_report
    assert report is not None
    assert report["outcome"] == "completed"
    assert report["area_m2"] == 123.4
    assert report["total_area_m2"] == 150.0
    assert report["duration_min"] == 105.0
    assert report["job_type"] == "CLEAN_TYPE_GLOBAL"
    assert report["map_id"] == 7
    assert isinstance(report["finished_at"], datetime)


async def test_abort_is_recorded_as_such(hub: TerraMowHub) -> None:
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_ABORT")
    )
    assert hub.last_mow_report is not None
    assert hub.last_mow_report["outcome"] == "aborted"


async def test_report_keeps_the_track_the_next_session_clears(
    hub: TerraMowHub,
) -> None:
    """The snapshot copies the coverage, so a new session cannot rewrite it."""
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )
    report = hub.last_mow_report
    assert report is not None
    captured = report["coverage_segments"]
    assert captured == [[{"x": 0, "y": 0}, {"x": 1000, "y": 1000}]]

    # A new session starts: the live coverage resets (issue #202) …
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    )
    assert hub.coverage_segments == []
    # … and the report still holds the finished session's track.
    assert report["coverage_segments"] == captured


async def test_manual_job_end_captures_before_dropping_the_coverage(
    hub: TerraMowHub,
) -> None:
    """Ending the job in the vendor app zeroes everything — snapshot first."""
    await hub.on_mission_status(_mission("MISSION_IDLE", "MISSION_STATE_IDLE"))
    await hub.on_current_work_data(
        json.dumps({"clean_area": 0, "total_area": 0, "work_duration": 0})
    )

    report = hub.last_mow_report
    assert report is not None
    assert report["outcome"] == "aborted"
    assert hub.coverage_segments == []
    assert report["coverage_segments"] == [[{"x": 0, "y": 0}, {"x": 1000, "y": 1000}]]


async def test_capture_survives_missing_and_unparsable_counters(
    hass: HomeAssistant,
) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="secret"), hass)
    hub._current_work_data = {"clean_area": "abc", "work_duration": None}
    hub._capture_mow_report("completed")

    report = hub.last_mow_report
    assert report is not None
    assert report["area_m2"] is None
    assert report["total_area_m2"] is None
    assert report["duration_min"] is None
    assert report["job_type"] is None

    # A non-dict dp_113 cache must not raise either.
    hub._current_work_data = None  # type: ignore[assignment]
    hub._capture_mow_report("aborted")
    assert hub.last_mow_report is not None
    assert hub.last_mow_report["outcome"] == "aborted"


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutes", "text"),
    [
        (None, "—"),
        (-1.0, "—"),
        (0.0, "0 min"),
        (45.0, "45 min"),
        (105.0, "1 h 45 min"),
        (120.0, "2 h 0 min"),
    ],
)
def test_format_duration(minutes: float | None, text: str) -> None:
    assert _format_duration(minutes) == text


def _render(report: dict[str, Any], **kwargs: Any) -> bytes:
    scene = build_scene(
        dict(MAP_DATA),
        {},
        {},
        True,
        session_path_segments=[[{"x": 0, "y": 0}, {"x": 1000, "y": 1000}]],
    )
    return render_mow_report(
        scene,
        dict(MAP_DATA),
        report=report,
        theme=kwargs.get("theme", "light"),
        language=kwargs.get("language", "en"),
        output_resolution=kwargs.get("output_resolution", 1024),
        finished_local=datetime(2026, 7, 25, 18, 30),
    )


def test_render_produces_a_png() -> None:
    png = _render(
        {
            "outcome": "completed",
            "area_m2": 123.4,
            "total_area_m2": 150.0,
            "duration_min": 105.0,
            "job_type": "CLEAN_TYPE_GLOBAL",
        }
    )
    assert png.startswith(b"\x89PNG")


def test_render_handles_an_aborted_report_without_numbers() -> None:
    png = _render(
        {
            "outcome": "aborted",
            "area_m2": None,
            "total_area_m2": None,
            "duration_min": None,
            "job_type": None,
        },
        theme="dark",
        language="de",
        output_resolution=512,
    )
    assert png.startswith(b"\x89PNG")


def test_render_without_a_total_area_shows_the_bare_area() -> None:
    png = _render(
        {
            "outcome": "completed",
            "area_m2": 42.0,
            "total_area_m2": 0,
            "duration_min": 10.0,
            "job_type": "CLEAN_TYPE_GLOBAL",
        }
    )
    assert png.startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# image entity
# ---------------------------------------------------------------------------


async def test_setup_creates_the_image_entity(hub: TerraMowHub) -> None:
    added: list[Any] = []
    entry = SimpleNamespace(
        entry_id="e1", runtime_data=hub.basic_data, options={}
    )
    await image_setup(hub.hass, entry, added.extend)  # type: ignore[arg-type]
    assert len(added) == 1
    assert isinstance(added[0], MowReportImage)


async def test_image_is_unavailable_until_a_session_ends(hub: TerraMowHub) -> None:
    image = MowReportImage(hub.basic_data, hub.hass)
    assert image.available is False
    assert image.extra_state_attributes == {}
    assert await image.async_image() is None


async def test_image_renders_and_exposes_the_session_numbers(
    hub: TerraMowHub,
) -> None:
    image = MowReportImage(hub.basic_data, hub.hass)
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )

    assert image.available is True
    attributes = image.extra_state_attributes
    assert attributes["outcome"] == "completed"
    assert attributes["area_m2"] == 123.4
    assert attributes["duration_min"] == 105.0
    assert attributes["job_type"] == "CLEAN_TYPE_GLOBAL"
    assert attributes["map_id"] == 7
    assert attributes["finished_at"].endswith("+00:00")

    png = await image.async_image()
    assert png is not None and png.startswith(b"\x89PNG")


async def test_image_is_rendered_once_per_session(hub: TerraMowHub) -> None:
    """The held bytes are reused until a newer session ends."""
    image = MowReportImage(hub.basic_data, hub.hass)
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )

    first = await image.async_image()
    renders: list[int] = []
    original = image._render

    def _counting(report: dict[str, Any]) -> bytes:
        renders.append(1)
        return original(report)

    image._render = _counting  # type: ignore[method-assign]
    assert await image.async_image() is first
    assert not renders, "a second fetch re-rendered the same session"

    # A new session ends: the next fetch must render again.
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_RUNNING")
    )
    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )
    await image.async_image()
    assert renders == [1]


async def test_push_update_refreshes_the_timestamp(hub: TerraMowHub) -> None:
    image = MowReportImage(hub.basic_data, hub.hass)
    assert image.image_last_updated is None

    await hub.on_mission_status(
        _mission("MISSION_GLOBAL_CLEAN", "MISSION_STATE_COMPLETE")
    )
    await image._handle_push_update("{}")

    report = hub.last_mow_report
    assert report is not None
    assert image.image_last_updated == report["finished_at"]

    # A repeat push for the same session leaves the held render alone.
    await image.async_image()
    held = image._rendered
    await image._handle_push_update("{}")
    assert image._rendered is held


async def test_push_update_without_a_report_is_a_no_op(hub: TerraMowHub) -> None:
    image = MowReportImage(hub.basic_data, hub.hass)
    await image._handle_push_update("{}")
    assert image.image_last_updated is None


async def test_image_without_a_hub_reports_nothing(hub: TerraMowHub) -> None:
    image = MowReportImage(hub.basic_data, hub.hass)
    hub.basic_data.lawn_mower = None
    assert image.available is False
    assert image.extra_state_attributes == {}
    assert await image.async_image() is None


async def test_added_to_hass_without_a_hub_registers_nothing(
    hass: HomeAssistant,
) -> None:
    basic_data = TerraMowBasicData(host=HOST, password="secret")
    image = MowReportImage(basic_data, hass)
    image.entity_id = "image.terramow_mow_report"
    await image.async_added_to_hass()  # returns early, no callbacks
