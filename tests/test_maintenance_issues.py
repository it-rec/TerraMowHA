"""Coverage for the blade / base-station maintenance repair issues.

Verifies the issue is raised once the recommended usage cycle is exceeded and
cleared below it, that the usage counter is read defensively, that the hub
syncs the issue when the dp_125 / dp_126 payloads arrive, and that both issues
are cleared together.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.terramow import TerraMowBasicData
from custom_components.terramow.const import (
    BASE_STATION_MAINTENANCE_CYCLE_MINUTES,
    BLADE_MAINTENANCE_CYCLE_MINUTES,
    DOMAIN,
)
from custom_components.terramow.hub import TerraMowHub
from custom_components.terramow.issues import (
    BASE_STATION_MAINTENANCE_ISSUE,
    BLADE_MAINTENANCE_ISSUE,
    _maintenance_issue_id,
    async_clear_maintenance_issues,
    async_sync_base_station_maintenance_issue,
    async_sync_blade_maintenance_issue,
)


def _issue(hass: HomeAssistant, entry_id: str, kind: str):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, _maintenance_issue_id(entry_id, kind)
    )


# ---------------------------------------------------------------------------
# issue creation / clearing thresholds
# ---------------------------------------------------------------------------


async def test_blade_issue_raised_when_cycle_exceeded(hass: HomeAssistant) -> None:
    async_sync_blade_maintenance_issue(
        hass, "e1", {"int_value": BLADE_MAINTENANCE_CYCLE_MINUTES}
    )
    issue = _issue(hass, "e1", BLADE_MAINTENANCE_ISSUE)
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders == {"hours": "240"}


async def test_blade_issue_cleared_below_cycle(hass: HomeAssistant) -> None:
    # first raise it, then a lower reading clears it
    async_sync_blade_maintenance_issue(
        hass, "e1", {"int_value": BLADE_MAINTENANCE_CYCLE_MINUTES}
    )
    async_sync_blade_maintenance_issue(hass, "e1", {"int_value": 10})
    assert _issue(hass, "e1", BLADE_MAINTENANCE_ISSUE) is None


async def test_base_station_issue_raised_and_cleared(hass: HomeAssistant) -> None:
    async_sync_base_station_maintenance_issue(
        hass, "e1", {"int_value": BASE_STATION_MAINTENANCE_CYCLE_MINUTES}
    )
    issue = _issue(hass, "e1", BASE_STATION_MAINTENANCE_ISSUE)
    assert issue is not None
    assert issue.translation_placeholders == {"days": "30"}

    async_sync_base_station_maintenance_issue(hass, "e1", {"int_value": 0})
    assert _issue(hass, "e1", BASE_STATION_MAINTENANCE_ISSUE) is None


async def test_usage_counter_read_defensively(hass: HomeAssistant) -> None:
    # a non-dict payload, a None value and a non-numeric value all read as 0,
    # so no issue is raised
    for bad in ([1, 2, 3], {"int_value": None}, {"int_value": "x"}, {}):
        async_sync_blade_maintenance_issue(hass, "e1", bad)
        assert _issue(hass, "e1", BLADE_MAINTENANCE_ISSUE) is None


async def test_clear_removes_both_issues(hass: HomeAssistant) -> None:
    async_sync_blade_maintenance_issue(
        hass, "e1", {"int_value": BLADE_MAINTENANCE_CYCLE_MINUTES}
    )
    async_sync_base_station_maintenance_issue(
        hass, "e1", {"int_value": BASE_STATION_MAINTENANCE_CYCLE_MINUTES}
    )
    async_clear_maintenance_issues(hass, "e1")
    assert _issue(hass, "e1", BLADE_MAINTENANCE_ISSUE) is None
    assert _issue(hass, "e1", BASE_STATION_MAINTENANCE_ISSUE) is None


# ---------------------------------------------------------------------------
# hub syncs the issue when the dp payloads arrive
# ---------------------------------------------------------------------------


def _hub() -> TerraMowHub:
    basic_data = TerraMowBasicData(
        host="192.0.2.170", password="secret", entry_id="e1"
    )
    hub = TerraMowHub(basic_data, MagicMock())
    hub.mqtt_client = MagicMock()
    hub.mqtt_client.is_connected.return_value = True
    hub.mqtt_client.publish.return_value.rc = 0
    return hub


def test_on_blade_time_syncs_maintenance_issue() -> None:
    hub = _hub()
    with patch(
        "custom_components.terramow.hub.async_sync_blade_maintenance_issue"
    ) as sync:
        asyncio.run(hub.on_blade_time(json.dumps({"int_value": 999})))
    sync.assert_called_once_with(hub.hass, "e1", {"int_value": 999})


def test_on_base_station_time_syncs_maintenance_issue() -> None:
    hub = _hub()
    with patch(
        "custom_components.terramow.hub.async_sync_base_station_maintenance_issue"
    ) as sync:
        asyncio.run(hub.on_base_station_time(json.dumps({"int_value": 999})))
    sync.assert_called_once_with(hub.hass, "e1", {"int_value": 999})


def test_on_blade_time_invalid_json_does_not_sync() -> None:
    hub = _hub()
    with patch(
        "custom_components.terramow.hub.async_sync_blade_maintenance_issue"
    ) as sync:
        asyncio.run(hub.on_blade_time("not-json"))
    sync.assert_not_called()


def test_on_base_station_time_without_entry_id_does_not_sync() -> None:
    hub = _hub()
    hub.basic_data.entry_id = None
    with patch(
        "custom_components.terramow.hub.async_sync_base_station_maintenance_issue"
    ) as sync:
        asyncio.run(hub.on_base_station_time(json.dumps({"int_value": 999})))
    sync.assert_not_called()
