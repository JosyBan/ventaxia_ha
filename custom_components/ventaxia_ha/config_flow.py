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
# The device ID and PSK can be auto-filled over Bluetooth (see ble.py), so the
# schema is built dynamically with whatever BLE detected as the defaults.
def _schema_advance_s_2023(device_id: str = "", psk: str = "") -> vol.Schema:
    """Build the newer-model form, pre-filling BLE-detected values."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT_2023): int,
            vol.Required(CONF_IDENTITY, default=DEFAULT_IDENTITY_2023): str,
            vol.Required(CONF_PSK_KEY, default=psk): str,
            vol.Required(CONF_PSK_IS_HEX, default=True): bool,
            vol.Required(CONF_WIFI_DEVICE_ID, default=device_id): str,
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
        """Newer (>2023) / SX / Econiq controller (identity + extracted PSK).

        On first display we try to read the device ID and PSK straight off the
        unit over Bluetooth and pre-fill them. Only the host IP then has to be
        entered by hand.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {**user_input, CONF_MODEL: MODEL_ADVANCE_S_2023}
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

            # Re-show the form keeping what the user typed.
            return self.async_show_form(
                step_id=MODEL_ADVANCE_S_2023,
                data_schema=_schema_advance_s_2023(
                    user_input.get(CONF_WIFI_DEVICE_ID, ""),
                    user_input.get(CONF_PSK_KEY, ""),
                ),
                errors=errors,
                description_placeholders={"ble_status": self._ble_status_retry()},
            )

        # First display: attempt Bluetooth auto-detect of device ID + PSK.
        device_id, psk, ble_status = await self._async_ble_autodetect()
        return self.async_show_form(
            step_id=MODEL_ADVANCE_S_2023,
            data_schema=_schema_advance_s_2023(device_id, psk),
            errors=errors,
            description_placeholders={"ble_status": ble_status},
        )

    @staticmethod
    def _ble_status_retry() -> str:
        """Status line shown when re-displaying the form after an error."""
        return (
            "If you reached the form by Bluetooth auto-detect, the device ID and "
            "PSK above came from the unit. Otherwise enter them by hand."
        )

    async def _async_ble_autodetect(self) -> tuple[str, str, str]:
        """Try to read device ID + PSK over BLE. Returns (device_id, psk, note)."""
        try:
            from .ble import async_read_credentials  # noqa: PLC0415

            creds = await async_read_credentials(self.hass)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("VentAxia BLE auto-detect unavailable: %s", err)
            return (
                "",
                "",
                "Bluetooth auto-detect found no unit in range (or this host has "
                "no Bluetooth adapter). Enter the device ID and PSK by hand — the "
                "PSK is the 'tlsKey' your unit exposes over Bluetooth in pairing "
                "mode, entered as hex.",
            )

        device_id = str(creds.get("device_id") or "")
        psk_hex = creds.get("psk_hex")
        if psk_hex:
            return (
                device_id,
                str(psk_hex),
                f"Auto-detected over Bluetooth — device ID '{device_id}' and the "
                "PSK have been filled in. Just add the Host (the unit's IP "
                "address) and submit.",
            )
        return (
            device_id,
            "",
            f"Auto-detected device ID '{device_id}' over Bluetooth, but the PSK is "
            "locked: the unit is already paired, so it reads back as zeros. Put the "
            "unit into pairing mode and reopen this to auto-read the PSK, or enter "
            "it by hand.",
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

        return self.async_show_form(step_id=model, data_schema=schema, errors=errors)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication credentials."""


class InvalidPsk(HomeAssistantError):
    """Error to indicate the PSK could not be decoded."""
