import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, DEFAULT_COMFORT_TEMP, DEFAULT_ECO_TEMP, DEFAULT_BOOST_TEMP, DEFAULT_COOLING_TEMP, DEFAULT_COOLING_ECO_TEMP

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([
        SmartClimateTemperatureNumber(coordinator, config_entry, "boost", "Boost Temperature", DEFAULT_BOOST_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "comfort", "Comfort Temperature", DEFAULT_COMFORT_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "eco", "Eco Temperature", DEFAULT_ECO_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "cooling", "Cooling Temperature", DEFAULT_COOLING_TEMP, 18.0, 28.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "cooling_eco", "Cooling Eco Temperature", DEFAULT_COOLING_ECO_TEMP, 20.0, 30.0),
        SmartClimateVentNumber(coordinator, config_entry, "humidity", "Humidity Threshold", 30, 90, "%"),
        SmartClimateVentNumber(coordinator, config_entry, "cycle_time", "Vent Cycle Time", 30, 300, "sec", step=5),
        SmartClimateVentNumber(coordinator, config_entry, "duration", "Vent Run Duration", 10, 240, "min", step=5),
        SmartClimateVentNumber(coordinator, config_entry, "fan_speed", "Ventilation Speed", 10, 100, PERCENTAGE, step=1, mode="slider"),
        SmartClimateVentNumber(coordinator, config_entry, "airout_duration", "Airout Max Duration", 5, 120, "min", step=5),
        SmartClimateVentNumber(coordinator, config_entry, "free_cooling_max_duration", "Free Cooling Max Duration", 10, 180, "min", step=10),
        SmartClimateVentNumber(coordinator, config_entry, "free_cooling_cooldown", "Free Cooling Cooldown", 1, 12, "hours", step=1),
        SmartClimateSolarNumber(coordinator, config_entry, "solar_threshold", "Solar Threshold (W)", 0, 10000, "W", step=100),
        SmartClimateSolarNumber(coordinator, config_entry, "solar_offset", "Solar Offset (°C)", 0.0, 5.0, "°C", step=0.5, mode="slider"),
        SmartClimateSolarNumber(coordinator, config_entry, "solar_delay_minutes", "Solar Drop Delay (min)", 0.0, 60.0, "min", step=1.0, mode="slider"),
    ])

class SmartClimateTemperatureNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER
    def __init__(self, coordinator, config_entry, temp_type, name, default, min_val, max_val):
        self.coordinator = coordinator
        self._temp_type = temp_type
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{temp_type}_temp"
        self._attr_native_min_value, self._attr_native_max_value = min_val, max_val
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}, "name": config_entry.data.get("name", "Smart Climate")}
        self._attr_icon = "mdi:snowflake-thermometer" if "cooling" in temp_type else "mdi:thermometer"

    @property
    def native_value(self):
        return getattr(self.coordinator, f"{self._temp_type}_temp")

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.coordinator, f"{self._temp_type}_temp", value)
        await self.coordinator.async_save_state()
        await self.coordinator.async_update()

class SmartClimateVentNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    def __init__(self, coordinator, config_entry, param_type, name, min_val, max_val, unit, step=1, mode=None):
        self.coordinator = coordinator
        self._param_type = param_type
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_vent_{param_type}"
        self._attr_native_min_value, self._attr_native_max_value = min_val, max_val
        self._attr_native_unit_of_measurement, self._attr_native_step = unit, step
        if mode: self._attr_mode = mode
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}, "name": config_entry.data.get("name", "Smart Climate")}
        
        icons = {"humidity": "mdi:water-percent", "cycle_time": "mdi:timer-refresh", "fan_speed": "mdi:fan", "airout_duration": "mdi:timer-sand", "free_cooling_max_duration": "mdi:timer-sand", "free_cooling_cooldown": "mdi:snowflake-clock"}
        self._attr_icon = icons.get(param_type, "mdi:timer-outline")
        if param_type in ["humidity", "fan_speed"]: self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self):
        maps = {"humidity": "humidity_threshold", "cycle_time": "vent_cycle_time", "duration": "vent_run_duration", "fan_speed": "vent_fan_speed"}
        return getattr(self.coordinator, maps.get(self._param_type, self._param_type))

    async def async_set_native_value(self, value: float) -> None:
        maps = {"humidity": "humidity_threshold", "cycle_time": "vent_cycle_time", "duration": "vent_run_duration", "fan_speed": "vent_fan_speed"}
        attr_name = maps.get(self._param_type, self._param_type)
        setattr(self.coordinator, attr_name, int(value) if self._param_type == "fan_speed" else value)
        if self._param_type == "fan_speed":
            if self.coordinator.vent_is_running: await self.coordinator._apply_fan_directions(self.coordinator.vent_current_phase)
            if self.coordinator.airout_is_running: await self.coordinator._apply_airout_direction()
        await self.coordinator.async_save_state()

class SmartClimateSolarNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    def __init__(self, coordinator, config_entry, param_type, name, min_val, max_val, unit, step=1, mode=None):
        self.coordinator = coordinator
        self._param_type = param_type
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{param_type}"
        self._attr_native_min_value, self._attr_native_max_value = min_val, max_val
        self._attr_native_unit_of_measurement, self._attr_native_step = unit, step
        if mode: self._attr_mode = mode
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}, "name": config_entry.data.get("name", "Smart Climate")}
        
        if param_type == "solar_threshold":
            self._attr_icon = "mdi:white-balance-sunny"
        elif param_type == "solar_delay_minutes":
            self._attr_icon = "mdi:timer-sand"
        else:
            self._attr_icon = "mdi:thermometer-chevron-up"

    @property
    def native_value(self): return getattr(self.coordinator, self._param_type)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.coordinator, self._param_type, value)
        await self.coordinator.async_save_state()
        await self.coordinator.async_update()