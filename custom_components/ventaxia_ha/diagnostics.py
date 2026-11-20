"""Diagnostics support for the Vent-Axia integration.

Dumps the config entry (with secrets redacted) and, for newer MQTT-based
controllers, the full cache of topic values plus the coordinator's derived
state. This is aimed at debugging unexpected unit behaviour (e.g. periodic
boosting): the raw ``vent/caf``, ``vent/cor`` and ``io/erh/*`` values together
show whether a boost is humidity-driven, an override, or something else.
"""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DOMAIN,
)

# Secrets / identifying values kept out of the dump.
TO_REDACT_ENTRY = {CONF_PSK_KEY, CONF_WIFI_DEVICE_ID, CONF_HOST}
# Topic values that carry identifying info (Wi-Fi SSID, IP address, …).
TO_REDACT_TOPICS = {"mdet/wifi/sta", "mdet/wifi/sta#rssi"}


def _coordinator_state(coordinator: Any) -> dict[str, Any]:
    """Best-effort snapshot of the MQTT coordinator's derived state."""
    state: dict[str, Any] = {}

    # Raw per-topic cache, with identifying topics redacted.
    values = getattr(coordinator, "values", None)
    if isinstance(values, dict):
        state["topic_values"] = {
            k: ("**REDACTED**" if k in TO_REDACT_TOPICS else v)
            for k, v in sorted(values.items())
        }

    last_seen = getattr(coordinator, "_last_seen", None)
    if last_seen is not None:
        try:
            state["seconds_since_last_message"] = round(
                time.monotonic() - last_seen, 1
            )
        except TypeError:
            pass

    # Derived fields useful for the boosting investigation.
    for attr in (
        "available",
        "_caf_ps_stable",
        "_caf_ps_pending",
        "_cor_confirmed",
        "_commanded_gtm",
    ):
        if hasattr(coordinator, attr):
            state[attr.lstrip("_")] = getattr(coordinator, attr)

    for prop in ("humidity_threshold", "current_mode", "effective_mode"):
        try:
            state[prop] = getattr(coordinator, prop)
        except Exception:  # noqa: BLE001 - diagnostics must never raise
            state[prop] = "<unavailable>"

    return state


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT_ENTRY),
    }

    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        data["coordinator_type"] = type(coordinator).__name__
        data["state"] = _coordinator_state(coordinator)

    return data
