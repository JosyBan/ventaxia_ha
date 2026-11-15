# Setting up a newer (>2023) Vent-Axia controller

A user guide for the key-less **Advance S (>2023) / SX / Econiq** controllers —
the ones with no printed Wi‑Fi key, that pair over Bluetooth and advertise as
`Sentinel Econiq`. For the older Advance S Wi‑Fi module, use the other setup
option and the main [README](../README.md).

> **TL;DR** — Add the integration, choose **Advance S (>2023) / SX / Econiq**,
> and enter five things: **Host** (the unit's IP), **Port** `8883`, **Identity**
> `zirconia`, the **PSK** (as hex), and the **Device ID**. If Home Assistant has
> a working Bluetooth adapter in range, the Device ID and PSK are filled in for
> you — see [Bluetooth auto-detect](#bluetooth-auto-detect).

---

## 1. What you need

| Field | What it is | Example |
|-------|-----------|---------|
| **Host** | The controller's IP address on your network | `10.10.5.42` |
| **Port** | Always `8883` for these units | `8883` |
| **Identity** | A fixed value baked into the Vent‑Axia app — leave as‑is | `zirconia` |
| **PSK** | The per‑unit pre‑shared key, entered as **hex** (tick *PSK is hex*) | `1a2b3c…` |
| **Device ID** | The unit's device identifier | `NNNNN-XXXXX` |

Find the **Host** from your router's DHCP list (look for the Vent‑Axia / ESP
device), or set a DHCP reservation so it never changes.

The **Device ID** and **PSK** come off the unit itself — see the next section.

---

## 2. Getting the PSK

These controllers don't print a Wi‑Fi key. The pre‑shared key (PSK) and Device
ID live on the unit's Bluetooth **GATT Auth service** and can be read three ways.

### Bluetooth auto-detect

When you open the setup form, the integration automatically scans over Home
Assistant's Bluetooth stack for the controller and tries to fill in the Device
ID and PSK. A grey note at the top of the form tells you what it found:

| What the note says | What to do |
|--------------------|-----------|
| *Auto-detected over Bluetooth — device ID and PSK filled in* | Just add the **Host** and submit. |
| *Auto-detected device ID …, but the PSK is locked* | The unit is already paired, so the PSK reads back blank. Put the unit in **pairing mode** and reopen the form, **or** enter the PSK by hand. |
| *Bluetooth auto-detect found no unit in range…* | No usable Bluetooth adapter is in range — enter the Device ID and PSK by hand. |

**Requirements for auto-detect:**

1. A **working Bluetooth scanner in range** of the controller. A Raspberry Pi's
   weak onboard radio often won't do — the reliable option is an **ESP32 flashed
   with ESPHome's [`bluetooth_proxy`](https://esphome.io/components/bluetooth_proxy/)**
   (set `bluetooth_proxy: active: true`), placed near the unit.
2. The PSK only fills in while the unit is **in pairing mode** (see below); the
   Device ID fills in either way.

> Auto-detect is a convenience. If you already have your PSK, you can always just
> type the five values in — it works exactly the same.

### Reading the PSK yourself (pairing mode)

The PSK is readable over Bluetooth **only while the unit is in pairing /
commissioning mode** — once provisioned it reads back as zeros ("locked"). To
read it:

1. Put the unit into **pairing / commissioning mode** (from the wall
   controller's commissioning menu, or on a factory-fresh unit).
2. With a BLE tool such as **nRF Connect** (or a small `bleak` script), connect
   and read the characteristic
   `638ff62c-3823-4e0f-8179-1695c46ee8ad` (`tlsKey`) on the Auth service
   `e6834e4b-7b3a-48e6-91e4-f1d005f564d3`. The bytes are the PSK — enter them as
   hex. The Device ID is the characteristic `673de933-963b-4298-bfc1-b0ccdada690a`.

### From the app's data

The Vent‑Axia Connect app caches the PSK in plaintext (no SecureStore), so it is
also reachable via `adb backup` (`allowBackup=true`) if you prefer.

More detail is in [`newer_model_notes.md`](newer_model_notes.md).

---

## 3. Step-by-step setup

1. **Install the integration** (Marketplace / HACS) and restart Home Assistant.
2. **Settings → Devices & Services → + Add Integration → "Vent‑Axia".**
3. Choose **Advance S (>2023) / SX / Econiq**.
4. Read the grey note (auto-detect result) and fill in anything not already
   filled: Host, Port `8883`, Identity `zirconia`, PSK (+ tick *PSK is hex*),
   Device ID.
5. **Submit.** The integration does a live TLS‑PSK handshake to validate before
   it finishes — if it errors, re-check the PSK and that the Host is reachable.

---

## 4. What you get

### Sensors

| Sensor | Notes |
|--------|-------|
| Outdoor / Extract Air Temperature | °C |
| Extract / Intake Humidity | % |
| Supply / Extract Fan Speed | rpm |
| Supply / Extract Fan Power | W |
| Power | total W |
| Wi‑Fi Signal | dBm (diagnostic, disabled by default) |
| **Filter Due** / **Filter Life Remaining** | next filter change date / days left; attributes show last change, interval and filter type |
| **Service Due** / **Service Due In** | next service date / days left |
| **Summer Bypass** | `Open` / `Closed`; attributes show position, mode and comfort temps |
| Override Remaining | minutes left on an active override |

### Controls

| Control | What it does |
|---------|--------------|
| **Ventilation Mode** (select) | Auto / Low / Normal / Boost / Purge / Max. "Auto" follows the unit's own schedule; the others apply a timed override. |
| **Override Duration** (number) | How long a selected mode runs before reverting to the schedule (minutes). |
| **Boost 15 min** (button) | One‑press 15‑minute boost. |
| **Boost Hold** (switch) | Boost **until turned off** — see below. |

---

## 5. Features & tips

### Modes and overrides

Selecting Low/Normal/Boost/Purge/Max applies a **timed** override for the
**Override Duration** you've set, after which the unit returns to its schedule.
Selecting **Auto** cancels any override and hands control back to the unit's
built‑in weekly program.

### Boost Hold — boost until turned off

The hardware override is always timed (the unit ignores a zero duration), so
there's no native "boost forever". The **Boost Hold** switch emulates it: while
on, it re‑arms a timed boost in the background; turning it off returns to Auto.

This is ideal for automations. For example, boost whenever the hob is in use:

```yaml
automation:
  - alias: "Kitchen hob → boost ventilation"
    trigger:
      - platform: state
        entity_id: binary_sensor.kitchen_hob_in_use
    action:
      - service: switch.turn_{{ 'on' if trigger.to_state.state == 'on' else 'off' }}
        target:
          entity_id: switch.ventaxia_XXXXX_boost_hold
```

If Home Assistant restarts, Boost Hold resumes automatically. If HA goes down
entirely, the boost safely self‑expires within the hour.

### Maintenance reminders

The **Filter Due** / **Service Due** sensors make easy dashboard reminders or
notification triggers, e.g. notify when the filter is within two weeks:

```yaml
- alias: "Filter change reminder"
  trigger:
    - platform: numeric_state
      entity_id: sensor.ventaxia_XXXXX_filter_life_remaining
      below: 14
  action:
    - service: notify.mobile_app
      data:
        message: "Vent-Axia filter is due soon."
```

---

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| **Setup fails to connect** | Check the Host is reachable and the PSK is correct (and that *PSK is hex* is ticked if you entered hex). Port must be `8883`. |
| **Some sensors are briefly "unavailable" after a restart** | They populate within a minute as the integration polls the controller. If one stays unavailable, reload the integration. |
| **Bluetooth auto-detect finds nothing** | HA needs a Bluetooth adapter/proxy in range. A Pi's onboard radio is often too weak — use an ESP32 `bluetooth_proxy`. Manual entry always works. |
| **PSK reads back blank/locked over Bluetooth** | The unit is already paired. Put it in pairing mode to read the PSK, or enter it by hand. |
| **Override Remaining or mode looks stale** | Values refresh every ~45 s; mode changes made on the wall controller reflect within that window. |

More protocol detail and the reverse‑engineering write‑up are in
[`newer_model_notes.md`](newer_model_notes.md) and
[`reverse_engineering.md`](reverse_engineering.md).
