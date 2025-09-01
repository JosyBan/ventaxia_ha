# File: ventaxia_ha/sensor.py
"""Sensor platform for VentAxia IoT integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
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

from custom_components.ventaxia_ha import const

from . import VentAxiaCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VentAxia sensors from a config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        VentAxiaSupplyRpmSensor(coordinator),
        VentAxiaExhaustRpmSensor(coordinator),
        VentAxiaManualAirflowSensor(coordinator),
        VentAxiaPowerSensor(coordinator),
        VentAxiaIndoorTempSensor(coordinator),
        VentAxiaOutdoorTempSensor(coordinator),
        VentAxiaSupplyTempSensor(coordinator),
        VentAxiaSupplyAirflowSensor(coordinator),
        VentAxiaExhaustAirflowSensor(coordinator),
        VentAxiaExternalHumiditySensor(coordinator),
        VentAxiaInternalHumiditySensor(coordinator),
        VentAxiaServiceSensor(coordinator),
        VentAxiaFilterSensor(coordinator),
        VentAxiaSchedulesSensor(coordinator),
        VentAxiaSilentHoursSensor(coordinator),
        VentAxiaSummerBypassSensor(coordinator),
        VentAxiaSummerBypassAFModeSensor(coordinator),
        VentAxiaSummerBypassIndoorTempSensor(coordinator),
        VentAxiaSummerBypassOutdoorTempSensor(coordinator),
    ]

    async_add_entities(entities)


class VentAxiaBaseSensor(SensorEntity):
    """Base class for VentAxia sensors."""

    def __init__(self, coordinator: VentAxiaCoordinator, sensor_type: str) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_{sensor_type}"

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


class VentAxiaSupplyRpmSensor(VentAxiaBaseSensor):
    """Supply RPM sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "supply_rpm")
        self._attr_name = "Supply RPM"
        self._attr_icon = "mdi:fan"
        self._attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.sup_rpm


class VentAxiaExhaustRpmSensor(VentAxiaBaseSensor):
    """Exhaust RPM sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "exhaust_rpm")
        self._attr_name = "Exhaust RPM"
        self._attr_icon = "mdi:fan"
        self._attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.exh_rpm


class VentAxiaManualAirflowSensor(VentAxiaBaseSensor):
    """User airflow mode sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "manual_airflow")
        self._attr_name = "Airflow Mode"
        self._attr_icon = "mdi:air-filter"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self._coordinator.device.manual_airflow_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        device = self._coordinator.device
        attrs = {}
        if device.as_af is not None:
            attrs["manual_airflow_mode"] = device.as_af
        if device.manual_airflow_timer_min is not None:
            attrs["manual_airflow_timer_min"] = device.manual_airflow_timer_min
        if device.manual_airflow_sec is not None:
            attrs["manual_airflow_sec"] = device.manual_airflow_sec
        if device.manual_airflow_active is not None:
            attrs["manual_airflow_active"] = device.manual_airflow_active
        if device.manual_airflow_end_time is not None:
            attrs["manual_airflow_end_time"] = device.manual_airflow_end_time
        return attrs if attrs else None


class VentAxiaPowerSensor(VentAxiaBaseSensor):
    """Power percentage sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "power")
        self._attr_name = "Power"
        self._attr_icon = "mdi:power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.pwr


class VentAxiaIndoorTempSensor(VentAxiaBaseSensor):
    """Indoor temperature sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "indoor_temp")
        self._attr_name = "Indoor Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self._coordinator.device.extract_temp_c


class VentAxiaOutdoorTempSensor(VentAxiaBaseSensor):
    """Outdoor temperature sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "outdoor_temp")
        self._attr_name = "Outdoor Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self._coordinator.device.outdoor_temp_c


class VentAxiaSupplyTempSensor(VentAxiaBaseSensor):
    """Supply air temperature sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "supply_temp")
        self._attr_name = "Supply Air Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        extract = self._coordinator.device.extract_temp_c
        outdoor = self._coordinator.device.outdoor_temp_c

        if extract is None or outdoor is None:
            return None

        return round(
            const.EXTRACT_WEIGHT * extract + (1 - const.EXTRACT_WEIGHT) * outdoor,
            2,
        )


class VentAxiaSupplyAirflowSensor(VentAxiaBaseSensor):
    """Supply airflow sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "supply_airflow")
        self._attr_name = "Supply Airflow"
        self._attr_icon = "mdi:weather-windy"
        self._attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_SECOND
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.cm_af_sup


class VentAxiaExhaustAirflowSensor(VentAxiaBaseSensor):
    """Exhaust airflow sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "exhaust_airflow")
        self._attr_name = "Exhaust Airflow"
        self._attr_icon = "mdi:weather-windy"
        self._attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_SECOND
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.cm_af_exh


class VentAxiaExternalHumiditySensor(VentAxiaBaseSensor):
    """External Humidity sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "external_humidity")
        self._attr_name = "External Humidity"
        self._attr_icon = "mdi:cloud-percent"
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.exr_rh


class VentAxiaInternalHumiditySensor(VentAxiaBaseSensor):
    """Internal Humidity sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "internal_humidity")
        self._attr_name = "Internal Humidity"
        self._attr_icon = "mdi:cloud-percent"
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._coordinator.device.itk_rh


class VentAxiaServiceSensor(VentAxiaBaseSensor):
    """Service Info sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "service_info")
        self._attr_name = "Service Info"
        self._attr_icon = "mdi:tools"
        self._attr_native_unit_of_measurement = UnitOfTime.MONTHS

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self._coordinator.device.service_months_remaining


class VentAxiaFilterSensor(VentAxiaBaseSensor):
    """Filter Info sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "filter_months_remaining")
        self._attr_name = "Filter Months Remaining"
        self._attr_icon = "mdi:tools"
        self._attr_native_unit_of_measurement = UnitOfTime.MONTHS

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self._coordinator.device.filter_months_remaining


class VentAxiaSchedulesSensor(VentAxiaBaseSensor):
    """Schedules Info sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "schedules")
        self._attr_name = "Schedules"
        self._attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> int:
        """Return number of defined schedules."""
        return len(self._coordinator.device.schedules)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._coordinator.device.schedules


class VentAxiaSilentHoursSensor(VentAxiaBaseSensor):
    """Silent Hours Info sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "silent_hours")
        self._attr_name = "Silent Hours"
        self._attr_icon = "mdi:weather-night"

    @property
    def native_value(self) -> str | None:
        """Return a short summary."""
        sh = self._coordinator.device.silent_hours
        if not sh:
            return None
        return f'{sh.get("from")}–{sh.get("to")}'

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._coordinator.device.silent_hours


class VentAxiaSummerBypassSensor(VentAxiaBaseSensor):
    """Summer bypass mode sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        super().__init__(coordinator, "summer_bypass_mode")
        self._attr_name = "Summer Bypass Mode"
        self._attr_icon = "mdi:weather-sunny"

    @property
    def native_value(self) -> str:
        """Return the current summer bypass mode."""
        return self._coordinator.device.summer_bypass_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._coordinator.device
        attrs: dict[str, Any] = {}
        attrs["af_mode"] = device.summer_bypass_af_mode
        attrs["indoor_temp_c"] = device.summer_bypass_indoor_temp
        attrs["outdoor_temp_c"] = device.summer_bypass_outdoor_temp
        return attrs


class VentAxiaSummerBypassAFModeSensor(VentAxiaBaseSensor):
    """Summer Bypass AF Mode sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        super().__init__(coordinator, "summer_bypass_af_mode")
        self._attr_name = "Summer Bypass Airflow Mode"
        self._attr_icon = "mdi:fan"

    @property
    def native_value(self) -> str:
        return self._coordinator.device.summer_bypass_af_mode


class VentAxiaSummerBypassIndoorTempSensor(VentAxiaBaseSensor):
    """Summer Bypass AF Mode sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        super().__init__(coordinator, "summer_bypass_indoor_temp")
        self._attr_name = "Summer Bypass Indoor Temp"
        self._attr_icon = "mdi:thermometer"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        return self._coordinator.device.summer_bypass_indoor_temp


class VentAxiaSummerBypassOutdoorTempSensor(VentAxiaBaseSensor):
    """Summer Bypass Outdoor Temp sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        super().__init__(coordinator, "summer_bypass_outdoor_temp")
        self._attr_name = "Summer Bypass Outdoor Temp"
        self._attr_icon = "mdi:thermometer"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        return self._coordinator.device.summer_bypass_outdoor_temp
