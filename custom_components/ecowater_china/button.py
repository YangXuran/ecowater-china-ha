"""Button platform for Ecowater China — trigger regeneration."""
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
    customer_id = config_entry.data["customer_id"]
    mac = config_entry.data.get("device_mac", "YOUR_DEVICE_MAC")
    async_add_entities([EcowaterRegenButton(customer_id, mac)])


class EcowaterRegenButton(ButtonEntity):
    """Button to trigger immediate regeneration."""

    def __init__(self, customer_id: str, mac: str) -> None:
        self._customer_id = customer_id
        self._mac = mac
        self._attr_name = "怡口 立即再生"
        self._attr_unique_id = "ecowater_regen"
        self._attr_icon = "mdi:refresh-auto"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, customer_id)},
            "name": "怡口 V80ECM",
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
