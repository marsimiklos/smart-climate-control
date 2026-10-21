"""Control logic of Smart Climate Control."""
import asyncio
import logging
import time
from typing import Any, Callable, List, Optional, Union

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_TURN_OFF,
    STATE_ON,
    STATE_OPEN,
)
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, CONF_HEAT_PUMP, CONF_ROOM_SENSOR, CONF_OUTSIDE_SENSOR,
    CONF_AVERAGE_SENSOR, CONF_DOOR_SENSOR, CONF_WINDOW_SENSORS,
    CONF_WINDOW_DELAY, CONF_BED_SENSORS, CONF_HEAT_PUMP_CONTACT,
    CONF_COMFORT_TEMP, CONF_ECO_TEMP, CONF_BOOST_TEMP, CONF_COOLING_TEMP,
    CONF_DEADBAND_BELOW, CONF_DEADBAND_ABOVE, CONF_MAX_HOUSE_TEMP,
    CONF_WEATHER_COMP_FACTOR, CONF_MAX_COMP_TEMP, CONF_MIN_COMP_TEMP,
    CONF_PRESENCE_TRACKER, CONF_LOW_TEMP_THRESHOLD, CONF_SAFETY_CUTOFF,
    CONF_MIN_RUN_TIME, DEFAULT_MIN_RUN_TIME,
    DEFAULT_COMFORT_TEMP, DEFAULT_ECO_TEMP, DEFAULT_BOOST_TEMP, DEFAULT_COOLING_TEMP,
    DEFAULT_DEADBAND, DEFAULT_MAX_HOUSE_TEMP, DEFAULT_WEATHER_COMP_FACTOR,
    DEFAULT_MAX_COMP_TEMP, DEFAULT_MIN_COMP_TEMP, DEFAULT_LOW_TEMP_THRESHOLD,
    DEFAULT_SAFETY_CUTOFF, DEFAULT_WINDOW_DELAY, CONF_FAN_GROUP_A, CONF_FAN_GROUP_B,
    CONF_HUMIDITY_SENSOR_A, CONF_HUMIDITY_SENSOR_B, CONF_VENT_CYCLE_TIME,
    CONF_VENT_DURATION, CONF_VENT_MAX_DURATION, CONF_HUMIDITY_THRESHOLD,
    CONF_VENT_AUTO_INTERVAL, CONF_VENT_FAN_SPEED, DEFAULT_VENT_CYCLE_TIME,
    DEFAULT_VENT_DURATION, DEFAULT_VENT_MAX_DURATION, DEFAULT_HUMIDITY_THRESHOLD,
    DEFAULT_VENT_AUTO_INTERVAL, DEFAULT_VENT_FAN_SPEED, CONF_AIROUT_DURATION,
    DEFAULT_AIROUT_DURATION, CONF_SOLAR_SENSOR, CONF_COOLING_ECO_TEMP, DEFAULT_COOLING_ECO_TEMP,
    CONF_CIRCULATE_INTERVAL, CONF_CIRCULATE_DURATION, CONF_CIRCULATE_FAN_SPEED,
    DEFAULT_CIRCULATE_INTERVAL, DEFAULT_CIRCULATE_DURATION, DEFAULT_CIRCULATE_FAN_SPEED,
    CONF_ENABLE_VENTILATION, DEFAULT_ENABLE_VENTILATION,
    CONF_SOLAR_DELAY, DEFAULT_SOLAR_DELAY,
    CONF_SOLAR_BASE_THRESHOLD, DEFAULT_SOLAR_BASE_THRESHOLD,
    CONF_CONSUMPTION_SENSOR, CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD,
    CONF_MIN_OFF_TIME, DEFAULT_MIN_OFF_TIME, CONF_BOOT_DELAY, DEFAULT_BOOT_DELAY,
    DEFAULT_SOLAR_THRESHOLD, DEFAULT_SOLAR_OFFSET,
    CONF_FREE_COOLING_MAX_DURATION, CONF_FREE_COOLING_COOLDOWN,
    DEFAULT_FREE_COOLING_MAX_DURATION, DEFAULT_FREE_COOLING_COOLDOWN,
    CONF_COMFORT_OFFSET, FALLBACK_OUTSIDE_TEMP, HUMIDITY_LOCK_MIN_OUTSIDE, AWAY_STATES,
)
from .logic import (
    WindowTracker, choose_logic_mode, next_solar_state, weather_compensation_offset,
)


_LOGGER = logging.getLogger(__name__)


class SmartClimateCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.heat_pump_entity_id = self._get_config_value(CONF_HEAT_PUMP)
        self._update_lock = asyncio.Lock()
        
        self.boot_time = time.time()
        self.smart_control_enabled = True
        self.override_mode = False
        self.force_eco_mode = False
        self.force_comfort_mode = False
        self.boost_mode = False
        self.current_action = "off"
        self.current_hvac_mode = "auto"
        self.active_logic_mode = "heat"
        
        self.last_avg_house_over_limit = False
        self.sleep_mode_active = False
        self.debug_text = "System initializing..."
        self.smart_control_active = False
        
        self._window_tracker = WindowTracker()
        self.window_open_start = None
        self.window_cooldown_start = None
        self.open_window_details = []
        self.state_listener_remove = None
        self.original_heat_pump_device_id = None

        self._listeners: list[Callable[[], None]] = []
        self._command_task: Optional[asyncio.Task] = None
        self._verify_task: Optional[asyncio.Task] = None
        self._sensor_debouncer = Debouncer(
            hass, _LOGGER, cooldown=5.0, immediate=True, function=self.async_update
        )
        self._last_vent_signature: Optional[tuple] = None
        self._update_pending = False
        self._vent_feature_loaded = self.has_ventilation

        self.comfort_offset_applied = 0.0
        self.min_runtime_remaining_minutes = 0
        self.min_off_remaining_minutes = 0
        
        self.last_sent_action = None
        self.last_sent_temperature = None
        self.last_sent_hvac_mode = None
        self.last_heat_pump_start: Optional[float] = None
        self.last_heat_pump_stop: Optional[float] = None
        self.current_target_temp = 20.0
        
        # Temperature settings
        self.comfort_temp = self._get_config_value(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
        self.eco_temp = self._get_config_value(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
        self.boost_temp = self._get_config_value(CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP)
        self.cooling_temp = self._get_config_value(CONF_COOLING_TEMP, DEFAULT_COOLING_TEMP)
        self.cooling_eco_temp = self._get_config_value(CONF_COOLING_ECO_TEMP, DEFAULT_COOLING_ECO_TEMP)

        # Ventilation State
        self.vent_enabled = True
        self.vent_is_running = False
        self.vent_manual_mode = False
        self.vent_start_time = None
        self.vent_cycle_start_time = None
        self.vent_current_phase = 0 
        self.vent_reason = "Idle"
        self.last_vent_auto_run = None
        self.vent_run_duration = self._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)
        self.vent_active_duration = self.vent_run_duration
        self.vent_auto_interval = self._get_config_value(CONF_VENT_AUTO_INTERVAL, DEFAULT_VENT_AUTO_INTERVAL)
        self.humidity_threshold = self._get_config_value(CONF_HUMIDITY_THRESHOLD, DEFAULT_HUMIDITY_THRESHOLD)
        self.vent_cycle_time = self._get_config_value(CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME)
        self.vent_fan_speed = self._get_config_value(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED)
        self.vent_humidity_cooldown_end = 0 
        self.last_vent_safety_check = 0 

        # Airout State
        self.airout_is_running = False
        self.airout_start_time = None
        self.airout_direction = "forward"
        self.airout_duration = self._get_config_value(CONF_AIROUT_DURATION, DEFAULT_AIROUT_DURATION)
        self.current_airout_limit = self.airout_duration
        
        # Free Cooling State
        self.free_cooling_enabled = False 
        self.free_cooling_max_duration = self._get_config_value(CONF_FREE_COOLING_MAX_DURATION, DEFAULT_FREE_COOLING_MAX_DURATION)
        self.free_cooling_cooldown = self._get_config_value(CONF_FREE_COOLING_COOLDOWN, DEFAULT_FREE_COOLING_COOLDOWN)
        self.last_free_cooling_run = 0 
        
        # Solar Sync State
        self.solar_sync_enabled = False
        self.solar_base_threshold = self._get_config_value(CONF_SOLAR_BASE_THRESHOLD, DEFAULT_SOLAR_BASE_THRESHOLD)

        self.solar_threshold = DEFAULT_SOLAR_THRESHOLD
        self.solar_offset = DEFAULT_SOLAR_OFFSET
        self.solar_delay_minutes = self._get_config_value(CONF_SOLAR_DELAY, DEFAULT_SOLAR_DELAY)
        self.consumption_threshold = self._get_config_value(CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD)
        self._solar_state = "none"  # "none", "base" or "offset"
        self.solar_below_threshold_start = None
        
        # Periodic Circulation State
        self.circulate_enabled = False
        self.circulate_is_running = False
        self.circulate_start_time = 0
        self.last_cooling_active_time = time.time()
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        if key in self.entry.options: return self.entry.options[key]
        return self.config.get(key, default)
    
    @property
    def has_ventilation(self) -> bool: return self._get_config_value(CONF_ENABLE_VENTILATION, DEFAULT_ENABLE_VENTILATION)
    @property
    def min_runtime(self) -> float: return self._get_config_value(CONF_MIN_RUN_TIME, DEFAULT_MIN_RUN_TIME) * 60
    @property
    def min_off_time(self) -> float: return self._get_config_value(CONF_MIN_OFF_TIME, DEFAULT_MIN_OFF_TIME) * 60
    @property
    def boot_delay_minutes(self) -> float: return self._get_config_value(CONF_BOOT_DELAY, DEFAULT_BOOT_DELAY)
    
    @property
    def deadband_below(self) -> float: return self._get_config_value(CONF_DEADBAND_BELOW, DEFAULT_DEADBAND)
    @property
    def deadband_above(self) -> float: return self._get_config_value(CONF_DEADBAND_ABOVE, DEFAULT_DEADBAND)
    @property
    def max_house_temp(self) -> float: return self._get_config_value(CONF_MAX_HOUSE_TEMP, DEFAULT_MAX_HOUSE_TEMP)
    @property
    def weather_comp_factor(self) -> float: return self._get_config_value(CONF_WEATHER_COMP_FACTOR, DEFAULT_WEATHER_COMP_FACTOR)
    @property
    def max_comp_temp(self) -> float: return self._get_config_value(CONF_MAX_COMP_TEMP, DEFAULT_MAX_COMP_TEMP)
    @property
    def min_comp_temp(self) -> float: return self._get_config_value(CONF_MIN_COMP_TEMP, DEFAULT_MIN_COMP_TEMP)
    @property
    def low_temp_threshold(self) -> float: return self._get_config_value(CONF_LOW_TEMP_THRESHOLD, DEFAULT_LOW_TEMP_THRESHOLD)
    @property
    def safety_cutoff_offset(self) -> float: return self._get_config_value(CONF_SAFETY_CUTOFF, DEFAULT_SAFETY_CUTOFF)
    @property
    def window_delay_minutes(self) -> float: return self._get_config_value(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)
    
    @property
    def circulate_interval(self) -> float: return self._get_config_value(CONF_CIRCULATE_INTERVAL, DEFAULT_CIRCULATE_INTERVAL)
    @property
    def circulate_duration(self) -> float: return self._get_config_value(CONF_CIRCULATE_DURATION, DEFAULT_CIRCULATE_DURATION)
    @property
    def circulate_fan_speed(self) -> float: return self._get_config_value(CONF_CIRCULATE_FAN_SPEED, DEFAULT_CIRCULATE_FAN_SPEED)

    @property
    def is_away(self) -> bool:
        tracker = self._get_config_value(CONF_PRESENCE_TRACKER)
        if not tracker:
            return False
        state = self.hass.states.get(tracker)
        return state is not None and state.state in AWAY_STATES

    @property
    def is_comfort_mode_active(self) -> bool:
        if self.boost_mode or self.force_comfort_mode or self.override_mode: return True
        if self.force_eco_mode or self.sleep_mode_active or self.is_away: return False
        return True

    # Option keys that map onto runtime values (which are also adjustable via number entities)
    _OPTION_ATTRS = {
        CONF_COOLING_TEMP: "cooling_temp",
        CONF_COOLING_ECO_TEMP: "cooling_eco_temp",
        CONF_SOLAR_BASE_THRESHOLD: "solar_base_threshold",
        CONF_SOLAR_DELAY: "solar_delay_minutes",
        CONF_CONSUMPTION_THRESHOLD: "consumption_threshold",
        CONF_VENT_DURATION: "vent_run_duration",
        CONF_VENT_AUTO_INTERVAL: "vent_auto_interval",
        CONF_HUMIDITY_THRESHOLD: "humidity_threshold",
        CONF_VENT_CYCLE_TIME: "vent_cycle_time",
        CONF_VENT_FAN_SPEED: "vent_fan_speed",
        CONF_FREE_COOLING_MAX_DURATION: "free_cooling_max_duration",
        CONF_FREE_COOLING_COOLDOWN: "free_cooling_cooldown",
    }

    async def async_apply_options(self) -> None:
        """Apply saved options. Only values the user actually set are touched, so
        runtime values adjusted through number entities are not reset."""
        for key, attr in self._OPTION_ATTRS.items():
            if key in self.entry.options:
                setattr(self, attr, self.entry.options[key])

        if self.has_ventilation != self._vent_feature_loaded:
            # The ventilation entities are only created when the feature is on
            await self.async_save_state()
            self.hass.config_entries.async_schedule_reload(self.entry.entry_id)
            return

        await self._setup_state_listeners()
        await self.async_save_state()
        await self.async_update()

    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after every state change. Returns a remover."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    async def async_shutdown(self) -> None:
        """Stop everything that runs in the background."""
        self._sensor_debouncer.async_shutdown()
        for task in (self._command_task, self._verify_task):
            if task and not task.done():
                task.cancel()
        if self.state_listener_remove:
            self.state_listener_remove()
            self.state_listener_remove = None
    
    async def async_save_state(self) -> None:
        await self.store.async_save({
            "comfort_temp": self.comfort_temp,
            "eco_temp": self.eco_temp,
            "boost_temp": self.boost_temp,
            "cooling_temp": self.cooling_temp,
            "cooling_eco_temp": self.cooling_eco_temp,
            "smart_control_enabled": self.smart_control_enabled,
            "last_heat_pump_start": self.last_heat_pump_start,
            "last_heat_pump_stop": self.last_heat_pump_stop,
            "last_vent_auto_run": self.last_vent_auto_run,
            "vent_enabled": self.vent_enabled,
            "vent_fan_speed": self.vent_fan_speed,
            "humidity_threshold": self.humidity_threshold,
            "vent_run_duration": self.vent_run_duration,
            "vent_auto_interval": self.vent_auto_interval,
            "vent_cycle_time": self.vent_cycle_time,
            "airout_direction": self.airout_direction,
            "airout_duration": self.airout_duration,
            "free_cooling_enabled": self.free_cooling_enabled,
            "last_free_cooling_run": self.last_free_cooling_run,
            "free_cooling_max_duration": self.free_cooling_max_duration,
            "free_cooling_cooldown": self.free_cooling_cooldown,
            "solar_sync_enabled": self.solar_sync_enabled,
            "solar_base_threshold": self.solar_base_threshold,
            "solar_threshold": self.solar_threshold,
            "solar_offset": self.solar_offset,
            "solar_delay_minutes": self.solar_delay_minutes,
            "consumption_threshold": self.consumption_threshold,
            "solar_state": self._solar_state,
            "solar_below_threshold_start": self.solar_below_threshold_start,
            "active_logic_mode": self.active_logic_mode,
            "current_hvac_mode": self.current_hvac_mode,
            "circulate_enabled": self.circulate_enabled,
            "last_cooling_active_time": self.last_cooling_active_time,
            "original_heat_pump_device_id": self.original_heat_pump_device_id,
        })
        # Every user-facing setter persists its change, so this keeps the entities in sync
        self._notify_listeners()

    async def async_initialize(self) -> None:
        stored_data = await self.store.async_load()
        if stored_data:
            self.comfort_temp = stored_data.get("comfort_temp", self.comfort_temp)
            self.eco_temp = stored_data.get("eco_temp", self.eco_temp)
            self.boost_temp = stored_data.get("boost_temp", self.boost_temp)
            self.cooling_temp = stored_data.get("cooling_temp", self.cooling_temp)
            self.cooling_eco_temp = stored_data.get("cooling_eco_temp", self.cooling_eco_temp)
            self.smart_control_enabled = stored_data.get("smart_control_enabled", True)
            self.last_heat_pump_start = stored_data.get("last_heat_pump_start")
            self.last_heat_pump_stop = stored_data.get("last_heat_pump_stop")
            self.last_vent_auto_run = stored_data.get("last_vent_auto_run")
            self.vent_enabled = stored_data.get("vent_enabled", True)
            self.vent_fan_speed = stored_data.get("vent_fan_speed", self._get_config_value(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED))
            self.humidity_threshold = stored_data.get("humidity_threshold", self._get_config_value(CONF_HUMIDITY_THRESHOLD, DEFAULT_HUMIDITY_THRESHOLD))
            self.vent_run_duration = stored_data.get("vent_run_duration", self._get_config_value(CONF_VENT_DURATION, DEFAULT_VENT_DURATION))
            self.vent_auto_interval = stored_data.get("vent_auto_interval", self._get_config_value(CONF_VENT_AUTO_INTERVAL, DEFAULT_VENT_AUTO_INTERVAL))
            self.vent_cycle_time = stored_data.get("vent_cycle_time", self._get_config_value(CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME))
            self.airout_direction = stored_data.get("airout_direction", "forward")
            self.airout_duration = stored_data.get("airout_duration", self._get_config_value(CONF_AIROUT_DURATION, DEFAULT_AIROUT_DURATION))
            self.free_cooling_enabled = stored_data.get("free_cooling_enabled", False)
            self.last_free_cooling_run = stored_data.get("last_free_cooling_run", 0)
            self.free_cooling_max_duration = stored_data.get("free_cooling_max_duration", self.free_cooling_max_duration)
            self.free_cooling_cooldown = stored_data.get("free_cooling_cooldown", self.free_cooling_cooldown)
            self.solar_sync_enabled = stored_data.get("solar_sync_enabled", False)
            self.solar_base_threshold = stored_data.get("solar_base_threshold", self._get_config_value(CONF_SOLAR_BASE_THRESHOLD, DEFAULT_SOLAR_BASE_THRESHOLD))
            self.solar_threshold = stored_data.get("solar_threshold", self.solar_threshold)
            self.solar_offset = stored_data.get("solar_offset", self.solar_offset)
            self.solar_delay_minutes = stored_data.get("solar_delay_minutes", self._get_config_value(CONF_SOLAR_DELAY, DEFAULT_SOLAR_DELAY))
            self.consumption_threshold = stored_data.get("consumption_threshold", self._get_config_value(CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD))
            self._solar_state = stored_data.get("solar_state", "none")
            self.solar_below_threshold_start = stored_data.get("solar_below_threshold_start")
            self.active_logic_mode = stored_data.get("active_logic_mode", "heat")
            self.current_hvac_mode = stored_data.get("current_hvac_mode", "auto")
            self.circulate_enabled = stored_data.get("circulate_enabled", False)
            self.last_cooling_active_time = stored_data.get("last_cooling_active_time", time.time())
            self.original_heat_pump_device_id = stored_data.get("original_heat_pump_device_id")

        await self._setup_state_listeners()
        _LOGGER.info(f"Smart Climate initialized. Vent enabled: {self.vent_enabled}")

    async def _setup_state_listeners(self):
        if self.state_listener_remove:
            self.state_listener_remove()
            self.state_listener_remove = None

        listen_sensors = []
        
        # Add window & door sensors
        listen_sensors.extend(self._as_list(self._get_config_value(CONF_WINDOW_SENSORS)))
        
        door_sensor = self._get_config_value(CONF_DOOR_SENSOR, None)
        if door_sensor: listen_sensors.append(door_sensor)
        
        # Add temperature & power sensors for immediate reaction
        for key in [CONF_ROOM_SENSOR, CONF_OUTSIDE_SENSOR, CONF_AVERAGE_SENSOR, CONF_SOLAR_SENSOR,
                    CONF_CONSUMPTION_SENSOR, CONF_PRESENCE_TRACKER]:
            sensor_id = self._get_config_value(key, None)
            if sensor_id and sensor_id not in listen_sensors:
                listen_sensors.append(sensor_id)
        
        if listen_sensors:
            self.state_listener_remove = async_track_state_change_event(self.hass, listen_sensors, self._handle_sensor_state_change)

    @callback
    def _handle_sensor_state_change(self, event: Event) -> None:
        # Debounced so chatty power sensors don't trigger an update on every change
        self._sensor_debouncer.async_schedule_call()

    @staticmethod
    def _as_list(value: Any) -> list:
        if not value: return []
        return list(value) if isinstance(value, (list, tuple)) else [value]

    def _all_fans(self) -> list:
        return (self._as_list(self._get_config_value(CONF_FAN_GROUP_A))
                + self._as_list(self._get_config_value(CONF_FAN_GROUP_B)))

    async def _apply_airout_direction(self):
        await self._set_fans(self._all_fans(), self.airout_direction)

    async def start_airout(self, reason: str = "Manual Switch", custom_duration: Optional[int] = None):
        if self.vent_is_running: await self.stop_ventilation("Airout Override")
        self.airout_is_running = True
        self.airout_start_time = time.time()
        self.vent_reason = reason
        self.current_airout_limit = custom_duration if custom_duration is not None else self.airout_duration
        await self._apply_airout_direction()
        self._notify_listeners()
        _LOGGER.info("Airout started (%s) in %s direction for %s mins", reason, self.airout_direction, self.current_airout_limit)

    async def stop_airout(self, reason: str):
        self.airout_is_running = False
        self.vent_reason = "Idle"
        await self._turn_off_fans(self._all_fans())
        self._notify_listeners()
        _LOGGER.info("Airout stopped: %s", reason)

    async def _manage_airout(self):
        now = time.time()
        elapsed_min = (now - self.airout_start_time) / 60
        limit = getattr(self, "current_airout_limit", self.airout_duration)
        if elapsed_min >= limit:
            await self.stop_airout(f"Duration reached ({limit}m)")
            return

        if self.vent_reason == "Free Cooling":
            room_temp = await self._get_sensor_value(self._get_config_value(CONF_ROOM_SENSOR))
            target_temp = self.cooling_temp if self.active_logic_mode == "cool" else self._determine_base_temperature(False)
            if room_temp is not None and room_temp <= target_temp:
                await self.stop_airout("Target temperature reached")

    async def async_update_ventilation(self, now=None) -> None:
        await self._async_update_ventilation()
        signature = (self.vent_is_running, self.airout_is_running, self.vent_reason, self.vent_current_phase)
        if signature != self._last_vent_signature:
            self._last_vent_signature = signature
            self._notify_listeners()

    async def _async_update_ventilation(self) -> None:
        if not self.has_ventilation:
            if self.vent_is_running: await self.stop_ventilation("Ventilation Feature Disabled")
            if self.airout_is_running: await self.stop_airout("Ventilation Feature Disabled")
            return
            
        if not self.vent_enabled:
            if self.vent_is_running: await self.stop_ventilation("Ventilation Disabled")
            if self.airout_is_running: await self.stop_airout("Ventilation Disabled")
            return

        if self.airout_is_running:
            await self._manage_airout()
            return

        if not self.vent_is_running:
            now_ts = time.time()
            if not self.circulate_is_running and (self.last_vent_safety_check is None or (now_ts - self.last_vent_safety_check) > 60):
                 self.last_vent_safety_check = now_ts
                 await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_A, []))
                 await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_B, []))
            await self._check_ventilation_triggers()
        
        if self.vent_is_running:
            await self._manage_ventilation_cycle()

    async def _get_max_humidity(self, sensor_conf: Union[str, List[str], None]) -> float:
        if not sensor_conf: return 0.0
        hum_sensors = sensor_conf if isinstance(sensor_conf, list) else [sensor_conf]
        max_hum = 0.0
        for sensor_id in hum_sensors:
            val = await self._get_sensor_value(sensor_id)
            if val is not None and val > max_hum: max_hum = val
        return max_hum

    async def _check_ventilation_triggers(self):
        if self.free_cooling_enabled and not self.airout_is_running:
            now_ts = time.time()
            cooldown_sec = self.free_cooling_cooldown * 3600
            if (now_ts - self.last_free_cooling_run) >= cooldown_sec:
                room_temp = await self._get_sensor_value(self._get_config_value(CONF_ROOM_SENSOR))
                outside_temp = await self._get_sensor_value(self._get_config_value(CONF_OUTSIDE_SENSOR))
                target_temp = self.cooling_temp if self.active_logic_mode == "cool" else self._determine_base_temperature(False)
                if room_temp is not None and outside_temp is not None:
                    if room_temp > target_temp and outside_temp < room_temp:
                        await self.start_airout(reason="Free Cooling", custom_duration=self.free_cooling_max_duration)
                        self.last_free_cooling_run = now_ts
                        await self.async_save_state()
                        return

        if time.time() > self.vent_humidity_cooldown_end:
            hum_a = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_A, None))
            hum_b = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_B, None))
            max_hum = 0
            target_phase = 1 
            if hum_a > self.humidity_threshold:
                max_hum = max(max_hum, hum_a)
                target_phase = 1 
            if hum_b > self.humidity_threshold:
                max_hum = max(max_hum, hum_b)
                if hum_b > hum_a: target_phase = 2
            
            if max_hum > self.humidity_threshold:
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
                    await self.start_ventilation_cycle(f"Scheduled Run ({self.vent_auto_interval}h)")
                    self.last_vent_auto_run = now_ts
                    await self.async_save_state()

    async def start_ventilation_cycle(self, reason: str, start_phase: int = 1, duration: Optional[float] = None):
        if self.vent_is_running: return 
        self.vent_active_duration = duration if duration else self.vent_run_duration
        self.vent_is_running = True
        self.vent_reason = reason
        self.vent_start_time = time.time()
        self.vent_cycle_start_time = time.time()
        self.vent_current_phase = start_phase
        await self._apply_fan_directions(self.vent_current_phase)
        self._notify_listeners()

    async def stop_ventilation(self, reason: str):
        self.vent_is_running = False
        self.vent_manual_mode = False
        self.vent_reason = "Idle"
        self.vent_current_phase = 0
        await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_A, []))
        await self._turn_off_fans(self._get_config_value(CONF_FAN_GROUP_B, []))
        self._notify_listeners()

    async def _manage_ventilation_cycle(self):
        now = time.time()
        hum_a = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_A, None))
        hum_b = await self._get_max_humidity(self._get_config_value(CONF_HUMIDITY_SENSOR_B, None))
        outside_temp = await self._get_sensor_value(self._get_config_value(CONF_OUTSIDE_SENSOR))
        
        if "Humidity" not in self.vent_reason and not self.vent_manual_mode:
             current_max = max(hum_a, hum_b)
             if current_max > self.humidity_threshold:
                  self.vent_reason = f"Humidity (Merge: {self.vent_reason})"

        max_duration_min = self._get_config_value(CONF_VENT_MAX_DURATION, DEFAULT_VENT_MAX_DURATION)
        limit_min = min(self.vent_active_duration, max_duration_min)
        run_time_min = (now - self.vent_start_time) / 60
        
        is_humidity_locked = False
        old_phase = self.vent_current_phase
        
        if "Humidity" in self.vent_reason:
            current_max = max(hum_a, hum_b)
            if "Merge" not in self.vent_reason:
                self.vent_reason = f"High Humidity ({current_max:.1f}%)"

            if current_max < (self.humidity_threshold - 5):
                 await self.stop_ventilation("Humidity normalized")
                 return
                 
            if outside_temp is None or outside_temp >= HUMIDITY_LOCK_MIN_OUTSIDE:
                if hum_a > self.humidity_threshold and hum_b <= self.humidity_threshold:
                    self.vent_current_phase = 1 
                    is_humidity_locked = True
                elif hum_b > self.humidity_threshold and hum_a <= self.humidity_threshold:
                    self.vent_current_phase = 2 
                    is_humidity_locked = True

        if old_phase != self.vent_current_phase:
            await self._apply_fan_directions(self.vent_current_phase)

        if run_time_min >= limit_min and not self.vent_manual_mode:
            if "Humidity" in self.vent_reason:
                self.vent_humidity_cooldown_end = now + (15 * 60)
            await self.stop_ventilation(f"Duration reached ({limit_min}m)")
            return

        cycle_elapsed = now - self.vent_cycle_start_time
        if cycle_elapsed >= self.vent_cycle_time:
            self.vent_cycle_start_time = now
            if not is_humidity_locked:
                self.vent_current_phase = 2 if self.vent_current_phase == 1 else 1
            await self._apply_fan_directions(self.vent_current_phase)

    async def _apply_fan_directions(self, phase: int):
        fans_a = self._get_config_value(CONF_FAN_GROUP_A, [])
        fans_b = self._get_config_value(CONF_FAN_GROUP_B, [])
        dir_a = "forward" if phase == 1 else "reverse"
        dir_b = "reverse" if phase == 1 else "forward"
        await self._set_fans(fans_a, dir_a)
        await self._set_fans(fans_b, dir_b)

    async def _set_fans(self, fan_list, direction, override_speed=None):
        if not fan_list: return
        fans = fan_list if isinstance(fan_list, list) else [fan_list]
        speed = override_speed if override_speed is not None else self.vent_fan_speed
        for fan in fans:
            try:
                await self.hass.services.async_call("fan", "set_percentage", {"entity_id": fan, "percentage": speed}, blocking=False)
                await self.hass.services.async_call("fan", "set_direction", {"entity_id": fan, "direction": direction}, blocking=False)
            except Exception as e:
                _LOGGER.warning("Failed to set fan %s: %s", fan, e)

    async def _turn_off_fans(self, fan_list):
        if not fan_list: return
        fans = fan_list if isinstance(fan_list, list) else [fan_list]
        for fan in fans:
            try:
                await self.hass.services.async_call("fan", "turn_off", {"entity_id": fan}, blocking=False)
            except Exception as e:
                _LOGGER.warning("Failed to turn off fan %s: %s", fan, e)

    async def _start_circulation(self):
        self.circulate_is_running = True
        self.circulate_start_time = time.time()
        await self._set_fans(self._all_fans(), "forward", self.circulate_fan_speed)

    async def _stop_circulation(self):
        self.circulate_is_running = False
        self.last_cooling_active_time = time.time()
        await self._turn_off_fans(self._all_fans())

    def _determine_base_temperature(self, is_cooling: bool) -> float:
        comf = self.cooling_temp if is_cooling else self.comfort_temp
        eco = self.cooling_eco_temp if is_cooling else self.eco_temp
        
        if not is_cooling and self.boost_mode: return self.boost_temp
        if self.override_mode or self.force_comfort_mode: return comf
        if self.force_eco_mode or self.sleep_mode_active or self.is_away: return eco
        return comf
    
    async def _calculate_heating_control(self, room_temp: Optional[float], outside_temp: float, avg_house_temp: Optional[float], base_temp: float, window_open_stop: bool, is_solar_active: bool, applied_solar_offset: float) -> tuple[str, Optional[float], str]:
        if window_open_stop: return "off", base_temp, "Window closed - Waiting restore" if self.window_cooldown_start else "Window/Door open"
        if self.last_heat_pump_start and (time.time() - self.last_heat_pump_start) < self.min_runtime: return "on", base_temp, "Minimum runtime active"
        if self.last_heat_pump_stop and (time.time() - self.last_heat_pump_stop) < self.min_off_time: 
            return "off", base_temp, f"Min off-time active ({int((self.min_off_time - (time.time() - self.last_heat_pump_stop))/60)}m left)"
        if self.override_mode: return "on", base_temp, "Manual override (deadband bypassed)"
        
        if avg_house_temp is not None:
            if self.last_avg_house_over_limit:
                if avg_house_temp > (self.max_house_temp - 0.5): return "off", base_temp, "House temp limit"
            elif avg_house_temp > self.max_house_temp:
                self.last_avg_house_over_limit = True; return "off", base_temp, "House temp limit"
            else: self.last_avg_house_over_limit = False
                
        if room_temp is None: return "off", base_temp, "No room temp data"
        
        if is_solar_active:
            target = base_temp + applied_solar_offset
            offset_msg = f" (+{applied_solar_offset:.1f}°C)" if applied_solar_offset > 0 else " (base temperature)"
            return "on", target, f"Solar Sync active{offset_msg}"
            
        turn_on_temp = base_temp - self.deadband_below
        turn_off_temp = base_temp + self.deadband_above

        if room_temp <= turn_on_temp:
            return "on", base_temp, f"Heating needed ({room_temp:.1f}°C <= {turn_on_temp:.1f}°C)"
        elif room_temp >= turn_off_temp:
            if self.is_comfort_mode_active and outside_temp < self.low_temp_threshold:
                if room_temp >= (turn_off_temp + self.safety_cutoff_offset): return "off", base_temp, f"Overheating protection ({room_temp:.1f}°C)"
                return "on", base_temp, f"Temperating (Low Temp: {outside_temp:.1f}°C < {self.low_temp_threshold}°C)"
            return "off", base_temp, f"Too hot ({room_temp:.1f}°C >= {turn_off_temp:.1f}°C)"
        else:
            if self.current_action == "on" and self.last_heat_pump_start and (time.time() - self.last_heat_pump_start) < self.min_runtime: return "on", base_temp, "Min runtime active"
            return self.current_action, base_temp, "In deadband"
    
    async def _calculate_cooling_control(self, room_temp: Optional[float], base_temp: float, window_open_stop: bool, is_solar_active: bool, applied_solar_offset: float) -> tuple[str, Optional[float], str]:
        if window_open_stop: return "off", base_temp, "Window closed - Waiting restore" if self.window_cooldown_start else "Window/Door open"
        
        if self.last_heat_pump_start and (time.time() - self.last_heat_pump_start) < self.min_runtime: return "on", base_temp, "Minimum runtime active"
        if self.last_heat_pump_stop and (time.time() - self.last_heat_pump_stop) < self.min_off_time: 
            return "off", base_temp, f"Min off-time active ({int((self.min_off_time - (time.time() - self.last_heat_pump_stop))/60)}m left)"
        
        if room_temp is None: return "off", base_temp, "No room temp data"
        
        if is_solar_active:
            target = base_temp - applied_solar_offset
            offset_msg = f" (-{applied_solar_offset:.1f}°C)" if applied_solar_offset > 0 else " (base temperature)"
            return "on", target, f"Solar Sync active{offset_msg}"
            
        turn_on_temp = base_temp + self.deadband_above
        turn_off_temp = base_temp - self.deadband_below
        
        if room_temp >= turn_on_temp: 
            return "on", base_temp, f"Cooling needed ({room_temp:.1f}°C >= {turn_on_temp:.1f}°C)"
        elif room_temp <= turn_off_temp: 
            return "off", base_temp, f"Too cold ({room_temp:.1f}°C <= {turn_off_temp:.1f}°C)"
        else: 
            if self.current_action == "on" and self.last_heat_pump_start and (time.time() - self.last_heat_pump_start) < self.min_runtime: return "on", base_temp, "Min runtime active"
            return self.current_action, base_temp, "In deadband"

    async def async_update(self, now=None) -> None:
        if self._update_lock.locked():
            # Re-run once the current pass is done, so the change that asked for this isn't lost
            self._update_pending = True
            return

        async with self._update_lock:
            self._update_pending = False
            try:
                await self._async_update()
            except Exception as e:
                _LOGGER.exception("Error in climate control update")
                self.debug_text = f"Error: {e}"
        self._notify_listeners()
        if self._update_pending:
            await self.async_update()

    async def _async_update(self) -> None:
        # 1. Boot guard (delay after HA start)
        elapsed_boot = (time.time() - self.boot_time) / 60
        if elapsed_boot < self.boot_delay_minutes:
            self.debug_text = f"Boot delay active... ({int((self.boot_delay_minutes - elapsed_boot) * 60)}s left)"
            return

        if not self.smart_control_enabled:
            if self.smart_control_active: await self._release_control()
            return
        
        self.smart_control_active = True
        room_temp = await self._get_sensor_value(self._get_config_value(CONF_ROOM_SENSOR))
        outside_raw = await self._get_sensor_value(self._get_config_value(CONF_OUTSIDE_SENSOR))
        outside_temp = outside_raw if outside_raw is not None else FALLBACK_OUTSIDE_TEMP
        window_open_stop = await self._check_window_status()

        self.active_logic_mode = choose_logic_mode(
            self.current_hvac_mode, outside_raw, room_temp, self.cooling_temp
        )

        # --- Two-Level Solar Sync Logic ---
        solar_power = 0.0
        solar_sensor_id = self._get_config_value(CONF_SOLAR_SENSOR)
        if solar_sensor_id:
            solar_power = await self._get_sensor_value(solar_sensor_id, 0.0)

        consumption_power = None
        consumption_sensor_id = self._get_config_value(CONF_CONSUMPTION_SENSOR)
        if consumption_sensor_id:
            consumption_power = await self._get_sensor_value(consumption_sensor_id, 0.0)

        self._solar_state, self.solar_below_threshold_start = next_solar_state(
            self._solar_state, self.solar_below_threshold_start, time.time(),
            enabled=self.solar_sync_enabled,
            solar_power=solar_power,
            consumption_power=consumption_power,
            offset_threshold=self.solar_threshold,
            base_threshold=self.solar_base_threshold,
            consumption_threshold=self.consumption_threshold,
            drop_delay_min=self.solar_delay_minutes,
        )

        is_solar_active = self._solar_state in ["base", "offset"]
        applied_solar_offset = self.solar_offset if self._solar_state == "offset" else 0.0
        # ----------------------------------------

        self.min_runtime_remaining_minutes = 0
        self.min_off_remaining_minutes = 0

        if self.active_logic_mode == "heat":
            avg_house_temp = await self._get_sensor_value(self._get_config_value(CONF_AVERAGE_SENSOR))
            await self._check_sleep_status()
            
            base_temp = self._determine_base_temperature(False)
            
            action, temperature, reason = await self._calculate_heating_control(
                room_temp, outside_temp, avg_house_temp, base_temp, window_open_stop, is_solar_active, applied_solar_offset
            )
            
            self.current_target_temp = temperature if temperature is not None else base_temp
            original_temperature = temperature
            self.comfort_offset_applied = 0.0
            is_temperating = "Temperating" in reason
            
            if self.active_logic_mode == "heat" and action == "on" and temperature is not None and not is_solar_active:
                if not is_temperating and self.is_comfort_mode_active:
                    offset_value = self._get_config_value(CONF_COMFORT_OFFSET, 0.0)
                    if offset_value > 0:
                        temperature += offset_value
                        self.comfort_offset_applied = offset_value
            
            weather_compensation = 0
            has_outside_sensor = self._get_config_value(CONF_OUTSIDE_SENSOR) is not None
            if action == "on" and has_outside_sensor and outside_temp < 0 and temperature is not None:
                weather_compensation = weather_compensation_offset(outside_temp, self.weather_comp_factor)
                temperature = min(temperature + weather_compensation, self.max_comp_temp)
                temperature = max(temperature, self.min_comp_temp)
                temperature = round(temperature)
            
            if self.last_heat_pump_start is not None and action == "on":
                remaining = max(0, self.min_runtime - (time.time() - self.last_heat_pump_start))
                if remaining > 0: self.min_runtime_remaining_minutes = int(remaining / 60)
            if self.last_heat_pump_stop is not None and action == "off":
                remaining_off = max(0, self.min_off_time - (time.time() - self.last_heat_pump_stop))
                if remaining_off > 0: self.min_off_remaining_minutes = int(remaining_off / 60)
            
            self.debug_text = self._format_debug_text(action, temperature, room_temp, None, outside_temp, reason, original_temperature, weather_compensation, has_outside_sensor, "heat")
        else:
            self.comfort_offset_applied = 0.0
            
            base_temp = self._determine_base_temperature(True)
            
            action, temperature, reason = await self._calculate_cooling_control(room_temp, base_temp, window_open_stop, is_solar_active, applied_solar_offset)
            self.current_target_temp = temperature if temperature is not None else base_temp
            
            if self.last_heat_pump_start is not None and action == "on":
                remaining = max(0, self.min_runtime - (time.time() - self.last_heat_pump_start))
                if remaining > 0: self.min_runtime_remaining_minutes = int(remaining / 60)
            if self.last_heat_pump_stop is not None and action == "off":
                remaining_off = max(0, self.min_off_time - (time.time() - self.last_heat_pump_stop))
                if remaining_off > 0: self.min_off_remaining_minutes = int(remaining_off / 60)

            # --- Periodic fan circulation ---
            if action == "on":
                self.last_cooling_active_time = time.time()
                if self.circulate_is_running:
                    await self._stop_circulation()
            elif action == "off":
                elapsed = (time.time() - self.last_cooling_active_time) / 3600
                target_interval = self.circulate_interval
                if self.force_eco_mode or self.sleep_mode_active:
                    target_interval *= 2
                
                if not self.circulate_is_running and elapsed >= target_interval and self.circulate_enabled:
                    await self._start_circulation()
                    
                if self.circulate_is_running:
                    circ_elapsed_min = (time.time() - self.circulate_start_time) / 60
                    if circ_elapsed_min >= self.circulate_duration:
                        await self._stop_circulation()
                    else:
                        action = "fan_only"
                        reason = f"Periodic Circulation ({int(self.circulate_duration - circ_elapsed_min)} min left)"
            # --------------------------------------

            self.debug_text = self._format_debug_text(action, temperature, room_temp, None, None, reason, None, 0, False, "cool")
        
        # Check for transitioning to OFF to start Min Off-Time counter
        if action == "off" and self.current_action != "off":
            self.last_heat_pump_stop = time.time()

        # Check for transitioning to ON to start Min Run-Time counter
        if action == "on" and self.current_action != "on":
            self.last_heat_pump_start = time.time()

        self.current_action = action
        target_hvac_action = "cool" if self.active_logic_mode == "cool" else "heat"
        await self._control_heat_pump_directly(action, temperature, target_hvac_action, bypass_protection=window_open_stop)
        self._schedule_contact_check()

        self.hass.bus.async_fire(f"{DOMAIN}_state_updated", {
            "entry_id": self.entry.entry_id, "action": action, "temperature": temperature,
            "debug": self.debug_text, "comfort_offset_applied": self.comfort_offset_applied,
            "min_runtime_remaining_minutes": self.min_runtime_remaining_minutes,
            "min_off_remaining_minutes": self.min_off_remaining_minutes
        })

    async def _control_heat_pump_directly(self, action: str, temperature: Optional[float], hvac_mode: str, bypass_protection: bool = False) -> None:
        if action == self.last_sent_action and temperature == self.last_sent_temperature and hvac_mode == self.last_sent_hvac_mode: return
        if not self.hass.states.get(self.heat_pump_entity_id): return

        self.last_sent_action = action
        self.last_sent_temperature = temperature
        self.last_sent_hvac_mode = hvac_mode
        await self.async_save_state()

        # Sending (with retries) takes tens of seconds. Run it in the background so the
        # update loop stays responsive; a newer command replaces a still running one.
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
        self._command_task = self.hass.async_create_background_task(
            self._send_heat_pump_command(action, temperature, hvac_mode),
            f"{DOMAIN}_send_command",
        )

    async def _send_heat_pump_command(self, action: str, temperature: Optional[float], hvac_mode: str) -> None:
        entity_id = self.heat_pump_entity_id
        call = self.hass.services.async_call
        try:
            if action == "on" and temperature is not None:
                for _ in range(3):
                    await call("climate", "set_temperature", {"entity_id": entity_id, "temperature": temperature, "hvac_mode": hvac_mode}, blocking=True)
                    await asyncio.sleep(8)
                    new_state = self.hass.states.get(entity_id)
                    if new_state and new_state.attributes.get("temperature") == temperature and new_state.state == hvac_mode and new_state.attributes.get("hvac_action", "off") not in ["off", "idle"]: break
                    await asyncio.sleep(3)
            elif action == "fan_only":
                for _ in range(3):
                    await call("climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "fan_only"}, blocking=True)
                    await asyncio.sleep(8)
                    new_state = self.hass.states.get(entity_id)
                    if new_state and new_state.state == "fan_only": break
                    await asyncio.sleep(3)
            elif action == "off":
                for _ in range(3):
                    await call("climate", SERVICE_TURN_OFF, {"entity_id": entity_id}, blocking=True)
                    await asyncio.sleep(12)
                    new_state = self.hass.states.get(entity_id)
                    if new_state and new_state.state == "off": break
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Failed to send command to %s", entity_id)

    def _schedule_contact_check(self) -> None:
        if not self._get_config_value(CONF_HEAT_PUMP_CONTACT) or self.current_action != "on": return
        if self._verify_task and not self._verify_task.done(): return
        self._verify_task = self.hass.async_create_background_task(
            self._verify_heat_pump_with_contact_sensor(), f"{DOMAIN}_contact_check"
        )

    async def _verify_heat_pump_with_contact_sensor(self) -> None:
        contact_sensor = self._get_config_value(CONF_HEAT_PUMP_CONTACT)
        try:
            await asyncio.sleep(20)
            if self.current_action != "on": return
            contact_state = self.hass.states.get(contact_sensor)
            if contact_state and contact_state.state != "on":
                hp_state = self.hass.states.get(self.heat_pump_entity_id)
                if hp_state:
                    target_hvac_action = "cool" if self.active_logic_mode == "cool" else "heat"
                    await self.hass.services.async_call("climate", "set_temperature", {"entity_id": self.heat_pump_entity_id, "temperature": hp_state.attributes.get('temperature', self.comfort_temp), "hvac_mode": target_hvac_action}, blocking=True)
                    await asyncio.sleep(20)
                    contact_state = self.hass.states.get(contact_sensor)
                    if contact_state and contact_state.state != "on":
                        await self.hass.services.async_call("persistent_notification", "create", {"title": "Smart Climate Alert", "message": "Heat pump may not be responding.", "notification_id": "smart_climate_heat_pump_alert"})
            elif contact_state:
                await self.hass.services.async_call("persistent_notification", "dismiss", {"notification_id": "smart_climate_heat_pump_alert"})
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Heat pump contact check failed")

    async def _release_control(self) -> None:
        if self.hass.states.get(self.heat_pump_entity_id):
             await self.hass.services.async_call("climate", "turn_off", {"entity_id": self.heat_pump_entity_id}, blocking=False)
        self.smart_control_active = False
        self.last_sent_action = None
        self.current_action = "off"
        self.debug_text = "Smart control disabled"

    async def _get_sensor_value(self, entity_id: str, default: Optional[float] = None) -> Optional[float]:
        if not entity_id: return default
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ["unknown", "unavailable"]: return default
        try: return float(state.state)
        except (ValueError, TypeError): return default
    
    async def _check_window_status(self) -> bool:
        open_sensors_ids = []
        open_sensors_names = []
        
        window_sensors = self._as_list(self._get_config_value(CONF_WINDOW_SENSORS))

        door_sensor = self._get_config_value(CONF_DOOR_SENSOR)
        
        def is_open(entity_id):
            if not entity_id: 
                return False
            st = self.hass.states.get(entity_id)
            return st and st.state in [STATE_ON, "true", STATE_OPEN]

        for sensor_id in window_sensors:
            if is_open(sensor_id):
                open_sensors_ids.append(sensor_id)
                st = self.hass.states.get(sensor_id)
                open_sensors_names.append(st.name if st.name else sensor_id)
                
        if is_open(door_sensor):
            open_sensors_ids.append(door_sensor)
            st = self.hass.states.get(door_sensor)
            open_sensors_names.append(st.name if st.name else door_sensor)

        self.open_window_details = open_sensors_names
        stop = self._window_tracker.update(bool(open_sensors_ids), time.time(), self.window_delay_minutes)
        self.window_open_start = self._window_tracker.open_start
        self.window_cooldown_start = self._window_tracker.cooldown_start
        return stop

    async def _check_sleep_status(self) -> None:
        bed_sensors = self._as_list(self._get_config_value(CONF_BED_SENSORS))
        states = [self.hass.states.get(entity_id) for entity_id in bed_sensors]
        states = [st for st in states if st is not None and st.state not in ("unknown", "unavailable")]
        if states: self.sleep_mode_active = any(st.state == "on" for st in states)
            
    def _format_debug_text(self, action, temperature, room_temp, avg_house_temp, outside_temp, reason, original_temperature, weather_compensation, has_outside_sensor, mode="heat") -> str:
        room_str = f"{room_temp:.1f}" if room_temp is not None else "N/A"
        avg_str = f"{avg_house_temp:.1f}" if avg_house_temp is not None else "N/A"
        outside_str = f"{outside_temp:.1f}°C" if has_outside_sensor and outside_temp is not None else "N/A"
        rt_info = ""
        if self.min_runtime_remaining_minutes > 0: rt_info = f" | Min runtime: {self.min_runtime_remaining_minutes} min"
        if self.min_off_remaining_minutes > 0: rt_info = f" | Min off-time: {self.min_off_remaining_minutes} min"
        
        if mode == "cool": 
            if action == "fan_only": act_str = "FAN"
            elif action == "on": act_str = "ON"
            else: act_str = "OFF"
            return f"COOL {act_str} | {temperature} | R: {room_str}°C | {reason}{rt_info}"
        if action == "off": return f"OFF | R: {room_str}°C | H: {avg_str}°C | O: {outside_str} | {reason}{rt_info}"
        if self.boost_mode: mode_str = "Boost"
        elif self.override_mode or self.force_comfort_mode: mode_str = "Force Comfort"
        elif self.force_eco_mode or self.sleep_mode_active or self.is_away: mode_str = "Eco"
        else: mode_str = "Comfort"
        temp_str = f"{temperature}°C (B:{original_temperature} +{weather_compensation})" if weather_compensation > 0 else f"{temperature}°C"
        return f"ON | {mode_str} {temp_str} | R: {room_str}°C | H: {avg_str}°C | O: {outside_str} | {reason}{rt_info}"

    async def enable_smart_control(self, enable: bool) -> None:
        self.smart_control_enabled = enable; await self.async_save_state()
        if not enable: await self._release_control()
        await self.async_update()
        
    async def enable_ventilation_control(self, enable: bool) -> None:
        self.vent_enabled = enable; await self.async_save_state()
        if not enable: await self.stop_ventilation("Disabled by User")
        self._notify_listeners()
    
    @property
    def current_heat_pump_state(self) -> dict:
        state = self.hass.states.get(self.heat_pump_entity_id)
        if state: return {"hvac_mode": state.state, "temperature": state.attributes.get("temperature"), "hvac_action": state.attributes.get("hvac_action")}
        return {}
    
    async def reset_temperatures(self) -> None:
        self.comfort_temp, self.eco_temp, self.boost_temp = DEFAULT_COMFORT_TEMP, DEFAULT_ECO_TEMP, DEFAULT_BOOST_TEMP
        self.cooling_temp, self.cooling_eco_temp = DEFAULT_COOLING_TEMP, DEFAULT_COOLING_ECO_TEMP
        await self.async_save_state()
        await self.async_update()