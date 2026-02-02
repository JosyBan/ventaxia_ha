# File: ventaxia_ha/button.py
"""Button platform for VentAxia IoT integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VentAxiaCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VentAxia buttons from a config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        VentAxiaResetModeButton(coordinator),
        VentAxiaNormalModeButton(coordinator),
        VentAxiaBoostModeButton(coordinator),
        VentAxiaPurgeModeButton(coordinator),
        VentAxiaCommissionModeButton(coordinator),
        VentAxiaStopCommissioningButton(coordinator),
    ]

    async_add_entities(entities)


class VentAxiaBaseButton(ButtonEntity):
    """Base class for VentAxia buttons."""

    def __init__(
        self, coordinator: VentAxiaCoordinator, button_type: str, name: str
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._button_type = button_type
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_{button_type}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo | None:  # type: ignore[override]
        """Return device information."""
        return self._coordinator.device_info

    @property
    def available(self):  # type: ignore[override]
        return self._coordinator.available

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self._coordinator.add_update_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        self._coordinator.remove_update_callback(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from coordinator."""
        self.async_write_ha_state()


class VentAxiaResetModeButton(VentAxiaBaseButton):
    """Reset/Cancel airflow mode button."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "reset_mode", "Reset Airflow Mode")
        self._attr_icon = "mdi:stop-circle"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._coordinator.async_send_airflow_mode("reset", 0)
            _LOGGER.info("Reset airflow mode command sent")
        except Exception as err:
            _LOGGER.error("Failed to send reset command: %s", err)


class VentAxiaCommissionModeButton(VentAxiaBaseButton):
    """Button to start commissioning based on dropdown selection."""

    def __init__(self, coordinator: VentAxiaCoordinator):
        self._coordinator = coordinator
        self._button_type = "commission_mode"
        self._attr_unique_id = (
            f"{coordinator.data['wifi_device_id']}_commission_mode_button"
        )
        self._attr_name = "Start Commissioning"
        self._attr_icon = "mdi:fan"

    async def async_press(self) -> None:
        """Send commissioning command using dropdown selection."""
        airflow = self._coordinator.commission_mode
        try:
            await self._coordinator.async_start_commissioning(airflow)
            _LOGGER.info("Commissioning started with mode: %s", airflow)
        except Exception as err:
            _LOGGER.error("Failed to start commissioning: %s", err)


class VentAxiaStopCommissioningButton(VentAxiaBaseButton):
    """Button to stop the commissioning keep-alive loop."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "stop_commissioning_mode", "Stop Commissioning")
        self._attr_icon = "mdi:stop-circle"

    async def async_press(self) -> None:
        """Stop the commissioning loop."""
        try:
            await self._coordinator.async_stop_commissioning()
            _LOGGER.info("Commissioning loop stopped")
        except Exception as err:
            _LOGGER.error("Failed to stop commissioning: %s", err)


class VentAxiaNormalModeButton(VentAxiaBaseButton):
    """Normal airflow mode button."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "normal_mode", "Normal Mode (15 min)")
        self._attr_icon = "mdi:fan"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._coordinator.async_send_airflow_mode("normal", 15)
            _LOGGER.info("Normal mode (15 min) command sent")
        except Exception as err:
            _LOGGER.error("Failed to send normal mode command: %s", err)


class VentAxiaBoostModeButton(VentAxiaBaseButton):
    """Boost airflow mode button."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "boost_mode", "Boost Mode (30 min)")
        self._attr_icon = "mdi:fan-plus"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._coordinator.async_send_airflow_mode("boost", 30)
            _LOGGER.info("Boost mode (30 min) command sent")
        except Exception as err:
            _LOGGER.error("Failed to send boost mode command: %s", err)


class VentAxiaPurgeModeButton(VentAxiaBaseButton):
    """Purge airflow mode button."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "purge_mode", "Purge Mode (60 min)")
        self._attr_icon = "mdi:fan-speed-3"

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self._coordinator.async_send_airflow_mode("purge", 60)
            _LOGGER.info("Purge mode (60 min) command sent")
        except Exception as err:
            _LOGGER.error("Failed to send purge mode command: %s", err)
