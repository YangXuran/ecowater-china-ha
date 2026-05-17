"""Button platform for Ecowater China — trigger regeneration."""

import logging
import aiohttp
import async_timeout

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, API_BASE, CONF_CUSTOMER_ID, CONF_PHONE_NUMBER

_LOGGER = logging.getLogger(__name__)

BUTTONS: dict[str, tuple[str, str, str]] = {
    "regenerate": (
        "Trigger Regeneration",
        "mdi:restart",
        "Immediately start a full regeneration cycle (backwash → brine draw → rinse)",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = []
    for key, (name, icon, desc) in BUTTONS.items():
        entities.append(EcowaterButton(config_entry, key, name, icon, desc))
    async_add_entities(entities)


class EcowaterButton(ButtonEntity):
    """Button to trigger regeneration on Ecowater V80ECM."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        key: str,
        name: str,
        icon: str,
        description: str,
    ) -> None:
        self._config_entry = config_entry
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"ecowater_btn_{key}"
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, config_entry.data.get(CONF_PHONE_NUMBER, "")),
            },
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }
        self._attr_entity_description = description

    async def async_press(self) -> None:
        """Send the regeneration command."""
        phone = self._config_entry.data.get(CONF_PHONE_NUMBER)
        customer_id = self._config_entry.data.get(CONF_CUSTOMER_ID)

        # The MAC is fetched from the device data if available,
        # otherwise falls back to the default discovered during reverse-engineering.
        headers = {
            "ewtoken": f"customer{customer_id}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EcowaterHA/1.0",
        }

        async with aiohttp.ClientSession() as session:
            # 1. Fetch MAC from device list
            mac = None
            try:
                async with async_timeout.timeout(10):
                    async with session.post(
                        f"{API_BASE}/api/applets/cusDev/cusDevListByMC3",
                        headers=headers,
                        data=f"customer={phone}&modelCode=",
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = data.get("data", [])
                            if items:
                                mac = items[0].get("mac")
            except Exception:
                pass

            if not mac:
                _LOGGER.error("Cannot trigger regeneration: failed to get device MAC")
                return

            # 2. Send control command (02=1 means immediate regeneration)
            try:
                async with async_timeout.timeout(15):
                    async with session.post(
                        f"{API_BASE}/api/applets/device/control",
                        headers=headers,
                        data=f"mac={mac}&02=1",
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("resCode") == 0:
                                _LOGGER.info(
                                    "Regeneration triggered successfully for MAC %s",
                                    mac,
                                )
                            else:
                                _LOGGER.error(
                                    "Regeneration trigger failed: %s",
                                    data,
                                )
                        else:
                            _LOGGER.error(
                                "Regeneration trigger HTTP %s: %s",
                                resp.status,
                                await resp.text(),
                            )
            except Exception as e:
                _LOGGER.error("Failed to trigger regeneration: %s", e)
