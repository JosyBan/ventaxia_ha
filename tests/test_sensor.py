"""Test VentAxia sensors."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.mark.asyncio
async def test_sensor_entities(hass: HomeAssistant, setup_integration):
    """Test that sensor entities are created."""
    entity_registry = er.async_get(hass)

    expected_sensors = [
        "sensor.ventaxia_supply_rpm",
        "sensor.ventaxia_exhaust_rpm",
        "sensor.ventaxia_airflow_mode",
        "sensor.ventaxia_power",
    ]

    for sensor in expected_sensors:
        entry = entity_registry.async_get(sensor)
        assert entry is not None
