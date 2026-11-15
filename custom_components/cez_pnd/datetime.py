"""Entita „Data od:“ – upravitelný začátek období."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PndConfigEntry
from .const import CONF_DATE_FROM, DATE_FMT
from .coordinator import PndCoordinator
from .entity import PndEntity, async_entity_names

KEY = "start_date"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PndConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    names = await async_entity_names(hass, "datetime")
    async_add_entities([PndStartDate(entry.runtime_data, entry, names.get(KEY, KEY))])


class PndStartDate(PndEntity, DateTimeEntity):
    """Začátek období; změna se uloží do nastavení a integrace se znovu načte."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PndCoordinator, entry: PndConfigEntry, name: str) -> None:
        super().__init__(coordinator, "datetime", KEY, name)
        self._entry = entry

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime:
        return self.coordinator.date_from.replace(tzinfo=dt_util.get_default_time_zone())

    async def async_set_value(self, value: datetime) -> None:
        local = dt_util.as_local(value).replace(tzinfo=None, second=0, microsecond=0)
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_DATE_FROM: local.strftime(DATE_FMT)},
        )
