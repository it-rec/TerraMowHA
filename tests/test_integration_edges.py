"""Full-stack edge cases: malformed or partial device data must degrade
gracefully in the real, fully set-up integration.

Reuses the real-``hass`` setup helpers from ``test_integration_setup``.
"""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from test_integration_setup import (
    push_dp,
    push_topic,
    resolve_entity_id,
    setup_terramow,
)

ALL_WEEK_DAYS = [
    "WEEK_DAY_MONDAY",
    "WEEK_DAY_TUESDAY",
    "WEEK_DAY_WEDNESDAY",
    "WEEK_DAY_THURSDAY",
    "WEEK_DAY_FRIDAY",
    "WEEK_DAY_SATURDAY",
    "WEEK_DAY_SUNDAY",
]


async def test_zone_select_survives_unparseable_sub_zone_id(
    hass: HomeAssistant,
) -> None:
    """A sub-zone whose id doesn't parse as an int must not crash the select
    (the option is offered, selecting it is rejected without a command)."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    zone_select = resolve_entity_id(hass, "select", "region_select")

    map_info = {
        "id": 1,
        "map_state": "MAP_STATE_COMPLETE",
        "regions": [
            {
                "id": 10,
                "sub_regions": [
                    {"id": "abc", "name": "Broken zone"},  # non-numeric id
                    {"id": None, "name": "No id zone"},  # dropped entirely
                    {"id": 7, "name": "Good zone"},
                ],
            }
        ],
    }
    await push_topic(hass, hub, "map/current/info", json.dumps(map_info))

    state = hass.states.get(zone_select)
    assert state.state == "all_zones"
    # The id-less zone is not offered; the unparseable one still is.
    assert state.attributes["options"] == [
        "all_zones",
        "Broken zone (ID: abc)",
        "Good zone (ID: 7)",
    ]

    # Selecting the broken option must not raise and must not send a command.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": zone_select, "option": "Broken zone (ID: abc)"},
        blocking=True,
    )
    assert hass.states.get(zone_select).state == "all_zones"
    hub.mqtt_client.publish.assert_not_called()

    # The select still works afterwards: a good zone sends the command.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": zone_select, "option": "Good zone (ID: 7)"},
        blocking=True,
    )
    assert hass.states.get(zone_select).state == "Good zone (ID: 7)"
    topic = hub.mqtt_client.publish.call_args[0][0]
    assert topic == "data_point/103/app"


async def test_battery_attributes_when_device_omits_tempreture_field(
    hass: HomeAssistant,
) -> None:
    """dp_108 without the (typo'd) 'tempreture' field: attributes fall back
    to 'unknown' and the temperature-state enum sensor stays unknown."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower

    battery = resolve_entity_id(hass, "sensor", "battery")
    temperature_state = resolve_entity_id(
        hass, "sensor", "battery_temperature_state"
    )

    await push_dp(hass, hub, 8, {"int_value": 55})
    await push_dp(
        hass,
        hub,
        108,
        {
            "state": "BATTERY_STATE_DISCHARGE",
            "charger_connected": False,
            "is_switch_on": True,
            # no 'tempreture' key
        },
    )

    state = hass.states.get(battery)
    assert state.state == "55"
    assert state.attributes["state"] == "BATTERY_STATE_DISCHARGE"
    assert state.attributes["temperature"] == "unknown"
    # The enum sensor filters the missing value to unknown instead of crashing.
    assert hass.states.get(temperature_state).state == "unknown"


async def test_calendar_ignores_unknown_disabled_week_day_enums(
    hass: HomeAssistant,
) -> None:
    """Unknown week-day enum strings (newer firmware) in disabled_week_days
    must be ignored, not disable the schedule or raise."""
    entry = await setup_terramow(hass)
    hub = entry.runtime_data.lawn_mower
    calendar = resolve_entity_id(hass, "calendar", "schedule")

    schedule_list = {
        "global_disabled": False,
        # One unknown token plus a known one: only Sunday is really disabled.
        "disabled_week_days": ["WEEK_DAY_FUNDAY", "WEEK_DAY_SUNDAY"],
        "items": [
            {
                "id": 1,
                "global_schedule_v2": {
                    "basic_config": {
                        "start_time": {"hour": 8, "minute": 30},
                        "end_time": {"hour": 10, "minute": 0},
                        # Also an unknown token inside week_days: ignored.
                        "week_days": [*ALL_WEEK_DAYS, "WEEK_DAY_FUNDAY"],
                    }
                },
            }
        ],
    }
    await push_dp(hass, hub, 122, {"schedule_list": schedule_list})

    # The schedule survived the unknown enums: an upcoming "Mowing" slot
    # exists (every day but Sunday recurs, so the next one is at most two
    # days out).
    state = hass.states.get(calendar)
    assert state is not None
    assert state.state in ("on", "off")
    assert state.attributes["message"] == "Mowing"
    assert state.attributes["start_time"].endswith("08:30:00")
    assert state.attributes["end_time"].endswith("10:00:00")
