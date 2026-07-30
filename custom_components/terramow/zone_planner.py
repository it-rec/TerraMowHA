"""Deterministic per-zone service-level planning."""

from __future__ import annotations

from datetime import datetime
from typing import Any

UNKNOWN_CHOICES = ("include", "exclude", "ask")


def _live_zones(map_data: dict[str, Any]) -> dict[int, str | None]:
    """Return device-reported sub-region ids and names."""
    zones: dict[int, str | None] = {}
    for region in map_data.get("regions") or []:
        if not isinstance(region, dict):
            continue
        for zone in region.get("sub_regions") or []:
            if not isinstance(zone, dict):
                continue
            zone_id = zone.get("id")
            if isinstance(zone_id, int) and not isinstance(zone_id, bool):
                name = zone.get("name")
                zones[zone_id] = name if isinstance(name, str) and name else None
    return zones


def build_zone_plan(
    *,
    map_data: dict[str, Any],
    last_seen: dict[int, str],
    policies: dict[int, dict[str, Any]],
    unknown_choice: str,
    now: datetime,
) -> dict[str, Any]:
    """Explain every policy decision and return deterministic due ids."""
    if unknown_choice not in UNKNOWN_CHOICES:
        raise ValueError(f"Invalid unknown choice: {unknown_choice}")
    map_id = map_data.get("id")
    zones = _live_zones(map_data)
    decisions: list[dict[str, Any]] = []
    due: list[dict[str, Any]] = []

    for zone_id, policy in policies.items():
        decision: dict[str, Any] = {
            "region_id": zone_id,
            "name": zones.get(zone_id),
            "included": False,
        }
        if zone_id not in zones:
            decision["reason"] = "removed"
        elif policy.get("map_id") not in (None, map_id):
            decision["reason"] = "map_mismatch"
        elif (
            policy.get("expected_name") is not None
            and policy.get("expected_name") != zones[zone_id]
        ):
            decision["reason"] = "renamed"
        elif policy.get("enabled", True) is False:
            decision["reason"] = "disabled"
        elif policy.get("manual_only", False) is True:
            decision["reason"] = "manual_only"
        else:
            interval = policy.get("interval_days")
            priority = policy.get("priority", 0)
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or interval <= 0
                or isinstance(priority, bool)
                or not isinstance(priority, int)
            ):
                decision["reason"] = "invalid_policy"
            else:
                stamp = last_seen.get(zone_id)
                observed = None
                if isinstance(stamp, str):
                    try:
                        observed = datetime.fromisoformat(stamp)
                        if observed.tzinfo is None:
                            observed = observed.replace(tzinfo=now.tzinfo)
                    except ValueError:
                        observed = None
                if observed is None:
                    decision["reason"] = f"unknown_{unknown_choice}"
                    decision["included"] = unknown_choice == "include"
                    decision["overdue_days"] = None
                else:
                    age_days = max(0.0, (now - observed).total_seconds() / 86400)
                    overdue = age_days - float(interval)
                    decision["age_days"] = round(age_days, 2)
                    decision["overdue_days"] = round(max(0.0, overdue), 2)
                    decision["included"] = overdue >= 0
                    decision["reason"] = "due" if overdue >= 0 else "not_due"
                decision["priority"] = priority
                if decision["included"]:
                    due.append(decision)
        decisions.append(decision)

    due.sort(
        key=lambda item: (
            -int(item.get("priority", 0)),
            -float(item.get("overdue_days") or 0),
            int(item["region_id"]),
        )
    )
    return {
        "map_id": map_id,
        "generated_at": now.isoformat(),
        "unknown_choice": unknown_choice,
        "blocked_on_unknown": any(
            item.get("reason") == "unknown_ask" for item in decisions
        ),
        "region_ids": [item["region_id"] for item in due],
        "due": due,
        "decisions": decisions,
    }
