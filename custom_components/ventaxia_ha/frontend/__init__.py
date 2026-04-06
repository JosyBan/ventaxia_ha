import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import JSMODULES, URL_BASE

_LOGGER = logging.getLogger(__name__)


class JSModuleRegistration:
    """Registers JavaScript modules in Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the registrar."""
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    async def async_register(self) -> None:
        """Register frontend resources."""
        await self._async_register_path()
        # Only register modules if Lovelace is in storage mode
        if self.lovelace is not None and hasattr(self.lovelace, "resources"):
            await self._async_wait_for_lovelace_resources()

    async def _async_register_path(self) -> None:
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(Path(__file__).parent), False)]
            )
            _LOGGER.debug("Path registered: %s -> %s", URL_BASE, Path(__file__).parent)
        except RuntimeError:
            _LOGGER.debug("Path already registered: %s", URL_BASE)

    async def _async_wait_for_lovelace_resources(self) -> None:
        async def _check_loaded(_now: Any) -> None:
            if self.lovelace and hasattr(self.lovelace, "resources"):
                await self._async_register_modules()
            else:
                async_call_later(self.hass, 5, _check_loaded)

        await _check_loaded(0)

    async def _async_register_modules(self) -> None:
        """Register JS modules in Lovelace safely."""
        if not self.lovelace or not hasattr(self.lovelace, "resources"):
            _LOGGER.warning(
                "Lovelace resources not available, skipping module registration"
            )
            return

        existing_resources = [
            r
            for r in self.lovelace.resources.async_items()
            if r["url"].startswith(URL_BASE)
        ]

        for module in JSMODULES:
            url = f"{URL_BASE}/{module['filename']}"
            registered = False

            for resource in existing_resources:
                if resource["url"].split("?")[0] == url:
                    registered = True
                    # Only update if version changed
                    query = (
                        resource["url"].split("?")[1] if "?" in resource["url"] else ""
                    )
                    if query != module["version"]:
                        await self.lovelace.resources.async_update_item(
                            resource["id"],
                            {
                                "res_type": "module",
                                "url": f"{url}?v={module['version']}",
                            },
                        )
                    break

            if not registered:
                await self.lovelace.resources.async_create_item(
                    {
                        "res_type": "module",
                        "url": f"{url}?v={module['version']}",
                    }
                )

    async def async_unregister(self) -> None:
        """Remove registered JS modules from Lovelace."""
        if not self.lovelace or not hasattr(self.lovelace, "resources"):
            return

        for module in JSMODULES:
            resources = [
                r
                for r in self.lovelace.resources.async_items()
                if r["url"].startswith(f"{URL_BASE}/{module['filename']}")
            ]
            for resource in resources:
                await self.lovelace.resources.async_delete_item(resource["id"])
