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
    "data26": ("Flow Rate", "L/min", "mdi:water"),
    "data25": ("Regen Count", "times", "mdi:counter"),
    "data2C": ("Soft Water Avail", "L", "mdi:water-check"),
    # --- 再生周期追踪 ---
    "data08": ("Regen Active", None, "mdi:sync"),
    "data24": ("Regen Stage", None, "mdi:swap-horizontal"),
    "data22": ("Cycle Water", "L", "mdi:water-plus"),
    "data23": ("Cycle Count", None, "mdi:numeric"),
    # --- 累计/历史 ---
    "data28": ("Total Water", "L", "mdi:water-pump"),
    # 以下字段为推测/未确认，暂时隐藏：
    # "data29": ("日均用水", "L", "mdi:water-percent"),
    # "data13": ("总用水量", "L", "mdi:counter"),
    # --- 设备状态 ---
    # "data00": ("设备状态", None, "mdi:information"),
    # "data0F": ("在线", None, "mdi:wifi"),
    # "data2B": ("盐量剩余天数", "天", "mdi:calendar-clock"),
    "data5A": ("Hardness", None, "mdi:water-opacity"),
    # "data60": ("信号强度", "dBm", "mdi:signal"),
}

SALT_PER_REGEN_DEFAULT = 1.76  # kg — 11L resin × 160g/L

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for field, (name, unit, icon) in DATA_FIELDS.items():
        entities.append(EcowaterSensor(coordinator, field, name, unit, icon))

    # Salt tracking sensors
    entities.append(SaltRemainingSensor(coordinator))
    entities.append(SaltConsumptionSensor(coordinator))

    async_add_entities(entities)

class EcowaterDataCoordinator(DataUpdateCoordinator):
    """Fetch data from Ecowater API."""

    def __init__(self, hass, config_entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._config_entry = config_entry
        self.phone = config_entry.data.get(CONF_PHONE_NUMBER)
        self.customer_id = config_entry.data.get(CONF_CUSTOMER_ID)
        self.openid = config_entry.data.get(CONF_OPENID, "")
        self.device_data = {}
        self.daily_stats = {}
        self._auth_failures = 0

        # Salt tracking state (persisted via config entry options)
        opts = dict(config_entry.options)
        self.salt_last_refill_data25 = opts.get("salt_last_refill_data25", 58)
        self.salt_per_regen = opts.get("salt_per_regen", SALT_PER_REGEN_DEFAULT)
        self.salt_refill_amount = opts.get("salt_refill_amount", 20.0)

    async def _async_update_data(self):
        headers = {
            "ewtoken": f"customer{self.customer_id}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "EcowaterHA/1.0",
        }

        async with aiohttp.ClientSession() as session:
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
                                self._auth_failures += 1
                                _LOGGER.warning(
                                    "Ecowater auth expired (failure #%d), trying refresh",
                                    self._auth_failures,
                                )
                                if self.openid and await self._try_refresh_customer_id(session):
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
                                                    _LOGGER.info("Ecowater auth refreshed")
            except Exception as e:
                _LOGGER.error("Failed to fetch device data: %s", e)

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

    # ---- Salt tracking ----

    @property
    def salt_remaining(self) -> float | None:
        """Estimated remaining salt in kg."""
        if self.salt_last_refill_data25 is None:
            return None
        try:
            data25 = int(self.device_data.get("data25", 0))
        except (ValueError, TypeError):
            return None
        used = self.salt_per_regen * (data25 - self.salt_last_refill_data25)
        return round(max(0.0, self.salt_refill_amount - used), 1)

    async def mark_salt_refill(self) -> None:
        """Mark a salt refill. Auto-calibrates salt_per_regen."""
        try:
            data25 = int(self.device_data.get("data25", 0))
        except (ValueError, TypeError):
            _LOGGER.warning("Cannot mark refill: data25 unavailable")
            return

        # Auto-calibrate on consecutive refills
        if (
            self.salt_last_refill_data25 is not None
            and data25 > self.salt_last_refill_data25
        ):
            regens = data25 - self.salt_last_refill_data25
            if regens > 0:
                calibrated = self.salt_refill_amount / regens
                if 0.5 <= calibrated <= 8.0:  # sanity check
                    self.salt_per_regen = round(calibrated, 3)
                    _LOGGER.info(
                        "Salt calibrated: %.3f kg/regen (%d regenerations for %.0f kg)",
                        self.salt_per_regen, regens, self.salt_refill_amount,
                    )

        self.salt_last_refill_data25 = data25
        await self._save_salt_state()
        self.async_update_listeners()

    async def _save_salt_state(self) -> None:
        """Persist salt calibration data to config entry options."""
        options = dict(self._config_entry.options)
        options["salt_last_refill_data25"] = self.salt_last_refill_data25
        options["salt_per_regen"] = self.salt_per_regen
        options["salt_refill_amount"] = self.salt_refill_amount
        self.hass.config_entries.async_update_entry(
            self._config_entry, options=options
        )

_FIELD_CN = {
    "data26": "怡口 即时流量",
    "data25": "怡口 再生次数",
    "data2C": "怡口 可用软水量",
    "data08": "怡口 再生进行中",
    "data24": "怡口 再生阶段",
    "data22": "怡口 本段用水",
    "data23": "怡口 本段计数",
    "data28": "怡口 累计用水量",
    "data5A": "怡口 进水硬度"
}

class EcowaterSensor(CoordinatorEntity, SensorEntity):
    """Ecowater sensor."""

    def __init__(self, coordinator, field, name, unit, icon):
        super().__init__(coordinator)
        self._field = field
        self._attr_has_entity_name = True
        en_slug = name.lower().replace(' ', '_')
        self._attr_unique_id = f"ecowater_{en_slug}"
        self._attr_name = _FIELD_CN.get(self._field, name)
        self.entity_id = f"sensor.ecowater_v80ecm_{en_slug}"
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
                if self._field == "data26" and isinstance(v, (int, float)):
                    return v / 10
                elif self._field == "data5A" and isinstance(v, (int, float)):
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

class SaltRemainingSensor(CoordinatorEntity, SensorEntity):
    """Estimated remaining salt in brine tank."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "怡口 剩余盐量"
        self.entity_id = "sensor.ecowater_v80ecm_salt_remaining"
        self._attr_unique_id = "ecowater_salt_remaining"
        self._attr_native_unit_of_measurement = "kg"
        self._attr_icon = "mdi:grain"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def native_value(self):
        return self.coordinator.salt_remaining

    @property
    def extra_state_attributes(self):
        return {
            "上次加盐时再生次数": self.coordinator.salt_last_refill_data25,
            "每次再生耗盐": f"{self.coordinator.salt_per_regen} kg",
            "加盐量": f"{self.coordinator.salt_refill_amount} kg",
        }

class SaltConsumptionSensor(CoordinatorEntity, SensorEntity):
    """Calibrated salt consumption per regeneration."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "怡口 每次再生耗盐"
        self.entity_id = "sensor.ecowater_v80ecm_salt_per_regen"
        self._attr_unique_id = "ecowater_salt_per_regen"
        self._attr_native_unit_of_measurement = "kg"
        self._attr_icon = "mdi:chart-bell-curve"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.phone)},
            "name": "Ecowater V80ECM",
            "manufacturer": "Ecowater",
            "model": "V80ECM",
        }

    @property
    def native_value(self):
        return self.coordinator.salt_per_regen

    @property
    def extra_state_attributes(self):
        return {
            "说明": "自动校准值 — 每次标记加盐时根据实际消耗更新",
            "理论值": f"{SALT_PER_REGEN_DEFAULT} kg (11L树脂×160g/L)",
        }
