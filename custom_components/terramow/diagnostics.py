"""Diagnostics support for TerraMow."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import DOMAIN

# 主机名/IP 与密码属于隐私信息，导出前打码。
TO_REDACT = {CONF_HOST, CONF_PASSWORD, "host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    basic_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)

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
        "activity": str(lawn_mower.activity),
        "mqtt_connected": bool(
            lawn_mower.mqtt_client and lawn_mower.mqtt_client.is_connected()
        ),
        "registered_data_points": sorted(lawn_mower.callbacks),
        "unknown_data_points_seen": sorted(
            getattr(lawn_mower, "_seen_unknown_dp_ids", [])
        ),
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
