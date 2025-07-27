"""Test config flow for VentAxia HA."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.ventaxia_ha.config_flow import CannotConnect
from custom_components.ventaxia_ha.const import DOMAIN


@pytest.mark.asyncio
async def test_successful_config_flow(hass: HomeAssistant):
    """Test config flow completes successfully."""
    with patch(
        "custom_components.ventaxia_ha.config_flow.AsyncNativePskClient.connect",
        return_value=None,
    ), patch(
        "custom_components.ventaxia_ha.config_flow.AsyncNativePskClient.close",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "192.168.1.100",
                "port": 47819,
                "identity": "ventaxia_identity",
                "psk_key": "ventaxia_psk",
                "wifi_device_id": "ventaxia_1234",
            },
        )
        assert result2["type"] == "create_entry"


@pytest.mark.asyncio
async def test_config_flow_cannot_connect(hass: HomeAssistant):
    """Test config flow when connection fails."""
    with patch(
        "custom_components.ventaxia_ha.config_flow.AsyncNativePskClient.connect",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "192.168.1.100",
                "port": 47819,
                "identity": "ventaxia_identity",
                "psk_key": "ventaxia_psk",
                "wifi_device_id": "ventaxia_1234",
            },
        )
        assert result2["type"] == "form"
        assert result2["errors"]["base"] == "cannot_connect"
