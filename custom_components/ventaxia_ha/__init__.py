# File: ventaxia_ha/__init__.py
"""The VentAxia IoT integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Dict, Optional

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from ventaxiaiot import (
    AsyncNativePskClient,
    PendingRequestTracker,
    VentClientCommands,
    VentMessageProcessor,
)

from .const import (
    AIRFLOW_MODES,
    CONF_HOST,
    CONF_IDENTITY,
    CONF_PORT,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DOMAIN,
    SERVICE_SET_AIRFLOW_MODE,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_SUMMER_BYPASS,
    TIME_REGEX,
    VALID_DAYS,
    VALID_DURATIONS,
    VALID_MODES,
)
from .runtime_timer import VentAxiaRuntimeTimer

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON, Platform.SELECT]

SERVICE_SET_AIRFLOW_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("mode"): vol.In(list(AIRFLOW_MODES.keys())),
        vol.Required("duration"): vol.In(VALID_DURATIONS),
    }
)


def validate_days(value: str) -> str:
    if value == "Every day" or all(d.strip() in VALID_DAYS for d in value.split(",")):
        return value
    raise vol.Invalid(f"Invalid days: {value}")


SERVICE_SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Required("from"): vol.Match(TIME_REGEX),  # HH:MM
        vol.Required("to"): vol.Match(TIME_REGEX),
        vol.Required("days"): vol.All(str, validate_days),
        vol.Required("mode"): vol.In(VALID_MODES),
    }
)

SERVICE_SET_SUMMER_BYPASS_SCHEMA = vol.Schema(
    {
        vol.Optional("m_byp"): vol.In([0, 1, 2, 3]),  # Bypass modes
        vol.Optional("af_enp"): vol.In([0, 1, 2, 3, 4]),  # Airflow modes
        vol.Optional("indoor_temp"): vol.Coerce(float),
        vol.Optional("outdoor_temp"): vol.Coerce(float),
    }
)


class VentAxiaCoordinator:
    """Coordinator for VentAxia IoT device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.manual_airflow_timer: VentAxiaRuntimeTimer | None = None
        self._connected = False  # Track connection state
        self.commission_mode = "normal"

        # Initialize connection components
        self.pending_tracker = PendingRequestTracker()
        self.client = AsyncNativePskClient(
            wifi_device_id=self.data[CONF_WIFI_DEVICE_ID],
            identity=self.data[CONF_IDENTITY],
            psk_key=self.data[CONF_PSK_KEY],
            host=self.data[CONF_HOST],
            port=self.data[CONF_PORT],
            connection_lost_callback=self._handle_disconnect,
        )
        self.processor = VentMessageProcessor(self.pending_tracker)
        self.commands = VentClientCommands(
            self.client.wifi_device_id, self.pending_tracker
        )

        self.device = self.processor.device
        self._receive_task: asyncio.Task | None = None
        self._callbacks: list[Callable[[], None]] = []

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        if CONF_WIFI_DEVICE_ID not in self.data:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, self.data[CONF_WIFI_DEVICE_ID])},
            name=self.device.dname or "VentAxia Device",
            manufacturer="VentAxia",
        )

    @property
    def available(self) -> bool:
        return self._connected

    async def async_send_airflow_mode(self, mode: str, duration: int) -> None:
        """Send airflow mode command to the device."""
        await self.commands.send_airflow_mode_request(self.client, mode, duration)

    async def async_start_commissioning(self, airflow="normal") -> None:
        """Send start_commissioning command to the device."""
        await self.commands.start_commissioning(self.client, airflow)

    async def async_stop_commissioning(self) -> None:
        """Send stop_commissioning command to the device."""
        await self.commands.stop_commissioning(self.client)

    async def async_send_update(self, data: dict, topic: str = "ee") -> None:
        """Send update command to the device."""
        await self.commands.send_update_request(self.client, data, topic)

    async def async_start(self) -> None:
        """Start the message receive loop."""
        await self.client.connect()
        self._connected = True
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Receive loop task."""
        try:
            async for msg in self.client:
                await self.processor.process(msg)
                self._notify_update()
        except asyncio.CancelledError:
            _LOGGER.debug("Receive loop cancelled")
        finally:
            await self.client.close()

    def _notify_update(self) -> None:
        """Notify all entities of new data."""
        for callback in self._callbacks:
            callback()

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback for data updates."""
        self._callbacks.append(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        """Remove a callback for data updates."""
        self._callbacks.remove(callback)

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass  # avoid crashing unload

    async def _handle_disconnect(self):
        _LOGGER.warning("VentAxia connection lost. Attempting to reconnect...")
        self._connected = False

        if not self.client._closing:
            await self.client.close()  # Ensure cleanup
        else:
            _LOGGER.debug("Client is already closing, skipping second close()")

        for attempt in range(5):  # Try reconnect 5 times
            try:
                await self.client.connect()
                self._connected = True  # Reset on successful connect
                self._receive_task = asyncio.create_task(self._receive_loop())
                _LOGGER.info("VentAxia reconnected successfully.")
                return
            except Exception as e:
                _LOGGER.warning(f"Reconnect attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(10)

        _LOGGER.error("Failed to reconnect after multiple attempts.")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VentAxia from a config entry."""
    coordinator = VentAxiaCoordinator(hass, entry)
    try:
        await coordinator.async_start()
    except Exception as ex:
        raise ConfigEntryNotReady from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_set_airflow_mode_service(call: ServiceCall):
        mode = call.data["mode"]
        duration_str = call.data["duration"]
        if mode not in AIRFLOW_MODES or duration_str not in VALID_DURATIONS:
            _LOGGER.error("Invalid mode or duration in service call")
            return

        duration = int(duration_str)  # Convert to integer for use in logic/API

        await coordinator.async_send_airflow_mode(mode, duration)

    async def async_update_schedule_service(call: ServiceCall):
        schedules = coordinator.processor.device._schedules  # Schedule dataclass
        # Prepare a dict with expected keys
        decoded: Dict[str, Optional[str]] = {
            key: call.data.get(key) for key in ["name", "from", "to", "days", "mode"]
        }

        data_to_send = {}

        # Helper function to handle encoding and sending
        if decoded and (name := decoded.get("name")):
            val = schedules.encode_ts_field(decoded)  # ✅decode→int

            if name == "shrs":
                schedules.shrs_raw = val  # keep raw
                schedules.silent_hours_decoded = decoded  # keep decoded
            else:  # ts
                schedules.ts_raw[name] = val  # keep raw
                schedules.ts_decoded[name] = decoded  # keep decoded
            data_to_send[name] = val

        if data_to_send:
            try:
                await coordinator.async_send_update(data_to_send)
            except ValueError as err:
                _LOGGER.error("Failed to send update: %s", err)

    async def async_set_summer_bypass_service(call: ServiceCall):
        """Handle service call to update summer bypass settings."""

        data_to_send = {}

        # Bypass mode (0–3)
        m_byp = call.data.get("m_byp")
        if m_byp is not None:
            data_to_send["m_byp"] = int(m_byp)

        # AF mode (1–4)
        af_enp = call.data.get("af_enp")
        if af_enp is not None:
            data_to_send["af_enp"] = int(af_enp)

        # Indoor temperature (°C → ×10)
        indoor = call.data.get("indoor_temp")
        if indoor is not None:
            data_to_send["by_ti"] = int(float(indoor) * 10)

        # Outdoor temperature (°C → ×10)
        outdoor = call.data.get("outdoor_temp")
        if outdoor is not None:
            data_to_send["by_to"] = int(float(outdoor) * 10)

        if not data_to_send:
            _LOGGER.error("No valid fields provided for summer bypass update")
            return

        try:
            await coordinator.async_send_update(data_to_send, topic="ee")
        except ValueError as err:
            _LOGGER.error("Failed to send summer bypass update: %s", err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AIRFLOW_MODE,
        async_set_airflow_mode_service,
        schema=SERVICE_SET_AIRFLOW_MODE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        async_update_schedule_service,
        schema=SERVICE_SET_SCHEDULE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SUMMER_BYPASS,
        async_set_summer_bypass_service,
        schema=SERVICE_SET_SUMMER_BYPASS_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload VentAxia config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
