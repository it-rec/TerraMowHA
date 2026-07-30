"""Measured battery-efficiency aggregates from local mower telemetry."""

from __future__ import annotations

import json
import statistics
from typing import Any

BATTERY_HEALTH_MAX_RECORDS = 30
BATTERY_HEALTH_MAX_AGE_SECONDS = 180 * 24 * 3600
BATTERY_HEALTH_MIN_TREND_SAMPLES = 6


def _number(value: Any) -> float | None:
    """Return a finite protocol number, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if result == result and abs(result) != float("inf") else None


def settings_signature(settings: dict[str, Any]) -> str:
    """Stable signature of only device-reported settings relevant to mowing."""
    relevant = {
        key: settings[key]
        for key in (
            "mow_speed_type",
            "blade_disk_speed_type",
            "cutting_height",
            "mow_height",
            "mow_spacing",
        )
        if key in settings
    }
    return json.dumps(relevant, sort_keys=True, separators=(",", ":"))


class BatteryHealthTracker:
    """Aggregate completed discharge and charge windows without raw sampling."""

    def __init__(self) -> None:
        self.discharge_records: list[dict[str, Any]] = []
        self.charge_records: list[dict[str, Any]] = []
        self.partial_discharges = 0
        self.interrupted_charges = 0
        self._discharge_start: dict[str, Any] | None = None
        self._charge_start: dict[str, Any] | None = None
        self._source = "live"

    def _expire(self, now: float) -> None:
        cutoff = now - BATTERY_HEALTH_MAX_AGE_SECONDS
        self.discharge_records = [
            item
            for item in self.discharge_records
            if _number(item.get("ended_at")) is not None
            and float(item["ended_at"]) >= cutoff
        ][-BATTERY_HEALTH_MAX_RECORDS:]
        self.charge_records = [
            item
            for item in self.charge_records
            if _number(item.get("ended_at")) is not None
            and float(item["ended_at"]) >= cutoff
        ][-BATTERY_HEALTH_MAX_RECORDS:]

    def observe(
        self,
        *,
        level: int | None,
        charger_connected: bool,
        is_mowing: bool,
        work: dict[str, Any],
        map_id: Any,
        settings: dict[str, Any],
        now: float,
    ) -> None:
        """Consume one coalesced device state and retain aggregates only."""
        self._expire(now)
        if level is None or not 0 <= level <= 100:
            return
        signature = settings_signature(settings)
        area = _number(work.get("clean_area"))
        duration = _number(work.get("work_duration"))

        if is_mowing:
            start = self._discharge_start
            if (
                start is None
                or start["map_id"] != map_id
                or start["settings"] != signature
                or level > start["level"]
            ):
                if start is not None:
                    self.partial_discharges += 1
                self._discharge_start = {
                    "level": level,
                    "started_at": now,
                    "area": area,
                    "duration": duration,
                    "map_id": map_id,
                    "settings": signature,
                }
            else:
                if start["area"] is None and area is not None:
                    start["area"] = area
                if start["duration"] is None and duration is not None:
                    start["duration"] = duration
                drop = int(start["level"]) - level
                area_delta = (
                    None
                    if area is None
                    or start["area"] is None
                    or area < start["area"]
                    else (area - start["area"]) / 10.0
                )
                duration_delta = (
                    None
                    if duration is None
                    or start["duration"] is None
                    or duration < start["duration"]
                    else duration - start["duration"]
                )
                if drop >= 10 and (
                    (area_delta is not None and area_delta > 0)
                    or (duration_delta is not None and duration_delta > 0)
                ):
                    self.discharge_records.append(
                        {
                            "ended_at": now,
                            "map_id": map_id,
                            "settings": signature,
                            "drop": drop,
                            "area_m2": area_delta,
                            "duration_seconds": duration_delta,
                        }
                    )
                    self.discharge_records = self.discharge_records[
                        -BATTERY_HEALTH_MAX_RECORDS:
                    ]
                    self._discharge_start = {
                        "level": level,
                        "started_at": now,
                        "area": area,
                        "duration": duration,
                        "map_id": map_id,
                        "settings": signature,
                    }
        elif self._discharge_start is not None:
            self.partial_discharges += 1
            self._discharge_start = None

        if charger_connected:
            if self._charge_start is None and level <= 20:
                self._charge_start = {"level": level, "started_at": now}
            if self._charge_start is not None and level >= 80:
                elapsed = now - float(self._charge_start["started_at"])
                gained = level - int(self._charge_start["level"])
                if elapsed > 0 and gained > 0:
                    self.charge_records.append(
                        {
                            "ended_at": now,
                            "start_level": self._charge_start["level"],
                            "end_level": level,
                            "duration_seconds": elapsed,
                            "gain": gained,
                        }
                    )
                    self.charge_records = self.charge_records[
                        -BATTERY_HEALTH_MAX_RECORDS:
                    ]
                self._charge_start = None
        elif self._charge_start is not None:
            self.interrupted_charges += 1
            self._charge_start = None

        if self._source == "restored":
            self._source = "revalidated"
        elif self._source == "revalidated":
            self._source = "live"

    def reset(self) -> None:
        """Clear the user-controlled baseline after battery service."""
        self.discharge_records = []
        self.charge_records = []
        self.partial_discharges = 0
        self.interrupted_charges = 0
        self._discharge_start = None
        self._charge_start = None
        self._source = "live"

    def dump(self) -> dict[str, Any]:
        """Serialize bounded aggregate windows, never raw samples."""
        return {
            "discharge_records": self.discharge_records[-BATTERY_HEALTH_MAX_RECORDS:],
            "charge_records": self.charge_records[-BATTERY_HEALTH_MAX_RECORDS:],
            "partial_discharges": self.partial_discharges,
            "interrupted_charges": self.interrupted_charges,
        }

    def restore(self, data: Any, now: float) -> None:
        """Restore valid aggregate lists and mark them non-live."""
        if not isinstance(data, dict):
            return
        discharge = data.get("discharge_records")
        charge = data.get("charge_records")
        self.discharge_records = (
            [item for item in discharge if isinstance(item, dict)]
            if isinstance(discharge, list)
            else []
        )
        self.charge_records = (
            [item for item in charge if isinstance(item, dict)]
            if isinstance(charge, list)
            else []
        )
        self.partial_discharges = int(data.get("partial_discharges") or 0)
        self.interrupted_charges = int(data.get("interrupted_charges") or 0)
        self._expire(now)
        self._source = "restored"

    def metrics(
        self, *, map_id: Any, settings: dict[str, Any], now: float
    ) -> dict[str, Any]:
        """Return measured rates and explicit evidence/confidence."""
        self._expire(now)
        signature = settings_signature(settings)
        comparable = [
            item
            for item in self.discharge_records
            if item.get("map_id") == map_id and item.get("settings") == signature
        ]
        area_rates = [
            float(item["area_m2"]) * 10 / float(item["drop"])
            for item in comparable
            if _number(item.get("area_m2")) is not None
            and (_number(item.get("drop")) or 0) > 0
        ]
        duration_rates = [
            float(item["duration_seconds"]) / 60 * 10 / float(item["drop"])
            for item in comparable
            if _number(item.get("duration_seconds")) is not None
            and (_number(item.get("drop")) or 0) > 0
        ]
        charge_minutes = [
            float(item["duration_seconds"]) / 60 for item in self.charge_records
        ]
        charge_rates = [
            float(item["gain"]) * 3600 / float(item["duration_seconds"])
            for item in self.charge_records
            if (_number(item.get("duration_seconds")) or 0) > 0
        ]

        trend = None
        if len(area_rates) >= BATTERY_HEALTH_MIN_TREND_SAMPLES:
            recent = statistics.fmean(area_rates[-3:])
            baseline = statistics.fmean(area_rates[:-3])
            if baseline > 0:
                trend = round((recent / baseline - 1) * 100, 1)
        sample_count = len(comparable) + len(self.charge_records)
        confidence = (
            "high"
            if sample_count >= 12
            else "medium"
            if sample_count >= 6
            else "low"
            if sample_count >= 1
            else "unavailable"
        )
        ended = [
            float(item["ended_at"])
            for item in [*comparable, *self.charge_records]
            if _number(item.get("ended_at")) is not None
        ]
        return {
            "area_m2_per_10_percent": (
                round(statistics.median(area_rates), 2) if area_rates else None
            ),
            "mowing_minutes_per_10_percent": (
                round(statistics.median(duration_rates), 2)
                if duration_rates
                else None
            ),
            "charge_20_80_minutes": (
                round(statistics.median(charge_minutes), 1)
                if charge_minutes
                else None
            ),
            "charge_percent_per_hour": (
                round(statistics.median(charge_rates), 1) if charge_rates else None
            ),
            "area_efficiency_trend_percent": trend,
            "discharge_samples": len(comparable),
            "charge_samples": len(self.charge_records),
            "partial_discharges": self.partial_discharges,
            "interrupted_charges": self.interrupted_charges,
            "observation_start": min(ended) if ended else None,
            "observation_end": max(ended) if ended else None,
            "confidence": confidence,
            "source": self._source,
        }
