"""Number platform for Ecowater China — salt refill amount."""
import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([EcowaterRefillAmount(coordinator)])


class EcowaterRefillAmount(NumberEntity):
    """Number input for salt refill amount (kg)."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._attr_name = "怡口 加盐量"
        self._attr_unique_id = "ecowater_salt_refill_amt"
        self._attr_has_entity_name = True
        self.entity_id = "number.ecowater_v80ecm_salt_refill_amt"
        self._attr_native_min_value = 1.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0
        self._attr_native_unit_of_measurement = "kg"
        self._attr_icon = "mdi:scale"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def native_value(self) -> float:
        return self.coordinator.salt_refill_amount

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.salt_refill_amount = float(value)
        await self.coordinator._save_salt_state()
        self.async_write_ha_state()
