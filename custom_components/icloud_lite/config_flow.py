"""Config + options flow for iCloud Lite."""
from __future__ import annotations

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
from homeassistant.helpers import config_validation as cv

from . import fetch_devices, login
from .const import CONF_DEVICES, CONF_INTERVAL, DEFAULT_INTERVAL, DOMAIN

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
        return ICloudLiteOptions()

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
        choices = {dev_id: info["name"] for dev_id, info in found.items()}
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
                    vol.Required(CONF_DEVICES): cv.multi_select(choices),
                    vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): INTERVAL_VALIDATOR,
                }
            ),
        )


class ICloudLiteOptions(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        choices = {dev_id: info["name"] for dev_id, info in coordinator.data.items()}
        current = [d for d in self.config_entry.options.get(CONF_DEVICES, []) if d in choices]
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICES, default=current): cv.multi_select(choices),
                    vol.Required(
                        CONF_INTERVAL,
                        default=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                    ): INTERVAL_VALIDATOR,
                }
            ),
        )
