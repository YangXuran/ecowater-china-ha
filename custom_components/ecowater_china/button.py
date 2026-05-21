"""Button platform for Ecowater China — trigger regeneration & salt refill."""
import logging
import aiohttp
import async_timeout

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, API_BASE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    customer_id = config_entry.data["customer_id"]
    mac = config_entry.data.get("device_mac", "YOUR_DEVICE_MAC")

    async_add_entities([
        EcowaterRegenButton(coordinator, customer_id, mac),
        EcowaterMarkSaltRefillButton(coordinator),
    ])


class EcowaterRegenButton(ButtonEntity):
    """Button to trigger immediate regeneration."""

    def __init__(self, coordinator, customer_id: str, mac: str) -> None:
        self.coordinator = coordinator
        self._customer_id = customer_id
        self._mac = mac
        self._attr_name = "怡口 立即再生"
        self._attr_unique_id = "ecowater_regen"
        self._attr_icon = "mdi:refresh-auto"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    async def async_press(self) -> None:
        headers = {
            "ewtoken": f"customer{self._customer_id}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EcowaterHA/1.0",
        }
        body = f"mac={self._mac}&02=1"

        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(10):
                async with session.post(
                    f"{API_BASE}/api/applets/device/control",
                    headers=headers,
                    data=body,
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Regeneration triggered successfully")
                    else:
                        text = await resp.text()
                        _LOGGER.error(
                            "Regeneration trigger failed (%d): %s", resp.status, text
                        )


class EcowaterMarkSaltRefillButton(ButtonEntity):
    """Button to mark a salt refill — records current data25 as baseline
    and auto-calibrates salt_per_regen from previous cycle."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._attr_name = "怡口 标记加盐"
        self._attr_unique_id = "ecowater_mark_salt_refill"
        self._attr_icon = "mdi:plus-circle"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    async def async_press(self) -> None:
        await self.coordinator.mark_salt_refill()
