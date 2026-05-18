"""Sensor platform for Ecowater China."""
import logging
import aiohttp
import async_timeout
from datetime import datetime, timezone, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, API_BASE, CONF_CUSTOMER_ID, CONF_PHONE_NUMBER, CONF_OPENID

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

# Fully confirmed mappings from Charles + mini program cross-reference
DATA_FIELDS = {
    # --- 小程序直接显示 ---
    "data0A": ("即时流量", "L/min", "mdi:water"),
    "data25": ("再生次数", "次", "mdi:counter"),
    "data2C": ("可用软水量", "L", "mdi:water-check"),
    # --- 再生周期追踪 ---
    "data08": ("再生进行中", None, "mdi:sync"),
    "data24": ("再生阶段", None, "mdi:swap-horizontal"),
    "data22": ("本段用水", "L", "mdi:water-plus"),
    "data23": ("本段计数", None, "mdi:numeric"),
    # --- 累计/历史 ---
    "data28": ("累计用水量", "L", "mdi:water-pump"),
    # 以下字段为推测/未确认，暂时隐藏：
    # "data29": ("日均用水", "L", "mdi:water-percent"),
    # "data13": ("总用水量", "L", "mdi:counter"),
    # --- 设备状态 ---
    # "data00": ("设备状态", None, "mdi:information"),
    # "data0F": ("在线", None, "mdi:wifi"),
    # "data2B": ("盐量剩余天数", "天", "mdi:calendar-clock"),
    "data5A": ("进水硬度", None, "mdi:water-opacity"),
    # "data60": ("信号强度", "dBm", "mdi:signal"),
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = EcowaterDataCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for field, (name, unit, icon) in DATA_FIELDS.items():
        entities.append(EcowaterSensor(coordinator, field, name, unit, icon))

    async_add_entities(entities)


class EcowaterDataCoordinator(DataUpdateCoordinator):
    """Fetch data from Ecowater API."""

    def __init__(self, hass, config_entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.phone = config_entry.data.get(CONF_PHONE_NUMBER)
        self.customer_id = config_entry.data.get(CONF_CUSTOMER_ID)
        self.openid = config_entry.data.get(CONF_OPENID, "")
        self.device_data = {}
        self.daily_stats = {}
        self._auth_failures = 0

    async def _async_update_data(self):
        headers = {
            "ewtoken": f"customer{self.customer_id}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EcowaterHA/1.0",
        }

        async with aiohttp.ClientSession() as session:
            # Fetch device data
            try:
                async with async_timeout.timeout(10):
                    async with session.post(
                        f"{API_BASE}/api/applets/cusDev/cusDevListByMC3",
                        headers=headers,
                        data=f"customer={self.phone}&modelCode=",
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data") and len(data["data"]) > 0:
                                self.device_data = data["data"][0]
                                self._auth_failures = 0
                            elif data.get("resCode") == "30001":
                                # Auth expired — try to refresh via openid
                                self._auth_failures += 1
                                _LOGGER.warning(
                                    "Ecowater auth expired (failure #%d), trying refresh",
                                    self._auth_failures,
                                )
                                if self.openid and await self._try_refresh_customer_id(session):
                                    # Retry with new customer_id
                                    headers["ewtoken"] = f"customer{self.customer_id}"
                                    async with async_timeout.timeout(10):
                                        async with session.post(
                                            f"{API_BASE}/api/applets/cusDev/cusDevListByMC3",
                                            headers=headers,
                                            data=f"customer={self.phone}&modelCode=",
                                        ) as resp2:
                                            if resp2.status == 200:
                                                data2 = await resp2.json()
                                                if data2.get("data") and len(data2["data"]) > 0:
                                                    self.device_data = data2["data"][0]
                                                    _LOGGER.info("Ecowater auth refreshed successfully")
            except Exception as e:
                _LOGGER.error("Failed to fetch device data: %s", e)

            # Fetch daily stats
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

    async def _try_refresh_customer_id(self, session) -> bool:
        """Try to get a new customer_id using the stable openid."""
        try:
            async with async_timeout.timeout(10):
                async with session.post(
                    f"{API_BASE}/api/applets/customer/getCustomer",
                    data=f"openid={self.openid}",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        new_id = data.get("data")
                        if new_id and data.get("resCode") == "0":
                            self.customer_id = new_id
                            _LOGGER.info("Ecowater customer_id refreshed: %s...", new_id[:8])
                            return True
        except Exception as e:
            _LOGGER.error("Failed to refresh customer_id: %s", e)
        return False


class EcowaterSensor(CoordinatorEntity, SensorEntity):
    """Ecowater sensor."""

    def __init__(self, coordinator, field, name, unit, icon):
        super().__init__(coordinator)
        self._field = field
        self._attr_name = f"怡口 {name}"
        self._attr_unique_id = f"ecowater_{field}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "怡口 V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def native_value(self):
        if self.coordinator.device_data:
            val = self.coordinator.device_data.get(self._field)
            if val is not None:
                v = float(val) if isinstance(val, (int, float)) else val
                # data5A stores hardness × 0.1; display value = raw × 10
                if self._field == "data5A" and isinstance(v, (int, float)):
                    return v * 10
                return v
        return None

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self.coordinator.daily_stats:
            attrs["今日用水"] = self.coordinator.daily_stats.get("softTotal", 0)
            attrs["今日平均"] = self.coordinator.daily_stats.get("ownAverage", 0)
        return attrs
