# Ventaxia Lovelace Card

A custom dashboard card for the Vent Axia Sentinel Kinetic Advance S, bundled with the [Ventaxia integration](../README.md). It lets you check the unit and control it from a dashboard without building your own cards: switch airflow modes, run timed boosts, edit schedules, set silent hours and tune the summer bypass.

The card is installed together with the integration. There is nothing separate to download from HACS.

## Features

The card has three tabs.

**Status**

- Shows the current airflow mode.
- Tap the circle to start a timed run of the selected mode (15, 30, 45 or 60 minutes). While a timer runs, the circle shows a countdown and a **Cancel** button that returns the unit to normal.
- The dots under the circle select the mode: Normal, Boost or Purge.
- **Scheduled mode**: lists your programs. Tap one to edit or delete it, or tap **New program** to add one (start/end time, days, mode).
- **Silent hours**: tap to edit the start/end time and days.
- **Summer bypass**: shows the indoor/outdoor temperature thresholds and bypass mode. Tap to edit them.

![screenshot1|50%][Status]

**Performance**

- Outdoor, extract (indoor) and supply air temperatures.

![screenshot2|50%][Performance]

**Maintenance**

- Filter months remaining and service information.

![screenshot3|50%][Maintenance]

## Installation

The card ships inside the integration, so once the integration is installed (see [HACS Installation](../README.md#hacs-installation)) and Home Assistant has restarted, the card is available automatically.

On startup the integration:

1. Serves the card file from `/ventaxia_ha/ventaxia-card.js`.
2. Adds it to your dashboard resources as a JavaScript module (`/ventaxia_ha/ventaxia-card.js?v=<integration version>`). The version suffix is updated when the integration is updated, so browsers pick up new card versions.

### If your dashboards are in YAML mode

Automatic resource registration only works when dashboard resources are managed in the UI (storage mode). If you manage resources in YAML, add this to your configuration:

```yaml
lovelace:
  resources:
    - url: /ventaxia_ha/ventaxia-card.js
      type: module
```

After the first install, or after an update, do a hard refresh of your browser (or clear the app cache on mobile) if the card does not appear.

## Adding the card to a dashboard

1. Open a dashboard and choose **Edit dashboard** > **Add card**.
2. Search for **VentAxia Card**.

Or add it through the YAML editor:

```yaml
type: custom:ventaxia-card
device_id: <your device id>
```

### Configuration

| Option      | Required    | Description                                                                                                                                        |
| ----------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `device_id` | Recommended | The Home Assistant device ID of your Ventaxia unit. The card uses it to find the integration's sensors, even if you have renamed their entity IDs. |

To find the device ID, go to **Settings > Devices & services > Ventaxia**, open the device, and copy the ID from the URL (`/config/devices/device/<device id>`).

If `device_id` is omitted, the card falls back to default entity IDs of the form `sensor.<name>` (for example `sensor.airflow_mode`). This only works if your entities still have their original names, so setting `device_id` is the safer choice.

## Entities the card reads

The card looks up these sensors from the integration:

`airflow_active`, `manual_airflow_timer`, `airflow_mode`, `schedules`, `silent_hours`, `summer_bypass_mode`, `summer_bypass_indoor_temp`, `summer_bypass_outdoor_temp`, `summer_bypass_airflow_mode`, `filter_months_remaining`, `service_info`, `outdoor_temperature`, `indoor_temperature`, `supply_air_temperature`.

If one is missing, the browser console logs `VentAxiaCard: no entity found for "<name>"` and that part of the card stays at its placeholder value.

## Services the card calls

The card controls the unit through the integration's own services, so anything you can do on the card you can also automate:

| Service                                       | Used for                                                |
| --------------------------------------------- | ------------------------------------------------------- |
| `ventaxia_ha.set_airflow_mode`                | Timed modes and cancel                                  |
| `ventaxia_ha.update_schedule_or_silent_hours` | Adding, editing and deleting programs, and silent hours |
| `ventaxia_ha.set_summer_bypass`               | Summer bypass settings                                  |

See `services.yaml` or **Developer tools > Actions** for the fields each one accepts.

## Troubleshooting

**If the card doesn't appear in the card picker, or shows "Custom element doesn't exist: ventaxia-card"**

- Restart Home Assistant after installing or updating the integration.
- Check **Settings > Dashboards > Resources** (enable Advanced mode in your profile if you do not see it). There should be an entry for `/ventaxia_ha/ventaxia-card.js`. If it is missing and you use YAML mode, add it as shown above.
- Hard refresh the browser.

**Values show placeholders or do not update**

- Add `device_id` to the card configuration.
- Open the browser developer console and look for `VentAxiaCard:` warnings.
- Confirm the sensors exist and have values under **Settings > Devices & services > Ventaxia**.

**Check the card version**

The browser console prints `VENTAXIA-CARD <version>` when the card loads. It should match the integration version.

For anything else, please [open an issue](https://github.com/JosyBan/ventaxia_ha/issues).

---

[Status]: \images\Screenshot1.png
[Performance]: \images\Screenshot2.png
[Maintenance]: \images\Screenshots3.png
