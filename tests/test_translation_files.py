"""Every translation file must stay key-complete and keep the App terminology.

``test_translation_keys.py`` checks that the keys the code uses exist in
``strings.json``; this module checks the other direction: every shipped
language mirrors the English key set, keeps its format placeholders, and the
English source matches ``strings.json``. The App-term assertions pin the
wording TerraMow uses in its own App so it isn't silently reverted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import custom_components.terramow as integration

COMPONENT_DIR = Path(integration.__file__).parent
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"
PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _leaves(value: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    if isinstance(value, dict):
        out: dict[tuple[str, ...], str] = {}
        for key, child in value.items():
            out.update(_leaves(child, (*path, key)))
        return out
    assert isinstance(value, str), ".".join(path)
    return {path: value}


def _translation_files() -> list[Path]:
    # zh-CN.json is a symlink to zh-Hans.json; on checkouts without symlink
    # support it is a one-line text file naming its target.
    return [
        path
        for path in sorted(TRANSLATIONS_DIR.glob("*.json"))
        if path.read_text(encoding="utf-8").lstrip().startswith("{")
    ]


ENGLISH = _leaves(_load(TRANSLATIONS_DIR / "en.json"))


@pytest.mark.parametrize("path", _translation_files(), ids=lambda p: p.stem)
def test_translation_file_matches_english_keys_and_placeholders(path: Path) -> None:
    values = _leaves(_load(path))
    assert set(values) == set(ENGLISH)
    for key, english in ENGLISH.items():
        assert values[key].strip(), ".".join(key)
        assert set(PLACEHOLDER.findall(values[key])) == set(
            PLACEHOLDER.findall(english)
        ), ".".join(key)


def test_english_translation_mirrors_strings_json() -> None:
    source = _leaves(_load(COMPONENT_DIR / "strings.json"))
    assert set(source) == set(ENGLISH)
    # Outside ``[%key:...%]`` references (resolved by HA's common strings),
    # the English file is the source text verbatim.
    for key, text in source.items():
        if not text.startswith("[%key:"):
            assert ENGLISH[key] == text, ".".join(key)


def test_nynorsk_is_shipped() -> None:
    assert (TRANSLATIONS_DIR / "nn.json").is_file()


@pytest.mark.parametrize(
    ("key", "term"),
    [
        ("entity.lawn_mower.lawn_mower.name", "Mower"),
        ("entity.sensor.mow_height.name", "Cutting Height"),
        ("entity.sensor.mow_speed.name", "Moving Speed"),
        ("entity.sensor.mow_speed.state.mow_speed_type_low", "Fine"),
        ("entity.sensor.mow_speed.state.mow_speed_type_medium", "Default"),
        ("entity.sensor.mow_speed.state.mow_speed_type_adaptive_high", "Adaptive"),
        ("entity.sensor.clean_mode.name", "Mowing Mode"),
        ("entity.sensor.clean_mode.state.map_clean_info_mode_global", "Auto Mowing"),
        (
            "entity.sensor.clean_mode.state.map_clean_info_mode_draw_region",
            "MowBox Mowing",
        ),
        ("entity.sensor.mission.state.mission_build_map", "Mapping"),
        ("entity.sensor.active_job.state.mission_edge_trim_clean", "Edge Mowing"),
        ("entity.binary_sensor.lift_alarm.name", "Robot Lifted Alert"),
        ("entity.select.mow_speed_setting.name", "Moving Speed"),
        (
            "entity.select.main_direction_mode.state.main_direction_mode_multiple",
            "Dual",
        ),
    ],
)
def test_english_uses_app_terminology(key: str, term: str) -> None:
    assert ENGLISH[tuple(key.split("."))] == term
