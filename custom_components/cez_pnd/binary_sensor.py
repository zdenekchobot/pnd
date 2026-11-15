"""Binární senzor „PND status“ – problém se stahováním dat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PndConfigEntry
from .coordinator import PndCoordinator
from .entity import PndEntity, async_entity_names

KEY = "status"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PndConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    names = await async_entity_names(hass, "binary_sensor")
    async_add_entities([PndStatus(entry.runtime_data, names.get(KEY, KEY))])


class PndStatus(PndEntity, BinarySensorEntity):
    """Zapnuto = poslední stažení dat selhalo (přihlášení, síť, chyba portálu)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: PndCoordinator, name: str) -> None:
        super().__init__(coordinator, "binary_sensor", KEY, name)

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return not self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        err = self.coordinator.last_exception
        return {"error": str(err) if err and not self.coordinator.last_update_success else None}
