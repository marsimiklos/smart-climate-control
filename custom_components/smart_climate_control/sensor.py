import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate Control sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    entities = [
        SmartClimateStatusSensor(coordinator, config_entry),
        SmartClimateModeSensor(coordinator, config_entry),
        SmartClimateTargetSensor(coordinator, config_entry),
        SmartClimateVentStatusSensor(coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class SmartClimateBaseSensor(SensorEntity):
    """Base sensor for Smart Climate Control."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry, sensor_type, name):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data.get("name", "Smart Climate Control"),
            "manufacturer": "Custom",
            "model": "Smart Climate Controller",
        }

    @property
    def available(self):
        """Sensors are always available."""
        return True


class SmartClimateStatusSensor(SmartClimateBaseSensor):
    """Status sensor showing current smart control logic and detailed diagnostics."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "status", "Status")
        self._attr_icon = "mdi:information-outline"

    @property
    def state(self):
        if not self.coordinator.smart_control_enabled:
            return "Smart control disabled"
        return self.coordinator.debug_text

    @property
    def extra_state_attributes(self):
        """Return extensive details about the current state."""
        heat_pump_state = self.coordinator.current_heat_pump_state
        is_temperating = "Temperating" in self.coordinator.debug_text
        
        # Calculate window timer
        window_timer_min = 0
        if self.coordinator.window_open_start is not None:
            import time
            window_timer_min = round((time.time() - self.coordinator.window_open_start) / 60, 1)

        return {
            # --- General System State ---
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "current_action": self.coordinator.current_action,
            "current_hvac_mode": self.coordinator.current_hvac_mode,
            
            # --- Heat Pump Details ---
            "controlled_entity": self.coordinator.heat_pump_entity_id,
            "heat_pump_mode": heat_pump_state.get("hvac_mode"),
            "heat_pump_action": heat_pump_state.get("hvac_action"),
            "heat_pump_temperature": heat_pump_state.get("temperature"),
            "heat_pump_current_temp": heat_pump_state.get("current_temperature"),
            
            # --- Control Logic Parameters ---
            "deadband_below": self.coordinator.deadband_below,
            "deadband_above": self.coordinator.deadband_above,
            "max_house_temp": self.coordinator.max_house_temp,
            "weather_comp_factor": self.coordinator.weather_comp_factor,
            "max_comp_temp": self.coordinator.max_comp_temp,
            "min_comp_temp": self.coordinator.min_comp_temp,
            
            # --- Advanced Logic States ---
            "comfort_offset_applied": self.coordinator.comfort_offset_applied,
            "min_runtime_remaining_minutes": self.coordinator.min_runtime_remaining_minutes,
            "is_temperating": is_temperating,
            "last_avg_house_over_limit": self.coordinator.last_avg_house_over_limit,
            
            # --- Window Logic ---
            "window_open_active": self.coordinator.window_open_start is not None,
            "window_open_duration_min": window_timer_min,
            "window_delay_setting": self.coordinator.window_delay_minutes,
        }


class SmartClimateModeSensor(SmartClimateBaseSensor):
    """Mode sensor showing what mode smart control is using."""
    
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "mode", "Mode")
        self._attr_icon = "mdi:home-thermometer"
    
    @property
    def state(self):
        if not self.coordinator.smart_control_enabled:
            return "Disabled"
            
        if self.coordinator.force_eco_mode or self.coordinator.sleep_mode_active:
            return "Force Eco" if self.coordinator.force_eco_mode else "Sleep Eco"
        elif self.coordinator.override_mode:
            return "Force Comfort"
        else:
            return "Comfort"

    @property
    def extra_state_attributes(self):
        return {
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "force_comfort": self.coordinator.override_mode,
            "force_eco": self.coordinator.force_eco_mode,
            "sleep_active": self.coordinator.sleep_mode_active,
        }

class SmartClimateTargetSensor(SmartClimateBaseSensor):
    """Target temperature sensor showing what smart control is targeting."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "target_temp", "Target")
        self._attr_icon = "mdi:thermometer-plus"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def state(self):
        base_temp = self.coordinator._determine_base_temperature()
        return base_temp

    @property
    def extra_state_attributes(self):
        return {
            "comfort_temp": self.coordinator.comfort_temp,
            "eco_temp": self.coordinator.eco_temp,
            "boost_temp": self.coordinator.boost_temp,
            "cooling_temp": self.coordinator.cooling_temp,
        }

class SmartClimateVentStatusSensor(SmartClimateBaseSensor):
    """Ventilation Status sensor."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_status", "Ventilation Status")
        self._attr_icon = "mdi:fan-clock"

    @property
    def state(self):
        if not self.coordinator.vent_enabled:
            return "Disabled"
        if self.coordinator.vent_is_running:
            return f"Running ({self.coordinator.vent_reason})"
        return "Idle"

    @property
    def extra_state_attributes(self):
        """Return ventilation details."""
        phase_text = "OFF"
        if self.coordinator.vent_current_phase == 1:
            phase_text = "Phase 1 (A OUT / B IN)"
        elif self.coordinator.vent_current_phase == 2:
            phase_text = "Phase 2 (A IN / B OUT)"
            
        import time
        cycle_elapsed = 0
        if self.coordinator.vent_cycle_start_time:
             cycle_elapsed = int(time.time() - self.coordinator.vent_cycle_start_time)
             
        run_elapsed_min = 0
        if self.coordinator.vent_start_time:
             run_elapsed_min = round((time.time() - self.coordinator.vent_start_time) / 60, 1)

        return {
            "is_running": self.coordinator.vent_is_running,
            "reason": self.coordinator.vent_reason,
            "current_phase_id": self.coordinator.vent_current_phase,
            "current_phase_desc": phase_text,
            "cycle_time_setting": self.coordinator.vent_cycle_time,
            "cycle_elapsed_sec": cycle_elapsed,
            "run_duration_setting": self.coordinator.vent_run_duration,
            "run_elapsed_min": run_elapsed_min,
            "auto_interval_hours": self.coordinator.vent_auto_interval,
            "humidity_threshold": self.coordinator.humidity_threshold,
            "last_auto_run": self.coordinator.last_vent_auto_run,
        }