from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VentAxiaCoordinator  # Only for type hints, won't execute at runtime
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    coordinator: VentAxiaCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities([VentAxiaCommissionModeSelect(coordinator)])


class VentAxiaCommissionModeSelect(SelectEntity):
    """Select normal or boost airflow for commissioning."""

    def __init__(self, coordinator: VentAxiaCoordinator):
        self._coordinator = coordinator
        self._attr_name = "Commissioning Mode Select"  # This sets the friendly name
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_select_commissioning_mode"  # Unique ID for HA
        self._attr_options = ["normal", "boost"]

    @property
    def current_option(self) -> str:
        return self._coordinator.commission_mode

    async def async_select_option(self, option: str) -> None:
        """Handle selection change in HA UI."""
        if option not in self._attr_options:
            return
        self._coordinator.commission_mode = option
        self.async_write_ha_state()
