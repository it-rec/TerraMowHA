"""Repair issues surfaced by the TerraMow integration.

Firmware incompatibility was previously only reflected in the version
compatibility sensor, which is easy to miss. This raises a Home Assistant
repair issue (the actionable cards on the dashboard) so the user gets a
clear, translated prompt to update the mower firmware — and clears it
automatically once a compatible firmware reports in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
    CURRENT_HA_VERSION,
    DOMAIN,
    MIN_REQUIRED_OVERALL_VERSION,
    CompatibilityStatus,
)

if TYPE_CHECKING:
    from . import TerraMowBasicData

# The requirements section of the README documents the supported versions.
DOCS_URL = "https://github.com/TerraMow/TerraMowHA#requirements"

BLADE_MAINTENANCE_ISSUE = "blade_maintenance_due"
BASE_STATION_MAINTENANCE_ISSUE = "base_station_maintenance_due"


def compatibility_issue_id(entry_id: str) -> str:
    """Return the per-config-entry issue id for the compatibility repair."""
    return f"firmware_incompatible_{entry_id}"


def _reason_version(reason: str) -> str:
    """Extract the version suffix from a ``prefix:version`` reason string."""
    if ":" in reason:
        return reason.split(":", 1)[1]
    return "unknown"


@callback
def async_sync_compatibility_issue(
    hass: HomeAssistant,
    entry_id: str,
    basic_data: TerraMowBasicData,
) -> None:
    """Create, update or clear the firmware compatibility repair issue.

    Mirrors the compatibility status computed from the firmware info: an
    incompatible or upgrade-required firmware raises an issue, while a
    compatible one (including the version-limited case) clears it.
    """
    issue_id = compatibility_issue_id(entry_id)
    status = basic_data.compatibility_status
    reason = basic_data.compatibility_reason or ""

    if status == CompatibilityStatus.UPGRADE_REQUIRED:
        if reason.startswith("ha_version_low:"):
            translation_key = "firmware_ha_module_too_low"
            placeholders = {
                "firmware_version": _reason_version(reason),
                "required_version": str(CURRENT_HA_VERSION),
            }
        else:
            translation_key = "firmware_overall_too_low"
            placeholders = {"required_version": str(MIN_REQUIRED_OVERALL_VERSION)}
        severity = ir.IssueSeverity.ERROR
    elif status == CompatibilityStatus.INCOMPATIBLE:
        translation_key = "firmware_incompatible"
        placeholders = {}
        severity = ir.IssueSeverity.ERROR
    elif status == CompatibilityStatus.DOWNGRADE_RECOMMENDED:
        translation_key = "plugin_downgrade_recommended"
        placeholders = {
            "firmware_version": _reason_version(reason),
            "plugin_version": str(CURRENT_HA_VERSION),
        }
        severity = ir.IssueSeverity.WARNING
    else:
        # COMPATIBLE (including the version-limited case) — nothing wrong.
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=severity,
        translation_key=translation_key,
        translation_placeholders=placeholders,
        learn_more_url=DOCS_URL,
    )


@callback
def async_clear_compatibility_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the compatibility repair issue (e.g. on config entry unload)."""
    ir.async_delete_issue(hass, DOMAIN, compatibility_issue_id(entry_id))


def _maintenance_issue_id(entry_id: str, kind: str) -> str:
    """Return the per-config-entry issue id for a maintenance repair."""
    return f"{kind}_{entry_id}"


def _used_minutes(data: Any) -> int:
    """Read the ``int_value`` usage counter from a dp payload, defaulting to 0."""
    try:
        return int(data.get("int_value", 0))
    except (ValueError, TypeError, AttributeError):
        return 0


@callback
def _async_sync_maintenance_issue(
    hass: HomeAssistant,
    entry_id: str,
    kind: str,
    used_minutes: int,
    cycle_minutes: int,
    placeholders: dict[str, str],
) -> None:
    """Raise a maintenance repair issue once the usage cycle is exceeded."""
    issue_id = _maintenance_issue_id(entry_id, kind)
    if used_minutes >= cycle_minutes:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=kind,
            translation_placeholders=placeholders,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


@callback
def async_sync_blade_maintenance_issue(
    hass: HomeAssistant, entry_id: str, blade_time: Any
) -> None:
    """Sync the blade-maintenance repair issue from the dp_126 payload."""
    _async_sync_maintenance_issue(
        hass,
        entry_id,
        BLADE_MAINTENANCE_ISSUE,
        _used_minutes(blade_time),
        BLADE_MAINTENANCE_CYCLE_MINUTES,
        {"hours": str(BLADE_MAINTENANCE_CYCLE_MINUTES // 60)},
    )


@callback
def async_sync_base_station_maintenance_issue(
    hass: HomeAssistant, entry_id: str, base_station_time: Any
) -> None:
    """Sync the base-station-maintenance repair issue from the dp_125 payload."""
    _async_sync_maintenance_issue(
        hass,
        entry_id,
        BASE_STATION_MAINTENANCE_ISSUE,
        _used_minutes(base_station_time),
        BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
        {"days": str(BASE_STATION_MAINTENANCE_CYCLE_MINUTES // (60 * 24))},
    )


@callback
def async_clear_maintenance_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Remove both maintenance repair issues (e.g. on config entry unload)."""
    ir.async_delete_issue(
        hass, DOMAIN, _maintenance_issue_id(entry_id, BLADE_MAINTENANCE_ISSUE)
    )
    ir.async_delete_issue(
        hass, DOMAIN, _maintenance_issue_id(entry_id, BASE_STATION_MAINTENANCE_ISSUE)
    )
