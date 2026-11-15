# How the newer Vent-Axia controller was reverse-engineered

A write-up of the method used to work out the newer (>2023 / SX / Econiq /
"Zirconia") controller's authentication and application protocol, so a Home
Assistant integration could talk to it directly over the local network.

Everything here was done against a privately-owned unit for interoperability.
The hard protocol facts (topic map, TLS parameters, override control) live in
[`newer_model_notes.md`](newer_model_notes.md); this document is the *story of
how* those were found.

## The problem

The community integration already supported the **older** Advance S: a Wi-Fi
module with a **printed** key, speaking raw-JSON over TLS on ports ~47811 via
the `ventaxiaiot` library. The newer **Econiq** controller is different:

- **no printed Wi-Fi key** — so authentication was unknown, and
- it did **not** respond to the old raw-JSON framing — so the application
  protocol was unknown too.

Two unknowns to solve: *how to authenticate* and *what the unit actually speaks*.

## Stage 1 — Decompile the app (learn the vocabulary)

The official **Vent-Axia Connect** Android app is ground truth: it already talks
to the unit, so the transport, credentials and message formats are all in it.

1. Obtained the **APK** (v7.3.0).
2. It is a **React Native / Expo** app, so the business logic is compiled to a
   **Hermes bytecode** bundle (`index.android.bundle`) rather than Java/smali.
3. Decompiled the Hermes bundle with **[`hbc-decompiler`](https://github.com/P1sec/hermes-dec)**
   (hermes-dec), producing a ~1.75M-line pseudo-source dump.
4. From there it was mostly `grep`. Searching for `uuid`, `tls`, `psk`, `mqtt`,
   `port`, `cipher`, and candidate topic strings surfaced the whole design:
   - a BLE **`ZirconiaDeviceAuthService`** exposing `deviceId`, `tlsIdentity`
     and **`tlsKey`** characteristics,
   - `pskCipherSuites: [140]` → `0x008C` → **`PSK-AES128-CBC-SHA`**,
   - a credentials structure with `tcpTlsIdentity` / `tcpTlsKey`,
   - and the key distinction **`mqttPort: 8883`** vs **`zirconiaPort: 47820`**.

**Lesson:** for an RN/Expo app, decompiling the Hermes bundle and grepping it is
far faster than live traffic capture — the app literally contains the constants.

## Stage 2 — Read the PSK over Bluetooth

The reason there is no printed key: the unit **provisions the pre-shared key over
BLE during pairing**.

1. Using **`bleak`** (Python BLE), connected to the unit and read the GATT
   characteristics found above — `tlsKey` (`638ff62c-…e8ad`) and `deviceId`
   (`673de933-…690a`).
2. Discovered they return the real values **only while the unit is in
   pairing/commissioning mode**; once provisioned the `tlsKey` reads back as all
   zeros while `deviceId` stays readable. (This exact behaviour is what the
   integration's Bluetooth auto-detect is built around.)
3. Result: the raw PSK bytes (kept out of the repo) plus identity **`zirconia`**.

## Stage 3 — Get the TLS-PSK handshake working

With key + identity + cipher in hand, the first TLS-PSK connections still **reset
immediately**.

1. Proved the *credentials* were correct first with **`openssl s_client`**:
   ```sh
   openssl s_client -connect <ip>:8883 \
     -psk <hex-key> -psk_identity zirconia \
     -cipher PSK-AES128-CBC-SHA -tls1_2
   ```
   That handshook cleanly — so the key/identity/cipher were right.
2. Python's `ssl` module kept failing where openssl worked. The difference:
   Python offered **TLS 1.3** in its ClientHello, and the unit's
   **ESP32 / mbedTLS** stack resets the connection on anything above TLS 1.2.
3. Fix: pin the version both ways —
   ```python
   ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
   ```
   Handshake succeeded. This pin lives in `client.py`.

**Lesson:** when a hand-rolled TLS client (openssl) connects but a high-level
library doesn't, suspect the **protocol-version** offer before the credentials.

## Stage 4 — Find the real application protocol

The biggest dead end: assuming the newer unit used the *older* model's raw-JSON
`<deviceId>/rd` framing on **47820**. A connect attempt got **no response at all**.

Back in the decompiled bundle, `mqttPort: 8883` was the clue. The newer model
runs a **real MQTT 3.1.1 broker inside the TLS-PSK socket on port 8883** — not
47820, and not the old framing.

Pointing **`paho-mqtt`** at a TLS-PSK socket on 8883 and subscribing to
`<deviceId>/#` immediately produced a stream of telemetry.

**Lesson:** don't assume a new model reuses the old transport. The app's own port
constants said otherwise; trusting them broke the deadlock.

## Stage 5 — Map topics and controls (live)

With a live MQTT feed, the rest was observation plus active probing:

- **Sensors:** matched live publishes to the topic strings seen in the app —
  `io/t1` (outdoor temp), `io/t3` (extract temp), `io/erh/val` / `io/irh/val`
  (humidity), `mdet/pwr` (power), `vent/afs/*` and `vent/afe/*` (supply/extract
  fans).
- **Control:** the app issues a user override by publishing to **`vent/uo`**:
  ```json
  {"gtm": N, "treq": "HH:MM:SS"}
  ```
  Publishing this live and watching `vent/caf`'s `ps` field change (and the fans
  ramp) confirmed the `gtm` scale: `0`=Auto/cancel, `1`=Low, `2`=Normal,
  `3`=Boost, `4`=Purge, `5`=Max. This was cross-checked against the physical
  controller by setting a mode in the app and watching the topic.
- **Auto detection:** `vent/cor` reports override status; an empty `trem` means
  the unit is following its own schedule (Auto). That is how the HA mode-select
  shows "Auto" correctly rather than snapping to the current airflow preset.

## The method, distilled

1. **Decompile the app** to learn the vocabulary (UUIDs, cipher, ports, topics).
2. **Read the secrets off BLE** (PSK + device ID), noting the pairing-mode gate.
3. **Confirm the transport with a hand-rolled client** (openssl) before blaming
   credentials — which exposed the TLS 1.2 pin.
4. **Find the real protocol** by trusting the app's own constants (MQTT on 8883),
   not the previous model's assumptions.
5. **Confirm by live capture and active probing** of your own unit — the app says
   *what* to send; the unit says *whether it worked*.

## Tools used

| Tool | Purpose |
|------|---------|
| `hbc-decompiler` (hermes-dec) | decompile the Hermes/RN app bundle |
| `grep` | mine the decompiled bundle for constants |
| `bleak` | read the PSK / device ID off the BLE Auth service |
| `openssl s_client` | prove the TLS-PSK credentials/cipher independently |
| Python `ssl` | pin TLS 1.2 for the real client |
| `paho-mqtt` | speak MQTT 3.1.1 over the TLS-PSK socket |
