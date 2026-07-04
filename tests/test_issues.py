"""Tests for the firmware compatibility repair issue."""

from unittest.mock import MagicMock, patch

from custom_components.terramow import TerraMowBasicData, issues
from custom_components.terramow.const import (
    CURRENT_HA_VERSION,
    DOMAIN,
    MIN_REQUIRED_OVERALL_VERSION,
    CompatibilityStatus,
)


def _basic_data(status: str, reason: str = "") -> TerraMowBasicData:
    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret", entry_id="e1")
    basic_data.compatibility_status = status
    basic_data.compatibility_reason = reason
    return basic_data


def _sync(basic_data):
    hass = MagicMock()
    with (
        patch.object(issues.ir, "async_create_issue") as create,
        patch.object(issues.ir, "async_delete_issue") as delete,
    ):
        issues.async_sync_compatibility_issue(hass, "e1", basic_data)
    return create, delete


def test_issue_id_is_scoped_to_entry() -> None:
    assert issues.compatibility_issue_id("abc") == "firmware_incompatible_abc"


def test_ha_module_too_low_raises_error_issue() -> None:
    create, delete = _sync(
        _basic_data(CompatibilityStatus.UPGRADE_REQUIRED, "ha_version_low:2")
    )
    create.assert_called_once()
    args, kwargs = create.call_args
    assert args[1] == DOMAIN
    assert args[2] == "firmware_incompatible_e1"
    assert kwargs["translation_key"] == "firmware_ha_module_too_low"
    assert kwargs["translation_placeholders"] == {
        "firmware_version": "2",
        "required_version": str(CURRENT_HA_VERSION),
    }
    assert kwargs["severity"] == issues.ir.IssueSeverity.ERROR
    assert kwargs["is_fixable"] is False
    assert kwargs["learn_more_url"]
    delete.assert_not_called()


def test_overall_version_too_low_raises_error_issue() -> None:
    create, delete = _sync(
        _basic_data(CompatibilityStatus.UPGRADE_REQUIRED, "overall_version_low:20")
    )
    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["translation_key"] == "firmware_overall_too_low"
    assert kwargs["translation_placeholders"] == {
        "required_version": str(MIN_REQUIRED_OVERALL_VERSION)
    }
    assert kwargs["severity"] == issues.ir.IssueSeverity.ERROR


def test_incompatible_raises_error_issue() -> None:
    create, _delete = _sync(_basic_data(CompatibilityStatus.INCOMPATIBLE))
    kwargs = create.call_args.kwargs
    assert kwargs["translation_key"] == "firmware_incompatible"
    assert kwargs["severity"] == issues.ir.IssueSeverity.ERROR


def test_downgrade_recommended_raises_warning_issue() -> None:
    create, _delete = _sync(
        _basic_data(CompatibilityStatus.DOWNGRADE_RECOMMENDED, "ha_version_high:9")
    )
    kwargs = create.call_args.kwargs
    assert kwargs["translation_key"] == "plugin_downgrade_recommended"
    assert kwargs["translation_placeholders"]["firmware_version"] == "9"
    assert kwargs["severity"] == issues.ir.IssueSeverity.WARNING


def test_compatible_clears_the_issue() -> None:
    create, delete = _sync(_basic_data(CompatibilityStatus.COMPATIBLE))
    create.assert_not_called()
    delete.assert_called_once()
    assert delete.call_args.args[1:] == (DOMAIN, "firmware_incompatible_e1")


def test_version_limited_is_treated_as_compatible() -> None:
    create, delete = _sync(
        _basic_data(CompatibilityStatus.COMPATIBLE, "ha_version_limited:2")
    )
    create.assert_not_called()
    delete.assert_called_once()


def test_clear_helper_deletes_issue() -> None:
    hass = MagicMock()
    with patch.object(issues.ir, "async_delete_issue") as delete:
        issues.async_clear_compatibility_issue(hass, "e1")
    delete.assert_called_once_with(hass, DOMAIN, "firmware_incompatible_e1")


def test_compatibility_info_creates_issue_end_to_end() -> None:
    """dp_127 payload with old firmware should raise the repair issue."""
    import asyncio
    import json

    from custom_components.terramow.hub import TerraMowHub

    basic_data = TerraMowBasicData(host="192.0.2.10", password="secret", entry_id="e1")
    hub = TerraMowHub(basic_data, MagicMock())

    with patch.object(issues.ir, "async_create_issue") as create:
        asyncio.run(
            hub.on_compatibility_info(
                json.dumps({"overall": 20, "module": {"home_assistant": 1}})
            )
        )
    create.assert_called_once()
    assert create.call_args.kwargs["translation_key"] == "firmware_overall_too_low"
