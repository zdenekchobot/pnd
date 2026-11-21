"""Coordinator pro ČEZ PND."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import PndAuthError, PndClient, PndError, parse_pnd_datetime, parse_stats
from .const import (
    ASSEMBLY,
    COL_COMPLETENESS,
    COL_TOTAL_INTERVAL,
    CONF_DATE_FROM,
    CONF_ELECTROMETER,
    CONF_SCAN_INTERVAL,
    DATE_FMT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Kolik chyb přihlášení za sebou se toleruje, než se nabídne nové přihlášení.
# Portál občas vrací chyby i při správném hesle, polling proto běží dál.
AUTH_FAILURES_BEFORE_REAUTH = 3

# Po chybě se další pokus zkusí dřív než za běžný interval (ten může být až 24 h).
RETRY_INTERVAL = timedelta(minutes=5)


def entry_options(entry: ConfigEntry) -> dict[str, Any]:
    """Data + options (options mají přednost)."""
    return {**entry.data, **entry.options}


def date_from_of(entry: ConfigEntry) -> datetime:
    """Datum „od“ jako naivní místní čas."""
    return datetime.strptime(entry_options(entry)[CONF_DATE_FROM], DATE_FMT)


@dataclass
class PndData:
    """Vyčtené hodnoty."""

    import_kwh: float | None = None
    import_status: float | None = None
    export_kwh: float | None = None
    export_status: float | None = None
    end_date: datetime | None = None


def extract(parsed: dict[str, dict[str, Any]]) -> PndData:
    """Z rozparsované tabulky vybere hodnoty řad +A a -A."""
    out = PndData()
    for series, sdata in parsed.items():
        values = sdata["values"]
        total = (values.get(COL_TOTAL_INTERVAL) or {}).get("value")
        status = (values.get(COL_COMPLETENESS) or {}).get("value")
        if series.startswith("+A"):
            out.import_kwh, out.import_status = total, status
        elif series.startswith("-A"):
            out.export_kwh, out.export_status = total, status
        else:
            continue
        if out.end_date is None and sdata.get("end"):
            end = parse_pnd_datetime(sdata["end"])
            if end is not None:
                out.end_date = end.replace(tzinfo=dt_util.get_default_time_zone())
    return out


class PndCoordinator(DataUpdateCoordinator[PndData]):
    """Pravidelné stahování tabulky za období „od“ → teď."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PndClient) -> None:
        opts = entry_options(entry)
        self._normal_interval = timedelta(
            minutes=int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._normal_interval,
        )
        self.client = client
        self.electrometer = str(opts[CONF_ELECTROMETER])
        self.date_from = date_from_of(entry)
        self._auth_failures = 0

    async def _async_update_data(self) -> PndData:
        try:
            data = await self._fetch()
        except UpdateFailed:
            self.update_interval = min(RETRY_INTERVAL, self._normal_interval)
            raise
        self.update_interval = self._normal_interval
        return data

    async def _fetch(self) -> PndData:
        now = dt_util.now().replace(tzinfo=None, second=0, microsecond=0)
        try:
            raw = await self.client.get_stats(
                ASSEMBLY, self.date_from, now, electrometer=self.electrometer
            )
        except PndAuthError as err:
            self._auth_failures += 1
            # Při startu hned, jinak až po opakovaných chybách. Ne ConfigEntryAuthFailed:
            # to by další stahování zastavilo; HA při startu nastavení opakuje.
            if self.data is None or self._auth_failures >= AUTH_FAILURES_BEFORE_REAUTH:
                self.config_entry.async_start_reauth(self.hass)
            raise UpdateFailed(str(err)) from err
        except PndError as err:
            raise UpdateFailed(str(err)) from err
        self._auth_failures = 0
        return extract(parse_stats(raw))
