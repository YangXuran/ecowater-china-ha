"""Binary sensor platform for Ecowater China — salt alerts."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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


class SaltLowAlert(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that triggers when salt is low.

    必须是 CoordinatorEntity：否则 coordinator 每 5 分钟刷新时它收不到通知，
    状态和属性会停在第一次渲染那一刻（表现为剩余盐量恒为启动时的错值）。
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)   # 必须调用，否则不会注册 coordinator 监听
        self._attr_name = "怡口 低盐告警"
        self._attr_unique_id = "ecowater_low_salt_alert"
        self._attr_has_entity_name = True
        self.entity_id = "binary_sensor.ecowater_v80ecm_low_salt_alert"
        self._attr_device_class = "problem"
        self._attr_icon = "mdi:alert"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
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
