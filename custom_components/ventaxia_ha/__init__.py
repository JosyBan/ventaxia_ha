# File: ventaxia_ha/__init__.py
"""The VentAxia IoT integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

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
    TIME_REGEX,
    VALID_DAYS,
    VALID_DURATIONS,
    VALID_MODES,
)
from .runtime_timer import VentAxiaRuntimeTimer

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

SERVICE_SET_AIRFLOW_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("mode"): vol.In(list(AIRFLOW_MODES.keys())),
        vol.Required("duration"): vol.In(VALID_DURATIONS),
    }
)

SERVICE_SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Required("from"): vol.Match(TIME_REGEX),  # HH:MM
        vol.Required("to"): vol.Match(TIME_REGEX),
        vol.Required("days"): vol.Any("Every day", [vol.In(VALID_DAYS)]),
        vol.Required("mode"): vol.In(VALID_MODES),
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

    async def async_send_update(self, data: dict) -> None:
        """Send update command to the device."""
        await self.commands.send_update_request(self.client, data)

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

        ts_update = call.data.get("ts")  # e.g. {"ts1": {from, to, days, mode}}
        shrs_update = call.data.get("shrs")  # e.g. {from, to, days, mode}
        data_to_send = {}

        # Helper function to handle encoding and sending
        async def _process_update(decoded_dict: dict):

            val = schedules.encode_ts_field(decoded_dict)  # ✅decode→int
            name = decoded_dict.get("name")
            if name == "shrs":
                schedules.shrs_raw = val  # keep raw
                schedules.silent_hours_decoded = decoded_dict  # keep decoded
            else:  # ts
                schedules.ts_raw[name] = val  # keep raw
                schedules.ts_decoded[name] = decoded_dict  # keep decoded
            data_to_send[name] = val
            return True

        # Process ts_update
        if ts_update:
            if not _process_update(ts_update):
                return

        # Process shrs_update
        if shrs_update:
            shrs_update["name"] = "shrs"
            if not _process_update(shrs_update):
                return

        if data_to_send:
            await coordinator.async_send_update(data_to_send)

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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload VentAxia config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
