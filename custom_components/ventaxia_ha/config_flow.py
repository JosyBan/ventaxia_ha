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
from ventaxiaiot import AsyncNativePskClient

from .const import (
    CONF_IDENTITY,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_IDENTITY): str,
        vol.Required(CONF_PSK_KEY): str,
        vol.Required(CONF_WIFI_DEVICE_ID): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    client = AsyncNativePskClient(
        wifi_device_id=data[CONF_WIFI_DEVICE_ID],
        identity=data[CONF_IDENTITY],
        psk_key=data[CONF_PSK_KEY],
        host=data[CONF_HOST],
        port=data[CONF_PORT],
    )

    try:
        await client.connect(timeout=10.0)
        await client.close()
    except ssl.SSLError as err:
        if "application data after close notify" in str(err):
            _LOGGER.error(
                "Non-critical SSL shutdown error (device misbehavior): %s", err
            )
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
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on wifi_device_id
                await self.async_set_unique_id(user_input[CONF_WIFI_DEVICE_ID])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
