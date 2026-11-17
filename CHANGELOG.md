# Changelog

Changes for the newer (>2023 / SX / Econiq) Advance S controller support.

## 0.10.6

**Fixes**
- Stop brief self-initiated mode blips flapping the entities. Some units start
  a ~2 second Boost "override" on their own and drop straight back to Auto,
  which flipped Ventilation Mode, Current Mode and Auto back and forth. Any
  change the unit makes by itself now has to hold for 6 seconds before HA shows
  it; modes chosen from HA still update instantly, and returning to Auto is
  never delayed.

## 0.10.0 - 0.10.5

**New controls**
- **Fan Mode Speeds**: the per-mode extract and supply fan speeds (the app's
  "Fan Mode Speeds" screen) are now editable from HA. Eight new number entities:
  Extract and Supply % for each of Low, Normal, Boost and Purge. Writing one
  speed preserves the preset's other values. They share a "Fan Speed" name so
  they group together under the device's Configuration section.

**Fixes**
- Keep config values that the unit serves once and then clears (an empty
  publish no longer blanks the fan-speed entities between polls).
- Allow stale devices to be removed from the integration.

## 0.9.0

**New controls**
- **Default Airflow** select (Low / Normal / Boost / Max): sets the unit's base
  airflow speed when it is idle on its schedule.
- **Bypass Indoor Comfort Temp** and **Bypass Outdoor Comfort Temp** numbers:
  the two summer bypass comfort thresholds, editable from HA (the rest of the
  bypass config is preserved on write).

## 0.8.5 - 0.8.10

**Current Mode / Auto**
- Split the old "Current Mode" into two cleaner entities: **Current Mode**
  (just the speed: Low / Normal / Boost / Purge / Max) and a separate **Auto**
  on/off sensor for schedule vs manual override.
- Stopped the Current Mode sensor flapping. The unit does brief (~2 second)
  auto purge bursts while on its schedule; those are now ignored, while real
  mode changes still show instantly.

**Responsiveness**
- Selecting a mode now updates the UI immediately instead of lagging a few
  seconds behind the unit.

**Fixes**
- Fixed an issue where some entities (notably the new Auto sensor) could stop
  refreshing.

**Performance**
- Less redundant work: identical re-published values no longer re-render every
  entity, and each payload is parsed once.
- Lighter polling: fast telemetry is read every cycle, config/maintenance
  values much less often.

## 0.8.0 - 0.8.4

- Added **Current Mode** sensor plus filter life, service due, summer bypass,
  and IAQ (humidity boost threshold, air quality) sensors, and extract/supply
  fan power.
- Fixed a stuck-airflow case after a timed override (the unit could keep
  running Purge/Boost while reporting Auto); HA now ends timed overrides itself
  just before the unit's own timer.

## 0.5.0

- Override Remaining now tracked locally (the unit's reported end timestamp
  carries no timezone and could not be trusted).
- Controls stay pressable across brief reconnects (QoS 1, reconnect backoff).
- Added a **Boost Hold** switch (boost until turned off), since the unit ignores
  an indefinite boost request.
