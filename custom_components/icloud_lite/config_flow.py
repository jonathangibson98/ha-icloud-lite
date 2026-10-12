"""Config + options flow for iCloud Lite."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pyicloud.exceptions import PyiCloudException, PyiCloudFailedLoginException

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import fetch_devices, login
from .const import CONF_DEVICES, CONF_INTERVAL, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

INTERVAL_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=60))


class ICloudLiteFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._api = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ICloudLiteOptions(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input[CONF_PASSWORD]
            if self.source != SOURCE_REAUTH:
                await self.async_set_unique_id(self._username.lower())
                self._abort_if_unique_id_configured()
            try:
                self._api = await self.hass.async_add_executor_job(
                    login, self.hass, self._username, self._password
                )
            except PyiCloudFailedLoginException:
                errors["base"] = "invalid_auth"
            except PyiCloudException:
                errors["base"] = "cannot_connect"
            else:
                if self._api.requires_2fa:
                    return await self.async_step_2fa()
                return await self._after_login()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self._username or ""): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._username = entry_data[CONF_USERNAME]
        return await self.async_step_user()

    async def async_step_2fa(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            ok = False
            try:
                ok = await self.hass.async_add_executor_job(
                    self._api.validate_2fa_code, user_input["code"].strip()
                )
                if ok and not self._api.is_trusted_session:
                    await self.hass.async_add_executor_job(self._api.trust_session)
            except PyiCloudException:
                ok = False
            if ok:
                return await self._after_login()
            errors["base"] = "invalid_code"

        return self.async_show_form(
            step_id="2fa",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )

    async def _after_login(self) -> ConfigFlowResult:
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data={CONF_USERNAME: self._username, CONF_PASSWORD: self._password},
            )
        return await self.async_step_devices()

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        found = await self.hass.async_add_executor_job(fetch_devices, self._api)
        
        # Build options formatted as "Device Name (Model)"
        options = []
        for dev_id, info in found.items():
            name = info.get("name", "Apple Device")
            model = info.get("model")
            label = f"{name} ({model})" if model and model != name else name
            options.append({"value": dev_id, "label": label})

        if user_input is not None:
            return self.async_create_entry(
                title=self._username,
                data={CONF_USERNAME: self._username, CONF_PASSWORD: self._password},
                options={
                    CONF_DEVICES: user_input[CONF_DEVICES],
                    CONF_INTERVAL: user_input[CONF_INTERVAL],
                },
            )

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICES, default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): INTERVAL_VALIDATOR,
                }
            ),
        )


class ICloudLiteOptions(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Display options menu when clicking Configure."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "settings"],
        )

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage tracked devices."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.data:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            updated_options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=updated_options)

        options = []
        for dev_id, info in coordinator.data.items():
            name = info.get("name", "Apple Device")
            model = info.get("model")
            label = f"{name} ({model})" if model and model != name else name
            options.append({"value": dev_id, "label": label})

        current_devices = self.config_entry.options.get(CONF_DEVICES, [])

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICES, default=current_devices): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure polling interval."""
        if user_input is not None:
            updated_options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=updated_options)

        current_interval = self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INTERVAL, default=current_interval): INTERVAL_VALIDATOR,
                }
            ),
        )
