"""Tests for the firmware version compatibility check."""

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    CURRENT_HA_VERSION,
    MIN_REQUIRED_OVERALL_VERSION,
    CompatibilityStatus,
)


def _info(overall: int, ha_version: int) -> dict:
    return {"overall": overall, "module": {"home_assistant": ha_version}}


def _basic_data() -> TerraMowBasicData:
    return TerraMowBasicData(host="192.0.2.1", password="secret")


def test_overall_version_too_low_requires_upgrade() -> None:
    data = _basic_data()
    status = data.check_version_compatibility(
        _info(MIN_REQUIRED_OVERALL_VERSION - 1, CURRENT_HA_VERSION)
    )
    assert status == CompatibilityStatus.UPGRADE_REQUIRED
    assert data.compatibility_reason.startswith("overall_version_low:")


def test_ha_version_below_minimum_requires_upgrade() -> None:
    data = _basic_data()
    status = data.check_version_compatibility(_info(MIN_REQUIRED_OVERALL_VERSION, 1))
    assert status == CompatibilityStatus.UPGRADE_REQUIRED
    assert data.compatibility_reason == "ha_version_low:1"


def test_supported_older_ha_version_is_compatible() -> None:
    """Regression test for upstream issue #79 (S800 reports version 2)."""
    data = _basic_data()
    status = data.check_version_compatibility(_info(MIN_REQUIRED_OVERALL_VERSION, 2))
    assert status == CompatibilityStatus.COMPATIBLE
    assert data.compatibility_reason == "ha_version_limited:2"
    data.compatibility_status = status
    message = data.get_compatibility_message()
    assert "version 3" in message
    assert "upgrade" not in message.lower()


def test_current_ha_version_is_fully_compatible() -> None:
    data = _basic_data()
    status = data.check_version_compatibility(
        _info(MIN_REQUIRED_OVERALL_VERSION, CURRENT_HA_VERSION)
    )
    assert status == CompatibilityStatus.COMPATIBLE
    assert data.compatibility_reason == ""
    data.compatibility_status = status
    assert data.get_compatibility_message() == (
        "Version compatible, all functions working"
    )


def test_newer_ha_version_recommends_downgrade() -> None:
    data = _basic_data()
    status = data.check_version_compatibility(
        _info(MIN_REQUIRED_OVERALL_VERSION, CURRENT_HA_VERSION + 1)
    )
    assert status == CompatibilityStatus.DOWNGRADE_RECOMMENDED
    assert data.compatibility_reason.startswith("ha_version_high:")


def test_malformed_payload_reports_incompatible() -> None:
    data = _basic_data()
    assert (
        data.check_version_compatibility({"module": None})
        == CompatibilityStatus.INCOMPATIBLE
    )
