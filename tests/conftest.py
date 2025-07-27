# C:\Users\josyb\Documents\Code\Vent Python\ventaxia_ha\tests\conftest.py

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

# Import classes from the external ventaxiaiot library that we need to mock
from ventaxiaiot import (
    AsyncNativePskClient,
    PendingRequestTracker,
    VentClientCommands,
    VentMessageProcessor,
)
# We also need to import the VentaxiaProtocol for config_flow, and VentaxiaDevice for its structure
from ventaxiaiot import (
    AsyncNativePskClient,
    PendingRequestTracker,
    VentClientCommands,
    VentMessageProcessor,
)


# Import constants from your integration
from custom_components.ventaxia_ha.const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_IDENTITY,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
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
    mock_async_native_psk_client.connect.return_value = None # Simulate successful connection
    mock_async_native_psk_client.close.return_value = None # Simulate successful close

    # If your integration uses async for msg in client, we might need a more advanced mock for __aiter__
    # For basic setup/entity tests, the above might suffice if the loop is short-lived or doesn't yield actual messages.
    # For now, we'll assume the loop doesn't block forever without actual data.

    # 2. Mock ventaxiaiot.VentMessageProcessor and its 'device' attribute
    # First, create a mock for the internal VentaxiaDevice object
    mock_ventaxia_device = AsyncMock(spec=VentaxiaDevice)
    # Populate the mock device with expected properties/attributes.
    # These are the values your sensors/entities will read.
    mock_ventaxia_device.dname = "Test VentAxia Device"
    mock_ventaxia_device.firmware = "V1.0.0" # Example, add if your device_info uses it
    mock_ventaxia_device.serial_no = "TEST12345" # Example, add if your device_info uses it

    # Populate properties that sensors would read
    mock_ventaxia_device.temp = 22.5
    mock_ventaxia_device.rh = 60
    mock_ventaxia_device.fan_speed = 3
    mock_ventaxia_device.operating_mode = "auto"
    mock_ventaxia_device.boost_remaining = 0
    mock_ventaxia_device.light_level = 50
    # Add any other attributes your sensors or device info might try to access from `coordinator.device`

    mock_ventaxia_processor = AsyncMock(spec=VentMessageProcessor)
    # Crucially, make the processor's 'device' attribute return our mock device
    mock_ventaxia_processor.device = mock_ventaxia_device
    mock_ventaxia_processor.process.return_value = None # Simulates processing a message

    # 3. Mock ventaxiaiot.VentClientCommands
    mock_vent_client_commands = AsyncMock(spec=VentClientCommands)
    mock_vent_client_commands.send_airflow_mode_request.return_value = True

    # 4. Mock ventaxiaiot.ventaxia_protocol.VentaxiaProtocol (used by config_flow)
    mock_ventaxia_protocol_class = AsyncMock(spec=VentaxiaProtocol)
    # For the class method `check_connection`, we mock it directly on the class mock
    mock_ventaxia_protocol_class.check_connection.return_value = True

    # Use patch context manager to apply all mocks during the test
    with patch("ventaxiaiot.AsyncNativePskClient", return_value=mock_async_native_psk_client), \
         patch("ventaxiaiot.VentMessageProcessor", return_value=mock_ventaxia_processor), \
         patch("ventaxiaiot.VentClientCommands", return_value=mock_vent_client_commands), \
         patch("ventaxiaiot.ventaxia_protocol.VentaxiaProtocol", new=mock_ventaxia_protocol_class):
        yield {
            "client": mock_async_native_psk_client,
            "processor": mock_ventaxia_processor,
            "commands": mock_vent_client_commands,
            "protocol_class": mock_ventaxia_protocol_class,
            "device": mock_ventaxia_device, # Yield the mock device for direct state manipulation in tests
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