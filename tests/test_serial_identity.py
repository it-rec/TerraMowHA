"""Serial-based stable identity: adoption, migration and flow dedupe.

The mower's serial (dp_102 ``sn``) only becomes known after the first MQTT
connect, so config entries start keyed on the host/IP. These tests cover the
one-time adoption that re-keys the config entry, entity registry unique_ids
and the device registry identifier — and the config-flow behavior that keeps
a DHCP address change from duplicating or orphaning anything afterwards.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow import TerraMowBasicData, async_setup_entry
from custom_components.terramow.config_flow import CannotConnect
from custom_components.terramow.const import CONF_SERIAL, DOMAIN
from custom_components.terramow.hub import TerraMowHub

HOST = "192.0.2.10"
SERIAL = "MP511TEST42"


def _entry(hass: HomeAssistant, **extra) -> MockConfigEntry:
    data = {CONF_HOST: HOST, CONF_PASSWORD: "secret", **extra}
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, unique_id=extra.get(CONF_SERIAL, HOST)
    )
    entry.add_to_hass(hass)
    return entry


def _hub_for(hass: HomeAssistant, entry: MockConfigEntry) -> TerraMowHub:
    basic_data = TerraMowBasicData(
        host=HOST,
        password="secret",
        entry_id=entry.entry_id,
        device_uid=entry.data.get(CONF_SERIAL) or HOST,
    )
    return TerraMowHub(basic_data, hass)


# ---------------------------------------------------------------------------
# hub._async_adopt_serial
# ---------------------------------------------------------------------------


async def test_adopt_serial_migrates_registries_and_entry(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass)
    hub = _hub_for(hass, entry)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HOST)},
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"lawn_mower.terramow@{HOST}.battery",
        config_entry=entry,
        device_id=device.id,
    )
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"version_compatibility.terramow@{HOST}",
        config_entry=entry,
        device_id=device.id,
    )
    # an id without the host fragment stays untouched
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "unrelated-unique-id",
        config_entry=entry,
        device_id=device.id,
    )

    await hub._async_adopt_serial(SERIAL)
    await hass.async_block_till_done()

    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.unique_id == SERIAL
    # entity registry unique_ids were re-keyed onto the serial
    assert entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"lawn_mower.terramow@{SERIAL}.battery"
    )
    assert entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"version_compatibility.terramow@{SERIAL}"
    )
    # the device identifier follows the serial
    assert device_registry.async_get_device({(DOMAIN, SERIAL)})
    assert device_registry.async_get_device({(DOMAIN, HOST)}) is None
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, "unrelated-unique-id")


async def test_adopt_serial_without_device_entry(hass: HomeAssistant) -> None:
    # first connect before the device registry entry exists: the entry is
    # still re-keyed; the device gets the serial identifier when created
    entry = _entry(hass)
    hub = _hub_for(hass, entry)
    await hub._async_adopt_serial(SERIAL)
    await hass.async_block_till_done()
    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.unique_id == SERIAL


async def test_adopt_serial_is_idempotent_and_guards(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    hub = _hub_for(hass, entry)
    hub.basic_data.device_uid = None

    with patch.object(hass.config_entries, "async_update_entry") as update:
        await hub._async_adopt_serial(SERIAL)
    update.assert_not_called()
    # repeat pushes keep the runtime identity in sync
    assert hub.basic_data.device_uid == SERIAL

    # a different serial at the same address is refused
    with patch.object(hass.config_entries, "async_update_entry") as update:
        await hub._async_adopt_serial("OTHER123")
    update.assert_not_called()
    assert entry.data[CONF_SERIAL] == SERIAL


async def test_adopt_serial_without_entry_is_a_noop(hass: HomeAssistant) -> None:
    hub = TerraMowHub(TerraMowBasicData(host=HOST, password="s"), hass)
    await hub._async_adopt_serial(SERIAL)  # no entry_id -> nothing to do

    hub.basic_data.entry_id = "missing-entry"
    await hub._async_adopt_serial(SERIAL)  # unknown entry -> nothing to do


def test_on_device_info_dispatches_serial_adoption() -> None:
    basic_data = TerraMowBasicData(host=HOST, password="s")
    hub = TerraMowHub(basic_data, MagicMock())
    hub.hass.loop.call_soon_threadsafe = MagicMock(side_effect=lambda fn, *a: fn(*a))
    created: list = []
    hub.hass.async_create_task = MagicMock(side_effect=created.append)

    asyncio.run(hub.on_device_info(json.dumps({"version": "9.9.210", "sn": SERIAL})))
    # one task for the sw_version update, one for the serial adoption
    assert len(created) == 2
    for coro in created:
        coro.close()

    # a payload without a serial only schedules the version update
    created.clear()
    asyncio.run(hub.on_device_info(json.dumps({"version": "9.9.210"})))
    assert len(created) == 1
    created[0].close()


# ---------------------------------------------------------------------------
# setup wiring
# ---------------------------------------------------------------------------


async def test_setup_uses_serial_as_device_uid(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    captured: dict = {}

    class _FakeHub:
        def __init__(self, basic_data, _hass) -> None:
            captured["basic_data"] = basic_data
            basic_data.lawn_mower = self

        def start(self) -> None:
            pass

        async def async_stop(self) -> None:
            pass

        async def async_adopt_pending_serial(self) -> None:
            pass

        async def async_restore_session_paths(self) -> None:
            pass

        async def async_restore_wifi_map(self) -> None:
            pass

        async def async_restore_fault_hotspots(self) -> None:
            pass

        async def async_restore_mow_counts(self) -> None:
            pass

        async def async_restore_wear_anchors(self) -> None:
            pass

        async def async_restore_passage_reliability(self) -> None:
            pass

        async def async_restore_safety_history(self) -> None:
            pass

        async def async_restore_map_integrity(self) -> None:
            pass

        async def async_restore_battery_health(self) -> None:
            pass

    with (
        patch("custom_components.terramow.validate_input", return_value={}),
        patch("custom_components.terramow.TerraMowHub", _FakeHub),
        patch(
            "custom_components.terramow.async_setup_map_card", AsyncMock()
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=None,
        ),
    ):
        assert await async_setup_entry(hass, entry)
    assert captured["basic_data"].device_uid == SERIAL


async def test_setup_migrates_host_keyed_identifier_to_serial(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HOST)},
    )
    from homeassistant.exceptions import ConfigEntryNotReady

    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    assert device_registry.async_get_device({(DOMAIN, SERIAL)}) is not None
    assert device_registry.async_get_device({(DOMAIN, HOST)}) is None


# ---------------------------------------------------------------------------
# config flow dedupe
# ---------------------------------------------------------------------------


class _Discovery(SimpleNamespace):
    pass


async def test_zeroconf_serial_match_updates_host(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery(host="192.0.2.99", properties={"sn": SERIAL}),
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # the DHCP address change healed the stored host
    assert entry.data[CONF_HOST] == "192.0.2.99"


async def test_zeroconf_host_dedupe_for_serial_keyed_entry(
    hass: HomeAssistant,
) -> None:
    # entry keyed by serial, rediscovered at the same host WITHOUT a serial in
    # the announcement -> deduped by host instead of creating a duplicate
    _entry(hass, **{CONF_SERIAL: SERIAL})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery(host=HOST, properties={}),
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_host_dedupe_for_serial_keyed_entry(
    hass: HomeAssistant,
) -> None:
    _entry(hass, **{CONF_SERIAL: SERIAL})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        return_value={"title": f"TerraMow ({HOST})"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST, CONF_PASSWORD: "secret"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_keeps_serial_identity(hass: HomeAssistant) -> None:
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        return_value={"title": "TerraMow (192.0.2.99)"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.99", CONF_PASSWORD: "secret"}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # the host moved, the identity did not
    assert entry.unique_id == SERIAL
    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.data[CONF_HOST] == "192.0.2.99"


# ---------------------------------------------------------------------------
# adoption vs. initial platform setup (ghost-device regression)
# ---------------------------------------------------------------------------


async def test_adoption_is_parked_while_setup_in_progress(
    hass: HomeAssistant,
) -> None:
    # Regression: a retained dp_102 arrives while the platforms are still
    # being set up. Migrating at that moment re-keys the registry under the
    # entities still being added and splits the device in two ("ghost"
    # device). The adoption must park itself instead.
    entry = _entry(hass)
    hub = _hub_for(hass, entry)
    entry.mock_state(hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS)

    await hub._async_adopt_serial(SERIAL)

    assert hub._pending_serial == SERIAL
    assert CONF_SERIAL not in entry.data
    assert entry.unique_id == HOST

    # once the entry has loaded, the parked serial is consumed and the
    # migration runs for real
    entry.mock_state(hass, config_entries.ConfigEntryState.LOADED)
    await hub.async_adopt_pending_serial()
    await hass.async_block_till_done()
    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.unique_id == SERIAL
    assert hub._pending_serial is None

    # consuming with nothing parked is a no-op
    await hub.async_adopt_pending_serial()


async def test_setup_removes_ghost_device_and_stale_entities(
    hass: HomeAssistant,
) -> None:
    # Repair for installs hit by the pre-1.13.1 race: the serial-keyed
    # device is the live one; a host-keyed duplicate device plus host-keyed
    # entity registry entries are dead ghosts and must be removed.
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    device_registry = dr.async_get(hass)
    real = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL)},
    )
    ghost = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HOST)},
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"lawn_mower.terramow@{SERIAL}.battery",
        config_entry=entry,
        device_id=real.id,
    )
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"lawn_mower.terramow@{HOST}.battery",
        config_entry=entry,
        device_id=ghost.id,
    )
    from homeassistant.exceptions import ConfigEntryNotReady

    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    # the ghost device and its host-keyed duplicate entity are gone
    assert device_registry.async_get_device({(DOMAIN, HOST)}) is None
    assert entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"lawn_mower.terramow@{HOST}.battery"
    ) is None
    # the live serial-keyed device and entity survive untouched
    assert device_registry.async_get_device({(DOMAIN, SERIAL)})
    assert entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"lawn_mower.terramow@{SERIAL}.battery"
    )


async def test_setup_consumes_parked_serial_after_load(hass: HomeAssistant) -> None:
    # Full-stack: the entry loads with a hub whose start() immediately parks
    # a serial (as a retained dp_102 would); the post-setup task must adopt
    # it and re-key the entry.
    entry = _entry(hass)

    def _start(hub_self) -> None:
        hub_self._pending_serial = SERIAL

    with (
        patch("custom_components.terramow.validate_input", return_value={}),
        patch.object(TerraMowHub, "start", _start),
    ):
        # the adoption triggers a reload mid-flight, so the initial
        # async_setup return value is not meaningful; assert the settled
        # state instead
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.unique_id == SERIAL
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_setup_sweeps_stale_host_entity_without_ghost_device(
    hass: HomeAssistant,
) -> None:
    # Stale host-keyed entity attached to the LIVE device (no ghost device
    # to cascade from): the explicit sweep must remove it.
    entry = _entry(hass, **{CONF_SERIAL: SERIAL})
    device_registry = dr.async_get(hass)
    real = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, SERIAL)},
    )
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"lawn_mower.terramow@{HOST}.battery",
        config_entry=entry,
        device_id=real.id,
    )
    from homeassistant.exceptions import ConfigEntryNotReady

    with (
        patch("custom_components.terramow.validate_input", side_effect=CannotConnect),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    assert entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"lawn_mower.terramow@{HOST}.battery"
    ) is None


async def test_adopt_pending_serial_reparks_if_setup_never_finishes(
    hass: HomeAssistant,
) -> None:
    entry = _entry(hass)
    hub = _hub_for(hass, entry)
    entry.mock_state(hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS)
    hub._pending_serial = SERIAL
    # the consumer gives up yielding after a bounded number of iterations;
    # the adoption gate then re-parks the serial for the next dp_102 push
    await hub.async_adopt_pending_serial()
    assert hub._pending_serial == SERIAL

    # a vanished entry stops the wait immediately and adoption is a no-op
    hub.basic_data.entry_id = "missing-entry"
    hub._pending_serial = SERIAL
    await hub.async_adopt_pending_serial()
    assert hub._pending_serial is None

    # without an entry_id there is nothing to wait for either
    hub.basic_data.entry_id = None
    hub._pending_serial = SERIAL
    await hub.async_adopt_pending_serial()
    assert hub._pending_serial is None


async def test_retained_dp102_during_setup_creates_no_ghost_device(
    hass: HomeAssistant,
) -> None:
    """True reproduction of the 1.13.0 ghost-device bug, as an invariant.

    The broker delivers the retained dp_102 the instant the hub connects —
    while the platforms are still adding entities. Simulate exactly that:
    ``start`` installs the mock client and immediately feeds dp_102 through
    the REAL ``on_mqtt_message`` dispatch, so the adoption coroutine fires at
    the first event-loop yield, mid-platform-setup. Whatever the migration
    internals do now or in the future, the observable invariant must hold:
    one device, no host-keyed registry leftovers, serial adopted.
    """
    entry = _entry(hass)  # fresh install: no serial stored yet

    def _start_with_retained_dp102(hub_self: TerraMowHub) -> None:
        client = MagicMock()
        client.is_connected.return_value = True
        client.publish.return_value = MagicMock(rc=0)
        hub_self.mqtt_client = client
        hub_self.register_all_callbacks()
        # the retained device-info message, delivered like the worker thread
        hub_self.on_mqtt_message(
            None,
            None,
            SimpleNamespace(
                topic="data_point/102/robot",
                payload=json.dumps(
                    {"version": "9.9.210", "sn": SERIAL}
                ).encode(),
            ),
        )

    with (
        patch(
            "custom_components.terramow.validate_input",
            return_value={"title": f"TerraMow ({HOST})"},
        ),
        patch.object(TerraMowHub, "start", _start_with_retained_dp102),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        # the adoption reload settles in follow-up tasks
        await asyncio.sleep(0)
        await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.data[CONF_SERIAL] == SERIAL
    assert entry.unique_id == SERIAL

    # THE invariant: exactly one device for this entry, keyed by the serial
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    assert (DOMAIN, SERIAL) in devices[0].identifiers

    # and no host-keyed entity registry leftovers anywhere
    entity_registry = er.async_get(hass)
    host_fragment = f"terramow@{HOST}"
    stale = [
        reg_entry.entity_id
        for reg_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if host_fragment in reg_entry.unique_id
    ]
    assert stale == []
