# File: ventaxia_ha/ble.py
"""Bluetooth auto-detection of Vent-Axia newer (>2023) controllers.

These controllers have no printed Wi-Fi key. The TLS pre-shared key and the
device ID are provisioned over BLE. This module scans for a nearby controller
and reads those values straight off its GATT Auth service, so the config flow
can pre-fill them instead of making the owner type them by hand.

The device ID characteristic is always readable. The PSK characteristic only
returns the real key while the unit is in pairing/commissioning mode; once the
unit is provisioned it reads back as all zeros (reported here as a locked PSK).
"""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# GATT UUIDs from the Vent-Axia Connect app bundle (ZirconiaDeviceAuthService).
AUTH_SERVICE_UUID = "e6834e4b-7b3a-48e6-91e4-f1d005f564d3"
DEVICE_ID_UUID = "673de933-963b-4298-bfc1-b0ccdada690a"
TLS_IDENTITY_UUID = "98faf8a5-1ee6-4b0c-911e-dc37bff5206f"
TLS_KEY_UUID = "638ff62c-3823-4e0f-8179-1695c46ee8ad"  # the PSK

# The newer controllers advertise under these BLE names.
DEVICE_NAME_PREFIXES = ("Sentinel Econiq", "Sentinel", "Econiq")


class BleError(Exception):
    """Base error for BLE auto-detection."""


class BleNotFound(BleError):
    """No Vent-Axia controller was seen over Bluetooth."""


class BleReadFailed(BleError):
    """A controller was found but its credentials could not be read."""


def _looks_like_controller(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    """Return True if a discovered BLE device looks like a Vent-Axia unit."""
    uuids = {u.lower() for u in (info.service_uuids or ())}
    if AUTH_SERVICE_UUID in uuids:
        return True
    name = info.name or ""
    return name.startswith(DEVICE_NAME_PREFIXES)


async def async_read_credentials(
    hass: HomeAssistant, address: str | None = None
) -> dict[str, str | None]:
    """Scan over BLE and read a controller's device ID and PSK.

    Returns a dict ``{"device_id", "psk_hex", "address"}``. ``psk_hex`` is
    ``None`` when the unit is already paired and the key reads back locked.

    Raises :class:`BleNotFound` if no controller is in range (including when no
    Bluetooth adapter is available), or :class:`BleReadFailed` on a read error.
    """
    # Imported lazily; provided by Home Assistant's bluetooth integration.
    from bleak_retry_connector import (  # noqa: PLC0415
        BleakClientWithServiceCache,
        establish_connection,
    )

    target = None
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        if address is not None:
            if info.address.lower() == address.lower():
                target = info
                break
            continue
        if _looks_like_controller(info):
            target = info
            break

    if target is None:
        raise BleNotFound("No Vent-Axia controller discovered over Bluetooth")

    ble_device = bluetooth.async_ble_device_from_address(
        hass, target.address, connectable=True
    )
    if ble_device is None:
        raise BleNotFound(f"No connectable BLE route to {target.address}")

    try:
        client = await establish_connection(
            BleakClientWithServiceCache, ble_device, target.address
        )
    except Exception as err:  # pylint: disable=broad-except
        raise BleReadFailed(f"Could not connect to {target.address}: {err}") from err

    try:
        device_raw = await client.read_gatt_char(DEVICE_ID_UUID)
        key_raw = await client.read_gatt_char(TLS_KEY_UUID)
    except Exception as err:  # pylint: disable=broad-except
        raise BleReadFailed(f"Could not read GATT characteristics: {err}") from err
    finally:
        try:
            await client.disconnect()
        except Exception:  # pylint: disable=broad-except
            pass

    device_id = device_raw.decode("utf-8", errors="ignore").strip("\x00").strip()
    # A provisioned unit returns an all-zero key; treat that as "locked".
    psk_hex: str | None = key_raw.hex() if any(key_raw) else None

    _LOGGER.debug(
        "VentAxia BLE auto-detect: address=%s device_id=%s psk=%s",
        target.address,
        device_id,
        "read" if psk_hex else "locked",
    )
    return {"device_id": device_id, "psk_hex": psk_hex, "address": target.address}
