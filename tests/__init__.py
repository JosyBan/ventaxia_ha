"""Common pytest fixtures for VentAxia HA tests."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Fixture to set up the integration in HA."""
    config = {
        "ventaxia_ha": {
            "host": "192.168.1.100",
            "port": 47819,
            "identity": "ventaxia_identity",
            "psk_key": "ventaxia_psk",
            "wifi_device_id": "ventaxia_1234",
        }
    }
    assert await async_setup_component(hass, "ventaxia_ha", config)
    await hass.async_block_till_done()
    return config
