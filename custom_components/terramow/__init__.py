"""The TerraMow integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_PASSWORD,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .config_flow import CannotConnect, InvalidAuth, validate_input
from .const import (
    CONF_ASSUME_JOB_COMPLETE,
    CONF_SERIAL,
    CURRENT_HA_VERSION,
    DEFAULT_ASSUME_JOB_COMPLETE,
    MIN_REQUIRED_OVERALL_VERSION,
    MIN_SUPPORTED_HA_VERSION,
    WEEKDAY_TO_DEVICE,
    CompatibilityStatus,
)
from .const import DOMAIN as DOMAIN
from .hub import TerraMowHub
from .issues import async_clear_compatibility_issue, async_clear_maintenance_issues
from .map_card import async_setup_map_card

SERVICE_START_SELECT_REGION = "start_select_region"
SERVICE_ADD_SCHEDULE = "add_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
ATTR_REGION_IDS = "region_ids"
ATTR_WEEK_DAYS = "week_days"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_DISABLED = "disabled"
ATTR_RUN_ONCE = "run_once"
ATTR_ITEM_ID = "item_id"

START_SELECT_REGION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_REGION_IDS): vol.All(
            cv.ensure_list, [vol.Coerce(int)], vol.Length(min=1)
        ),
    }
)

ADD_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_WEEK_DAYS): vol.All(
            cv.ensure_list, [vol.In(WEEKDAY_TO_DEVICE)], vol.Length(min=1)
        ),
        vol.Required(ATTR_START_TIME): cv.time,
        vol.Required(ATTR_END_TIME): cv.time,
        vol.Optional(ATTR_DISABLED, default=False): cv.boolean,
        vol.Optional(ATTR_RUN_ONCE, default=False): cv.boolean,
    }
)

DELETE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_ITEM_ID): vol.Coerce(int),
    }
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LAWN_MOWER, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT, Platform.NUMBER, Platform.CAMERA, Platform.IMAGE, Platform.UPDATE, Platform.BUTTON, Platform.SWITCH, Platform.LIGHT, Platform.EVENT, Platform.CALENDAR, Platform.TODO]

@dataclass
class TerraMowBasicData:
    host: str
    password: str
    # The hub; the attribute keeps its historical name from the time the
    # lawn mower entity itself played the hub role.
    lawn_mower: TerraMowHub | None = None
    # Stable device identity used for unique_ids and device identifiers: the
    # serial once known (config entry data), the host until then.
    device_uid: str | None = None
    compatibility_status: str = CompatibilityStatus.COMPATIBLE
    firmware_version: dict[str, Any] | None = None
    compatibility_reason: str = ""  # Store the specific reason for compatibility check failure
    entry_id: str | None = None  # Config entry id, used to scope repair issues
    # Option: treat any finished job as 100 % complete even without an explicit
    # firmware completion signal (CONF_ASSUME_JOB_COMPLETE). Read from the
    # config entry options at setup; an options change reloads the entry.
    assume_job_complete: bool = False

    def check_version_compatibility(self, compatibility_info: dict[str, Any]) -> str:
        """Check version compatibility and return status."""
        try:
            overall_version = compatibility_info.get("overall", 0)
            module_info = compatibility_info.get("module", {})
            ha_version = module_info.get("home_assistant", 0)

            _LOGGER.info(
                "Version compatibility check: firmware overall=%d, firmware HA version=%d, plugin HA version=%d",
                overall_version, ha_version, CURRENT_HA_VERSION
            )

            # Check if firmware meets minimum requirements
            if overall_version < MIN_REQUIRED_OVERALL_VERSION:
                _LOGGER.warning(
                    "Firmware version too low: overall=%d < minimum required=%d",
                    overall_version, MIN_REQUIRED_OVERALL_VERSION
                )
                self.compatibility_reason = f"overall_version_low:{overall_version}"
                return CompatibilityStatus.UPGRADE_REQUIRED

            # Check HA version compatibility
            if ha_version < MIN_SUPPORTED_HA_VERSION:
                _LOGGER.warning(
                    "Firmware HA version is too low: %d < %d, please upgrade firmware",
                    ha_version, MIN_SUPPORTED_HA_VERSION
                )
                self.compatibility_reason = f"ha_version_low:{ha_version}"
                return CompatibilityStatus.UPGRADE_REQUIRED
            elif ha_version < CURRENT_HA_VERSION:
                # Older but supported HA module version (e.g. the S800 reports
                # version 2 on its latest firmware). Everything except the
                # version-3-only live map/path features keeps working, so do
                # not nag the user to upgrade firmware that does not exist.
                _LOGGER.info(
                    "Firmware HA version %d is older than plugin version %d; "
                    "version-%d-only features (live map/path) are unavailable",
                    ha_version, CURRENT_HA_VERSION, CURRENT_HA_VERSION
                )
                self.compatibility_reason = f"ha_version_limited:{ha_version}"
                return CompatibilityStatus.COMPATIBLE
            elif ha_version > CURRENT_HA_VERSION:
                _LOGGER.warning(
                    "Firmware HA version is higher: %d > %d, recommend upgrading plugin",
                    ha_version, CURRENT_HA_VERSION
                )
                self.compatibility_reason = f"ha_version_high:{ha_version}"
                return CompatibilityStatus.DOWNGRADE_RECOMMENDED

            _LOGGER.info("Version compatibility check passed")
            self.compatibility_reason = ""  # Clear the reason for failure
            return CompatibilityStatus.COMPATIBLE

        except Exception as e:
            _LOGGER.error("Version compatibility check failed: %s", e)
            return CompatibilityStatus.INCOMPATIBLE

    def get_compatibility_message(self) -> str:
        """Get user-friendly compatibility status message."""
        if self.compatibility_status == CompatibilityStatus.COMPATIBLE:
            if self.compatibility_reason.startswith("ha_version_limited:"):
                firmware_version = self.compatibility_reason.split(':')[1]
                return (
                    f"Version compatible (firmware HA module version {firmware_version}); "
                    f"live map and path view require version {CURRENT_HA_VERSION}"
                )
            return "Version compatible, all functions working"
        elif self.compatibility_status == CompatibilityStatus.UPGRADE_REQUIRED:
            # Provide different prompts based on the specific reason
            if self.compatibility_reason.startswith("overall_version_low:"):
                return f"Firmware overall version too low, please upgrade firmware to version {MIN_REQUIRED_OVERALL_VERSION} or higher"
            elif self.compatibility_reason.startswith("ha_version_low:"):
                return f"Firmware HA module version too low (current: {self.compatibility_reason.split(':')[1]}, required: {CURRENT_HA_VERSION}), please upgrade firmware"
            else:
                return f"Firmware version too low, please upgrade firmware to overall version {MIN_REQUIRED_OVERALL_VERSION} or higher"
        elif self.compatibility_status == CompatibilityStatus.DOWNGRADE_RECOMMENDED:
            if self.compatibility_reason.startswith("ha_version_high:"):
                firmware_version = self.compatibility_reason.split(':')[1]
                return f"Firmware HA module version is higher (firmware: {firmware_version}, plugin: {CURRENT_HA_VERSION}), recommend upgrading plugin"
            else:
                return "Firmware HA version is higher than plugin version, recommend upgrading plugin or using corresponding firmware version"
        else:
            return "Version incompatible, cannot work properly"


# The config entry carries the live integration state (hub, compatibility,
# firmware) in its runtime_data instead of hass.data.
type TerraMowConfigEntry = ConfigEntry[TerraMowBasicData]


async def async_setup_entry(hass: HomeAssistant, entry: TerraMowConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]

    device_uid = entry.data.get(CONF_SERIAL) or host

    # Automatic migration of the device identifier. Legacy devices used the
    # arbitrary "TerraMowLawnMower" identifier domain (and before that a
    # misspelled variant) keyed on the host; the identifier is now
    # (DOMAIN, serial-or-host) as Home Assistant expects.
    device_registry = dr.async_get(hass)
    new_identifier = (DOMAIN, device_uid)
    legacy_identifiers = [
        ('TerraMowLanwMower', host),  # original misspelled identifier
        ('TerraMowLawnMower', host),  # pre-DOMAIN identifier
        (DOMAIN, host),  # host-keyed identifier from before serial adoption
    ]
    for legacy_identifier in legacy_identifiers:
        if legacy_identifier == new_identifier:
            continue
        old_device_entry = device_registry.async_get_device({legacy_identifier})
        if old_device_entry is None:
            continue
        # Check if a device with the new identifier already exists to avoid conflicts
        if device_registry.async_get_device({new_identifier}):
            if (
                entry.data.get(CONF_SERIAL)
                and entry.entry_id in old_device_entry.config_entries
            ):
                # Ghost left behind by a serial adoption that raced the
                # initial platform setup (<= 1.13.0): the host-keyed
                # duplicate can never be served again, the serial-keyed
                # device is the live one. Remove the ghost.
                _LOGGER.info(
                    "Removing stale duplicate device %s", legacy_identifier
                )
                device_registry.async_remove_device(old_device_entry.id)
            else:
                _LOGGER.warning("Cannot migrate device, a device with the new identifier already exists. Please remove the old device manually.")
        else:
            _LOGGER.info(
                "Migrating device identifier from %s to %s",
                legacy_identifier, new_identifier,
            )
            device_registry.async_update_device(
                old_device_entry.id, new_identifiers={new_identifier}
            )
        break

    if entry.data.get(CONF_SERIAL):
        # Same race cleanup on the entity side: once the serial is adopted,
        # entities only ever generate serial-based unique_ids, so host-keyed
        # registry entries are dead duplicates from the pre-1.13.1 race.
        host_fragment = f"terramow@{host}"
        entity_registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if host_fragment in reg_entry.unique_id:
                _LOGGER.info(
                    "Removing stale duplicate entity %s", reg_entry.entity_id
                )
                entity_registry.async_remove(reg_entry.entity_id)
    # End of Automatic migration

    _LOGGER.info("Setting up TerraMow with host %s", host)
    _LOGGER.debug("TerraMow entry data: %s", dict(entry.data))

    # Verify the broker accepts our credentials before bringing up platforms.
    # An InvalidAuth error triggers the reauth flow; a connection failure
    # asks Home Assistant to retry setup later.
    try:
        await validate_input(hass, {CONF_HOST: host, CONF_PASSWORD: password})
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed("Invalid TerraMow credentials") from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to TerraMow at {host}"
        ) from err

    basic_data = TerraMowBasicData(
        host=host,
        password=password,
        entry_id=entry.entry_id,
        device_uid=device_uid,
        assume_job_complete=bool(
            entry.options.get(
                CONF_ASSUME_JOB_COMPLETE, DEFAULT_ASSUME_JOB_COMPLETE
            )
        ),
    )

    # Stash the live integration state on the config entry itself; Home
    # Assistant clears runtime_data automatically when the entry unloads.
    entry.runtime_data = basic_data

    # Map card resources + WebSocket feed (idempotent across entries).
    await async_setup_map_card(hass)

    # The hub owns the MQTT connection and all protocol state. Starting it
    # before the platforms are forwarded guarantees every entity can
    # register its callbacks in __init__ regardless of platform order.
    hub = TerraMowHub(basic_data, hass)
    # Park any session path segments a previous run persisted BEFORE the hub
    # connects, so the first dp_113 frame can decide their fate (issue #239).
    await hub.async_restore_session_paths()
    # The self-sampled Wi-Fi heatmap likewise survives restarts (issue #200).
    await hub.async_restore_wifi_map()
    await hub.async_restore_fault_hotspots()
    await hub.async_restore_mow_counts()
    hub.start()

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # A failed platform setup means async_unload_entry never runs; stop
        # the hub here or its MQTT worker thread keeps reconnecting forever
        # and every setup retry would stack another hub+thread on top.
        await hub.async_stop()
        raise

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _async_register_services(hass)

    # A retained dp_102 usually arrives while the platforms are still being
    # set up, so the serial adoption parks itself in the hub. Consume it now
    # that the update listener is registered; the task runs after the entry
    # reaches LOADED, so the adoption's reload reconciles cleanly.
    entry.async_create_task(hass, hub.async_adopt_pending_serial())

    return True


async def _async_options_updated(hass: HomeAssistant, entry: TerraMowConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_START_SELECT_REGION):
        return

    def _resolve_hubs(entity_ids: list[str]) -> list[TerraMowHub]:
        registry = er.async_get(hass)
        targets: list[TerraMowHub] = []
        for entity_id in entity_ids:
            entry = registry.async_get(entity_id)
            if entry is None or entry.config_entry_id is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="entity_not_registered",
                    translation_placeholders={"entity_id": entity_id},
                )
            config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
            basic_data = getattr(config_entry, "runtime_data", None)
            if basic_data is None or basic_data.lawn_mower is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="lawn_mower_not_ready",
                    translation_placeholders={"entity_id": entity_id},
                )
            targets.append(basic_data.lawn_mower)
        return targets

    async def handle_start_select_region(call: ServiceCall) -> None:
        region_ids: list[int] = call.data[ATTR_REGION_IDS]
        for hub in _resolve_hubs(call.data[ATTR_ENTITY_ID]):
            # Confirmed write: waits for the device's dp_119 ack and raises
            # on rejection, so callers (and the map card's toast) see real
            # failures instead of optimistic success.
            await hub.async_start_select_region_clean(region_ids)

    async def handle_add_schedule(call: ServiceCall) -> None:
        start = call.data[ATTR_START_TIME]
        end = call.data[ATTR_END_TIME]
        item = TerraMowHub.build_schedule_item(
            week_days=[WEEKDAY_TO_DEVICE[day] for day in call.data[ATTR_WEEK_DAYS]],
            start_hour=start.hour,
            start_minute=start.minute,
            end_hour=end.hour,
            end_minute=end.minute,
            disabled=call.data[ATTR_DISABLED],
            run_once=call.data[ATTR_RUN_ONCE],
        )
        for hub in _resolve_hubs(call.data[ATTR_ENTITY_ID]):
            item_id = await hub.async_add_schedule(item)
            _LOGGER.info("Added schedule slot (item id %s)", item_id)

    async def handle_delete_schedule(call: ServiceCall) -> None:
        item_id: int = call.data[ATTR_ITEM_ID]
        for hub in _resolve_hubs(call.data[ATTR_ENTITY_ID]):
            await hub.async_delete_schedule(item_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_SELECT_REGION,
        handle_start_select_region,
        schema=START_SELECT_REGION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_SCHEDULE,
        handle_add_schedule,
        schema=ADD_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SCHEDULE,
        handle_delete_schedule,
        schema=DELETE_SCHEDULE_SCHEMA,
    )


async def async_unload_entry(hass: HomeAssistant, entry: TerraMowConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # If unloading is successful, stop the hub. runtime_data is cleared by HA.
    if unload_ok:
        async_clear_compatibility_issue(hass, entry.entry_id)
        async_clear_maintenance_issues(hass, entry.entry_id)
        basic_data = entry.runtime_data
        if basic_data.lawn_mower is not None:
            await basic_data.lawn_mower.async_stop()
        # Drop the shared service once the last entry is gone.
        remaining = [
            other
            for other in hass.config_entries.async_loaded_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        ]
        if not remaining:
            for service in (
                SERVICE_START_SELECT_REGION,
                SERVICE_ADD_SCHEDULE,
                SERVICE_DELETE_SCHEDULE,
            ):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)

    return unload_ok
