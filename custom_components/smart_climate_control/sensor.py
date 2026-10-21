from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from homeassistant.util import dt as dt_util
from .entity import SmartClimateEntity

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    sensors = [
        SmartClimateStatusSensor(coordinator, config_entry),
        SmartClimateModeSensor(coordinator, config_entry),
        SmartClimateTargetSensor(coordinator, config_entry),
        SmartClimateLogicModeSensor(coordinator, config_entry),
        SmartClimateRuntimeSensor(coordinator, config_entry),
        SmartClimateCyclesSensor(coordinator, config_entry),
        SmartClimateEnergySensor(coordinator, config_entry),
        SmartClimateAvgRunSensor(coordinator, config_entry),
        SmartClimateDiagnosisSensor(coordinator, config_entry),
        SmartClimateHeatingRateSensor(coordinator, config_entry),
        SmartClimatePreheatStartSensor(coordinator, config_entry),
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
            "force_heating": self.coordinator.force_heating,
            "preheat_active": self.coordinator.preheat_active,
            "schedule_eco": self.coordinator.schedule_eco_active,
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
        if coordinator.schedule_eco_active:
            return "Schedule Eco"
        if coordinator.preheat_active:
            return "Preheat"
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


def _day_attributes(stats) -> dict:
    return {
        "hours": round(stats.run_hours, 2),
        "cycles": stats.cycles,
        "energy_kwh": round(stats.energy_kwh, 3),
    }


class _DailyTotalSensor(SmartClimateBaseSensor):
    """Statistic that restarts from zero every local midnight."""
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def last_reset(self):
        return dt_util.start_of_local_day()

    @property
    def extra_state_attributes(self):
        stats = self.coordinator.stats
        yesterday = stats.yesterday
        return {
            "yesterday": _day_attributes(yesterday) if yesterday else None,
            "history": {day: _day_attributes(d) for day, d in sorted(stats.history.items())},
        }


class SmartClimateRuntimeSensor(_DailyTotalSensor):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "runtime_today", "Runtime Today")

    @property
    def native_value(self):
        return round(self.coordinator.stats.today.run_hours, 2)


class SmartClimateCyclesSensor(_DailyTotalSensor):
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "cycles_today", "Cycles Today")

    @property
    def native_value(self):
        return self.coordinator.stats.today.cycles


class SmartClimateEnergySensor(_DailyTotalSensor):
    """Estimated electric energy. Needs a power sensor or a rated power in the options."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "energy_today", "Estimated Energy Today")

    @property
    def available(self):
        return bool(self.coordinator.rated_power or self.coordinator._get_config_value("heat_pump_power_sensor"))

    @property
    def native_value(self):
        return round(self.coordinator.stats.today.energy_kwh, 3)


class SmartClimateAvgRunSensor(SmartClimateBaseSensor):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "avg_run_today", "Average Run Length Today")

    @property
    def native_value(self):
        avg = self.coordinator.stats.today.avg_run_minutes
        return round(avg, 1) if avg is not None else None


class SmartClimateDiagnosisSensor(SmartClimateBaseSensor):
    """Tells whether the compressor is cycling too often."""
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["no_data", "ok", "short_cycling"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:stethoscope"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "cycle_diagnosis", "Cycle Diagnosis")

    @property
    def native_value(self):
        return self.coordinator.stats.diagnosis()[0]

    @property
    def extra_state_attributes(self):
        state, avg, cycles = self.coordinator.stats.diagnosis()
        attributes = {"cycles_yesterday_and_today": cycles}
        if avg is not None:
            attributes["average_run_minutes"] = round(avg, 1)
        if state == "short_cycling":
            attributes["advice"] = "The heat pump switches on and off often. Increase the deadband or the minimum run time."
        return attributes


class SmartClimateHeatingRateSensor(SmartClimateBaseSensor):
    """How fast the house heats up at the current outside temperature (learned)."""
    _attr_native_unit_of_measurement = "°C/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "heating_rate", "Learned Heating Rate")

    @property
    def native_value(self):
        return round(self.coordinator.thermal.rate_for(self.coordinator.last_outside_temp), 2)

    @property
    def extra_state_attributes(self):
        thermal = self.coordinator.thermal
        return {"learned": thermal.samples > 0, "samples": thermal.samples, "bins": thermal.bins()}


class SmartClimatePreheatStartSensor(SmartClimateBaseSensor):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "preheat_start", "Preheat Start")

    @property
    def native_value(self):
        return self.coordinator.preheat_start

    @property
    def extra_state_attributes(self):
        return {"active": self.coordinator.preheat_active, "predicted_minutes": self.coordinator.preheat_minutes}
