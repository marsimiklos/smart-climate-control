import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN, 
    DEFAULT_COMFORT_TEMP, DEFAULT_ECO_TEMP, DEFAULT_BOOST_TEMP, DEFAULT_COOLING_TEMP,
    DEFAULT_HUMIDITY_THRESHOLD, DEFAULT_VENT_CYCLE_TIME, DEFAULT_VENT_DURATION,
    DEFAULT_VENT_FAN_SPEED
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate Control number entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    # Order: Boost, Comfort, Eco, Cooling (logical order)
    entities = [
        SmartClimateTemperatureNumber(coordinator, config_entry, "boost", "Boost Temperature", DEFAULT_BOOST_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "comfort", "Comfort Temperature", DEFAULT_COMFORT_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "eco", "Eco Temperature", DEFAULT_ECO_TEMP, 16.0, 25.0),
        SmartClimateTemperatureNumber(coordinator, config_entry, "cooling", "Cooling Temperature", DEFAULT_COOLING_TEMP, 18.0, 28.0),
        # Ventilation Numbers
        SmartClimateVentNumber(coordinator, config_entry, "humidity", "Humidity Threshold", 30, 90, "%"),
        SmartClimateVentNumber(coordinator, config_entry, "cycle_time", "Vent Cycle Time", 30, 300, "sec", step=5),
        SmartClimateVentNumber(coordinator, config_entry, "duration", "Vent Run Duration", 10, 240, "min", step=5),
        # ÚJ: Ventilátor sebesség
        SmartClimateVentNumber(coordinator, config_entry, "fan_speed", "Ventilation Speed", 10, 100, PERCENTAGE, step=1, mode="slider"),
    ]
    
    async_add_entities(entities)


class SmartClimateTemperatureNumber(NumberEntity):
    """Temperature number entity for Smart Climate Control."""

    _attr_has_entity_name = True
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, config_entry, temp_type, name, default, min_val, max_val):
        """Initialize the number entity."""
        self.coordinator = coordinator
        self._temp_type = temp_type
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_{temp_type}_temp"
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data.get("name", "Smart Climate Control"),
            "manufacturer": "Custom",
            "model": "Smart Climate Controller",
        }
        self._attr_icon = "mdi:thermometer" if temp_type != "cooling" else "mdi:snowflake-thermometer"

    @property
    def native_value(self):
        """Return the current value."""
        if self._temp_type == "comfort":
            return self.coordinator.comfort_temp
        elif self._temp_type == "eco":
            return self.coordinator.eco_temp
        elif self._temp_type == "boost":
            return self.coordinator.boost_temp
        elif self._temp_type == "cooling":
            return self.coordinator.cooling_temp
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if self._temp_type == "comfort":
            self.coordinator.comfort_temp = value
        elif self._temp_type == "eco":
            self.coordinator.eco_temp = value
        elif self._temp_type == "boost":
            self.coordinator.boost_temp = value
        elif self._temp_type == "cooling":
            self.coordinator.cooling_temp = value
        
        await self.coordinator.async_save_state()
        await self.coordinator.async_update()


class SmartClimateVentNumber(NumberEntity):
    """Ventilation parameter number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, config_entry, param_type, name, min_val, max_val, unit, step=1, mode=None):
        """Initialize."""
        self.coordinator = coordinator
        self._param_type = param_type
        self._attr_name = name
        self._attr_unique_id = f"{config_entry.entry_id}_vent_{param_type}"
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_unit_of_measurement = unit
        self._attr_native_step = step
        if mode:
            self._attr_mode = mode
            
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data.get("name", "Smart Climate Control"),
        }
        
        if param_type == "humidity":
             self._attr_icon = "mdi:water-percent"
             self._attr_mode = NumberMode.SLIDER
        elif param_type == "cycle_time":
             self._attr_icon = "mdi:timer-refresh"
        elif param_type == "fan_speed":
             self._attr_icon = "mdi:fan"
             self._attr_mode = NumberMode.SLIDER
        else:
             self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        if self._param_type == "humidity":
            return self.coordinator.humidity_threshold
        elif self._param_type == "cycle_time":
            return self.coordinator.vent_cycle_time
        elif self._param_type == "duration":
            return self.coordinator.vent_run_duration
        elif self._param_type == "fan_speed":
            return self.coordinator.vent_fan_speed
        return 0

    async def async_set_native_value(self, value: float) -> None:
        if self._param_type == "humidity":
            self.coordinator.humidity_threshold = value
        elif self._param_type == "cycle_time":
            self.coordinator.vent_cycle_time = value
        elif self._param_type == "duration":
            self.coordinator.vent_run_duration = value
        elif self._param_type == "fan_speed":
            self.coordinator.vent_fan_speed = int(value)
            # If running, update speed immediately
            if self.coordinator.vent_is_running:
                await self.coordinator._apply_fan_directions(self.coordinator.vent_current_phase)
        
        # Save state to persist changes
        await self.coordinator.async_save_state()