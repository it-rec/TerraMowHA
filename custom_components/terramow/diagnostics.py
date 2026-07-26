"""Diagnostics support for TerraMow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import TerraMowConfigEntry

# The hostname/IP and password are private information; redact them before export.
TO_REDACT = {CONF_HOST, CONF_PASSWORD, "host", "serial"}


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

    # Copies of the unknown-dp bookkeeping; the MQTT worker thread keeps
    # appending to the live structures while this export runs.
    unknown = lawn_mower.diagnostics_snapshot()

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
        "unknown_data_points_seen": unknown["seen_unknown_dp_ids"],
        # Latest raw payload per unhandled data point, to identify undocumented
        # dps from real data. Keyed by dp id (as a string for JSON portability).
        "unknown_data_point_payloads": {
            str(dp_id): payload
            for dp_id, payload in sorted(unknown["unknown_dp_payloads"].items())
        },
        # Timestamped change-history per undocumented dp (only value changes are
        # recorded). A single export therefore shows how dynamic values move —
        # e.g. when dp_134 toggled or dp_109 climbed — which is what lets these
        # be decoded against user actions. Times are UTC ISO-8601.
        "unknown_data_point_history": {
            str(dp_id): [
                {
                    "time": datetime.fromtimestamp(ts, tz=UTC).isoformat(),
                    "payload": payload,
                }
                for ts, payload in entries
            ]
            for dp_id, entries in sorted(unknown["unknown_dp_history"].items())
        },
        # Last dp_119 command acknowledgement (seq + code).
        "last_command_ack": unknown["last_command_ack"],
        # Redelivered MQTT messages dropped per topic (the broker fanning one
        # publish out across the overlapping "#" and specific subscriptions).
        "duplicate_deliveries": unknown["duplicate_deliveries"],
        # App-direction data-point writes captured since the last restart —
        # the source material for documenting undocumented write formats
        # (e.g. the dp_122 schedule ADD/DELETE). Includes echoes of our own
        # commands. Times are UTC ISO-8601.
        "app_dp_captures": [
            {
                "time": datetime.fromtimestamp(ts, tz=UTC).isoformat(),
                "topic": topic,
                "payload": payload,
            }
            for ts, topic, payload in unknown["app_dp_captures"]
        ],
        # Messages on topics outside the documented namespace (via the "#"
        # discovery subscription) — the hunt for the internal commander's
        # channel. Times are UTC ISO-8601.
        "unknown_topic_captures": [
            {
                "time": datetime.fromtimestamp(ts, tz=UTC).isoformat(),
                "topic": topic,
                "payload": payload,
            }
            for ts, topic, payload in unknown["unknown_topic_captures"]
        ],
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
        "passage_reliability": lawn_mower.passage_reliability,
        "safety_breaches": lawn_mower.safety_breach_state,
        # Digests and changed layer names only; the private lawn geometry
        # baseline itself stays in local storage and is not exported.
        "map_integrity": lawn_mower.map_integrity_state,
        "battery_health": lawn_mower.battery_health_metrics,
        "mission_preflight": lawn_mower.mission_preflight_catalog,
    }

    return diagnostics
