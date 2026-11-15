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
from datetime import datetime, timedelta
from typing import Any, Callable

import paho.mqtt.client as mqtt
from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

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


# Airflow override (the app's "Change mode"): publish {"gtm": N, "treq": "HH:MM:SS"}
# to <deviceId>/vent/uo. gtm 0=Off/cancel, 1=Low, 2=Normal, 3=Boost, 4=Purge,
# 5=Max (matches the caf "ps" field the unit reports). Verified on a live unit.
OVERRIDE_TOPIC = "vent/uo"
MODE_TO_GTM = {"Auto": 0, "Low": 1, "Normal": 2, "Boost": 3, "Purge": 4, "Max": 5}
GTM_TO_MODE = {1: "Low", 2: "Normal", 3: "Boost", 4: "Purge", 5: "Max"}
MODE_OPTIONS = ["Auto", "Low", "Normal", "Boost", "Purge", "Max"]
# Default override duration (minutes) when a mode is selected; adjustable via the
# Override Duration number entity. The unit reverts to its schedule afterwards.
DEFAULT_OVERRIDE_MINUTES = 15
MIN_OVERRIDE_MINUTES = 5
MAX_OVERRIDE_MINUTES = 480
BOOST_DURATION = "00:15:00"

# The hardware override (vent/uo) is always timed — the unit ignores a zero
# duration, so there is no native "boost until cancelled". The Boost Hold switch
# emulates it by re-arming a timed boost in chunks while it is on.
HOLD_CHUNK_MINUTES = 60
HOLD_REARM_BUFFER_MINUTES = 5
REFRESH_INTERVAL = timedelta(seconds=30)


def minutes_to_treq(minutes: int) -> str:
    """Format a whole-minute duration as the unit's "HH:MM:SS" treq string."""
    minutes = max(0, int(minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def treq_to_seconds(treq: str) -> int:
    """Parse an "HH:MM:SS" treq string into whole seconds (0 on failure)."""
    try:
        hh, mm, ss = (int(part) for part in treq.split(":"))
    except (ValueError, AttributeError):
        return 0
    return hh * 3600 + mm * 60 + ss


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
        # Override duration (minutes) used when a mode is selected; settable via
        # the Override Duration number entity.
        self.override_minutes: int = DEFAULT_OVERRIDE_MINUTES
        # Locally-tracked override end time. The unit's own `vent/cor` `trem`
        # timestamp is in the controller's local wall-clock with no timezone, so
        # it cannot be trusted for a countdown when the unit's clock differs from
        # HA's. We know exactly what duration we asked for, so we track it here.
        self._local_override_end: datetime | None = None
        # Boost Hold ("boost until turned off") — re-arms a timed boost.
        self.boost_hold: bool = False
        self._refresh_unsub: Callable[[], None] | None = None

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
        # Automatically reconnect (with backoff) if the socket drops. loop_start's
        # network thread drives the retries; without this a dropped connection
        # would leave every entity stuck "unavailable" until HA restarts.
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.tls_set_context(self._build_context())
        self._client = client

        host = self.data[CONF_HOST]
        port = self.data[CONF_PORT]
        await self.hass.async_add_executor_job(client.connect, host, port, 30)
        client.loop_start()

        # Drive the override countdown and the Boost Hold re-arm on a steady tick,
        # independent of how often the unit publishes telemetry.
        self._refresh_unsub = async_track_time_interval(
            self.hass, self._tick, REFRESH_INTERVAL
        )

    async def async_stop(self) -> None:
        if self._refresh_unsub is not None:
            self._refresh_unsub()
            self._refresh_unsub = None
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.loop_stop()
                await self.hass.async_add_executor_job(client.disconnect)
            except Exception:  # pragma: no cover - best effort shutdown
                _LOGGER.debug("Error during MQTT shutdown", exc_info=True)

    def _tick(self, now=None) -> None:
        """Periodic tick: re-arm a held boost and refresh countdown entities."""
        if self.boost_hold:
            end = self._local_override_end
            if (
                end is None
                or (end - dt_util.now()).total_seconds()
                < HOLD_REARM_BUFFER_MINUTES * 60
            ):
                self._apply_boost_chunk()
        self._notify()

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
    def _override_active(self) -> bool | None:
        """Whether a user override is running.

        True while our locally-tracked override is still in the future, or while
        the unit's `vent/cor` reports a non-empty `trem` (an override started
        outside HA, e.g. from the wall controller). Empty `trem` with no local
        override means the unit is following its schedule (the "Auto" state).
        Returns None when nothing is known yet.
        """
        if self._local_override_end is not None:
            return self._local_override_end > dt_util.now()
        raw = self.values.get("vent/cor")
        if raw is None:
            return None
        try:
            cor = json.loads(raw)
        except (ValueError, AttributeError):
            return None
        return bool(cor.get("trem"))

    def _device_override_end(self) -> datetime | None:
        """Parse the unit's reported override end (vent/cor 'trem'); clock-based."""
        raw = self.values.get("vent/cor")
        if not raw:
            return None
        try:
            trem = json.loads(raw).get("trem")
        except (ValueError, AttributeError):
            return None
        if not trem:
            return None
        try:
            parsed = datetime.fromisoformat(trem)
        except (ValueError, TypeError):
            return None
        # The unit reports local wall-clock time without a zone.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    @property
    def override_ends_at(self) -> datetime | None:
        """When the active override ends.

        Prefers our locally-tracked end (immune to the unit's clock/timezone);
        falls back to the unit's reported `trem` for overrides started elsewhere.
        """
        local = self._local_override_end
        if local is not None and local > dt_util.now():
            return local
        if local is None:
            return self._device_override_end()
        return None

    @property
    def override_remaining_minutes(self) -> int | None:
        """Minutes left on the active override, or None when idle."""
        ends = self.override_ends_at
        if ends is None:
            return None
        remaining = (ends - dt_util.now()).total_seconds() / 60
        return max(0, round(remaining))

    @property
    def current_mode(self) -> str | None:
        """Current ventilation mode for the select.

        "Auto" when the unit is following its schedule (no override), otherwise
        the active override speed from caf 'ps'. Falls back to the raw speed
        until the override status (vent/cor) has been received.
        """
        active = self._override_active
        if active is False:
            return "Auto"
        raw = self.values.get("vent/caf")
        if not raw:
            return "Auto" if active is None else None
        try:
            ps = json.loads(raw).get("ps")
        except (ValueError, AttributeError):
            return None
        return GTM_TO_MODE.get(ps)

    def set_override(self, gtm: int, treq: str) -> None:
        """Publish an airflow override to the unit and track its end locally."""
        if self._client is None:
            return
        payload = json.dumps({"gtm": gtm, "treq": treq})
        # QoS 1 so a press issued during a brief reconnect is still delivered.
        self._client.publish(f"{self.device_id}/{OVERRIDE_TOPIC}", payload, qos=1)
        _LOGGER.debug("VentAxia override -> %s", payload)
        # Track the end locally (clock-independent). gtm 0 cancels the override.
        if gtm == 0:
            self._local_override_end = None
        else:
            secs = treq_to_seconds(treq)
            self._local_override_end = (
                dt_util.now() + timedelta(seconds=secs) if secs > 0 else None
            )
        self._notify()

    def _apply_boost_chunk(self) -> None:
        """(Re)issue a timed boost chunk to keep Boost Hold alive."""
        self.set_override(MODE_TO_GTM["Boost"], minutes_to_treq(HOLD_CHUNK_MINUTES))

    def set_boost_hold(self, on: bool) -> None:
        """Turn 'boost until cancelled' on or off (emulated via re-arming)."""
        self.boost_hold = on
        if on:
            self._apply_boost_chunk()
        else:
            self.set_override(0, "00:00:00")
        self._notify()

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


class VentAxiaMqttModeSelect(SelectEntity):
    """Airflow mode override for the newer controller."""

    _attr_has_entity_name = True
    _attr_name = "Ventilation Mode"
    _attr_icon = "mdi:fan"
    _attr_options = MODE_OPTIONS

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_mode"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        # Controls stay pressable across brief reconnects; the command is sent
        # with QoS 1 and delivered once the socket is back.
        return True

    @property
    def current_option(self) -> str | None:
        return self._coordinator.current_mode

    async def async_select_option(self, option: str) -> None:
        gtm = MODE_TO_GTM.get(option)
        if gtm is None:
            return
        treq = (
            "00:00:00" if gtm == 0
            else minutes_to_treq(self._coordinator.override_minutes)
        )
        self._coordinator.set_override(gtm, treq)

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)


class VentAxiaMqttBoostButton(ButtonEntity):
    """One-press boost for a fixed duration."""

    _attr_has_entity_name = True
    _attr_name = "Boost 15 min"
    _attr_icon = "mdi:fan-plus"

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_boost"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        # A button is stateless; keep it pressable across brief reconnects.
        return True

    async def async_press(self) -> None:
        self._coordinator.set_override(MODE_TO_GTM["Boost"], BOOST_DURATION)


class VentAxiaMqttBoostHoldSwitch(SwitchEntity, RestoreEntity):
    """Boost until turned off.

    The unit's override is always timed (a zero duration is ignored), so this
    switch emulates an indefinite boost by re-arming a timed boost in chunks
    while it is on — ideal for driving from an automation (e.g. a hob sensor)
    instead of wiring a relay to the hardware Boost input.
    """

    _attr_has_entity_name = True
    _attr_name = "Boost Hold"
    _attr_icon = "mdi:fan-plus"

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_boost_hold"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def is_on(self) -> bool:
        return self._coordinator.boost_hold

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._coordinator.set_boost_hold(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._coordinator.set_boost_hold(False)

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        # Restore the hold across restarts; re-arm if it was on.
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            self._coordinator.set_boost_hold(True)
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)


class VentAxiaMqttDurationNumber(RestoreNumber):
    """How long a selected mode override runs before the unit reverts."""

    _attr_has_entity_name = True
    _attr_name = "Override Duration"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = MIN_OVERRIDE_MINUTES
    _attr_native_max_value = MAX_OVERRIDE_MINUTES
    _attr_native_step = 5
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = "box"

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_override_duration"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def native_value(self) -> float:
        return self._coordinator.override_minutes

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.override_minutes = int(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._coordinator.override_minutes = int(last.native_value)


class VentAxiaMqttRemainingSensor(SensorEntity):
    """Minutes left on the active override (blank when on schedule)."""

    _attr_has_entity_name = True
    _attr_name = "Override Remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_override_remaining"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._coordinator.available

    @property
    def native_value(self) -> int:
        return self._coordinator.override_remaining_minutes or 0

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)
