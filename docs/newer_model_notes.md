# Newer controller notes (Advance S >2023 / SX / Econiq / "Zirconia")

Reverse-engineering notes for the key-less controllers, gathered from a live
unit (BLE advertises as `Sentinel Econiq`, Device Information service reports
manufacturer `Vent-Axia`, model `50`) and from static analysis of the
Vent-Axia Connect app (v7.3.0, a React Native / Hermes bundle).

These controllers are **not** the older Advance S with a Wi-Fi module. They
have no printed Wi-Fi key; the TLS pre-shared key is provisioned over
Bluetooth during pairing.

## Connection parameters (confirmed against a live unit)

| Parameter | Value |
|-----------|-------|
| Transport | TLS-PSK over TCP |
| Port      | `47820` (the app calls it `zirconiaPort`; `8883` is also open) |
| PSK identity | `zirconia` (hard-coded in the app; the unit resets the TCP connection for other identities such as `12345`) |
| Cipher    | `PSK-AES128-CBC-SHA` (`pskCipherSuites: [140]` = `0x008C`) |
| TLS version | **must be pinned to TLS 1.2** — the ESP32/mbedTLS stack resets the connection if the ClientHello offers TLS 1.3 |
| PSK key   | per-unit, provisioned over BLE (see below) |
| Device ID | per-unit, e.g. `59375-7KK9M` |

The PSK is a short (8-byte on the sampled unit) value. The app passes it to
its native TLS layer base64-encoded; on the wire it is the raw bytes.

`custom_components/ventaxia_ha/client.py` implements the TLS 1.2 pin and
hex-PSK handling; the config flow exposes the `Advance S (>2023) / SX /
Econiq` model option. The TLS handshake has been verified end-to-end with the
integration's own client.

## BLE provisioning (where the PSK comes from)

The app exposes three GATT services on the controller. UUIDs from the bundle:

- **ZirconiaDeviceAuthService** `e6834e4b-7b3a-48e6-91e4-f1d005f564d3`
  - `deviceId`    `673de933-963b-4298-bfc1-b0ccdada690a`
  - `tlsIdentity` `98faf8a5-1ee6-4b0c-911e-dc37bff5206f`
  - `tlsKey`      `638ff62c-3823-4e0f-8179-1695c46ee8ad`  ← **the PSK**
- **ZirconiaDeviceProtocolService** `e6ec2fd8-e888-4eb2-9680-e78ed6ea89e1`
  - `fragmentedPackage` `e6ec2fd8-e888-4eb2-9681-e78ed6ea89e1`
  - `wholePackage`      `a8e23cea-978d-ac8d-374c-cbb4eeb63f41`
  - `notifier`          `6b1526ff-e3de-1fab-2c4e-10ae479b9245`
- **ZirconiaDeviceConfigurationService** `c119e858-0531-4681-9674-5a11f0e53bb4`
  - `mode`                   `7c4adc0d-2f33-11e7-93ae-92361f002671`
  - `factorySettingsChanged` `7c4adc0e-2f33-11e7-93ae-92361f002671`

The Auth characteristics return the real `tlsKey` / `tlsIdentity` **only while
the unit is in pairing/commissioning mode**; once provisioned they read back as
zeros (the `deviceId` stays readable). So the PSK can be read directly over BLE
by putting the unit into pairing mode and reading `638ff62c-…e8ad` — no root
and no app backup required. The app also caches it; since it is a React Native
app with no SecureStore/Keychain usage, the value is stored in plaintext in the
app's data (reachable via `adb backup`, `allowBackup=true`).

## Application protocol — real MQTT on port 8883

The older model speaks "MQTT-shaped JSON over TLS-PSK" with topics
`<deviceId>/rd|wr|ee` (handled by `ventaxiaiot`). The newer model is
**different**: it runs a real MQTT 3.1.1 broker over the TLS-PSK socket on
**port 8883** (the app's `mqttPort`, not `zirconiaPort` 47820). The
`ventaxiaiot` raw-JSON framing is ignored by this model.

Connect with identity `zirconia`, the provisioned PSK, TLS pinned to 1.2, then
subscribe to `<deviceId>/#`. The unit publishes retained telemetry. Confirmed
live topics (device id `59375-7KK9M`):

| Topic (`<deviceId>/…`) | Meaning | Example |
|---|---|---|
| `io/t1` | outdoor air temp (°C) | `8.8` |
| `io/t3` | extract air temp (°C) | `18.6` |
| `io/erh/val` | extract humidity (%) | `57.6` |
| `io/irh/val` | intake humidity (%) | `70.0` |
| `mdet/pwr` | total power (W) | `49.3` |
| `mdet/wifi/sta` | Wi-Fi status (JSON) | `{"rssi":-71,"ssid":"IoT",…}` |
| `vent/afs/{rpm,pwr,pwm}` | supply fan | `2096.8 / 24.4 / 50.0` |
| `vent/afe/{rpm,pwr,pwm}` | extract fan | `2094.9 / 24.4 / 50.0` |

Other topics seen in the app bundle (not all published at rest): `vent/afc`,
`vent/cm`, `vent/caf`, `vent/daf`, `vent/maxaf`, `vent/filtertmr/*`,
`vent/filter1/typ`, `vent/filter2/typ`, `vent/pf`, `vent/saq`, `vent/uo`, plus
`.../conf/wr` and `.../typ/wr` for writes (control is not yet implemented here).

**Status:** implemented. `mqtt_coordinator.py` provides an MQTT coordinator and
sensor platform for this model, wired in via the `Advance S (>2023)` config-flow
option. Read-only sensors work; airflow-mode control over the `vent/.../wr`
topics remains as future work.
