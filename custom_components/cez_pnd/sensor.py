"""Senzory: import, export, úplnost dat a konec období."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PndConfigEntry
from .coordinator import PndCoordinator, PndData
from .entity import DATE_ICON, PndEntity, async_entity_names


@dataclass(frozen=True, kw_only=True)
class PndSensorDescription(SensorEntityDescription):
    """Popis senzoru s funkcí pro výběr hodnoty."""

    value_fn: Callable[[PndData], float | datetime | None]


SENSORS: tuple[PndSensorDescription, ...] = (
    PndSensorDescription(
        key="import",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d: d.import_kwh,
    ),
    PndSensorDescription(
        key="import_status",
        icon="mdi:progress-pencil",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=3,
        value_fn=lambda d: d.import_status,
    ),
    PndSensorDescription(
        key="export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda d: d.export_kwh,
    ),
    PndSensorDescription(
        key="export_status",
        icon="mdi:progress-pencil",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=3,
        value_fn=lambda d: d.export_status,
    ),
    PndSensorDescription(
        key="end_date",
        icon=DATE_ICON,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.end_date,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PndConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    names = await async_entity_names(hass, "sensor")
    async_add_entities(
        PndSensor(coordinator, desc, names.get(desc.key, desc.key)) for desc in SENSORS
    )


class PndSensor(PndEntity, SensorEntity):
    """Hodnota z tabulky statistik."""

    entity_description: PndSensorDescription

    def __init__(
        self, coordinator: PndCoordinator, description: PndSensorDescription, name: str
    ) -> None:
        super().__init__(coordinator, "sensor", description.key, name)
        self.entity_description = description
        if description.state_class == SensorStateClass.TOTAL:
            self._attr_last_reset = coordinator.date_from.replace(
                tzinfo=dt_util.get_default_time_zone()
            )

    @property
    def native_value(self) -> float | datetime | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
