"""Ecowater China integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button", "number", "binary_sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # Create the shared coordinator once, before platforms load
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    from .sensor import EcowaterDataCoordinator
    coordinator = EcowaterDataCoordinator(hass, entry)
    # 必须在这里首次拉取，再交给平台。
    # 若放在 sensor.py 里，平台是并发加载的，binary_sensor 可能先建好，
    # 此时 coordinator.device_data 还是空的，data25 读成 0，
    # 剩余盐量会被算成 20 - 1.6 × (0 - 88) = +160.8 这种荒谬值。
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
