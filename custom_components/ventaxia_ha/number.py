# File: ventaxia_ha/number.py
"""Number platform for VentAxia IoT integration (newer controllers only)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VentAxia number entities for the newer (MQTT) controller."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    from .mqtt_coordinator import (
        VentAxiaMqttCoordinator,
        VentAxiaMqttDurationNumber,
        VentAxiaMqttHumidityThresholdNumber,
    )

    if isinstance(coordinator, VentAxiaMqttCoordinator):
        async_add_entities(
            [
                VentAxiaMqttDurationNumber(coordinator),
                VentAxiaMqttHumidityThresholdNumber(coordinator),
            ]
        )
