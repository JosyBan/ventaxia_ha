# File: ventaxia_ha/runtime_timer.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

if TYPE_CHECKING:
    from . import VentAxiaCoordinator  # Only for type hints, won't execute at runtime

_LOGGER = logging.getLogger(__name__)


class VentAxiaRuntimeTimer(SensorEntity):
    """Logbook-friendly runtime timer for VentAxia manual airflow."""

    _attr_icon = "mdi:timer"
    _attr_native_unit_of_measurement = "seconds"

    def __init__(
        self, hass: HomeAssistant, coordinator: "VentAxiaCoordinator", name: str
    ):
        self.hass = hass
        self._name = name
        self._coordinator = coordinator
        self._timer_state = "idle"
        self._timer_duration = 0
        self._timer_start = None
        self._timer_finish = None
        self._update_task: asyncio.Task | None = None
        self._attr_unique_id = f"{coordinator.data['wifi_device_id']}_{name}"

    @property
    def name(self):
        return self._name

    @property
    def device_info(self) -> DeviceInfo | None:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def native_value(self):
        return self.remaining

    @property
    def extra_state_attributes(self):
        return {
            "timer_state": self._timer_state,
            "timer_duration_mins": self._timer_duration,
            "timer_duration_sec": self._timer_duration * 60,
            "timer_start": self._timer_start.isoformat() if self._timer_start else None,
            "timer_finish": (
                self._timer_finish.isoformat() if self._timer_finish else None
            ),
        }

    @property
    def remaining(self) -> int:
        if self._timer_state != "active" or not self._timer_finish:
            return 0
        return max(
            0, int((self._timer_finish - datetime.now(timezone.utc)).total_seconds())
        )

    async def async_start_timer(self, duration_minutes: int):
        """Start the timer."""
        if self._timer_state == "active" and self._update_task:
            return  # Already running, do nothing

        self._timer_state = "active"
        self._timer_duration = duration_minutes
        now = datetime.now(timezone.utc)
        self._timer_start = now
        self._timer_finish = now + timedelta(minutes=duration_minutes)

        # Fire start event for logbook
        self.hass.bus.async_fire(
            "ventaxia_timer_started",
            {"entity_id": self.entity_id, "duration": duration_minutes},
        )

        # Start per-second state updates internally. Only start loop if not running
        if not self._update_task:
            self._update_task = self.hass.async_create_task(self._timer_update_loop())

        self.async_write_ha_state()

    async def _timer_update_loop(self):
        try:
            while self._timer_state == "active" and self._timer_finish:
                self.async_write_ha_state()  # HA will call native_value() to get remaining

                if self.remaining <= 0:
                    await self.async_cancel_timer(finished=True)
                    break

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            self._update_task = None

    async def async_cancel_timer(self, finished=False):
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

        if finished:
            self._timer_state = "idle"
            # Fire finish event
            self.hass.bus.async_fire(
                "ventaxia_timer_finished", {"entity_id": self.entity_id}
            )
        else:
            self._timer_state = "idle"

        self._timer_start = None
        self._timer_finish = None
        self._timer_duration = 0
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when entity is removed/unloaded."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None
