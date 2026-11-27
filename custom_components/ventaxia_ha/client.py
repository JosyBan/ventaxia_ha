# File: ventaxia_ha/client.py
"""Client helpers for the VentAxia integration.

The upstream :class:`ventaxiaiot.AsyncNativePskClient` expects the PSK as a
UTF-8 string (the Wi-Fi key printed on the older Advance S Wi-Fi module).

The newer Kinetic Advance S (>2023) / Econiq / SX controllers have no printed
key. Their PSK is a fixed byte string that the app receives over Bluetooth
during pairing; owners read it out as a hex string. Those bytes are not valid
UTF-8, so this wrapper lets the PSK be supplied as hex and passed to the TLS
layer as raw bytes.
"""
from __future__ import annotations

import asyncio
import logging
import ssl

from ventaxiaiot import AsyncNativePskClient

_LOGGER = logging.getLogger(__name__)


def decode_psk(psk_key: str, psk_is_hex: bool) -> bytes:
    """Return the PSK as raw bytes.

    When ``psk_is_hex`` is set, ``psk_key`` is interpreted as a hex string
    (whitespace and an optional ``0x`` prefix are tolerated). Otherwise it is
    treated as a UTF-8 Wi-Fi key, matching upstream behaviour.
    """
    if psk_is_hex:
        cleaned = psk_key.strip().lower().replace("0x", "").replace(":", "")
        cleaned = "".join(cleaned.split())
        return bytes.fromhex(cleaned)
    return psk_key.encode("utf-8")


class VentAxiaPskClient(AsyncNativePskClient):
    """PSK client that also accepts a hex-encoded (raw-byte) PSK.

    Behaves exactly like the upstream client for the older models; when
    ``psk_is_hex`` is true the stored key is the decoded raw bytes instead of
    the UTF-8 encoding of the string.
    """

    # The newer (>2023) / SX / Econiq controllers run mbedTLS on an ESP32 and
    # reset the connection if the ClientHello offers TLS 1.3. The handshake
    # only completes when the client is pinned to TLS 1.2. (Verified against a
    # live unit: an unpinned context resets; pinning to 1.2 succeeds.)
    pin_tls12: bool = False

    def __init__(
        self, *args, psk_is_hex: bool = False, pin_tls12: bool = False, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.pin_tls12 = pin_tls12
        if psk_is_hex:
            # ``psk_key`` may be positional or keyword depending on the caller.
            raw = kwargs.get("psk_key")
            if raw is None and len(args) >= 2:
                raw = args[1]
            if raw is not None:
                self.psk_key = decode_psk(raw, True)
                _LOGGER.debug(
                    "Using hex PSK (%d bytes) for %s",
                    len(self.psk_key),
                    kwargs.get("host", "device"),
                )

    async def connect(self, timeout: float = 30.0) -> None:
        """Open the TLS-PSK connection, pinning TLS 1.2 when required.

        Mirrors the upstream connect() but clamps the context to TLS 1.2 for
        controllers that reset on a TLS 1.3-capable ClientHello. When
        ``pin_tls12`` is false this defers entirely to the upstream behaviour.
        """
        if not self.pin_tls12:
            return await super().connect(timeout=timeout)

        if self._running and self.writer is not None:
            return
        if self._closing:
            raise ConnectionError("Client is currently closing")

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers("PSK-AES128-CBC-SHA")
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_psk_client_callback(self.psk_callback)

        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=context),
                timeout=timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.reader = None
            self.writer = None
            raise ConnectionError(
                f"Failed to connect to {self.host}:{self.port}: "
                f"{type(err).__name__}: {err}"
            ) from err

        self.reader = reader
        self.writer = writer
        self._running = True
        self._closing = False
        self._reader_task = asyncio.create_task(
            self._reader_loop(), name="ventaxiaiot_reader"
        )
