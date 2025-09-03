# File: ventaxia_ha/entities.py

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)

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
