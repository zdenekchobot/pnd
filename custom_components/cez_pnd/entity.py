"""Společný základ entit."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PndCoordinator


async def async_entity_names(hass: HomeAssistant, platform: str) -> dict[str, str]:
    """Přeložené názvy entit {klíč: název} v jazyce HA.

    Friendly name má být přesně „PND import“, „Data od:“ apod. HA (2026.10)
    předřazuje každé entitě se zařízením název zařízení („ELM123456 PND import“);
    bez prefixu je jen název uložený v registru entit, viz `async_added_to_hass`.
    """
    trans = await async_get_translations(hass, hass.config.language, "entity", {DOMAIN})
    prefix = f"component.{DOMAIN}.entity.{platform}."
    return {
        key[len(prefix) : -len(".name")]: value
        for key, value in trans.items()
        if key.startswith(prefix) and key.endswith(".name")
    }


class PndEntity(CoordinatorEntity[PndCoordinator]):
    """Entita zařízení ELM<číslo> (unique_id a entity_id = elm<číslo>_<klíč>)."""

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: PndCoordinator, platform: str, key: str, name: str
    ) -> None:
        super().__init__(coordinator)
        object_id = f"elm{coordinator.electrometer}_{key}"
        self._attr_unique_id = object_id
        self.entity_id = f"{platform}.{object_id}"
        self._attr_name = name
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, object_id.split("_", 1)[0])},
            name=f"ELM{coordinator.electrometer}",
            manufacturer="ČEZ Distribuce",
            model="Elektroměr (Portál naměřených dat)",
            serial_number=coordinator.electrometer,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://pnd.cezdistribuce.cz/cezpnd2/external/dashboard/view",
        )

    async def async_added_to_hass(self) -> None:
        """Krátký friendly name: název v registru, pokud ho uživatel nezměnil."""
        await super().async_added_to_hass()
        reg = er.async_get(self.hass)
        if (entry := reg.async_get(self.entity_id)) is not None and entry.name is None:
            reg.async_update_entity(self.entity_id, name=self._attr_name)
