"""Sensor platform for Ecowater China.

Reverse-engineered from the 怡口智控 WeChat mini-program API
(iot2.chinaecowater.com) using Charles Proxy.

Device: V80ECM (modelCode: 000400)
9 sensors covering flow, volume, regeneration status, and hardness.
Plus 1 button for triggering regeneration.
"""
import logging
import aiohttp
import async_timeout
from datetime import datetime, timezone, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, API_BASE, CONF_CUSTOMER_ID, CONF_PHONE_NUMBER

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

# ── Confirmed data fields ──────────────────────────────────
# Mapped via Charles Proxy + WeChat mini-program screenshot cross-reference.
# Unconfirmed (inference-only) fields are commented out — see README.md.
# See README.md for full field documentation.
DATA_FIELDS: dict[str, tuple[str, str | None, str]] = {
    # --- Directly visible in mini-program (confirmed) ---
    "data0A": ("Instant Flow Rate", "L/min", "mdi:water"),
    "data25": ("Regeneration Count", "times", "mdi:counter"),
    "data2C": ("Available Soft Water", "L", "mdi:water-check"),
    # --- Regeneration tracking (confirmed via full-cycle capture) ---
    "data08": ("Regeneration Active", None, "mdi:sync"),
    "data24": ("Regeneration Stage", None, "mdi:swap-horizontal"),
    "data22": ("Segment Water Use", "L", "mdi:water-plus"),
    "data23": ("Segment Count", None, "mdi:numeric"),
    # --- Cumulative (confirmed via continuous tracking) ---
    "data28": ("Cumulative Water Use", "L", "mdi:water-pump"),
    # --- Settings (confirmed via config comparison) ---
    "data5A": ("Inlet Hardness", None, "mdi:water-opacity"),

    # ═══ Unconfirmed / inference-only fields (commented out) ═══
    # "data29": ("Daily Avg Water Use", "L", "mdi:water-percent"),
    # "data13": ("Total Water Use", "L", "mdi:counter"),
    # "data00": ("Device Status", None, "mdi:information"),
    # "data0F": ("Online", None, "mdi:wifi"),
    # "data2B": ("Salt Remaining Days", "days", "mdi:calendar-clock"),
    # "data60": ("Signal Strength", "dBm", "mdi:signal"),
}


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = EcowaterDataCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for field, (name, unit, icon) in DATA_FIELDS.items():
        entities.append(EcowaterSensor(coordinator, field, name, unit, icon))

    async_add_entities(entities)


class EcowaterDataCoordinator(DataUpdateCoordinator):
    """Fetch data from Ecowater China API."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.phone = config_entry.data.get(CONF_PHONE_NUMBER)
        self.customer_id = config_entry.data.get(CONF_CUSTOMER_ID)
        self.device_data: dict = {}
        self.daily_stats: dict = {}

    async def _async_update_data(self) -> dict:
        headers = {
            "ewtoken": f"customer{self.customer_id}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EcowaterHA/1.0",
        }

        async with aiohttp.ClientSession() as session:
            # ── Device state ──
            try:
                async with async_timeout.timeout(10):
                    async with session.post(
                        f"{API_BASE}/api/applets/cusDev/cusDevListByMC3",
                        headers=headers,
                        data=f"customer={self.phone}&modelCode=",
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = data.get("data", [])
                            if items:
                                self.device_data = items[0]
            except Exception as e:
                _LOGGER.error("Failed to fetch device data: %s", e)

            # ── Daily statistics ──
            today = datetime.now().strftime("%Y-%m-%d")
            try:
                async with async_timeout.timeout(10):
                    async with session.post(
                        f"{API_BASE}/api/app/statiscal/observe/daily",
                        headers=headers,
                        data=f"phone={self.phone}&modelCode=&currentDay={today}",
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self.daily_stats = data.get("data", {})
            except Exception as e:
                _LOGGER.error("Failed to fetch daily stats: %s", e)

        return self.device_data


class EcowaterSensor(CoordinatorEntity, SensorEntity):
    """Ecowater sensor entity."""

    def __init__(
        self, coordinator, field: str, name: str, unit: str | None, icon: str
    ) -> None:
        super().__init__(coordinator)
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"ecowater_{field}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def native_value(self):
        if self.coordinator.device_data:
            val = self.coordinator.device_data.get(self._field)
            if val is not None:
                v = float(val) if isinstance(val, (int, float)) else val
                # data5A stores hardness x0.1; display value = raw x10
                if self._field == "data5A" and isinstance(v, (int, float)):
                    return v * 10
                return v
        return None

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self.coordinator.daily_stats:
            attrs["daily_total"] = self.coordinator.daily_stats.get("softTotal", 0)
            attrs["daily_avg"] = self.coordinator.daily_stats.get("ownAverage", 0)
        return attrs
