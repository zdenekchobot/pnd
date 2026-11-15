"""ČEZ Distribuce PND integrace."""

from __future__ import annotations

import logging
from datetime import (
    datetime as DateTime,  # „datetime“ v balíčku zastiňuje platforma datetime.py
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import PndClient
from .const import CONF_DATE_FROM, CONF_ELECTROMETER, CONF_SCAN_INTERVAL, DATE_FMT
from .coordinator import PndCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DATETIME, Platform.SENSOR]

type PndConfigEntry = ConfigEntry[PndCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PndConfigEntry) -> bool:
    client = PndClient(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = PndCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PndConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.client.close()
    return ok


async def _async_reload(hass: HomeAssistant, entry: PndConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Převod položky z prototypu (verze 1: sestava + zařízení)."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        old = {**entry.data, **entry.options}
        kind, _, dev_id = str(old.get("device", "")).partition(":")
        if kind != "elm" or not dev_id:
            _LOGGER.error(
                "Položku %s nelze převést: prototyp používal sadu EAN, "
                "nová verze podporuje jen elektroměr. Přidej integraci znovu.",
                entry.title,
            )
            return False
        # prototyp ukládal jen datum 'YYYY-MM-DD'
        day = DateTime.strptime(str(old.get(CONF_DATE_FROM))[:10], "%Y-%m-%d")
        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_USERNAME: old[CONF_USERNAME],
                CONF_PASSWORD: old[CONF_PASSWORD],
                CONF_ELECTROMETER: dev_id,
            },
            options={
                CONF_DATE_FROM: day.strftime(DATE_FMT),
                CONF_SCAN_INTERVAL: int(old.get(CONF_SCAN_INTERVAL, 60)),
            },
            unique_id=f"elm{dev_id}",
            title=f"Elektroměr {dev_id}",
            version=2,
        )
    return True
