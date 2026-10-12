"""iCloud Lite - track only the Apple devices you pick. No dashboards, no stationary zones."""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudException, PyiCloudFailedLoginException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_INTERVAL, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.DEVICE_TRACKER]


def login(hass: HomeAssistant, username: str, password: str) -> PyiCloudService:
    """Log in to iCloud (blocking - run in executor)."""
    cookie_dir = hass.config.path(".storage", DOMAIN)
    os.makedirs(cookie_dir, exist_ok=True)
    return PyiCloudService(username, password, cookie_directory=cookie_dir, with_family=True)


def fetch_devices(api: PyiCloudService) -> dict[str, dict[str, Any]]:
    """Refresh once and return {device_id: info} for every device (blocking)."""
    try:
        api.devices.update()
    except Exception as err:
        _LOGGER.debug("Could not force refresh FindMyiPhone devices: %s", err)

    result: dict[str, dict[str, Any]] = {}
    for device in api.devices:
        data = device.data
        result[data["id"]] = {
            "name": data.get("name") or data.get("deviceDisplayName") or "Apple device",
            "model": data.get("deviceDisplayName"),
            "battery": data.get("batteryLevel"),
            "battery_status": data.get("batteryStatus"),
            "location": data.get("location"),
        }
    return result


class ICloudLiteCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls iCloud on a fixed interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: PyiCloudService) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )
        self.api = api

    def _fetch(self) -> dict[str, dict[str, Any]]:
        if self.api.requires_2fa:
            raise ConfigEntryAuthFailed("Apple wants a fresh 2FA code")
        return fetch_devices(self.api)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            new = await self.hass.async_add_executor_job(self._fetch)
        except ConfigEntryAuthFailed:
            raise
        except PyiCloudFailedLoginException as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"iCloud update failed: {err}") from err

        # Keep the last known location if Apple returns nothing (phone offline)
        for dev_id, info in new.items():
            if info["location"] is None and self.data and dev_id in self.data:
                info["location"] = self.data[dev_id].get("location")
        return new


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        api = await hass.async_add_executor_job(
            login, hass, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
        )
    except PyiCloudFailedLoginException as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PyiCloudException as err:
        raise ConfigEntryNotReady(str(err)) from err

    if api.requires_2fa:
        raise ConfigEntryAuthFailed("Apple wants a fresh 2FA code")

    coordinator = ICloudLiteCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
