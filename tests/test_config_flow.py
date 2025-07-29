# tests/test_config_flow.py

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

# Ensure these exceptions are correctly imported from your config_flow.py
from custom_components.ventaxia_ha.config_flow import CannotConnect, InvalidAuth
from custom_components.ventaxia_ha.const import DOMAIN

from .const import MOCK_CONFIG

# Note: The `hass` fixture is provided by `pytest-homeassistant-custom-component`
# We now use the `mock_ventaxia_iot_components` fixture from tests/conftest.py


async def test_successful_config_flow(
    hass: HomeAssistant, mock_ventaxia_iot_components: dict
):
    """Test a successful config flow."""
    # Access the mock VentaxiaProtocol class from the components dict
    mock_ventaxia_protocol_class = mock_ventaxia_iot_components["protocol_class"]

    # Start the configuration flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Check that the form is shown
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Fill in the form with mock data
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )

    # Check that the flow completed successfully
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_CONFIG[CONF_HOST]
    assert result["data"] == MOCK_CONFIG

    # Ensure the check_connection method was called on our mock VentaxiaProtocol class
    mock_ventaxia_protocol_class.check_connection.assert_called_once()
    # Also, check that the AsyncNativePskClient.connect was called during setup_entry
    mock_ventaxia_iot_components["client"].connect.assert_called_once()


async def test_config_flow_cannot_connect(
    hass: HomeAssistant, mock_ventaxia_iot_components: dict
):
    """Test connection error during config flow."""
    # Make the mock VentaxiaProtocol's check_connection raise an exception for this test
    mock_ventaxia_iot_components["protocol_class"].check_connection.side_effect = (
        CannotConnect
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )

    # Check that the form is shown again with an error
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["step_id"] == "user"

    mock_ventaxia_iot_components["protocol_class"].check_connection.assert_called_once()
    # Connect should not be called if check_connection fails
    mock_ventaxia_iot_components["client"].connect.assert_not_called()


async def test_config_flow_invalid_auth(
    hass: HomeAssistant, mock_ventaxia_iot_components: dict
):
    """Test invalid authentication error during config flow."""
    # Make the mock VentaxiaProtocol's check_connection raise an InvalidAuth exception
    mock_ventaxia_iot_components["protocol_class"].check_connection.side_effect = (
        InvalidAuth
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )

    # Check that the form is shown again with an invalid_auth error
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["step_id"] == "user"

    mock_ventaxia_iot_components["protocol_class"].check_connection.assert_called_once()
    mock_ventaxia_iot_components["client"].connect.assert_not_called()


async def test_config_flow_already_configured(
    hass: HomeAssistant, mock_ventaxia_iot_components: dict, setup_integration
):
    """Test that duplicate host/device ID is aborted."""
    # A config entry is already set up by `setup_integration` fixture

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_CONFIG
    )

    # It should abort if it detects an existing entry
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
