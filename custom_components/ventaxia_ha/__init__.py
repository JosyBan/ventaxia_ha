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
    VALID_DURATIONS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

SERVICE_SET_AIRFLOW_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("mode"): vol.In(list(AIRFLOW_MODES.keys())),
        vol.Required("duration"): vol.In(VALID_DURATIONS),
    }
)


class VentAxiaCoordinator:
    """Coordinator for VentAxia IoT device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.data = entry.data

        # Initialize connection components
        self.pending_tracker = PendingRequestTracker()
        self.client = AsyncNativePskClient(
            wifi_device_id=self.data[CONF_WIFI_DEVICE_ID],
            identity=self.data[CONF_IDENTITY],
            psk_key=self.data[CONF_PSK_KEY],
            host=self.data[CONF_HOST],
            port=self.data[CONF_PORT],
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

    async def async_send_airflow_mode(self, mode: str, duration: int) -> None:
        """Send airflow mode command to the device."""
        await self.commands.send_airflow_mode_request(self.client, mode, duration)

    async def async_start(self) -> None:
        """Start the message receive loop."""
        await self.client.connect()
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
            await self._receive_task


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
        duration = call.data["duration"]
        if mode not in AIRFLOW_MODES or duration not in VALID_DURATIONS:
            _LOGGER.error("Invalid mode or duration in service call")
            return
        await coordinator.async_send_airflow_mode(mode, duration)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AIRFLOW_MODE,
        async_set_airflow_mode_service,
        schema=SERVICE_SET_AIRFLOW_MODE_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload VentAxia config entry."""
    coordinator: VentAxiaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
