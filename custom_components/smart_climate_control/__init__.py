import logging
import asyncio
from datetime import timedelta, datetime
from typing import Any, Dict, Optional, List, Union
import time

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    Platform,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ATTR_TEMPERATURE,
    STATE_ON,
    STATE_OPEN,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback, Event
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DOMAIN,
    CONF_HEAT_PUMP,
    CONF_ROOM_SENSOR,
    CONF_OUTSIDE_SENSOR,
    CONF_AVERAGE_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_WINDOW_SENSORS,
    CONF_WINDOW_DELAY,
    CONF_BED_SENSORS,
    CONF_HEAT_PUMP_CONTACT,
    CONF_COMFORT_TEMP,
    CONF_ECO_TEMP,
    CONF_BOOST_TEMP,
    CONF_COOLING_TEMP,
    CONF_DEADBAND_BELOW,
    CONF_DEADBAND_ABOVE,
    CONF_MAX_HOUSE_TEMP,
    CONF_WEATHER_COMP_FACTOR,
    CONF_MAX_COMP_TEMP,
    CONF_MIN_COMP_TEMP,
    CONF_PRESENCE_TRACKER,
    CONF_LOW_TEMP_THRESHOLD,
    CONF_SAFETY_CUTOFF,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_ECO_TEMP,
    DEFAULT_BOOST_TEMP,
    DEFAULT_COOLING_TEMP,
    DEFAULT_DEADBAND,
    DEFAULT_MAX_HOUSE_TEMP,
    DEFAULT_WEATHER_COMP_FACTOR,
    DEFAULT_MAX_COMP_TEMP,
    DEFAULT_MIN_COMP_TEMP,
    DEFAULT_LOW_TEMP_THRESHOLD,
    DEFAULT_SAFETY_CUTOFF,
    DEFAULT_WINDOW_DELAY,
    # Ventilation
    CONF_FAN_GROUP_A,
    CONF_FAN_GROUP_B,
    CONF_HUMIDITY_SENSOR_A,
    CONF_HUMIDITY_SENSOR_B,
    CONF_VENT_CYCLE_TIME,
    CONF_VENT_DURATION,
    CONF_VENT_MAX_DURATION,
    CONF_HUMIDITY_THRESHOLD,
    CONF_VENT_AUTO_INTERVAL,
    CONF_VENT_FAN_SPEED,
    DEFAULT_VENT_CYCLE_TIME,
    DEFAULT_VENT_DURATION,
    DEFAULT_VENT_MAX_DURATION,
    DEFAULT_HUMIDITY_THRESHOLD,
    DEFAULT_VENT_AUTO_INTERVAL,
    DEFAULT_VENT_FAN_SPEED,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SWITCH, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Climate Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    coordinator = SmartClimateCoordinator(hass, entry)
    await coordinator.async_initialize()
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
    }
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _setup_device_links(hass, entry)
    await async_setup_services(hass)
    
    # Standard heating/cooling update (60s)
    entry.async_on_unload(
        async_track_time_interval(
            hass, coordinator.async_update, timedelta(seconds=60)
        )
    )

    # Ventilation update (2s) - Faster check for cycle precision
    entry.async_on_unload(
        async_track_time_interval(
            hass, coordinator.async_update_ventilation, timedelta(seconds=2)
        )
    )
    
    return True

async def _setup_device_links(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up device links by moving heat pump entity to our device."""
    await asyncio.sleep(1)
    
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    
    our_device = device_reg.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    
    if not our_device:
        _LOGGER.error("Smart Climate Control device not found")
        return
    
    heat_pump_entity_id = entry.data[CONF_HEAT_PUMP]
    
    heat_pump_entity = entity_reg.async_get(heat_pump_entity_id)
    
    if not heat_pump_entity:
        _LOGGER.error(f"Heat pump entity {heat_pump_entity_id} not found in entity registry")
        return
    
    original_device_id = heat_pump_entity.device_id
    
    original_area = None
    if original_device_id:
        original_device = device_reg.async_get(original_device_id)
        if original_device:
            original_area = original_device.area_id
    
    try:
        entity_reg.async_update_entity(
            heat_pump_entity_id,
            device_id=our_device.id,
        )
        
        if original_area:
            device_reg.async_update_device(
                our_device.id,
                suggested_area=original_area,
            )
            
    except Exception as e:
        _LOGGER.error(f"FAILED to move heat pump entity: {e}")
        return
    
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.original_heat_pump_device_id = original_device_id
    
    _LOGGER.info(f"Device linking complete")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        await coordinator._release_control()
        await coordinator.stop_ventilation(reason="Unload")
        if coordinator.window_listener_remove:
            coordinator.window_listener_remove()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Smart Climate Control."""
    
    async def handle_force_eco(call: ServiceCall) -> None:
        """Handle force eco mode service."""
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            coordinator.force_eco_mode = call.data.get("enable", True)
            if coordinator.force_eco_mode:
                coordinator.force_comfort_mode = False
            await coordinator.async_update()
    
    async def handle_force_comfort(call: ServiceCall) -> None:
        """Handle force comfort mode service."""
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            coordinator.force_comfort_mode = call.data.get("enable", True)
            if coordinator.force_comfort_mode:
                coordinator.force_eco_mode = False
            await coordinator.async_update()
    
    async def handle_reset_temperatures(call: ServiceCall) -> None:
        """Handle temperature reset service."""
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            await coordinator.reset_temperatures()
            
    async def handle_trigger_ventilation(call: ServiceCall) -> None:
        """Manually trigger ventilation cycle."""
        duration = call.data.get("duration")
        for entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry_id]["coordinator"]
            if duration:
                 coordinator.vent_run_duration = duration
            await coordinator.start_ventilation_cycle(reason="Manual Service Call")
    
    hass.services.async_register(DOMAIN, "force_eco", handle_force_eco)
    hass.services.async_register(DOMAIN, "force_comfort", handle_force_comfort)
    hass.services.async_register(DOMAIN, "reset_temperatures", handle_reset_temperatures)
    hass.services.async_register(DOMAIN, "trigger_ventilation", handle_trigger_ventilation)

class SmartClimateCoordinator:
    """Coordinator for Smart Climate Control with heating, cooling AND ventilation."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        
        self.heat_pump_entity_id = self.config[CONF_HEAT_PUMP]
        
        # State variables (Climate)
        self.smart_control_enabled = True
        self.override_mode = False
        self.force_eco_mode = False
        self.force_comfort_mode = False
        self.current_action = "off"
        self.current_hvac_mode = "heat"
        self.last_avg_house_over_limit = False
        self.sleep_mode_active = False
        self.debug_text = "System initializing..."
        self.smart_control_active = False
        
        # Window Logic Variables
        self.window_open_start = None
        self.window_cooldown_start = None # Tracks time after closing window
        self.open_window_details = [] # List of currently open window names
        self.window_listener_remove = None # Cleanup function for listeners

        self.comfort_offset_applied = 0.0
        self.min_runtime_remaining_minutes = 0
        
        self.last_sent_action = None
        self.last_sent_temperature = None
        self.last_sent_hvac_mode = None
        
        self.last_heat_pump_start: Optional[float] = None
        self.min_runtime: float = self.entry.options.get("min_run_time", 0) * 60
        
        # Temperature settings
        self.comfort_temp = self.config.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
        self.eco_temp = self.config.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
        self.boost_temp = self.config.get(CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP)
        self.cooling_temp = self.config.get(CONF_COOLING_TEMP, DEFAULT_COOLING_TEMP)

        # VENTILATION STATE
        self.vent_enabled = True
        self.vent_is_running = False
        self.vent_manual_mode = False
        self.vent_start_time = None
        self.vent_cycle_start_time = None
        self.vent_current_phase = 0 
        self.vent_reason = "Idle"
        self.last_vent_auto_run = None
        self.vent_run_duration = self._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)
        self.vent_auto_interval = self._get_config_value(CONF_VENT_AUTO_INTERVAL, DEFAULT_VENT_AUTO_INTERVAL)
        self.humidity_threshold = self._get_config_value(CONF_HUMIDITY_THRESHOLD, DEFAULT_HUMIDITY_THRESHOLD)
        self.vent_cycle_time = self._get_config_value(CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME)
        self.vent_fan_speed = self._get_config_value(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED)
        
        self.entry.add_update_listener(self.async_options_updated)
    
    def _get_config_value(self, key: str, default: Any) -> Any:
        """Get value from options (preferred) or config (fallback)."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.config.get(key, default)
    
    @property
    def deadband_below(self) -> float:
        return self._get_config_value(CONF_DEADBAND_BELOW, DEFAULT_DEADBAND)
    
    @property
    def deadband_above(self) -> float:
        return self._get_config_value(CONF_DEADBAND_ABOVE, DEFAULT_DEADBAND)
    
    @property
    def max_house_temp(self) -> float:
        return self._get_config_value(CONF_MAX_HOUSE_TEMP, DEFAULT_MAX_HOUSE_TEMP)
    
    @property
    def weather_comp_factor(self) -> float:
        return self._get_config_value(CONF_WEATHER_COMP_FACTOR, DEFAULT_WEATHER_COMP_FACTOR)
    
    @property
    def max_comp_temp(self) -> float:
        return self._get_config_value(CONF_MAX_COMP_TEMP, DEFAULT_MAX_COMP_TEMP)
    
    @property
    def min_comp_temp(self) -> float:
        return self._get_config_value(CONF_MIN_COMP_TEMP, DEFAULT_MIN_COMP_TEMP)
    
    @property
    def low_temp_threshold(self) -> float:
        return self._get_config_value(CONF_LOW_TEMP_THRESHOLD, DEFAULT_LOW_TEMP_THRESHOLD)
    
    @property
    def safety_cutoff_offset(self) -> float:
        return self._get_config_value(CONF_SAFETY_CUTOFF, DEFAULT_SAFETY_CUTOFF)

    @property
    def window_delay_minutes(self) -> float:
        return self._get_config_value(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)

    @property
    def is_comfort_mode_active(self) -> bool:
        if self.force_comfort_mode: return True
        if self.override_mode: return True
        if self.force_eco_mode or self.sleep_mode_active: return False
        return True
    
    @staticmethod
    async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update."""
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
            coordinator.cooling_temp = coordinator._get_config_value(CONF_COOLING_TEMP, DEFAULT_COOLING_TEMP)
            coordinator.min_runtime = entry.options.get("min_run_time", 0) * 60
            
            # Update ventilation params
            coordinator.vent_run_duration = coordinator._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)
            coordinator.vent_auto_interval = coordinator._get_config_value(CONF_VENT_AUTO_INTERVAL, DEFAULT_VENT_AUTO_INTERVAL)
            coordinator.humidity_threshold = coordinator._get_config_value(CONF_HUMIDITY_THRESHOLD, DEFAULT_HUMIDITY_THRESHOLD)
            coordinator.vent_cycle_time = coordinator._get_config_value(CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME)
            coordinator.vent_fan_speed = coordinator._get_config_value(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED)
            
            # Re-setup listeners in case window sensors changed
            await coordinator._setup_window_listeners()
            
            await coordinator.async_update()
    
    async def async_save_state(self) -> None:
        """Save current state to storage."""
        await self.store.async_save({
            "comfort_temp": self.comfort_temp,
            "eco_temp": self.eco_temp,
            "boost_temp": self.boost_temp,
            "cooling_temp": self.cooling_temp,
            "smart_control_enabled": self.smart_control_enabled,
            "last_heat_pump_start": self.last_heat_pump_start,
            # Ventilation persistence
            "last_vent_auto_run": self.last_vent_auto_run,
            "vent_enabled": self.vent_enabled,
            "vent_fan_speed": self.vent_fan_speed,
        })

    async def async_initialize(self) -> None:
        """Initialize the coordinator."""
        stored_data = await self.store.async_load()
        if stored_data:
            self.comfort_temp = stored_data.get("comfort_temp", self.comfort_temp)
            self.eco_temp = stored_data.get("eco_temp", self.eco_temp)
            self.boost_temp = stored_data.get("boost_temp", self.boost_temp)
            self.cooling_temp = stored_data.get("cooling_temp", self.cooling_temp)
            self.smart_control_enabled = stored_data.get("smart_control_enabled", True)
            self.last_heat_pump_start = stored_data.get("last_heat_pump_start")
            
            self.last_vent_auto_run = stored_data.get("last_vent_auto_run")
            self.vent_enabled = stored_data.get("vent_enabled", True)
            self.vent_fan_speed = stored_data.get("vent_fan_speed", self._get_config_value(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED))
            
        # Setup instant listeners for windows
        await self._setup_window_listeners()
        
        _LOGGER.info(f"Smart Climate initialized. Vent enabled: {self.vent_enabled}")

    async def _setup_window_listeners(self):
        """Setup listeners for window/door sensors for immediate reaction."""
        # Remove existing listener if present
        if self.window_listener_remove:
            self.window_listener_remove()
            self.window_listener_remove = None

        sensors = []
        # Get sensors from options or config (as list)
        window_sensors = self._get_config_value(CONF_WINDOW_SENSORS, [])
        if isinstance(window_sensors, str):
            window_sensors = [window_sensors]
        
        sensors.extend(window_sensors)

        door_sensor = self.config.get(CONF_DOOR_SENSOR)
        if door_sensor:
            sensors.append(door_sensor)
        
        if sensors:
            _LOGGER.info(f"Setting up immediate listeners for window sensors: {sensors}")
            self.window_listener_remove = async_track_state_change_event(
                self.hass, sensors, self._handle_window_state_change
            )

    @callback
    async def _handle_window_state_change(self, event: Event):
        """Handle immediate update when a window sensor changes."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        _LOGGER.debug(f"Window sensor changed: {entity_id} -> {new_state.state if new_state else 'None'}. Triggering immediate update.")
        await self.async_update()

    # ========================================================================================
    #                               VENTILATION LOGIC
    # ========================================================================================
    
    async def async_update_ventilation(self, now=None) -> None:
        """Main loop for ventilation control (runs frequently)."""
        if not self.vent_enabled:
            if self.vent_is_running:
                await self.stop_ventilation("Ventilation Disabled")
            return

        if not self.vent_is_running:
            await self._check_ventilation_triggers()
        
        if self.vent_is_running:
            await self._manage_ventilation_cycle()

    async def _get_max_humidity(self, sensor_conf: Union[str, List[str], None]) -> float:
        if not sensor_conf:
            return 0.0
        
        sensors = sensor_conf
        if isinstance(sensors, str):
            sensors = [sensors]
            
        max_hum = 0.0
        for sensor_id in sensors:
            val = await self._get_sensor_value(sensor_id)
            if val is not None and val > max_hum:
                max_hum = val
        return max_hum

    async def _check_ventilation_triggers(self):
        hum_a = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_A, None))
        hum_b = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_B, None))
        
        max_hum = 0
        target_phase = 1 
        
        if hum_a > self.humidity_threshold:
            max_hum = max(max_hum, hum_a)
            target_phase = 1 
            
        if hum_b > self.humidity_threshold:
            max_hum = max(max_hum, hum_b)
            if hum_b > hum_a:
                target_phase = 2
        
        if max_hum > self.humidity_threshold:
            self.vent_run_duration = self._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)
            await self.start_ventilation_cycle(f"High Humidity ({max_hum:.1f}%)", start_phase=target_phase)
            return

        if self.vent_auto_interval > 0:
            now_ts = time.time()
            if self.last_vent_auto_run is None:
                self.last_vent_auto_run = now_ts
                await self.async_save_state()
            else:
                elapsed_hours = (now_ts - self.last_vent_auto_run) / 3600
                if elapsed_hours >= self.vent_auto_interval:
                    self.vent_run_duration = self._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)
                    await self.start_ventilation_cycle(f"Scheduled Run ({self.vent_auto_interval}h)")
                    self.last_vent_auto_run = now_ts
                    await self.async_save_state()

    async def start_ventilation_cycle(self, reason: str, start_phase: int = 1):
        if self.vent_is_running:
            return 
            
        _LOGGER.info(f"Starting Ventilation: {reason}")
        self.vent_is_running = True
        self.vent_reason = reason
        self.vent_start_time = time.time()
        self.vent_cycle_start_time = time.time()
        self.vent_current_phase = start_phase
        
        await self._apply_fan_directions(self.vent_current_phase)
        
        self.hass.bus.async_fire(f"{DOMAIN}_ventilation_started", {
            "reason": reason,
            "duration": self.vent_run_duration
        })

    async def stop_ventilation(self, reason: str):
        _LOGGER.info(f"Stopping Ventilation: {reason}")
        self.vent_is_running = False
        self.vent_manual_mode = False
        self.vent_reason = "Idle"
        self.vent_current_phase = 0
        
        await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_A, []))
        await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_B, []))

    async def _manage_ventilation_cycle(self):
        now = time.time()
        max_duration_min = self._get_config_value(CONF_VENT_MAX_DURATION, DEFAULT_VENT_MAX_DURATION)
        limit_min = min(self.vent_run_duration, max_duration_min)
        run_time_min = (now - self.vent_start_time) / 60
        
        if "Humidity" in self.vent_reason:
            hum_a = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_A, None))
            hum_b = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_B, None))
            current_max = max(hum_a, hum_b)
            if current_max < (self.humidity_threshold - 5):
                 await self.stop_ventilation("Humidity normalized")
                 return

        if run_time_min >= limit_min and not self.vent_manual_mode:
            await self.stop_ventilation(f"Duration reached ({limit_min}m)")
            return

        cycle_elapsed = now - self.vent_cycle_start_time
        if cycle_elapsed >= self.vent_cycle_time:
            self.vent_cycle_start_time = now
            if self.vent_current_phase == 1:
                self.vent_current_phase = 2
            else:
                self.vent_current_phase = 1
            
            _LOGGER.debug(f"Ventilation switching to Phase {self.vent_current_phase}")
            await self._apply_fan_directions(self.vent_current_phase)

    async def _apply_fan_directions(self, phase: int):
        fans_a = self._get_config_value(CONF_FAN_GROUP_A, [])
        fans_b = self._get_config_value(CONF_FAN_GROUP_B, [])
        dir_a = "forward" if phase == 1 else "reverse"
        dir_b = "reverse" if phase == 1 else "forward"
        await self._set_fans(fans_a, dir_a)
        await self._set_fans(fans_b, dir_b)

    async def _set_fans(self, fan_list, direction):
        if not fan_list: return
        if isinstance(fan_list, str):
            fan_list = [fan_list]
        for fan in fan_list:
            try:
                await self.hass.services.async_call(
                    "fan", "set_percentage", 
                    {"entity_id": fan, "percentage": self.vent_fan_speed}, 
                    blocking=False
                )
                await self.hass.services.async_call(
                    "fan", "set_direction", 
                    {"entity_id": fan, "direction": direction}, 
                    blocking=False
                )
            except Exception as e:
                _LOGGER.warning(f"Failed to set fan {fan}: {e}")

    async def _turn_off_fans(self, fan_list):
        if not fan_list: return
        if isinstance(fan_list, str):
            fan_list = [fan_list]
        for fan in fan_list:
            try:
                await self.hass.services.async_call(
                    "fan", "turn_off", {"entity_id": fan}, blocking=False
                )
            except Exception as e:
                _LOGGER.warning(f"Failed to turn off fan {fan}: {e}")

    # ========================================================================================
    #                               EXISTING CLIMATE LOGIC
    # ========================================================================================

    async def async_update(self, now=None) -> None:
        """Update climate control logic."""
        try:
            if not self.smart_control_enabled:
                if self.smart_control_active:
                    await self._release_control()
                return
            
            self.smart_control_active = True
            
            # Get sensor values
            room_temp = await self._get_sensor_value(self.config[CONF_ROOM_SENSOR])
            outside_temp = None
            if self.config.get(CONF_OUTSIDE_SENSOR):
                outside_temp = await self._get_sensor_value(self.config[CONF_OUTSIDE_SENSOR], 5.0)
            else:
                outside_temp = 5.0
            
            # Check windows (returns True if heating should stop)
            window_open_stop_heating = await self._check_window_status()
            
            # For HEATING mode
            if self.current_hvac_mode == "heat":
                avg_house_temp = await self._get_sensor_value(self.config.get(CONF_AVERAGE_SENSOR))
                await self._check_sleep_status()
                base_temp = self._determine_base_temperature()
                
                action, temperature, reason = await self._calculate_heating_control(
                    room_temp, outside_temp, avg_house_temp, base_temp, window_open_stop_heating
                )
                
                original_temperature = temperature
                self.comfort_offset_applied = 0.0
                is_temperating = "Temperating" in reason
                
                # Apply Offset logic
                if self.current_hvac_mode == "heat" and action == "on" and temperature is not None:
                    if not is_temperating and self.is_comfort_mode_active:
                        offset_value = self.entry.options.get("comfort_temp_offset")
                        if offset_value is None:
                            offset_value = self.config.get("comfort_temp_offset", 0.0)
                        
                        if offset_value > 0:
                            temperature += offset_value
                            self.comfort_offset_applied = offset_value
                
                # Apply weather compensation for heating
                weather_compensation = 0
                has_outside_sensor = self.config.get(CONF_OUTSIDE_SENSOR) is not None
                
                if action == "on" and has_outside_sensor and outside_temp < 0 and temperature is not None:
                    weather_compensation = min(abs(outside_temp) * self.weather_comp_factor, 5.0)
                    temperature = min(temperature + weather_compensation, self.max_comp_temp)
                    temperature = max(temperature, self.min_comp_temp)
                    temperature = round(temperature)
                
                # Min runtime calculation for debug
                self.min_runtime_remaining_minutes = 0
                if self.last_heat_pump_start is not None and action == "on":
                    elapsed = time.time() - self.last_heat_pump_start
                    remaining = max(0, self.min_runtime - elapsed)
                    if remaining > 0:
                        self.min_runtime_remaining_minutes = int(remaining / 60)
                
                self.debug_text = self._format_debug_text(
                    action, temperature, room_temp, None, outside_temp, reason,
                    original_temperature, weather_compensation, has_outside_sensor, "heat"
                )
            
            # For COOLING mode
            else:
                self.comfort_offset_applied = 0.0
                self.min_runtime_remaining_minutes = 0
                
                base_temp = self.cooling_temp
                action, temperature, reason = await self._calculate_cooling_control(
                    room_temp, base_temp, window_open_stop_heating
                )
                
                self.debug_text = self._format_debug_text(
                    action, temperature, room_temp, None, None, reason,
                    None, 0, False, "cool"
                )
            
            self.current_action = action
            # MÓDOSÍTÁS: A window_open_stop_heating értéket átadjuk bypass_protection-ként
            # Így ha ablak miatt kell leállni, nem számít a minimum működési idő.
            await self._control_heat_pump_directly(action, temperature, self.current_hvac_mode, bypass_protection=window_open_stop_heating)
            await self._verify_heat_pump_with_contact_sensor()
            
            self.hass.bus.async_fire(f"{DOMAIN}_state_updated", {
                "entry_id": self.entry.entry_id,
                "action": action,
                "temperature": temperature,
                "debug": self.debug_text,
                "comfort_offset_applied": self.comfort_offset_applied,
                "min_runtime_remaining_minutes": self.min_runtime_remaining_minutes
            })
            
        except Exception as e:
            _LOGGER.error(f"Error in climate control update: {e}")
            self.debug_text = f"Error: {str(e)}"
    
    async def _get_sensor_value(self, entity_id: str, default: Optional[float] = None) -> Optional[float]:
        """Get sensor value with validation."""
        if not entity_id:
            return default
        
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ["unknown", "unavailable"]:
            return default
        
        try:
            value = float(state.state)
            return value
        except (ValueError, TypeError):
            pass
        
        return default
    
    async def _check_window_status(self) -> bool:
        """Check status of windows with hysteresis (cooldown) on close."""
        open_sensors_ids = []
        open_sensors_names = []
        
        configured_delay = self.window_delay_minutes
        
        # 1. Collect all window sensors
        window_sensors = self._get_config_value(CONF_WINDOW_SENSORS, [])
        # Ensure it is a list
        if isinstance(window_sensors, str):
            window_sensors = [window_sensors]
            
        door_sensor = self.config.get(CONF_DOOR_SENSOR)
        
        # Helper to check if a sensor is open
        def is_open(entity_id):
            if not entity_id: return False
            st = self.hass.states.get(entity_id)
            return st and st.state in [STATE_ON, "true", STATE_OPEN]

        # Check Window Sensors
        for sensor_id in window_sensors:
            if is_open(sensor_id):
                open_sensors_ids.append(sensor_id)
                st = self.hass.states.get(sensor_id)
                open_sensors_names.append(st.name if st.name else sensor_id)

        # Check Door Sensor
        if is_open(door_sensor):
            open_sensors_ids.append(door_sensor)
            st = self.hass.states.get(door_sensor)
            open_sensors_names.append(st.name if st.name else door_sensor)

        # Update detailed status for sensor.py
        self.open_window_details = open_sensors_names
        
        now = time.time()
        
        # LOGIC:
        if open_sensors_ids:
            # CASE: Window is OPEN
            
            # Reset cooldown because window is open again
            self.window_cooldown_start = None
            
            # Start timer if this is the first detection
            if self.window_open_start is None:
                self.window_open_start = now
                _LOGGER.info(f"Window/Door open detected: {open_sensors_names}. Timer started.")
                return False # Allow delay time before acting
            else:
                elapsed_minutes = (now - self.window_open_start) / 60
                
                if elapsed_minutes > configured_delay:
                    return True # Stop Heating/Cooling
                else:
                    return False # Within delay
        else:
            # CASE: Window is CLOSED
            
            # If we were previously in "Window Open" mode (timer active)
            if self.window_open_start is not None:
                
                # Check if we ACTUALLY reached the limit where we stopped the heat.
                # If we closed the window BEFORE the delay passed, we should NOT enter cooldown,
                # just reset everything.
                elapsed_since_open = (now - self.window_open_start) / 60
                
                if elapsed_since_open < configured_delay:
                    # We closed it before the timer triggered a stop.
                    # Just reset.
                    _LOGGER.info(f"Window closed before delay ({elapsed_since_open:.1f}m < {configured_delay}m). Resetting timer, no cooldown.")
                    self.window_open_start = None
                    self.window_cooldown_start = None
                    return False

                # If we haven't started cooldown yet, start it now
                if self.window_cooldown_start is None:
                    self.window_cooldown_start = now
                    _LOGGER.info("All windows closed after being open > delay. Starting restore cooldown.")
                
                # Check cooldown duration
                cooldown_elapsed = (now - self.window_cooldown_start) / 60
                
                if cooldown_elapsed < configured_delay:
                    # Still cooling down / waiting to restore
                    return True # Keep Heating OFF
                else:
                    # Cooldown complete
                    _LOGGER.info("Window restore cooldown complete. Resuming climate control.")
                    self.window_open_start = None
                    self.window_cooldown_start = None
                    return False
            else:
                # Normal operation, no windows tracking
                self.window_cooldown_start = None
                return False

    async def _check_sleep_status(self) -> None:
        """Check if sleep mode should be active."""
        bed_sensors = self.config.get(CONF_BED_SENSORS, [])
        if len(bed_sensors) >= 1:
            bed_sensor = self.hass.states.get(bed_sensors[0])
            if bed_sensor:
                self.sleep_mode_active = (bed_sensor.state == "on")
            
    async def _check_presence_status(self) -> bool:
        """Check if someone is home."""
        presence_tracker = self.config.get(CONF_PRESENCE_TRACKER)
        if not presence_tracker: return True
        state = self.hass.states.get(presence_tracker)
        if not state: return True
        state_value = str(state.state).lower().strip()
        entity_domain = presence_tracker.split('.')[0]
        if entity_domain in ['device_tracker', 'person']:
            return state_value not in ['away', 'not_home', 'unknown', 'unavailable']
        elif entity_domain == 'zone':
            try: return int(state.state) > 0
            except: return state_value not in ['0', 'unknown', 'unavailable']
        elif entity_domain == 'sensor':
            if state_value in ['home', 'on', 'true', '1']: return True
            elif state_value in ['away', 'not_home', 'not home', 'off', 'false', '0', 'unknown', 'unavailable']: return False
            else: return True
        elif entity_domain == 'input_boolean': return state_value == 'on'
        elif entity_domain == 'group': return state_value in ['on', 'home']
        else: return state_value not in ['away', 'not_home', 'not home', 'off', '0', 'false', 'unknown', 'unavailable']

    def _determine_base_temperature(self) -> float:
        if self.force_comfort_mode: return self.comfort_temp
        elif self.force_eco_mode or self.sleep_mode_active: return self.eco_temp
        elif self.override_mode: return self.comfort_temp
        return self.comfort_temp
    
    async def _calculate_heating_control(
        self, room_temp: Optional[float], outside_temp: float,
        avg_house_temp: Optional[float], base_temp: float, window_open_stop: bool
    ) -> tuple[str, Optional[float], str]:
        
        # 1. Window Safety Logic (Highest Priority)
        if window_open_stop:
            status_msg = "Window/Door open"
            if self.window_cooldown_start is not None:
                status_msg = "Window closed - Waiting restore"
            return "off", base_temp, status_msg
            
        if self.last_heat_pump_start is not None:
            elapsed = time.time() - self.last_heat_pump_start
            if elapsed < self.min_runtime:
                return "on", base_temp, f"Minimum runtime active"
                
        if self.override_mode: return "on", base_temp, "Manual override"
        someone_home = await self._check_presence_status()
        if not someone_home: return "off", base_temp, "Nobody home"

        if avg_house_temp is not None:
            if self.last_avg_house_over_limit:
                if avg_house_temp > (self.max_house_temp - 0.5): return "off", base_temp, "House temp limit"
            elif avg_house_temp > self.max_house_temp:
                self.last_avg_house_over_limit = True
                return "off", base_temp, "House temp limit"
            else:
                self.last_avg_house_over_limit = False
                
        if room_temp is None: return "off", base_temp, "No room temp data"
        turn_on_temp = base_temp - self.deadband_below
        turn_off_temp = base_temp + self.deadband_above
        
        if room_temp <= turn_on_temp:
            self.last_heat_pump_start = time.time()
            return "on", base_temp, f"Heating needed ({room_temp:.1f}°C <= {turn_on_temp:.1f}°C)"
        elif room_temp >= turn_off_temp:
            if self.is_comfort_mode_active and outside_temp < self.low_temp_threshold:
                safety_cutoff = turn_off_temp + self.safety_cutoff_offset
                if room_temp >= safety_cutoff: return "off", base_temp, f"Overheating protection ({room_temp:.1f}°C)"
                return "on", base_temp, f"Temperating (Low Temp: {outside_temp:.1f}°C < {self.low_temp_threshold}°C)"
            else:
                return "off", base_temp, f"Too hot ({room_temp:.1f}°C >= {turn_off_temp:.1f}°C)"
        else:
            if self.current_action == "on" and self.last_heat_pump_start is not None:
                elapsed = time.time() - self.last_heat_pump_start
                if elapsed < self.min_runtime: return "on", base_temp, "Min runtime active"
            return self.current_action, base_temp, "In deadband"
    
    async def _calculate_cooling_control(
        self, room_temp: Optional[float], base_temp: float, window_open_stop: bool
    ) -> tuple[str, Optional[float], str]:
        
        if window_open_stop:
             status_msg = "Window/Door open"
             if self.window_cooldown_start is not None:
                 status_msg = "Window closed - Waiting restore"
             return "off", base_temp, status_msg
             
        someone_home = await self._check_presence_status()
        if not someone_home: return "off", base_temp, "Nobody home"
        if room_temp is None: return "off", base_temp, "No room temp data"
        
        turn_on_temp = base_temp + self.deadband_above
        turn_off_temp = base_temp - self.deadband_below
        
        if room_temp >= turn_on_temp: return "on", base_temp, f"Cooling needed ({room_temp:.1f}°C >= {turn_on_temp:.1f}°C)"
        elif room_temp <= turn_off_temp: return "off", base_temp, f"Too cold ({room_temp:.1f}°C <= {turn_off_temp:.1f}°C)"
        else: return self.current_action, base_temp, "In deadband"
    
    async def _control_heat_pump_directly(self, action: str, temperature: Optional[float], hvac_mode: str, bypass_protection: bool = False) -> None:
        """Control the heat pump entity directly with minimum runtime enforcement."""
        now = time.time()
    
        # Ellenőrizzük, ha kikapcsolásra készül, hogy a minimum futásidő letelt-e
        # MÓDOSÍTÁS: Csak akkor blokkoljuk a leállást, ha NINCS bypass (azaz nem vészleállás/ablaknyitás)
        if action == "off" and self.last_heat_pump_start is not None and not bypass_protection:
            runtime = now - self.last_heat_pump_start
            if runtime < self.min_runtime:
                _LOGGER.info(f"Minimum runtime not reached ({runtime:.0f}s < {self.min_runtime}s), keeping heat pump on.")
                return
    
        if action == self.last_sent_action and temperature == self.last_sent_temperature and hvac_mode == self.last_sent_hvac_mode:
            return
    
        heat_pump_state = self.hass.states.get(self.heat_pump_entity_id)
        if not heat_pump_state:
            _LOGGER.error(f"Heat pump entity {self.heat_pump_entity_id} not found")
            return
    
        current_hvac_mode = heat_pump_state.state
    
        self.last_sent_action = action
        self.last_sent_temperature = temperature
        self.last_sent_hvac_mode = hvac_mode
    
        if action == "on" and temperature is not None:
            if self.last_heat_pump_start is None:
                self.last_heat_pump_start = now
            await self.async_save_state()
            
            for attempt in range(3):
                _LOGGER.info(f"Sending heat pump command: mode={hvac_mode}, temp={temperature}°C (attempt {attempt+1}/3)")
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {
                        "entity_id": self.heat_pump_entity_id,
                        "temperature": temperature,
                        "hvac_mode": hvac_mode,
                    },
                    blocking=True,
                )
    
                await asyncio.sleep(8)
                new_state = self.hass.states.get(self.heat_pump_entity_id)
    
                if not new_state:
                    continue
    
                new_temp = new_state.attributes.get("temperature")
                new_mode = new_state.state
                hvac_action = new_state.attributes.get("hvac_action", "off")
    
                if (
                    new_temp == temperature and
                    new_mode == hvac_mode and
                    hvac_action not in ["off", "idle"]
                ):
                    _LOGGER.info(f" Heat pump acknowledged command on attempt {attempt+1}")
                    break
                else:
                    _LOGGER.warning(
                        f" Heat pump did not respond properly on attempt {attempt+1}: "
                        f"mode={new_mode}, hvac_action={hvac_action}, temp={new_temp}"
                    )
                    await asyncio.sleep(3)
            else:
                _LOGGER.error(f" Failed to start heat pump after 3 attempts")
        elif action == "off":
            for attempt in range(3):
                _LOGGER.info(f"Turning off heat pump (attempt {attempt+1}/3)")
                await self.hass.services.async_call(
                    "climate",
                    SERVICE_TURN_OFF,
                    {"entity_id": self.heat_pump_entity_id},
                    blocking=True,
                )
    
                await asyncio.sleep(12)
    
                new_state = self.hass.states.get(self.heat_pump_entity_id)
                if not new_state:
                    continue
    
                if new_state.state == "off":
                    _LOGGER.info("Heat pump successfully turned off.")
                    break
                else:
                    _LOGGER.warning(f"Heat pump still on after attempt {attempt+1}, current state: {new_state.state}")
                    await asyncio.sleep(5)
    
    async def _verify_heat_pump_with_contact_sensor(self) -> None:
        """Verify heat pump is actually running using contact sensor."""
        contact_sensor = self.config.get(CONF_HEAT_PUMP_CONTACT)
        if not contact_sensor:
            return
        
        if self.current_action != "on":
            return
        
        await asyncio.sleep(20)
        
        vent_state = self.hass.states.get(contact_sensor)
        if not vent_state:
            _LOGGER.warning(f"Contact sensor {contact_sensor} not found")
            return
        
        vents_open = vent_state.state == "on"
        
        if not vents_open:
            _LOGGER.warning(f"  Heat pump command may have failed - contact sensor shows not running. Retrying...")
            
            heat_pump_state = self.hass.states.get(self.heat_pump_entity_id)
            if heat_pump_state:
                current_temp = heat_pump_state.attributes.get('temperature', self.comfort_temp if self.current_hvac_mode == "heat" else self.cooling_temp)
                
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {
                        "entity_id": self.heat_pump_entity_id,
                        "temperature": current_temp,
                        "hvac_mode": self.current_hvac_mode,
                    },
                    blocking=True,
                )
                
                await asyncio.sleep(20)
                verify_state = self.hass.states.get(contact_sensor)
                
                if verify_state and verify_state.state == "on":
                    _LOGGER.info(f" Heat pump started after retry")
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "dismiss",
                        {"notification_id": "smart_climate_heat_pump_alert"}
                    )
                else:
                    _LOGGER.error(f" Heat pump still not running after retry")
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "Smart Climate Control Alert",
                            "message": f"Heat pump may not be responding to commands. Contact sensor: {contact_sensor}",
                            "notification_id": "smart_climate_heat_pump_alert"
                        }
                    )
        else:
            _LOGGER.debug(f" Heat pump verified running via contact sensor")
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": "smart_climate_heat_pump_alert"}
            )
    
    async def _release_control(self) -> None:
        if self.hass.states.get(self.heat_pump_entity_id):
             await self.hass.services.async_call("climate", "turn_off", {"entity_id": self.heat_pump_entity_id}, blocking=False)
        self.smart_control_active = False
        self.last_sent_action = None
        self.current_action = "off"
        self.debug_text = "Smart control disabled"
    
    def _format_debug_text(self, action, temperature, room_temp, avg_house_temp, outside_temp, reason, original_temperature, weather_compensation, has_outside_sensor, mode="heat") -> str:
        room_str = f"{room_temp:.1f}" if room_temp is not None else "N/A"
        avg_str = f"{avg_house_temp:.1f}" if avg_house_temp is not None else "N/A"
        outside_str = f"{outside_temp:.1f}°C" if has_outside_sensor and outside_temp is not None else "N/A"
        runtime_info = f" | Min runtime: {self.min_runtime_remaining_minutes} min" if self.min_runtime_remaining_minutes > 0 else ""
        if mode == "cool":
            if action == "off": return f"COOL OFF | R: {room_str}°C | {reason}{runtime_info}"
            else: return f"COOL ON | {temperature}°C | R: {room_str}°C | {reason}{runtime_info}"
        if action == "off":
            return f"OFF | R: {room_str}°C | H: {avg_str}°C | O: {outside_str} | {reason}{runtime_info}"
        else:
            mode_str = "Comfort"
            if self.override_mode: mode_str = "Force Comfort"
            elif self.force_eco_mode: mode_str = "Force Eco"
            temp_str = f"{temperature}°C"
            if weather_compensation > 0: temp_str = f"{temperature}°C (B:{original_temperature} +{weather_compensation})"
            return f"ON | {mode_str} {temp_str} | R: {room_str}°C | H: {avg_str}°C | O: {outside_str} | {reason}{runtime_info}"

    async def enable_smart_control(self, enable: bool) -> None:
        self.smart_control_enabled = enable
        await self.async_save_state()
        if not enable: await self._release_control()
        await self.async_update()
        
    async def enable_ventilation_control(self, enable: bool) -> None:
        """Enable/Disable ventilation subsystem."""
        self.vent_enabled = enable
        await self.async_save_state()
        if not enable:
             await self.stop_ventilation("Disabled by User")
    
    @property
    def current_heat_pump_state(self) -> dict:
        state = self.hass.states.get(self.heat_pump_entity_id)
        if state:
            return {"hvac_mode": state.state, "temperature": state.attributes.get("temperature"), "hvac_action": state.attributes.get("hvac_action")}
        return {}
    
    async def reset_temperatures(self) -> None:
        self.comfort_temp = DEFAULT_COMFORT_TEMP
        self.eco_temp = DEFAULT_ECO_TEMP
        self.boost_temp = DEFAULT_BOOST_TEMP
        self.cooling_temp = DEFAULT_COOLING_TEMP
        await self.async_save_state()
        await self.async_update()