# Ventaxia for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

[![Project Maintenance][maintenance-shield]][user_profile]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

This custom component integrates Vent Axia Sentinel Kinetic Advance S MVHR (mechanical ventilation with heat recovery) System with the Wifi module with [Home Assistant][ha], allowing you to monitor various parameters from your device.

# Supported Devices

This integration relies on the [ventaxiaiot python library](https://github.com/JosyBan/ventaxiaiot). Currently it only supports this Ventaxia model:

    Vent Axia Sentinel Kinetic Advance S

**This component will set up the following platforms.**

| Platform | Description                                        |
| -------- | -------------------------------------------------- |
| `sensor` | Provides various readings for your Ventaxia device |

![example][logo]

## HACS Installation

This is the recommended way to install.

1. Open [HACS][hacs] in your Home Assistant UI
2. Click on the three dots in the top right corner and select Custom repositories.
3. In the "Add custom repository" field, paste https://github.com/JosyBan/ventaxia_ha.
4. Select Integration as the Category.
5. Click ADD
6. Once added, search for "ventaxia" in the HACS Integrations section.
7. Click on the "ventaxia" integration.
8. Click Download and confirm.
9. Restart Home Assistant.
10. In the HA UI, click Settings in the left nav bar, then click "Devices & Services". By default you should be viewing the Integrations tab. Click "+ Add Integration" button at bottom right and then search for "ventaxia".

## Manual Installation

1. Download the integration: Download the latest release from the [Release Page][ventaxia-releases].
2. Unpack the ventaxia_ha folder from the downloaded archive.
3. Copy the entire ventaxia_ha folder into your Home Assistant's custom_components directory. If this directory doesn't exist, you'll need to create it.
4. Your Home Assistant configuration directory typically resides at /config (e.g., /config/custom_components/ventaxia_ha/).
5. Restart Home Assistant.
6. In the HA UI, click Settings in the left nav bar, then click "Devices & Services". By default you should be viewing the Integrations tab. Click "+ Add Integration" button at bottom right and then search for "ventaxia".

## Configuration

After installation and restarting Home Assistant, you can configure the Ventaxia integration via the Home Assistant UI.

    Go to Settings > Devices & Services.

    Click on ADD INTEGRATION.

    Search for "Ventaxia" and select it.

    Follow the on-screen prompts to enter your Ventaxia device's connection details:

        Host/IP Address: The IP address or hostname of your Ventaxia device on your local network.

        Key: This is the WIFI Key printed on the device

        Deice ID: This is the WIFI SSID of the device

Once successfully configured, the integration will automatically discover and create relevant sensor entities. You can find the full list of available entities under Settings > Devices & Services > Ventaxia integration once it's set up.

## Troubleshooting

Troubleshooting

    Integration not found after restart:
        Ensure the ventaxia_ha folder is directly inside custom_components (i.e., custom_components/ventaxia_ha/ and not custom_components/ventaxia_ha/ventaxia_ha/).
        Clear your browser cache.

    Failed to connect / Device offline:
        Verify the IP address or hostname entered during configuration is correct.
        Ensure your Ventaxia device is powered on and connected to your local network.
        Check for any firewall rules on your Home Assistant host or network that might be blocking communication with the Ventaxia device.
        Review your Home Assistant logs (Settings > System > Logs) for more specific error messages related to the ventaxia integration.

    Sensors not updating:
        Confirm that your Ventaxia device is actively operating.
        Restart Home Assistant to force a re-initialization of the integration.
        Check the Home Assistant logs for any errors originating from the ventaxia_ha component.

For further assistance, please open an issue on the GitHub repository.

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md).

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template.

And it was heavely inspired by [@CJNE](https://github.com/CJNE)'s [ha-myenergi] project.

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[ha-myenergi]: https://github.com/CJNE/ha-myenergi
[ventaxia_ha]: https://github.com/JosyBan/ventaxia_ha
[ventaxia-releases]: https://github.com/JosyBan/ventaxia_ha/releases
[commits]: https://github.com/JosyBan/ventaxia_ha/commits/main/
[ha]: https://home-assistant.io
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[logo]: logo@2x.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/JosyBan/ventaxia_ha.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40JosyBan-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/JosyBan/ventaxia_ha.svg?style=for-the-badge
[releases]: https://github.com/JosyBan/ventaxia_ha/releases
[user_profile]: https://github.com/JosyBan
