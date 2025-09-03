# File: ventaxia_ha/sensor.py
"""Sensor platform for VentAxia IoT integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import as_utc

from custom_components.ventaxia_ha import const

from . import VentAxiaCoordinator
from .const import DOMAIN

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


# Map of entity descriptions
ENTITY_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="supply_rpm",
        name="Supply RPM",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="exhaust_rpm",
        name="Exhaust RPM",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="manual_airflow",
        name="Airflow Mode",
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="manual_airflow_active",
        name="Airflow Active",
        icon="mdi:fan-clock",
    ),
    SensorEntityDescription(
        key="power",
        name="Power",
        icon="mdi:power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="indoor_temp",
        name="Indoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outdoor_temp",
        name="Outdoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="supply_temp",
        name="Supply Air Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="supply_airflow",
        name="Supply Airflow",
        icon="mdi:weather-windy",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="exhaust_airflow",
        name="Exhaust Airflow",
        icon="mdi:weather-windy",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="external_humidity",
        name="External Humidity",
        icon="mdi:cloud-percent",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="internal_humidity",
        name="Internal Humidity",
        icon="mdi:cloud-percent",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="service_info",
        name="Service Info",
        icon="mdi:tools",
        native_unit_of_measurement=UnitOfTime.MONTHS,
    ),
    SensorEntityDescription(
        key="filter_months_remaining",
        name="Filter Months Remaining",
        icon="mdi:tools",
        native_unit_of_measurement=UnitOfTime.MONTHS,
    ),
    SensorEntityDescription(
        key="schedules",
        name="Schedules",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="silent_hours",
        name="Silent Hours",
        icon="mdi:weather-night",
    ),
    SensorEntityDescription(
        key="summer_bypass_mode",
        name="Summer Bypass Mode",
        icon="mdi:weather-sunny",
    ),
    SensorEntityDescription(
        key="summer_bypass_af_mode",
        name="Summer Bypass Airflow Mode",
        icon="mdi:fan",
    ),
    SensorEntityDescription(
        key="summer_bypass_indoor_temp",
        name="Summer Bypass Indoor Temp",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    SensorEntityDescription(
        key="summer_bypass_outdoor_temp",
        name="Summer Bypass Outdoor Temp",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
)


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


class VentAxiaSensor(SensorEntity):
    """Representation of a VentAxia sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self, coordinator: VentAxiaCoordinator, description: SensorEntityDescription
    ) -> None:
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_{description.key}"
        if description.key == "manual_airflow":
            self._last_manual_airflow_active: bool | None = (
                None  # Track last active state
            )

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
                const.EXTRACT_WEIGHT * device.extract_temp_c
                + (1 - const.EXTRACT_WEIGHT) * device.outdoor_temp_c,
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

        key = self.entity_description.key

        if key == "manual_airflow":
            device = self._coordinator.device
            # Only proceed if active state changed
            if self._last_manual_airflow_active == device.manual_airflow_active:
                return

            # Offload timer start/cancel to background task
            self.hass.async_create_task(self._update_manual_airflow_timer())

    async def _update_manual_airflow_timer(self):
        """Start or cancel the manual airflow timer only on state change."""
        device = self._coordinator.device
        timer_entity = "timer.manual_airflow_timer"

        self._last_manual_airflow_active = device.manual_airflow_active

        async def call_service(service: str, data: dict):
            """Helper to call a service safely in fire-and-forget mode."""
            try:
                await self.hass.services.async_call("timer", service, data)
            except Exception as e:
                _LOGGER.error("Failed to call timer.%s with %s: %s", service, data, e)

        if device.manual_airflow_active:
            # Compute remaining seconds
            remaining_sec = max(
                0,
                int(
                    (
                        device.manual_airflow_end_time - datetime.now(timezone.utc)
                    ).total_seconds()
                ),
            )
            if remaining_sec > 0:
                self.hass.async_create_task(
                    call_service(
                        "start",
                        {
                            "entity_id": timer_entity,
                            "duration": remaining_sec,
                        },
                    )
                )
        else:
            # Cancel timer if airflow is no longer active
            self.hass.async_create_task(
                call_service(
                    "cancel",
                    {"entity_id": timer_entity},
                )
            )
