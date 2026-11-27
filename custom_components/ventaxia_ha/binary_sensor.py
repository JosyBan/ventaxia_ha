# File: ventaxia_ha/binary_sensor.py
"""Binary sensor platform for VentAxia IoT integration (newer >2023 model)."""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VentAxia binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    from .mqtt_coordinator import VentAxiaMqttCoordinator

    if isinstance(coordinator, VentAxiaMqttCoordinator):
        async_add_entities(
            [
                VentAxiaMqttBinarySensor(
                    coordinator,
                    "auto",
                    "Auto",
                    lambda c: c.auto,
                    icon="mdi:fan-auto",
                )
            ]
        )


class VentAxiaMqttBinarySensor(BinarySensorEntity):
    """A binary sensor whose state is computed from the MQTT coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: "VentAxiaMqttCoordinator",  # noqa: F821
        key: str,
        name: str,
        value_fn: Callable[[Any], bool | None],
        *,
        icon: str | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._value_fn = value_fn
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_name = name
        if icon is not None:
            self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return (
            self._coordinator.available
            and self._value_fn(self._coordinator) is not None
        )

    @property
    def is_on(self) -> bool | None:
        return self._value_fn(self._coordinator)

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)
