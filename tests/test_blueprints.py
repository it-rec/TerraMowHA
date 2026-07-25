"""Validate every shipped automation blueprint.

Blueprints are YAML, so nothing else in the quality gate looks at them: a
broken template or a mistyped service name ships happily and only fails when
a user imports it. This loads each one the way Home Assistant does,
substitutes its inputs and runs the automation config validator over the
result — which is exactly the step that would reject it on import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    async_validate_config_item,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import loader as yaml_loader

from custom_components.terramow.const import DOMAIN

BLUEPRINT_DIR = Path("blueprints/automation/terramow")

# Plausible values for every input the shipped blueprints declare. A new
# blueprint input with no entry here fails the completeness test below, so
# this table cannot silently fall behind.
INPUT_VALUES: dict[str, Any] = {
    "mower": "lawn_mower.terramow",
    "mower_event": "event.terramow_mower_event",
    "weather_entity": "weather.home",
    "rain_sensor": "binary_sensor.terramow_rain_detected",
    "problem_sensor": "binary_sensor.terramow_problem",
    "mission_state_sensor": "sensor.terramow_mission_state",
    "back_to_station_reason_sensor": "sensor.terramow_back_to_station_reason",
    "gdd_helper": "input_number.terramow_gdd",
    "interrupted_helper": "input_boolean.terramow_quiet_hours",
    "paused_helper": "input_boolean.terramow_presence_paused",
    "presence_entities": ["binary_sensor.garden_gate", "binary_sensor.garden_motion"],
    "notify_action": {
        "action": "notify.persistent_notification",
        "data": {"message": "test"},
    },
    "start_time": "09:00:00",
    "evaluation_time": "10:00:00",
    "quiet_start": "20:00:00",
    "quiet_end": "08:00:00",
    "clear_for": {"hours": 0, "minutes": 3, "seconds": 0},
    "weekdays": ["mon", "wed"],
    "region_ids": [1, 2],
    "base_temperature": 10,
    "gdd_threshold": 50,
    "precipitation_probability": 40,
    "lookahead_hours": 3,
    "resume_after": True,
}


def _blueprint_paths() -> list[Path]:
    paths = sorted(BLUEPRINT_DIR.glob("*.yaml"))
    assert paths, "no blueprints found"
    return paths


def _load(path: Path) -> Blueprint:
    return Blueprint(
        yaml_loader.load_yaml(str(path)),
        expected_domain="automation",
        path=str(path),
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


@pytest.mark.parametrize(
    "path", _blueprint_paths(), ids=lambda path: path.name
)
def test_blueprint_metadata(path: Path) -> None:
    """Name, description and an importable source_url are all present."""
    blueprint = _load(path)
    metadata = blueprint.metadata

    assert metadata["name"].startswith("TerraMow"), "name should identify the device"
    assert metadata["description"].strip()
    # The import badges in the README point at this URL; a stale one imports
    # the wrong blueprint.
    assert metadata["source_url"].endswith(f"/{path.name}")
    assert blueprint.inputs, "a blueprint with no inputs is a plain automation"


@pytest.mark.parametrize(
    "path", _blueprint_paths(), ids=lambda path: path.name
)
def test_blueprint_inputs_are_all_covered_by_the_test_values(path: Path) -> None:
    """Keeps INPUT_VALUES honest as blueprints gain inputs."""
    missing = [name for name in _load(path).inputs if name not in INPUT_VALUES]
    assert not missing, f"add test values for {missing}"


@pytest.mark.parametrize(
    "path", _blueprint_paths(), ids=lambda path: path.name
)
async def test_blueprint_validates_as_an_automation(
    hass: HomeAssistant, path: Path
) -> None:
    """The substituted blueprint passes the validator Home Assistant runs.

    This is what catches a malformed template, an unknown action shape or a
    condition that cannot compile — the failures a user would otherwise hit
    at import time.
    """
    blueprint = _load(path)
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": path.name,
                "input": {
                    name: INPUT_VALUES[name]
                    for name in blueprint.inputs
                    if name in INPUT_VALUES
                },
            }
        },
    )
    config = inputs.async_substitute()
    config["alias"] = f"test {path.stem}"

    validated = await async_validate_config_item(hass, "automation", config)

    assert validated is not None, "the validator rejected the blueprint"
    assert validated.validation_status == "ok", validated.validation_error


@pytest.mark.parametrize(
    "path", _blueprint_paths(), ids=lambda path: path.name
)
def test_blueprint_only_calls_known_terramow_services(path: Path) -> None:
    """A typo in a service name would only surface when the automation runs."""
    raw = path.read_text(encoding="utf-8")
    known = {
        f"{DOMAIN}.start_select_region",
        f"{DOMAIN}.add_schedule",
        f"{DOMAIN}.delete_schedule",
    }
    for line in raw.splitlines():
        stripped = line.strip()
        for prefix in ("service: ", "action: "):
            if stripped.startswith(prefix):
                called = stripped[len(prefix) :].strip()
                if called.startswith(f"{DOMAIN}."):
                    assert called in known, f"unknown service {called}"
