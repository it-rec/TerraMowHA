"""Measured selective-mission history and preflight estimates."""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime
from typing import Any

PREFLIGHT_MAX_RECORDS = 30
PREFLIGHT_MAX_AGE_SECONDS = 180 * 24 * 3600


def zone_geometry_signature(
    map_data: dict[str, Any], region_ids: list[int]
) -> str | None:
    """Fingerprint the exact device-reported boundaries of selected zones."""
    wanted = set(region_ids)
    found: dict[int, Any] = {}
    for region in map_data.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for sub_region in region.get("sub_regions") or []:
            if not isinstance(sub_region, dict):
                continue
            region_id = sub_region.get("id")
            if region_id in wanted:
                found[region_id] = sub_region.get("boundary")
    if set(found) != wanted:
        return None
    encoded = json.dumps(found, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(encoded.encode(), digest_size=12).hexdigest()


def mow_settings_signature(settings: dict[str, Any]) -> str:
    """Stable signature of the device's relevant reported mowing settings."""
    keys = (
        "mow_speed_type",
        "blade_disk_speed_type",
        "cutting_height",
        "mow_height",
        "mow_spacing",
        "main_direction_mode",
    )
    return json.dumps(
        {key: settings[key] for key in keys if key in settings},
        sort_keys=True,
        separators=(",", ":"),
    )


class MissionPreflightTracker:
    """Keep bounded qualifying observations for integration-started zone jobs."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.active: dict[str, Any] | None = None
        self.source = "live"

    def begin(
        self,
        *,
        region_ids: list[int],
        map_id: Any,
        geometry: str | None,
        settings: dict[str, Any],
        battery_level: int | None,
        charger_connected: bool,
        now: float,
    ) -> bool:
        """Start measuring only when every selected zone exists in the live map."""
        if not region_ids or geometry is None:
            return False
        self.active = {
            "region_ids": sorted(set(region_ids)),
            "map_id": map_id,
            "geometry": geometry,
            "settings": mow_settings_signature(settings),
            "started_at": now,
            "last_battery": battery_level,
            "battery_used": 0,
            "charger_connected": charger_connected,
            "recharge_legs": 0,
        }
        return True

    def observe(
        self,
        *,
        battery_level: int | None,
        charger_connected: bool,
        completed: bool,
        aborted: bool,
        work: dict[str, Any],
        map_id: Any,
        geometry: str | None,
        settings: dict[str, Any],
        now: float,
    ) -> None:
        """Update the current measured job and capture only a clean completion."""
        active = self.active
        if active is None:
            return
        previous_level = active.get("last_battery")
        if (
            isinstance(previous_level, int)
            and isinstance(battery_level, int)
            and battery_level < previous_level
        ):
            active["battery_used"] += previous_level - battery_level
        if battery_level is not None:
            active["last_battery"] = battery_level
        if charger_connected and not active["charger_connected"]:
            active["recharge_legs"] += 1
        active["charger_connected"] = charger_connected

        comparable = (
            active["map_id"] == map_id
            and active["geometry"] == geometry
            and active["settings"] == mow_settings_signature(settings)
        )
        if aborted or not comparable:
            self.active = None
            return
        if not completed:
            return
        duration = work.get("work_duration")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or duration <= 0
        ):
            self.active = None
            return
        self.records.append(
            {
                "ended_at": now,
                "region_ids": active["region_ids"],
                "map_id": map_id,
                "geometry": geometry,
                "settings": active["settings"],
                "duration_seconds": float(duration),
                "battery_used": active["battery_used"],
                "recharge_legs": active["recharge_legs"],
            }
        )
        self.records = self.records[-PREFLIGHT_MAX_RECORDS:]
        self.active = None

    def _expire(self, now: float) -> None:
        cutoff = now - PREFLIGHT_MAX_AGE_SECONDS
        self.records = [
            record
            for record in self.records
            if isinstance(record.get("ended_at"), (int, float))
            and record["ended_at"] >= cutoff
        ][-PREFLIGHT_MAX_RECORDS:]

    def estimate(
        self,
        *,
        region_ids: list[int],
        map_id: Any,
        geometry: str | None,
        settings: dict[str, Any],
        battery_level: int | None,
        sunset: Any,
        now: datetime,
    ) -> dict[str, Any]:
        """Estimate from exact comparable observations or return unavailable."""
        self._expire(now.timestamp())
        key = sorted(set(region_ids))
        signature = mow_settings_signature(settings)
        comparable = [
            record
            for record in self.records
            if record.get("region_ids") == key
            and record.get("map_id") == map_id
            and record.get("geometry") == geometry
            and record.get("settings") == signature
        ]
        if not comparable:
            return {"available": False, "sample_count": 0, "source": self.source}
        duration = statistics.median(
            float(record["duration_seconds"]) for record in comparable
        )
        battery = statistics.median(
            float(record["battery_used"]) for record in comparable
        )
        recharge = round(
            statistics.median(
                int(record["recharge_legs"]) for record in comparable
            )
        )
        finish = now.timestamp() + duration
        daylight_warning: bool | None = None
        if isinstance(sunset, dict):
            hour = sunset.get("hour")
            minute = sunset.get("minute")
            if isinstance(hour, int) and isinstance(minute, int):
                try:
                    sunset_at = now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    daylight_warning = finish > sunset_at.timestamp()
                except ValueError:
                    pass
        confidence = (
            "high"
            if len(comparable) >= 8
            else "medium"
            if len(comparable) >= 3
            else "low"
        )
        return {
            "available": True,
            "duration_seconds": round(duration),
            "battery_percent": round(battery, 1),
            "battery_margin_percent": (
                round(battery_level - battery, 1)
                if battery_level is not None
                else None
            ),
            "recharge_legs": recharge,
            "estimated_finish": datetime.fromtimestamp(
                finish, tz=now.tzinfo
            ).isoformat(),
            "daylight_warning": daylight_warning,
            "sample_count": len(comparable),
            "confidence": confidence,
            "source": self.source,
        }

    def dump(self) -> dict[str, Any]:
        """Persist completed aggregates only; an in-flight job is not restored."""
        return {"records": self.records[-PREFLIGHT_MAX_RECORDS:]}

    def restore(self, data: Any, now: float) -> None:
        """Restore bounded completed observations as non-live evidence."""
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            return
        self.records = [
            record for record in data["records"] if isinstance(record, dict)
        ][-PREFLIGHT_MAX_RECORDS:]
        self._expire(now)
        self.source = "restored"

    def revalidate(self) -> None:
        """Mark restored records revalidated after a matching live map report."""
        if self.source == "restored":
            self.source = "revalidated"
