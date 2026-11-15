"""Coordinator pro ČEZ PND."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
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
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )
        self.client = client
        self.electrometer = str(opts[CONF_ELECTROMETER])
        self.date_from = date_from_of(entry)

    async def _async_update_data(self) -> PndData:
        now = dt_util.now().replace(tzinfo=None, second=0, microsecond=0)
        try:
            raw = await self.client.get_stats(
                ASSEMBLY, self.date_from, now, electrometer=self.electrometer
            )
        except PndAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PndError as err:
            raise UpdateFailed(str(err)) from err
        return extract(parse_stats(raw))
