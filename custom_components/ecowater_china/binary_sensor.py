"""Binary sensor platform for Ecowater China — salt alerts."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

LOW_SALT_THRESHOLD = 3.0  # kg — alert when remaining salt drops below this


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([SaltLowAlert(coordinator)])


class SaltLowAlert(BinarySensorEntity):
    """Binary sensor that triggers when salt is low."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._attr_name = "怡口 低盐告警"
        self._attr_unique_id = "ecowater_salt_low"
        self._attr_device_class = "problem"
        self._attr_icon = "mdi:alert"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "怡口 V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def is_on(self) -> bool:
        """True when salt is low (alert active)."""
        remaining = self.coordinator.salt_remaining
        if remaining is None:
            return False
        return remaining < LOW_SALT_THRESHOLD

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "告警阈值": f"{LOW_SALT_THRESHOLD} kg",
            "剩余盐量": self.coordinator.salt_remaining,
            "说明": "剩余盐量低于阈值时触发，可配合自动化推送通知",
        }
