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

import calendar
import json
import logging
import ssl
import threading
import time
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later, async_track_time_interval
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
    ),
    SensorEntityDescription(
        key="vent/afe/pwr",
        name="Extract Fan Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="vent/saq",
        name="Supply Air Quality",
        icon="mdi:air-filter",
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
# How long before a timed override's tracked end to pre-empt it with an explicit
# Auto. Must exceed the tick interval so a tick reliably fires while the override
# is still active (the unit's own expiry can otherwise stick the airflow).
OVERRIDE_PREEMPT_SECONDS = 40
# The unit emits brief (~2s) auto-purge bursts while running its own schedule. A
# transition to Purge on the schedule path is held this long before the Current
# Mode sensor reflects it, so those blips never flap the sensor; every other mode
# change is reflected immediately. Purge preset code is 4 (see GTM_TO_MODE).
CAF_DEBOUNCE_SECONDS = 6
PURGE_PS = 4
# After a mode is selected, show it in the UI immediately ("optimistic") until the
# unit's live state catches up — or at most this long, so the UI never lies if a
# command is dropped.
OPTIMISTIC_SECONDS = 20


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


def add_months(dt: datetime, months: int) -> datetime:
    """Return dt advanced by a whole number of months (clamping the day)."""
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


# The controller serves a topic's *current* value immediately on an exact-topic
# subscription, but its broker has a small subscription table — holding more than
# a handful of subscriptions makes it silently drop the rest (so many sensors sat
# "unavailable"). The "<deviceId>/#" wildcard only delivers a topic when the
# device next publishes it on its own slow cadence, and never serves the
# maintenance/bypass values at all.
#
# So we keep "#" for live telemetry and *poll* current values in small batches:
# subscribe a few topics (the broker serves their current value), then
# unsubscribe them again, cycling through the whole list. Only a few
# subscriptions are ever held at once, so nothing gets dropped.
POLL_TOPICS: tuple[str, ...] = (
    "io/t1",
    "io/t3",
    "io/erh/val",
    "io/irh/val",
    "mdet/pwr",
    "mdet/wifi/sta",
    "vent/afs/rpm",
    "vent/afe/rpm",
    "vent/afs/pwr",
    "vent/afe/pwr",
    "vent/caf",
    "vent/cor",
    "mdet/svctmr/last",
    "mdet/svctmr/int",
    "vent/filtertmr/last",
    "vent/filtertmr/int",
    "vent/filter1/typ",
    "vent/filter2/typ",
    "vent/sbs",
    "vent/sbc",
    "vent/saq",
    "io/erh/conf",
)
POLL_BATCH = 4          # topics subscribed at once (keep well under the table size)
POLL_SERVE_WAIT = 1.2   # seconds to let the broker serve a batch before unsubscribe
POLL_BATCH_GAP = 0.3    # pause between batches
POLL_INTERVAL = 45      # seconds between full refresh cycles

# The controller's broker occasionally drops the TLS socket; paho reconnects
# within a second or two. Don't flap every entity to "unavailable" for those
# brief blips — only report unavailable after this long with no live connection.
AVAILABILITY_GRACE = 240.0  # seconds


class VentAxiaMqttCoordinator:
    """Maintain the MQTT-over-TLS-PSK connection and cache published values."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.device_id: str = entry.data[CONF_WIFI_DEVICE_ID]
        self.values: dict[str, Any] = {}
        self._connected = False
        self._last_seen: float | None = None
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
        # Debounced airflow preset for the Current Mode sensor. The unit emits
        # brief (~2s) caf "ps" blips (e.g. a momentary Purge burst) while in
        # Auto; surfacing each one spams the logbook with Normal→Purge→Normal.
        # We only commit a new preset after it has held for CAF_DEBOUNCE_SECONDS.
        self._caf_ps_stable: int | None = None
        self._caf_ps_pending: int | None = None
        self._caf_debounce_unsub: Callable[[], None] | None = None
        # Optimistic mode: the mode just commanded via the select, shown in the UI
        # until the unit's live state reflects it (or OPTIMISTIC_SECONDS elapses).
        self._commanded_gtm: int | None = None
        self._commanded_at: float = 0.0
        self._refresh_unsub: Callable[[], None] | None = None
        self._tick_count: int = 0
        # Background value-poller (works around the broker's tiny sub table).
        self._poll_thread: threading.Thread | None = None
        self._poll_stop = threading.Event()
        self._poll_wake = threading.Event()

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

        # Start the background value-poller.
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="ventaxia-poll", daemon=True
        )
        self._poll_thread.start()

    async def async_stop(self) -> None:
        if self._refresh_unsub is not None:
            self._refresh_unsub()
            self._refresh_unsub = None
        if self._caf_debounce_unsub is not None:
            self._caf_debounce_unsub()
            self._caf_debounce_unsub = None
        self._poll_stop.set()
        self._poll_wake.set()
        if self._poll_thread is not None:
            await self.hass.async_add_executor_job(self._poll_thread.join, 5)
            self._poll_thread = None
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.loop_stop()
                await self.hass.async_add_executor_job(client.disconnect)
            except Exception:  # pragma: no cover - best effort shutdown
                _LOGGER.debug("Error during MQTT shutdown", exc_info=True)

    def _poll_loop(self) -> None:
        """Cycle through POLL_TOPICS, briefly subscribing so the broker serves
        each value, then unsubscribing — keeping only a few subscriptions held at
        once so the controller's small subscription table never overflows."""
        while not self._poll_stop.is_set():
            if self._connected and self._client is not None:
                client = self._client
                for i in range(0, len(POLL_TOPICS), POLL_BATCH):
                    if self._poll_stop.is_set() or not self._connected:
                        break
                    batch = POLL_TOPICS[i : i + POLL_BATCH]
                    for topic in batch:
                        try:
                            client.subscribe(f"{self.device_id}/{topic}", qos=0)
                        except Exception:  # pragma: no cover
                            pass
                    if self._poll_stop.wait(POLL_SERVE_WAIT):
                        break
                    for topic in batch:
                        try:
                            client.unsubscribe(f"{self.device_id}/{topic}")
                        except Exception:  # pragma: no cover
                            pass
                    if self._poll_stop.wait(POLL_BATCH_GAP):
                        break
                self.hass.loop.call_soon_threadsafe(self._notify)
            # Wait until the next cycle, or until woken by a (re)connect.
            self._poll_wake.wait(POLL_INTERVAL)
            self._poll_wake.clear()

    @callback
    def _tick(self, now=None) -> None:
        """Periodic tick: re-arm a held boost, revert elapsed overrides, refresh countdowns.

        Marked @callback so async_track_time_interval runs it on the event loop
        (a bare function would run in an executor thread, and the entity state
        writes it triggers via _notify are only safe on the loop).
        """
        self._tick_count += 1
        if self.boost_hold:
            end = self._local_override_end
            if (
                end is None
                or (end - dt_util.now()).total_seconds()
                < HOLD_REARM_BUFFER_MINUTES * 60
            ):
                self._apply_boost_chunk()
        elif (
            self._local_override_end is not None
            and (self._local_override_end - dt_util.now()).total_seconds()
            <= OVERRIDE_PREEMPT_SECONDS
        ):
            # Pre-empt the unit's own override timer. Letting the unit expire the
            # override itself occasionally leaves it stuck running the override
            # airflow (notably Purge, or after a mid-override mode switch) while
            # reporting Auto — the motors keep spinning and only a manual
            # Normal -> Auto clears it. An explicit Auto (gtm 0) sent *while the
            # override is still active* cleanly returns the unit to its schedule
            # (verified live), whereas the same command after it has already
            # stuck is a no-op. So cancel it ourselves a little early, which
            # avoids the unit's flaky self-expiry entirely.
            _LOGGER.debug("VentAxia override pre-empt: reverting to Auto")
            self.set_override(0, "00:00:00")
        self._notify()

    # ---- paho callbacks (run in paho's network thread) -------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        rc = getattr(reason_code, "value", reason_code)
        if rc not in (0, mqtt.CONNACK_ACCEPTED if hasattr(mqtt, "CONNACK_ACCEPTED") else 0):
            _LOGGER.warning("VentAxia MQTT connect failed: rc=%s", reason_code)
            return
        self._connected = True
        self._last_seen = time.monotonic()
        # "#" delivers live telemetry the device pushes on its own cadence; the
        # poll thread fills in current values (and the maintenance/bypass topics
        # the wildcard never serves).
        client.subscribe(f"{self.device_id}/#", qos=0)
        self._poll_wake.set()  # run a full poll now
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
        self._last_seen = time.monotonic()
        # Flatten the Wi-Fi JSON blob into a synthetic rssi topic.
        if suffix == "mdet/wifi/sta":
            try:
                self.values["mdet/wifi/sta#rssi"] = json.loads(payload).get("rssi")
            except (ValueError, AttributeError):
                pass
        if suffix == "vent/caf":
            self.hass.loop.call_soon_threadsafe(self._on_caf_update)
        self.hass.loop.call_soon_threadsafe(self._notify)

    @staticmethod
    def _caf_ps(raw: Any) -> int | None:
        """Parse the airflow preset ("ps") out of a raw caf payload."""
        try:
            return json.loads(raw).get("ps")
        except (ValueError, TypeError, AttributeError):
            return None

    def _on_caf_update(self) -> None:
        """Track caf 'ps' changes for the Current Mode sensor (on the event loop).

        Real mode changes (Low/Normal/Boost/Max) commit immediately so the sensor
        stays responsive. Only a transition *to Purge* is debounced, because the
        unit emits brief (~2s) auto-purge bursts while on its schedule that would
        otherwise flap the sensor Normal→Purge→Normal. A sustained Purge still
        shows after ``CAF_DEBOUNCE_SECONDS``; a manual Purge goes through the
        override path and is never affected.
        """
        ps = self._caf_ps(self.values.get("vent/caf"))
        if ps is None or ps == self._caf_ps_stable:
            # Unchanged (or back to committed) — drop any pending Purge change.
            self._caf_ps_pending = None
            if self._caf_debounce_unsub is not None:
                self._caf_debounce_unsub()
                self._caf_debounce_unsub = None
            return
        if ps != PURGE_PS or self._caf_ps_stable is None:
            # Genuine mode change (or the very first reading) — reflect at once.
            self._caf_ps_pending = None
            if self._caf_debounce_unsub is not None:
                self._caf_debounce_unsub()
                self._caf_debounce_unsub = None
            self._caf_ps_stable = ps
            self._notify()
            return
        # A bare transition to Purge — hold it until it proves it's not a blip.
        if ps == self._caf_ps_pending:
            return  # already waiting on this value
        self._caf_ps_pending = ps
        if self._caf_debounce_unsub is not None:
            self._caf_debounce_unsub()
        self._caf_debounce_unsub = async_call_later(
            self.hass, CAF_DEBOUNCE_SECONDS, self._commit_caf
        )

    def _commit_caf(self, _now=None) -> None:
        """Promote a pending caf preset to stable once it has held long enough."""
        self._caf_debounce_unsub = None
        if self._caf_ps_pending is None:
            return
        self._caf_ps_stable = self._caf_ps_pending
        self._caf_ps_pending = None
        self._notify()

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

    def _commanded_mode(self) -> str | None:
        """The optimistic just-commanded mode ("Auto" or a speed), or None once
        the unit's live state matches it or OPTIMISTIC_SECONDS have elapsed."""
        if self._commanded_gtm is None:
            return None
        target = (
            "Auto" if self._commanded_gtm == 0
            else GTM_TO_MODE.get(self._commanded_gtm)
        )
        if self._live_mode() == target or (
            time.monotonic() - self._commanded_at
        ) > OPTIMISTIC_SECONDS:
            self._commanded_gtm = None  # reconciled (or timed out)
            return None
        return target

    @property
    def current_mode(self) -> str | None:
        """Current ventilation mode for the select.

        Right after a selection this is the *commanded* mode (optimistic), so the
        UI updates instantly instead of waiting for the unit to republish its
        state. Once the live value matches (or OPTIMISTIC_SECONDS pass) it reverts
        to the real value: "Auto" on schedule, else the override speed from caf.
        """
        return self._commanded_mode() or self._live_mode()

    def _live_mode(self) -> str | None:
        """The ventilation mode as last reported by the unit (no optimism)."""
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

    @property
    def effective_mode(self) -> str | None:
        """The speed the unit is actually running right now, e.g. ``Low``.

        During a manual timed override this is the live override speed; while
        following the schedule it's the debounced airflow preset. Whether that
        speed is schedule-driven ("Auto") is exposed separately by the ``auto``
        property / binary sensor, so this stays a clean mode name.
        """
        # A just-commanded speed shows immediately (optimistic); "Auto" isn't a
        # speed, so for that we fall through to the live/debounced value.
        cmd = self._commanded_mode()
        if cmd and cmd != "Auto":
            return cmd
        if self._override_active:
            # During a manual timed override show the live override speed.
            return self._live_mode()
        # On schedule, use the debounced preset so brief airflow blips (a ~2s
        # Purge burst, etc.) don't flap the sensor between e.g. Normal and Purge.
        return GTM_TO_MODE.get(self._caf_ps_stable) if self._caf_ps_stable else None

    @property
    def auto(self) -> bool | None:
        """Whether the unit is following its own schedule (True) rather than a
        manual override (False). None until the override state is known."""
        active = self._override_active
        return None if active is None else not active

    # ---- maintenance / bypass (exact-subscription topics) ----------------
    def _parse_local_dt(self, key: str) -> datetime | None:
        """Parse an ISO timestamp the unit reports in its local clock (no zone)."""
        raw = self.values.get(key)
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    def _int_val(self, key: str) -> int | None:
        raw = self.values.get(key)
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    def _due(self, last_key: str, interval_key: str) -> datetime | None:
        last = self._parse_local_dt(last_key)
        months = self._int_val(interval_key)
        if last is None or months is None:
            return None
        return add_months(last, months)

    @property
    def filter_due(self) -> datetime | None:
        return self._due("vent/filtertmr/last", "vent/filtertmr/int")

    @property
    def filter_days_remaining(self) -> int | None:
        due = self.filter_due
        if due is None:
            return None
        return max(0, (due - dt_util.now()).days)

    @property
    def service_due(self) -> datetime | None:
        return self._due("mdet/svctmr/last", "mdet/svctmr/int")

    @property
    def service_days_remaining(self) -> int | None:
        due = self.service_due
        if due is None:
            return None
        return max(0, (due - dt_util.now()).days)

    def _json_val(self, key: str) -> dict | None:
        raw = self.values.get(key)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (ValueError, AttributeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @property
    def bypass_state(self) -> str | None:
        """'Open' when the summer bypass is engaged, else 'Closed'."""
        sbs = self._json_val("vent/sbs")
        if sbs is None:
            return None
        # `op` is the active bypass output (0 = closed/not bypassing).
        return "Open" if sbs.get("op") else "Closed"

    @property
    def humidity_threshold(self) -> float | None:
        """Extract-humidity % at which the unit auto-boosts (io/erh/conf 'th')."""
        conf = self._json_val("io/erh/conf")
        if conf is None:
            return None
        try:
            return float(conf.get("th"))
        except (TypeError, ValueError):
            return None

    def set_humidity_threshold(self, value: float) -> None:
        """Write a new humidity boost threshold, preserving the other IAQ fields."""
        if self._client is None:
            return
        conf = self._json_val("io/erh/conf")
        # Preserve the humidity-response fields the app sets; fall back to the
        # unit's known defaults only if we have not read the config yet.
        if conf is None:
            conf = {"are": True, "rre": True, "rror": 900, "gtm": 3}
        conf = dict(conf)
        conf["th"] = float(value)
        payload = json.dumps(conf)
        self._client.publish(f"{self.device_id}/io/erh/conf/wr", payload, qos=1)
        _LOGGER.debug("VentAxia humidity threshold -> %s", payload)
        # Optimistic cache update so the UI reflects the change immediately.
        self.values["io/erh/conf"] = payload
        self._notify()

    def set_override(self, gtm: int, treq: str) -> None:
        """Publish an airflow override to the unit and track its end locally."""
        if self._client is None:
            return
        payload = json.dumps({"gtm": gtm, "treq": treq})
        # QoS 1 so a press issued during a brief reconnect is still delivered.
        self._client.publish(f"{self.device_id}/{OVERRIDE_TOPIC}", payload, qos=1)
        _LOGGER.debug("VentAxia override -> %s", payload)
        # Show the commanded mode in the UI at once; reconciled in current_mode.
        self._commanded_gtm = gtm
        self._commanded_at = time.monotonic()
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
        # Stay available through brief reconnects: only report unavailable after
        # AVAILABILITY_GRACE seconds with no live connection or data.
        if self._connected:
            return True
        if self._last_seen is None:
            return False
        return (time.monotonic() - self._last_seen) < AVAILABILITY_GRACE

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


class VentAxiaMqttHumidityThresholdNumber(NumberEntity):
    """Extract-humidity % at which the unit automatically boosts (IAQ)."""

    _attr_has_entity_name = True
    _attr_name = "Humidity Boost Threshold"
    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 60
    _attr_native_max_value = 90
    _attr_native_step = 1
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = "slider"

    def __init__(self, coordinator: VentAxiaMqttCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_humidity_threshold"

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return (
            self._coordinator.available
            and self._coordinator.humidity_threshold is not None
        )

    @property
    def native_value(self) -> float | None:
        return self._coordinator.humidity_threshold

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.set_humidity_threshold(value)

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)


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


class VentAxiaMqttDerivedSensor(SensorEntity):
    """A sensor whose value is computed from the coordinator (not a raw topic)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VentAxiaMqttCoordinator,
        key: str,
        name: str,
        value_fn: Callable[[VentAxiaMqttCoordinator], Any],
        *,
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
        icon: str | None = None,
        attrs_fn: Callable[[VentAxiaMqttCoordinator], dict | None] | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_name = name
        if device_class is not None:
            self._attr_device_class = device_class
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if icon is not None:
            self._attr_icon = icon
        if entity_category is not None:
            self._attr_entity_category = entity_category

    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        return self._coordinator.device_info

    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._coordinator.available and self._value_fn(self._coordinator) is not None

    @property
    def native_value(self) -> Any:
        return self._value_fn(self._coordinator)

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._attrs_fn(self._coordinator) if self._attrs_fn else None

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_update_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_update_callback(self._handle_update)


def _filter_attrs(c: VentAxiaMqttCoordinator) -> dict | None:
    attrs: dict[str, Any] = {}
    last = c.values.get("vent/filtertmr/last")
    interval = c._int_val("vent/filtertmr/int")
    t1 = c.values.get("vent/filter1/typ")
    t2 = c.values.get("vent/filter2/typ")
    if last:
        attrs["last_changed"] = last
    if interval is not None:
        attrs["interval_months"] = interval
    if t1:
        attrs["supply_filter_type"] = t1
    if t2:
        attrs["extract_filter_type"] = t2
    return attrs or None


def _service_attrs(c: VentAxiaMqttCoordinator) -> dict | None:
    attrs: dict[str, Any] = {}
    last = c.values.get("mdet/svctmr/last")
    interval = c._int_val("mdet/svctmr/int")
    if last:
        attrs["last_service"] = last
    if interval is not None:
        attrs["interval_months"] = interval
    return attrs or None


def _bypass_attrs(c: VentAxiaMqttCoordinator) -> dict | None:
    sbs = c._json_val("vent/sbs") or {}
    sbc = c._json_val("vent/sbc") or {}
    attrs: dict[str, Any] = {}
    if "pos" in sbs:
        attrs["position"] = sbs["pos"]
    if "am" in sbs:
        attrs["auto_mode"] = sbs["am"]
    if "mod" in sbc:
        attrs["mode"] = sbc["mod"]
    if "ect" in sbc:
        attrs["comfort_extract_temp"] = sbc["ect"]
    if "ict" in sbc:
        attrs["comfort_indoor_temp"] = sbc["ict"]
    return attrs or None


def _current_mode_attrs(c: VentAxiaMqttCoordinator) -> dict | None:
    active = c._override_active
    attrs: dict[str, Any] = {}
    if active is not None:
        attrs["following"] = "override" if active else "schedule"
    if active:
        rem = c.override_remaining_minutes
        if rem is not None:
            attrs["override_remaining_min"] = rem
    return attrs or None


def build_maintenance_sensors(
    coordinator: VentAxiaMqttCoordinator,
) -> list[VentAxiaMqttDerivedSensor]:
    """Filter-life, service-due and summer-bypass sensors for the newer model."""
    return [
        VentAxiaMqttDerivedSensor(
            coordinator, "current_mode", "Current Mode",
            lambda c: c.effective_mode,
            icon="mdi:fan",
            attrs_fn=_current_mode_attrs,
        ),
        VentAxiaMqttDerivedSensor(
            coordinator, "filter_due", "Filter Due",
            lambda c: c.filter_due,
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:air-filter", attrs_fn=_filter_attrs,
        ),
        VentAxiaMqttDerivedSensor(
            coordinator, "filter_remaining", "Filter Life Remaining",
            lambda c: c.filter_days_remaining,
            device_class=SensorDeviceClass.DURATION,
            unit=UnitOfTime.DAYS, icon="mdi:air-filter",
        ),
        VentAxiaMqttDerivedSensor(
            coordinator, "service_due", "Service Due",
            lambda c: c.service_due,
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:wrench-clock", attrs_fn=_service_attrs,
        ),
        VentAxiaMqttDerivedSensor(
            coordinator, "service_remaining", "Service Due In",
            lambda c: c.service_days_remaining,
            device_class=SensorDeviceClass.DURATION,
            unit=UnitOfTime.DAYS, icon="mdi:wrench-clock",
        ),
        VentAxiaMqttDerivedSensor(
            coordinator, "summer_bypass", "Summer Bypass",
            lambda c: c.bypass_state,
            icon="mdi:valve", attrs_fn=_bypass_attrs,
        ),
    ]
