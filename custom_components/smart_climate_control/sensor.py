from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .entity import SmartClimateEntity

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    sensors = [
        SmartClimateStatusSensor(coordinator, config_entry),
        SmartClimateModeSensor(coordinator, config_entry),
        SmartClimateTargetSensor(coordinator, config_entry),
        SmartClimateLogicModeSensor(coordinator, config_entry),
    ]
    
    if getattr(coordinator, "has_ventilation", True):
        sensors.append(SmartClimateVentStatusSensor(coordinator, config_entry))
        
    async_add_entities(sensors)

class SmartClimateBaseSensor(SmartClimateEntity, SensorEntity):
    def __init__(self, coordinator, config_entry, sensor_type, name):
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        self._attr_name = name

class SmartClimateStatusSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "status", "Status")
        self._attr_icon = "mdi:information-outline"
        
    @property
    def native_value(self):
        # A state can be at most 255 characters long
        text = self.coordinator.debug_text if self.coordinator.smart_control_enabled else "Smart control disabled"
        return text[:255]
        
    @property
    def extra_state_attributes(self):
        return {
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "current_action": self.coordinator.current_action,
            "current_hvac_mode": self.coordinator.current_hvac_mode,
            "active_logic_mode": self.coordinator.active_logic_mode,
            "window_open_active": self.coordinator.window_open_start is not None,
            "solar_sync_active": self.coordinator.solar_sync_enabled,
            "solar_state": self.coordinator._solar_state,
            "away": self.coordinator.is_away,
            "sleep": self.coordinator.sleep_mode_active,
            "open_windows": self.coordinator.open_window_details,
            "comfort_offset_applied": self.coordinator.comfort_offset_applied,
        }

class SmartClimateModeSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "mode", "Mode")
        self._attr_icon = "mdi:home-thermometer"
        
    @property
    def native_value(self):
        coordinator = self.coordinator
        if not coordinator.smart_control_enabled:
            return "Disabled"
        if coordinator.boost_mode:
            return "Boost"
        if coordinator.override_mode or coordinator.force_comfort_mode:
            return "Force Comfort"
        if coordinator.force_eco_mode:
            return "Force Eco"
        if coordinator.sleep_mode_active:
            return "Sleep Eco"
        if coordinator.is_away:
            return "Away Eco"
        return "Comfort"

class SmartClimateTargetSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "target_temp", "Target")
        self._attr_icon = "mdi:thermometer-plus"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        
    @property
    def native_value(self):
        target = self.coordinator.current_target_temp
        return round(target, 1) if target is not None else None

class SmartClimateVentStatusSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_status", "Ventilation Status")
        self._attr_icon = "mdi:fan-clock"
        
    @property
    def native_value(self):
        if not self.coordinator.vent_enabled: 
            return "Disabled"
        if self.coordinator.airout_is_running: 
            return f"Airout ({self.coordinator.airout_direction})"
        return f"Running ({self.coordinator.vent_reason})" if self.coordinator.vent_is_running else "Idle"
        
    @property
    def extra_state_attributes(self):
        return {
            "is_running": self.coordinator.vent_is_running,
            "airout_is_running": self.coordinator.airout_is_running,
            "reason": self.coordinator.vent_reason,
            "current_phase_id": self.coordinator.vent_current_phase,
        }

class SmartClimateLogicModeSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "logic_mode", "Active Logic")
        self._attr_icon = "mdi:thermostat-box"
        
    @property
    def native_value(self):
        if not self.coordinator.smart_control_enabled: return "Off"
        return "Cooling" if self.coordinator.active_logic_mode == "cool" else "Heating"