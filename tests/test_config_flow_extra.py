"""Additional config flow coverage: validate_input, zeroconf, options."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.terramow.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_input,
)
from custom_components.terramow.const import (
    CONF_MAP_RESOLUTION,
    CONF_MAP_SHOW_COVERAGE,
    CONF_MAP_THEME,
    DEFAULT_MAP_SHOW_COVERAGE,
    DEFAULT_MAP_THEME,
    DOMAIN,
    MAP_RESOLUTION_OPTIONS,
)

USER_INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "secret"}


class _FakeMqttClient:
    """Minimal paho stand-in that delivers a scripted CONNACK."""

    rc = 0
    connect_raises = False

    def __init__(self, *args, **kwargs) -> None:
        self.on_connect = None

    def username_pw_set(self, username, password) -> None:
        pass

    def connect(self, host, port, keepalive) -> None:
        if type(self).connect_raises:
            raise OSError("no route to host")

    def loop_start(self) -> None:
        # paho would deliver the CONNACK from its network thread; do it inline.
        if self.on_connect is not None:
            self.on_connect(self, None, None, type(self).rc)

    def loop_stop(self) -> None:
        pass

    def disconnect(self) -> None:
        pass


def _patch_client(rc: int = 0, connect_raises: bool = False):
    client_cls = type(
        "ScriptedClient",
        (_FakeMqttClient,),
        {"rc": rc, "connect_raises": connect_raises},
    )
    return patch(
        "custom_components.terramow.config_flow.create_mqtt_client",
        side_effect=client_cls,
    )


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


async def test_validate_input_success(hass: HomeAssistant) -> None:
    with _patch_client(rc=0):
        info = await validate_input(hass, USER_INPUT)
    assert info["title"] == "TerraMow (192.0.2.10)"


@pytest.mark.parametrize("rc", [4, 5])
async def test_validate_input_auth_failure(hass: HomeAssistant, rc: int) -> None:
    with _patch_client(rc=rc), pytest.raises(InvalidAuth):
        await validate_input(hass, USER_INPUT)


async def test_validate_input_cannot_connect_on_exception(hass: HomeAssistant) -> None:
    with _patch_client(connect_raises=True), pytest.raises(CannotConnect):
        await validate_input(hass, USER_INPUT)


async def test_validate_input_cannot_connect_on_no_connack(hass: HomeAssistant) -> None:
    # rc other than 0/4/5 leaves connected=False -> CannotConnect
    with _patch_client(rc=3), pytest.raises(CannotConnect):
        await validate_input(hass, USER_INPUT)


# ---------------------------------------------------------------------------
# zeroconf discovery
# ---------------------------------------------------------------------------


class _Discovery:
    def __init__(self, host):
        self.host = host


async def test_zeroconf_discovery_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery("192.0.2.55"),
    )
    # discovery moves straight to the password step
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user_pass"

    with patch(
        "custom_components.terramow.config_flow.validate_input",
        return_value={"title": "TerraMow (192.0.2.55)"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "secret"}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.0.2.55", CONF_PASSWORD: "secret"}


async def test_zeroconf_without_host_aborts(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery(None),
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_zeroconf_password_step_reports_invalid_auth(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_Discovery("192.0.2.55"),
    )
    with patch(
        "custom_components.terramow.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


# ---------------------------------------------------------------------------
# options flow
# ---------------------------------------------------------------------------


async def test_options_flow_sets_map_resolution(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    resolution = MAP_RESOLUTION_OPTIONS[-1]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAP_RESOLUTION: resolution}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # unset fields fall back to their defaults
    assert result["data"] == {
        CONF_MAP_RESOLUTION: resolution,
        CONF_MAP_THEME: DEFAULT_MAP_THEME,
        CONF_MAP_SHOW_COVERAGE: DEFAULT_MAP_SHOW_COVERAGE,
    }


async def test_options_flow_sets_theme_and_coverage(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_MAP_RESOLUTION: MAP_RESOLUTION_OPTIONS[0],
            CONF_MAP_THEME: "dark",
            CONF_MAP_SHOW_COVERAGE: True,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAP_THEME] == "dark"
    assert result["data"][CONF_MAP_SHOW_COVERAGE] is True
