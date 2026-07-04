"""Assert the quality_scale.yaml is complete and consistent (Platinum audit)."""

import yaml
from pathlib import Path

_GOLD = {
    "devices", "diagnostics", "discovery", "discovery-update-info",
    "docs-data-update", "docs-examples", "docs-known-limitations",
    "docs-supported-devices", "docs-supported-functions", "docs-troubleshooting",
    "docs-use-cases", "dynamic-devices", "entity-category", "entity-device-class",
    "entity-disabled-by-default", "entity-translations", "exception-translations",
    "icon-translations", "reconfiguration-flow", "repair-issues", "stale-devices",
}

_PLATINUM = {"async-dependency", "inject-websession", "strict-typing"}


def _rules() -> dict:
    data = yaml.safe_load(
        Path("custom_components/terramow/quality_scale.yaml").read_text(encoding="utf-8")
    )
    return data["rules"]


def _status(value) -> str:
    return value if isinstance(value, str) else value["status"]


def test_all_gold_rules_are_done_or_exempt() -> None:
    rules = _rules()
    for rule in _GOLD:
        assert rule in rules, f"{rule} missing from quality_scale.yaml"
        assert _status(rules[rule]) in ("done", "exempt"), rule


def test_all_platinum_rules_are_done_or_exempt() -> None:
    rules = _rules()
    for rule in _PLATINUM:
        assert rule in rules, f"{rule} missing from quality_scale.yaml"
        assert _status(rules[rule]) in ("done", "exempt"), rule


def test_manifest_declares_platinum() -> None:
    import json

    manifest = json.loads(
        Path("custom_components/terramow/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["quality_scale"] == "platinum"
