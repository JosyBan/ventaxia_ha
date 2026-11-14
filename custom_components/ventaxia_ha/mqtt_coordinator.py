# File: ventaxia_ha/mqtt_coordinator.py
"""MQTT coordinator for the newer (>2023) Advance S / SX / Econiq controllers.

Unlike the older Advance S (raw null-framed JSON over TLS-PSK, handled by
``ventaxiaiot``), these controllers run a real MQTT broker over a TLS-PSK
socket on port 8883. After connecting with identity ``zirconia`` and the
provisioned PSK (pinned to TLS 1.2), the client subscribes to
``<deviceId>/#`` and the unit publishes retained telemetry such as:

    <deviceId>/io/t1          outdoor air temperature (C)
    <deviceId>/io/t3          extract air temperature (C)
    <deviceId>/io/erh/val     extract relative humidity (%)
    <deviceId>/io/irh/val     intake relative humidity (%)
    <deviceId>/mdet/pwr       total power (W)
    <deviceId>/mdet/wifi/sta  {"rssi":..,"ssid":..}
    <deviceId>/vent/afs/rpm   supply fan speed (rpm)   (+ /pwr /pwm)
    <deviceId>/vent/afe/rpm   extract fan speed (rpm)  (+ /pwr /pwm)

Confirmed against a live unit; see docs/newer_model_notes.md.
"""
from __future__ import annotations

import json
import logging
import ssl
from typing import Any, Callable

import paho.mqtt.client as mqtt
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
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .client import decode_psk
from .const import (
    CONF_HOST,
    CONF_IDENTITY,
    CONF_PORT,
    CONF_PSK_IS_HEX,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Topic suffix (after "<deviceId>/") -> sensor description.
MQTT_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="io/t1",
        name="Outdoor Air Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="io/t3",
        name="Extract Air Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="io/erh/val",
        name="Extract Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="io/irh/val",
        name="Intake Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="mdet/pwr",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="vent/afs/rpm",
        name="Supply Fan Speed",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="vent/afe/rpm",
        name="Extract Fan Speed",
        icon="mdi:fan",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="vent/afs/pwr",
        name="Supply Fan Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="vent/afe/pwr",
        name="Extract Fan Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="mdet/wifi/sta#rssi",
        name="Wi-Fi Signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


class VentAxiaMqttCoordinator:
    """Maintain the MQTT-over-TLS-PSK connection and cache published values."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.device_id: str = entry.data[CONF_WIFI_DEVICE_ID]
        self.values: dict[str, Any] = {}
        self._connected = False
        self._callbacks: set[Callable[[], None]] = set()
        self._client: mqtt.Client | None = None

    # ---- lifecycle -------------------------------------------------------
    def _build_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("PSK-AES128-CBC-SHA")
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        identity = self.data[CONF_IDENTITY]
        psk = decode_psk(
            self.data[CONF_PSK_KEY], self.data.get(CONF_PSK_IS_HEX, False)
        )
        ctx.set_psk_client_callback(lambda hint: (identity, psk))
        return ctx

    async def async_start(self) -> None:
        """Create the client and connect (runs blocking setup in executor)."""
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"ha-{self.device_id}",
            )
        except (AttributeError, TypeError):  # older paho without CallbackAPIVersion
            client = mqtt.Client(client_id=f"ha-{self.device_id}")

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.tls_set_context(self._build_context())
        self._client = client

        host = self.data[CONF_HOST]
        port = self.data[CONF_PORT]
        await self.hass.async_add_executor_job(client.connect, host, port, 30)
        client.loop_start()

    async def async_stop(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.loop_stop()
                await self.hass.async_add_executor_job(client.disconnect)
            except Exception:  # pragma: no cover - best effort shutdown
                _LOGGER.debug("Error during MQTT shutdown", exc_info=True)

    # ---- paho callbacks (run in paho's network thread) -------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        rc = getattr(reason_code, "value", reason_code)
        if rc not in (0, mqtt.CONNACK_ACCEPTED if hasattr(mqtt, "CONNACK_ACCEPTED") else 0):
            _LOGGER.warning("VentAxia MQTT connect failed: rc=%s", reason_code)
            return
        self._connected = True
        client.subscribe(f"{self.device_id}/#", qos=0)
        self.hass.loop.call_soon_threadsafe(self._notify)

    def _on_disconnect(self, *args):
        self._connected = False
        self.hass.loop.call_soon_threadsafe(self._notify)

    def _on_message(self, client, userdata, msg):
        suffix = msg.topic[len(self.device_id) + 1:] if msg.topic.startswith(
            self.device_id + "/"
        ) else msg.topic
        payload = msg.payload.decode("utf-8", "replace")
        self.values[suffix] = payload
        # Flatten the Wi-Fi JSON blob into a synthetic rssi topic.
        if suffix == "mdet/wifi/sta":
            try:
                self.values["mdet/wifi/sta#rssi"] = json.loads(payload).get("rssi")
            except (ValueError, AttributeError):
                pass
        self.hass.loop.call_soon_threadsafe(self._notify)

    # ---- helpers ---------------------------------------------------------
    def _notify(self) -> None:
        for cb in tuple(self._callbacks):
            cb()

    def get(self, key: str) -> Any:
        return self.values.get(key)

    @property
    def available(self) -> bool:
        return self._connected

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=f"VentAxia {self.device_id}",
            manufacturer="Vent-Axia",
            model="Sentinel Kinetic Advance S (>2023)",
        )

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.add(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        self._callbacks.discard(callback)


class VentAxiaMqttSensor(SensorEntity):
    """A sensor backed by one MQTT topic of the newer controller."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: VentAxiaMqttCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return (
            self._coordinator.available
            and self._coordinator.get(self.entity_description.key) is not None
        )

    @property
    def native_value(self) -> Any:
        raw = self._coordinator.get(self.entity_description.key)
        if raw is None:
            return None
        if self.entity_description.native_unit_of_measurement is None:
            return raw
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)
