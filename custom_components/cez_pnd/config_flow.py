"""Config flow: přihlášení a interval → elektroměr a datum „od“."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import PndAuthError, PndClient, PndError
from .const import (
    CONF_DATE_FROM,
    CONF_ELECTROMETER,
    CONF_SCAN_INTERVAL,
    DATE_FMT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
INTERVAL_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        max=MAX_SCAN_INTERVAL,
        step=1,
        unit_of_measurement="min",
        mode=selector.NumberSelectorMode.BOX,
    )
)


async def fetch_electrometers(username: str, password: str) -> dict[str, str]:
    """Přihlásí se a vrátí {číslo elektroměru: popisek}."""
    client = PndClient(username, password)
    try:
        await client.login()
        definition = await client.get_definition()
    finally:
        await client.close()
    return {
        str(d["value"]): str(d.get("label") or d["value"])
        for d in definition.get("electrometers") or []
    }


def _normalize_date(value: str) -> str:
    """DateTimeSelector vrací 'YYYY-MM-DD HH:MM:SS' (případně bez sekund)."""
    for fmt in (DATE_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime(DATE_FMT)
        except ValueError:
            continue
    raise vol.Invalid("invalid_date")


def _default_date_from() -> str:
    return datetime.now().replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    ).strftime(DATE_FMT)


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_DATE_FROM, default=defaults.get(CONF_DATE_FROM, _default_date_from())
            ): selector.DateTimeSelector(),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): INTERVAL_SELECTOR,
        }
    )


class PndConfigFlow(ConfigFlow, domain=DOMAIN):
    """Nastavení integrace."""

    VERSION = 2

    def __init__(self) -> None:
        self._user: dict[str, Any] = {}
        self._electrometers: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._electrometers = await fetch_electrometers(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except PndAuthError:
                errors["base"] = "invalid_auth"
            except PndError:
                errors["base"] = "cannot_connect"
            else:
                if not self._electrometers:
                    errors["base"] = "no_devices"
                else:
                    self._user = user_input
                    return await self.async_step_electrometer()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                        vol.Required(
                            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                        ): INTERVAL_SELECTOR,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_electrometer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            elm = str(user_input[CONF_ELECTROMETER]).strip()
            try:
                date_from = _normalize_date(user_input[CONF_DATE_FROM])
            except vol.Invalid:
                errors[CONF_DATE_FROM] = "invalid_date"
            else:
                await self.async_set_unique_id(f"elm{elm}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Elektroměr {elm}",
                    data={
                        CONF_USERNAME: self._user[CONF_USERNAME],
                        CONF_PASSWORD: self._user[CONF_PASSWORD],
                        CONF_ELECTROMETER: elm,
                    },
                    options={
                        CONF_DATE_FROM: date_from,
                        CONF_SCAN_INTERVAL: int(self._user[CONF_SCAN_INTERVAL]),
                    },
                )
        return self.async_show_form(
            step_id="electrometer",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ELECTROMETER, default=next(iter(self._electrometers))
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in self._electrometers.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                        )
                    ),
                    vol.Required(
                        CONF_DATE_FROM, default=_default_date_from()
                    ): selector.DateTimeSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await fetch_electrometers(entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except PndAuthError:
                errors["base"] = "invalid_auth"
            except PndError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PndOptionsFlow()


class PndOptionsFlow(OptionsFlow):
    """Změna data „od“ a intervalu."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                date_from = _normalize_date(user_input[CONF_DATE_FROM])
            except vol.Invalid:
                errors[CONF_DATE_FROM] = "invalid_date"
            else:
                return self.async_create_entry(
                    data={
                        CONF_DATE_FROM: date_from,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    }
                )
        cur = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(cur), errors=errors
        )
