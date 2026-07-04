"""Validate the icons.json translations (Gold quality scale)."""

import json
from pathlib import Path

_BASE = Path("custom_components/terramow")


def _load(name: str) -> dict:
    return json.loads((_BASE / name).read_text(encoding="utf-8"))


def test_icons_json_is_well_formed() -> None:
    icons = _load("icons.json")
    assert "entity" in icons
    for platform, keys in icons["entity"].items():
        assert isinstance(keys, dict) and keys
        for key, spec in keys.items():
            assert spec.get("default", "").startswith("mdi:"), f"{platform}/{key}"


def test_every_icon_key_matches_a_translation_key() -> None:
    icons = _load("icons.json")["entity"]
    strings = _load("strings.json")["entity"]
    for platform, keys in icons.items():
        assert platform in strings, platform
        for key in keys:
            assert key in strings[platform], f"{platform}/{key} missing from strings.json"


def test_platform_modules_no_longer_hardcode_icons() -> None:
    # icons.json is the single source of truth; entities must not also set
    # a hard-coded _attr_icon (which would shadow the translation).
    for module in _BASE.glob("*.py"):
        assert '_attr_icon = "mdi' not in module.read_text(encoding="utf-8"), module.name
