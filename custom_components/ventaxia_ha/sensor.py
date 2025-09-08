# File: ventaxia_ha/sensor.py
"""Sensor platform for VentAxia IoT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import as_utc

from . import VentAxiaCoordinator
from .const import DOMAIN, EXTRACT_WEIGHT
from .entities import ENTITY_DESCRIPTIONS
from .runtime_timer import VentAxiaRuntimeTimer

_LOGGER = logging.getLogger(__name__)

# Simple mapping: entity key -> device attribute
RETURN_VALUE: dict[str, str] = {
    "supply_rpm": "sup_rpm",
    "exhaust_rpm": "exh_rpm",
    "manual_airflow": "manual_airflow_mode",
    "manual_airflow_active": "manual_airflow_active",
    "power": "pwr",
    "indoor_temp": "extract_temp_c",
    "outdoor_temp": "outdoor_temp_c",
    "supply_airflow": "cm_af_sup",
    "exhaust_airflow": "cm_af_exh",
    "external_humidity": "exr_rh",
    "internal_humidity": "itk_rh",
    "service_info": "service_months_remaining",
    "filter_months_remaining": "filter_months_remaining",
    "summer_bypass_mode": "summer_bypass_mode",
    "summer_bypass_af_mode": "summer_bypass_af_mode",
    "summer_bypass_indoor_temp": "summer_bypass_indoor_temp",
    "summer_bypass_outdoor_temp": "summer_bypass_outdoor_temp",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VentAxia sensors from a config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        VentAxiaSensor(coordinator, description) for description in ENTITY_DESCRIPTIONS
    )

    # Add the runtime timer entity
    runtime_timer = VentAxiaRuntimeTimer(hass, coordinator, name="manual_airflow_timer")
    coordinator.manual_airflow_timer = runtime_timer
    async_add_entities([runtime_timer])


class VentAxiaSensor(SensorEntity):
    """Representation of a VentAxia sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self, coordinator: VentAxiaCoordinator, description: SensorEntityDescription
    ) -> None:
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo | None:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._coordinator.available

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_coordinator_update)

    @property
    def native_value(self) -> Any:
        device = self._coordinator.device
        key = self.entity_description.key

        # Use mapping for simple direct attributes
        if key in RETURN_VALUE:
            value = getattr(device, RETURN_VALUE[key], None)

            # Round service_info and filter_months_remaining to 1 decimal
            if key in ["service_info", "filter_months_remaining"]:
                return round(value, 1) if value is not None else None

            return value

        # Other complex cases
        if key == "schedules":
            return len(device.schedules)
        if key == "silent_hours":
            sh = device.silent_hours
            if not sh:
                return None
            return f"{sh.get('from')}–{sh.get('to')}"
        # Handle supply_temp as exception
        if key == "supply_temp":
            if device.extract_temp_c is None or device.outdoor_temp_c is None:
                return None
            return round(
                EXTRACT_WEIGHT * device.extract_temp_c
                + (1 - EXTRACT_WEIGHT) * device.outdoor_temp_c,
                2,
            )

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self._coordinator.device
        key = self.entity_description.key

        if key == "manual_airflow":
            attrs = {}
            if device.as_af is not None:
                attrs["manual_airflow_mode"] = device.manual_airflow_mode
            if device.manual_airflow_timer_min is not None:
                attrs["manual_airflow_timer_min"] = device.manual_airflow_timer_min
            if device.manual_airflow_sec is not None:
                attrs["manual_airflow_sec"] = device.manual_airflow_sec
            if device.manual_airflow_active is not None:
                attrs["manual_airflow_active"] = device.manual_airflow_active
            if device.manual_airflow_end_time is not None:
                attrs["manual_airflow_end_time"] = as_utc(
                    device.manual_airflow_end_time
                )  # ensure UTC datetime
            return attrs if attrs else None

        if key == "schedules":
            return device.schedules

        if key == "silent_hours":
            return device.silent_hours

        if key == "summer_bypass_mode":
            return {
                "af_mode": device.summer_bypass_af_mode,
                "indoor_temp_c": device.summer_bypass_indoor_temp,
                "outdoor_temp_c": device.summer_bypass_outdoor_temp,
            }

        return None

    @callback
    def _handle_coordinator_update(self):
        """Update HA state and handle manual airflow timer changes."""
        self.async_write_ha_state()
        device = self._coordinator.device
        key = self.entity_description.key

        if (
            key == "manual_airflow"
            and self._coordinator.manual_airflow_timer is not None
        ):
            # Start/stop the runtime timer
            timer_entity = self._coordinator.manual_airflow_timer

            if device.manual_airflow_active:
                self.hass.async_create_task(
                    timer_entity.async_start_timer(
                        duration_minutes=device.manual_airflow_timer_min
                    )
                )
            else:
                # Optionally stop/cancel the timer if airflow ends early
                self.hass.async_create_task(timer_entity.async_cancel_timer())
