# File: ventaxia_ha/sensor.py
"""Sensor platform for VentAxia IoT integration."""
from __future__ import annotations

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
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
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
        VentAxiaUserAirflowModeSensor(coordinator),
        VentAxiaPowerSensor(coordinator),
        VentAxiaIndoorTempSensor(coordinator),
        VentAxiaOutdoorTempSensor(coordinator),
        VentAxiaSupplyTempSensor(coordinator),
        VentAxiaSupplyAirflowSensor(coordinator),
        VentAxiaExhaustAirflowSensor(coordinator),
        VentAxiaExternalHumiditySensor(coordinator),
        VentAxiaInternalHumiditySensor(coordinator),
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
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        return self._coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self._coordinator.add_update_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        self._coordinator.remove_update_callback(self.async_write_ha_state)


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


class VentAxiaUserAirflowModeSensor(VentAxiaBaseSensor):
    """User airflow mode sensor."""

    def __init__(self, coordinator: VentAxiaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "user_airflow_mode")
        self._attr_name = "Airflow Mode"
        self._attr_icon = "mdi:air-filter"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self._coordinator.device.get_user_airflow_mode

    @property
    def extra_state_attributes(self) -> dict[str, any] | None:
        """Return additional state attributes."""
        device = self._coordinator.device
        attrs = {}
        if device.as_af is not None:
            attrs["mode_code"] = device.as_af
        if device.ar_min is not None:
            attrs["duration_minutes"] = device.ar_min
        if device.as_rsec is not None:
            attrs["remaining_seconds"] = device.as_rsec
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

        return round(
            const.EXTRACT_WEIGHT * self._coordinator.device.extract_temp_c
            + (1 - const.EXTRACT_WEIGHT) * self._coordinator.device.extract_temp_c,
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
