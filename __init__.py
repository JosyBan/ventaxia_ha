"""The VentAxia IoT integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import config_validation as cv

from ventaxiaiot import AsyncNativePskClient, VentMessageProcessor, VentClientCommands, PendingRequestTracker

from .const import (
    DOMAIN, 
    CONF_HOST, 
    CONF_PORT, 
    CONF_IDENTITY, 
    CONF_PSK_KEY, 
    CONF_WIFI_DEVICE_ID,
    SERVICE_SET_AIRFLOW_MODE,
    AIRFLOW_MODES,
    VALID_DURATIONS
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
            port=self.data[CONF_PORT]
        )
        self.processor = VentMessageProcessor(self.pending_tracker)
        self.commands = VentClientCommands(self.client.wifi_device_id, self.pending_tracker)
        
        self.device = self.processor.device
        self._receive_task: asyncio.Task | None = None
        self._callbacks: list[callable] = []

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.data[CONF_WIFI_DEVICE_ID])},
            name=self.device.dname or "VentAxia