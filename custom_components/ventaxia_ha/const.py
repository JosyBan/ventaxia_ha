# File: ventaxia_ha/const.py

"""Constants for the VentAxia IoT integration."""

DOMAIN = "ventaxia_ha"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_IDENTITY = "identity"
CONF_PSK_KEY = "psk_key"
CONF_WIFI_DEVICE_ID = "wifi_device_id"

# Default values
DEFAULT_PORT = 47819

# Airflow modes
AIRFLOW_MODES = {
    "reset": 0,
    "normal": 2,
    "boost": 3,
    "purge": 4,
}

VALID_DURATIONS = [0, 15, 30, 45, 60]

# Service names
SERVICE_SET_AIRFLOW_MODE = "set_airflow_mode"

# weighting for the supply temp
EXTRACT_WEIGHT = 0.9
