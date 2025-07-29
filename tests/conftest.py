# C:\Users\josyb\Documents\Code\Vent Python\ventaxia_ha\tests\conftest.py

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

# We also need to import the VentaxiaProtocol for config_flow, and VentaxiaDevice for its structure
# Import classes from the external ventaxiaiot library that we need to mock
from ventaxiaiot import AsyncNativePskClient, VentClientCommands, VentMessageProcessor

# Import constants from your integration
from custom_components.ventaxia_ha.const import (
    CONF_HOST,
    CONF_IDENTITY,
    CONF_PORT,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DOMAIN,
)

# --- MOCKING THE EXTERNAL VENTAXIAIOT LIBRARY COMPONENTS ---


@pytest.fixture
async def mock_ventaxia_iot_components():
    """
    Fixture to mock the essential classes from the ventaxiaiot library
    that your integration uses.
    """
    # 1. Mock ventaxiaiot.AsyncNativePskClient (used by VentAxiaCoordinator)
    mock_async_native_psk_client = AsyncMock(spec=AsyncNativePskClient)
    mock_async_native_psk_client.connect.return_value = (
        None  # Simulate successful connection
    )
    mock_async_native_psk_client.close.return_value = None  # Simulate successful close

    # If your integration uses async for msg in client, we might need a more advanced mock for __aiter__
    # For basic setup/entity tests, the above might suffice if the loop is short-lived or doesn't yield actual messages.
    # For now, we'll assume the loop doesn't block forever without actual data.

    mock_ventaxia_processor = AsyncMock(spec=VentMessageProcessor)
    # Crucially, make the processor's 'device' attribute return our mock device
    mock_ventaxia_processor.device = mock_async_native_psk_client
    mock_ventaxia_processor.process.return_value = (
        None  # Simulates processing a message
    )

    # 3. Mock ventaxiaiot.VentClientCommands
    mock_vent_client_commands = AsyncMock(spec=VentClientCommands)
    mock_vent_client_commands.send_airflow_mode_request.return_value = True

    # Use patch context manager to apply all mocks during the test
    with patch(
        "ventaxiaiot.AsyncNativePskClient", return_value=mock_async_native_psk_client
    ), patch(
        "ventaxiaiot.VentMessageProcessor", return_value=mock_ventaxia_processor
    ), patch(
        "ventaxiaiot.VentClientCommands", return_value=mock_vent_client_commands
    ):
        yield {
            "client": mock_async_native_psk_client,
            "processor": mock_ventaxia_processor,
            "commands": mock_vent_client_commands,
        }


# --- FIXTURE TO SET UP THE VENTAXIA INTEGRATION IN HOME ASSISTANT ---


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_ventaxia_iot_components: dict):
    """
    Fixture to set up the VentAxia integration in HA, using all mocked components.
    """
    config = {
        DOMAIN: {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 47819,
            CONF_IDENTITY: "ventaxia_identity",
            CONF_PSK_KEY: "ventaxia_psk",
            CONF_WIFI_DEVICE_ID: "ventaxia_1234",
        }
    }

    # This call will now use the mocked ventaxiaiot components, avoiding real network calls.
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    # The integration should now be loaded. The `mock_ventaxia_iot_components`
    # dictionary contains references to your mocked objects if you need to
    # assert calls on them within individual tests.
    return config
