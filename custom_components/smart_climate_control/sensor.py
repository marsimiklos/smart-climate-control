import logging
import time
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([
        SmartClimateStatusSensor(coordinator, config_entry),
        SmartClimateModeSensor(coordinator, config_entry),
        SmartClimateTargetSensor(coordinator, config_entry),
        SmartClimateVentStatusSensor(coordinator, config_entry),
    ])

class SmartClimateBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, config_entry, sensor_type, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        self._attr_name = name
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}, "name": config_entry.data.get("name", "Smart Climate")}
    @property
    def available(self): return True

class SmartClimateStatusSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "status", "Status")
        self._attr_icon = "mdi:information-outline"
    @property
    def state(self): return self.coordinator.debug_text if self.coordinator.smart_control_enabled else "Smart control disabled"
    @property
    def extra_state_attributes(self):
        return {
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "current_action": self.coordinator.current_action,
            "current_hvac_mode": self.coordinator.current_hvac_mode,
            "active_logic_mode": self.coordinator.active_logic_mode,
            "window_open_active": self.coordinator.window_open_start is not None,
            "solar_sync_active": self.coordinator.solar_sync_enabled,
            "comfort_offset_applied": self.coordinator.comfort_offset_applied,
        }

class SmartClimateModeSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "mode", "Mode")
        self._attr_icon = "mdi:home-thermometer"
    @property
    def state(self):
        if not self.coordinator.smart_control_enabled: return "Disabled"
        if self.coordinator.force_eco_mode or self.coordinator.sleep_mode_active: return "Force Eco" if self.coordinator.force_eco_mode else "Sleep Eco"
        return "Force Comfort" if self.coordinator.override_mode else "Comfort"

class SmartClimateTargetSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "target_temp", "Target")
        self._attr_icon = "mdi:thermometer-plus"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def state(self): return self.coordinator.current_target_temp

class SmartClimateVentStatusSensor(SmartClimateBaseSensor):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_status", "Ventilation Status")
        self._attr_icon = "mdi:fan-clock"
    @property
    def state(self):
        if not self.coordinator.vent_enabled: return "Disabled"
        if self.coordinator.airout_is_running: return f"Airout ({self.coordinator.airout_direction})"
        return f"Running ({self.coordinator.vent_reason})" if self.coordinator.vent_is_running else "Idle"
    @property
    def extra_state_attributes(self):
        return {
            "is_running": self.coordinator.vent_is_running,
            "airout_is_running": self.coordinator.airout_is_running,
            "reason": self.coordinator.vent_reason,
            "current_phase_id": self.coordinator.vent_current_phase,
        }