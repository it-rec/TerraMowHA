"""Diagnostics support for TerraMow."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import TerraMowConfigEntry

# The hostname/IP and password are private information; redact them before export.
TO_REDACT = {CONF_HOST, CONF_PASSWORD, "host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TerraMowConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    basic_data = getattr(entry, "runtime_data", None)

    diagnostics: dict[str, Any] = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
    }

    if basic_data is None:
        diagnostics["error"] = "integration data not loaded"
        return diagnostics

    diagnostics["compatibility"] = {
        "status": basic_data.compatibility_status,
        "reason": basic_data.compatibility_reason,
        "message": basic_data.get_compatibility_message(),
        "firmware_version": basic_data.firmware_version,
    }

    lawn_mower = basic_data.lawn_mower
    if lawn_mower is None:
        diagnostics["device"] = None
        return diagnostics

    diagnostics["device"] = {
        "model": lawn_mower.device_model,
        "mission": str(lawn_mower.mission),
        "sub_mission": str(lawn_mower.sub_mission),
        "mission_state": str(lawn_mower.mission_state),
        "connection_error": lawn_mower.connection_error,
        "mqtt_connected": bool(
            lawn_mower.mqtt_client and lawn_mower.mqtt_client.is_connected()
        ),
        "registered_data_points": sorted(lawn_mower.callbacks),
        "unknown_data_points_seen": sorted(
            getattr(lawn_mower, "_seen_unknown_dp_ids", [])
        ),
        # Latest raw payload per unhandled data point, to identify undocumented
        # dps from real data. Keyed by dp id (as a string for JSON portability).
        "unknown_data_point_payloads": {
            str(dp_id): payload
            for dp_id, payload in sorted(
                getattr(lawn_mower, "_unknown_dp_payloads", {}).items()
            )
        },
    }
    diagnostics["state"] = {
        "task_status": lawn_mower.task_status,
        "battery_status": lawn_mower.battery_status,
        "map_status": lawn_mower.map_status,
        "global_params": lawn_mower.global_params,
        "current_work_data": lawn_mower.current_work_data,
        "statistics_data": lawn_mower.statistics_data,
        "base_station_time": lawn_mower.base_station_time,
        "blade_time": lawn_mower.blade_time,
        "schedule_data": lawn_mower.schedule_data,
    }

    return diagnostics
