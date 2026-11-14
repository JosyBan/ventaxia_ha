# File: ventaxia_ha/config_flow.py
"""Config flow for VentAxia IoT integration."""
from __future__ import annotations

import logging
import ssl
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .client import VentAxiaPskClient, decode_psk
from .const import (
    CONF_IDENTITY,
    CONF_MODEL,
    CONF_PSK_IS_HEX,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DEFAULT_IDENTITY_2023,
    DEFAULT_PORT,
    DEFAULT_PORT_2023,
    DOMAIN,
    MODEL_ADVANCE_S,
    MODEL_ADVANCE_S_2023,
)

_LOGGER = logging.getLogger(__name__)

# Older Advance S with a Wi-Fi module: identity is blank, PSK is the printed
# Wi-Fi key, device id is the printed SSID.
STEP_ADVANCE_S_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_IDENTITY, default=""): str,
        vol.Required(CONF_PSK_KEY): str,
        vol.Required(CONF_WIFI_DEVICE_ID): str,
    }
)

# Newer (>2023) / SX / Econiq controllers: no printed key. Identity is a fixed
# app constant and the PSK is extracted (as hex) from the pairing exchange.
STEP_ADVANCE_S_2023_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT_2023): int,
        vol.Required(CONF_IDENTITY, default=DEFAULT_IDENTITY_2023): str,
        vol.Required(CONF_PSK_KEY): str,
        vol.Required(CONF_PSK_IS_HEX, default=True): bool,
        vol.Required(CONF_WIFI_DEVICE_ID): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    psk_is_hex = data.get(CONF_PSK_IS_HEX, False)

    # Surface an obviously malformed hex PSK before attempting a connection.
    if psk_is_hex:
        try:
            decode_psk(data[CONF_PSK_KEY], True)
        except ValueError as err:
            raise InvalidPsk from err

    client = VentAxiaPskClient(
        wifi_device_id=data[CONF_WIFI_DEVICE_ID],
        identity=data[CONF_IDENTITY],
        psk_key=data[CONF_PSK_KEY],
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        psk_is_hex=psk_is_hex,
        pin_tls12=data.get(CONF_MODEL) == MODEL_ADVANCE_S_2023,
    )

    try:
        await client.connect(timeout=10.0)
        await client.close()
    except ssl.SSLError as err:
        if "application data after close notify" in str(err):
            _LOGGER.error(
                "Non-critical SSL shutdown error (device misbehavior): %s", err
            )
        elif (
            "bad record mac" in str(err).lower()
            or "wrong version number" in str(err).lower()
        ):
            _LOGGER.error("Invalid credentials: %s", err)
            raise InvalidAuth from err
        else:
            _LOGGER.error("Cannot connect to VentAxia device: %s", err)
            raise CannotConnect from err
    except Exception as err:
        _LOGGER.error("Cannot connect to VentAxia device: %s", err)
        raise

    return {"title": f"VentAxia Device ({data[CONF_HOST]})"}


class VentAxiaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VentAxia IoT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: choose the device model."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[MODEL_ADVANCE_S, MODEL_ADVANCE_S_2023],
        )

    async def async_step_advance_s(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Older Advance S with a Wi-Fi module (printed Key + SSID)."""
        return await self._async_handle_model_step(
            MODEL_ADVANCE_S, STEP_ADVANCE_S_SCHEMA, user_input
        )

    async def async_step_advance_s_2023(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Newer (>2023) / SX / Econiq controller (identity + extracted PSK)."""
        return await self._async_handle_model_step(
            MODEL_ADVANCE_S_2023, STEP_ADVANCE_S_2023_SCHEMA, user_input
        )

    async def _async_handle_model_step(
        self,
        model: str,
        schema: vol.Schema,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Shared handling for both model forms."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {**user_input, CONF_MODEL: model}
            try:
                info = await validate_input(self.hass, data)
            except InvalidPsk:
                errors["base"] = "invalid_psk"
            except InvalidAuth:
                errors["base"] = "auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_WIFI_DEVICE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id=model, data_schema=schema, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication credentials."""


class InvalidPsk(HomeAssistantError):
    """Error to indicate the PSK could not be decoded."""
