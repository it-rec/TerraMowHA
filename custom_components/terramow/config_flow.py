"""Config flow for the TerraMow integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import aiomqtt
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    OptionsFlow,
)
from homeassistant.config_entries import (
    ConfigFlow as BaseConfigFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    # Imported lazily for typing only: ConfigFlowResult is not present on the
    # oldest supported Home Assistant versions, and ``from __future__ import
    # annotations`` keeps these annotations from being evaluated at runtime.
    from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_ASSUME_JOB_COMPLETE,
    CONF_MAP_RESOLUTION,
    CONF_MAP_SHOW_COVERAGE,
    CONF_MAP_THEME,
    CONF_SERIAL,
    DEFAULT_ASSUME_JOB_COMPLETE,
    DEFAULT_MAP_RESOLUTION,
    DEFAULT_MAP_SHOW_COVERAGE,
    DEFAULT_MAP_THEME,
    DOMAIN,
    MAP_RESOLUTION_OPTIONS,
    MAP_THEME_OPTIONS,
    MQTT_PORT,
    MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_USER_PASS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): str,
    }
)


def _is_auth_failure(err: aiomqtt.MqttCodeError) -> bool:
    """Return True when a CONNACK refusal means bad credentials.

    MQTT 3.1.1 CONNACK codes 4 (bad username/password) and 5 (not
    authorized); paho 2.x may normalize these to the MQTT 5 reason codes
    134/135, delivered as ``ReasonCode`` objects carrying a ``value``.
    """
    code = getattr(err.rc, "value", err.rc)
    return code in (4, 5, 134, 135)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input and test the MQTT connection.

    Raises InvalidAuth on authentication failure (broker rejects credentials)
    and CannotConnect for any other failure mode. ``hass`` is unused but kept:
    the signature is the config-flow validate convention and tests patch it.
    """
    try:
        # Belt and braces around aiomqtt's own operation timeout, so a
        # half-open TCP connect can never hang the flow.
        async with asyncio.timeout(10):
            async with aiomqtt.Client(
                hostname=data[CONF_HOST],
                port=MQTT_PORT,
                username=MQTT_USERNAME,
                password=data[CONF_PASSWORD],
                timeout=5,
            ):
                pass  # a successful CONNACK is all the validation needed
    except aiomqtt.MqttCodeError as err:
        if _is_auth_failure(err):
            raise InvalidAuth from err
        _LOGGER.error("Connection failed: %s", err)
        raise CannotConnect from err
    except (aiomqtt.MqttError, OSError, TimeoutError) as err:
        _LOGGER.error("Connection failed: %s", err)
        raise CannotConnect from err

    return {"title": f"TerraMow ({data[CONF_HOST]})"}


class ConfigFlow(BaseConfigFlow, domain=DOMAIN):
    """Handle a config flow for TerraMow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                host = user_input[CONF_HOST]
                _LOGGER.info('Setting up for host "%s"', host)
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                if self._host_already_configured(host):
                    # Serial-keyed entries are not keyed by host, so the
                    # unique-id check alone would let a duplicate through.
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
        )

    async def async_step_zeroconf(self, discovery_info: Any) -> ConfigFlowResult:
        """Handle a flow initialized by zeroconf discovery."""
        host = getattr(discovery_info, "host", None)
        if host is None and isinstance(discovery_info, dict):
            host = discovery_info.get("host")
        if not host:
            return self.async_abort(reason="cannot_connect")

        _LOGGER.info("Zeroconf discovered TerraMow at %s", host)

        # Prefer the serial from the announcement's TXT properties as the
        # stable identity; entries created before serial adoption (or
        # announcements without one) fall back to the host. Matching a
        # serial-keyed entry updates its host, which is what heals a DHCP
        # address change.
        properties = getattr(discovery_info, "properties", None)
        serial = properties.get("sn") if isinstance(properties, dict) else None
        await self.async_set_unique_id(serial or host)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        if self._host_already_configured(host):
            # A serial-keyed entry rediscovered without a serial in the
            # announcement does not match the unique id; dedupe by host.
            return self.async_abort(reason="already_configured")

        self._discovered_host = host
        self.context["title_placeholders"] = {"host": host}

        return await self.async_step_user_pass()

    def _host_already_configured(self, host: str) -> bool:
        """Return True if an existing entry already uses this host."""
        return any(
            entry.data.get(CONF_HOST) == host
            for entry in self._async_current_entries()
        )

    async def async_step_user_pass(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for the password after zeroconf discovery."""
        errors: dict[str, str] = {}

        if self._discovered_host is None:
            return await self.async_step_user(user_input)

        if user_input is not None:
            data = {
                CONF_HOST: self._discovered_host,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                info = await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                _LOGGER.info(
                    'Setting up discovered host "%s"', self._discovered_host
                )
                return self.async_create_entry(
                    title=info["title"],
                    data=data,
                )

        return self.async_show_form(
            step_id="user_pass",
            data_schema=STEP_USER_PASS_DATA_SCHEMA,
            description_placeholders={"host": self._discovered_host},
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Trigger the re-authentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}
        entry_id = self.context.get("entry_id")
        entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id is not None
            else None
        )

        if user_input is not None and entry is not None:
            updated_data = {
                **entry.data,
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                await validate_input(self.hass, updated_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data=updated_data
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry (e.g. a changed IP/host)."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if user_input is not None and entry is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                new_host = user_input[CONF_HOST]
                # Abort if the new host is already used by another entry.
                for other in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        other.entry_id != entry.entry_id
                        and other.data.get(CONF_HOST) == new_host
                    ):
                        return self.async_abort(reason="already_configured")
                _LOGGER.info('Reconfiguring host to "%s"', new_host)
                serial = entry.data.get(CONF_SERIAL)
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=info["title"],
                    # Keep the adopted serial (the mower moved address, it
                    # did not change identity) and the serial-based unique
                    # id; host-keyed entries keep following the host.
                    data={**user_input, CONF_SERIAL: serial}
                    if serial
                    else user_input,
                    unique_id=serial or new_host,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, entry.data if entry else {}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TerraMowOptionsFlow(config_entry)


class TerraMowOptionsFlow(OptionsFlow):
    """Handle TerraMow options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAP_RESOLUTION,
                    default=options.get(CONF_MAP_RESOLUTION, DEFAULT_MAP_RESOLUTION),
                ): vol.In(MAP_RESOLUTION_OPTIONS),
                vol.Required(
                    CONF_MAP_THEME,
                    default=options.get(CONF_MAP_THEME, DEFAULT_MAP_THEME),
                ): vol.In(MAP_THEME_OPTIONS),
                vol.Required(
                    CONF_MAP_SHOW_COVERAGE,
                    default=options.get(
                        CONF_MAP_SHOW_COVERAGE, DEFAULT_MAP_SHOW_COVERAGE
                    ),
                ): bool,
                vol.Required(
                    CONF_ASSUME_JOB_COMPLETE,
                    default=options.get(
                        CONF_ASSUME_JOB_COMPLETE, DEFAULT_ASSUME_JOB_COMPLETE
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
