# tests/const.py

from custom_components.ventaxia_ha.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_IDENTITY,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
)

# Mock configuration data for testing config flows
MOCK_CONFIG = {
    CONF_HOST: "192.168.1.100",
    CONF_PORT: 47819,
    CONF_IDENTITY: "test_identity",
    CONF_PSK_KEY: "test_psk",
    CONF_WIFI_DEVICE_ID: "test_device_id",
}

# Add more mock data if needed for different scenarios or device states
MOCK_DEVICE_INFO = {
    "model": "VentAxia Svara",
    "firmware": "1.0.0",
    "serial": "VENT12345",
}

MOCK_SENSOR_DATA = {
    "temperature": 23.0,
    "humidity": 60,
    "fan_speed": 3,
    "mode": "auto",
    "boost_time": 0,
    "light_level": 50,
    "status": "online",
}