# File: ventaxia_ha/__init__.py
"""The VentAxia HA integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Dict, Optional

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    EVENT_HOMEASSISTANT_STARTED,
    CoreState,
    HomeAssistant,
    ServiceCall,
)
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
    INTEGRATION_VERSION,
    SERVICE_SET_AIRFLOW_MODE,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_SUMMER_BYPASS,
    TIME_REGEX,
    VALID_DAYS,
    VALID_DURATIONS,
    VALID_MODES,
)
from .frontend import JSModuleRegistration
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
    },
    extra=vol.ALLOW_EXTRA,  # <-- allows additional keys like "delete"
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
    """Coordinator that maintains a persistent VentAxia connection."""

    CONNECTION_LIFETIME = 30 * 60
    RECONNECT_DELAY = 10.0
    CONNECT_TIMEOUT = 30.0

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.manual_airflow_timer: VentAxiaRuntimeTimer | None = None
        self._connected = False
        self._conn_lock = asyncio.Lock()
        self._stopping = False
        self._supervisor_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._connection_lost = asyncio.Event()
        self.commission_mode = "normal"
        self._callbacks: set[Callable[[], None]] = set()

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
        """Return whether the device connection is active."""
        return self._connected

    async def async_send_airflow_mode(self, mode: str, duration: int) -> None:
        await self.ensure_connection()
        await self.commands.send_airflow_mode_request(self.client, mode, duration)

    async def async_start_commissioning(self, airflow="normal") -> None:
        await self.ensure_connection()
        await self.commands.start_commissioning(self.client, airflow)

    async def async_stop_commissioning(self) -> None:
        await self.ensure_connection()
        await self.commands.stop_commissioning(self.client)

    async def async_send_update(self, data: dict, topic: str = "ee") -> None:
        await self.ensure_connection()
        await self.commands.send_update_request(self.client, data, topic)

    async def async_start(self) -> None:
        """Start the background connection supervisor."""
        self._stopping = False
        if self._supervisor_task is None or self._supervisor_task.done():
            self._supervisor_task = self.hass.async_create_task(
                self._connection_supervisor(),
                name="ventaxia_connection_supervisor",
            )

    async def ensure_connection(self) -> None:
        """Ensure a connection exists, serializing connection attempts."""
        async with self._conn_lock:
            if self._stopping:
                raise ConnectionError("VentAxia integration is stopping")
            if self._connected and self.client.writer is not None:
                return

            _LOGGER.debug(
                "Connecting to VentAxia device at %s:%s",
                self.data[CONF_HOST],
                self.data[CONF_PORT],
            )
            self._connection_lost.clear()
            try:
                await self.client.connect(timeout=self.CONNECT_TIMEOUT)
            except Exception:
                self._connected = False
                self._connection_lost.set()
                raise

            self._connected = True
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = self.hass.async_create_task(
                    self._receive_loop(), name="ventaxia_receive_loop"
                )
            _LOGGER.info("Connected to VentAxia device")

    async def _connection_supervisor(self) -> None:
        """Keep sensor data flowing and retry failed connections."""
        while not self._stopping:
            try:
                await self.ensure_connection()
                # Keep a successful session for up to 30 minutes. A disconnect
                # signals the event earlier and triggers the same reconnect path.
                try:
                    await asyncio.wait_for(
                        self._connection_lost.wait(),
                        timeout=self.CONNECTION_LIFETIME,
                    )
                except asyncio.TimeoutError:
                    _LOGGER.info(
                        "VentAxia session reached 30-minute limit; reconnecting"
                    )
                if self._stopping:
                    break
                await self._close_connection()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("VentAxia connection failed: %s", err)

            if not self._stopping:
                _LOGGER.debug(
                    "Retrying VentAxia connection in %.0f seconds",
                    self.RECONNECT_DELAY,
                )
                try:
                    await asyncio.sleep(self.RECONNECT_DELAY)
                except asyncio.CancelledError:
                    raise

    async def _receive_loop(self) -> None:
        """Process incoming messages until the client connection ends."""
        try:
            async for msg in self.client:
                await self.processor.process(msg)
                self._notify_update()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("VentAxia receive loop failed")
        finally:
            if not self._stopping and self._connected and not self.client._running:
                self._connected = False
                self._connection_lost.set()

    async def _handle_disconnect(self) -> None:
        """Signal the supervisor when the socket drops unexpectedly."""
        if self._connected:
            _LOGGER.warning("VentAxia connection lost")
        self._connected = False
        self._connection_lost.set()

    async def _close_connection(self) -> None:
        """Close the client and stop the associated receive loop."""
        async with self._conn_lock:
            self._connected = False
            task = self._receive_task
            self._receive_task = None
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    _LOGGER.debug("Receive task ended during close", exc_info=True)
            try:
                await self.client.close()
            except Exception:
                _LOGGER.warning("Error closing VentAxia client", exc_info=True)
            self._connection_lost.set()

    def _notify_update(self) -> None:
        """Notify registered entities that new data is available."""
        for callback in tuple(self._callbacks):
            callback()

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Register an entity update callback."""
        self._callbacks.add(callback)

    def remove_update_callback(self, callback: Callable[[], None]) -> None:
        """Unregister an entity update callback."""
        self._callbacks.discard(callback)

    async def async_stop(self) -> None:
        """Stop the supervisor and close the connection on unload."""
        self._stopping = True
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
        self._supervisor_task = None
        await self._close_connection()


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register frontend modules after HA startup."""
    module_register = JSModuleRegistration(hass)
    await module_register.async_register()


@websocket_api.decorators.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/version",
    }
)
@websocket_api.decorators.async_response
async def websocket_get_version(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Handle version request from frontend."""
    connection.send_result(
        msg["id"],
        {"version": INTEGRATION_VERSION},
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:

    # Register websocket command for version checking
    websocket_api.async_register_command(hass, websocket_get_version)

    async def _setup_frontend(_event=None) -> None:
        await async_register_frontend(hass)

    if hass.state == CoreState.running:
        await _setup_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _setup_frontend)

    return True


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
        delete_flag = call.data.get("delete", False)

        # Helper function to handle encoding and sending
        if decoded and (name := decoded.get("name")):

            if delete_flag:
                val = 0  # send 0 to device
            else:
                val = schedules.encode_ts_field(decoded)  # ✅decode→int

            if name == "shrs":
                schedules.shrs_raw = val  # keep raw
                schedules.silent_hours_decoded = decoded  # keep decoded
            else:  # ts
                if delete_flag:
                    schedules.ts_raw.pop(name, None)
                    schedules.ts_decoded.pop(name, None)
                else:
                    schedules.ts_raw[name] = val
                    schedules.ts_decoded[name] = decoded
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
