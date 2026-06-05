import logging
from typing import Any, Dict, Optional, List, Union
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, CONF_HEAT_PUMP, CONF_ROOM_SENSOR, CONF_OUTSIDE_SENSOR,
    CONF_AVERAGE_SENSOR, CONF_DOOR_SENSOR, CONF_WINDOW_SENSORS,
    CONF_WINDOW_DELAY, CONF_BED_SENSORS, CONF_PRESENCE_TRACKER,
    CONF_HEAT_PUMP_CONTACT, CONF_COMFORT_TEMP, CONF_ECO_TEMP,
    CONF_BOOST_TEMP, CONF_DEADBAND_BELOW, CONF_DEADBAND_ABOVE,
    CONF_MAX_HOUSE_TEMP, CONF_WEATHER_COMP_FACTOR, CONF_MAX_COMP_TEMP,
    CONF_MIN_COMP_TEMP, CONF_COMFORT_OFFSET, CONF_MIN_RUN_TIME,
    CONF_LOW_TEMP_THRESHOLD, CONF_SAFETY_CUTOFF, CONF_FAN_GROUP_A,
    CONF_FAN_GROUP_B, CONF_HUMIDITY_SENSOR_A, CONF_HUMIDITY_SENSOR_B,
    CONF_VENT_CYCLE_TIME, CONF_VENT_DURATION, CONF_VENT_MAX_DURATION,
    CONF_HUMIDITY_THRESHOLD, CONF_VENT_AUTO_INTERVAL, CONF_VENT_FAN_SPEED,
    CONF_SOLAR_SENSOR, CONF_COOLING_ECO_TEMP, DEFAULT_COMFORT_TEMP, 
    DEFAULT_ECO_TEMP, DEFAULT_BOOST_TEMP, DEFAULT_DEADBAND, DEFAULT_MAX_HOUSE_TEMP,
    DEFAULT_WEATHER_COMP_FACTOR, DEFAULT_MAX_COMP_TEMP, DEFAULT_MIN_COMP_TEMP,
    DEFAULT_COMFORT_OFFSET, DEFAULT_MIN_RUN_TIME, DEFAULT_LOW_TEMP_THRESHOLD,
    DEFAULT_SAFETY_CUTOFF, DEFAULT_VENT_CYCLE_TIME, DEFAULT_VENT_DURATION,
    DEFAULT_VENT_MAX_DURATION, DEFAULT_HUMIDITY_THRESHOLD, DEFAULT_VENT_AUTO_INTERVAL,
    DEFAULT_VENT_FAN_SPEED, DEFAULT_WINDOW_DELAY, DEFAULT_COOLING_ECO_TEMP
)

_LOGGER = logging.getLogger(__name__)

class SmartClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input.get(CONF_NAME, "Smart Climate Control"), data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_NAME, default="Smart Climate"): str,
            vol.Required(CONF_HEAT_PUMP): selector.EntitySelector(selector.EntitySelectorConfig(domain="climate")),
            vol.Required(CONF_ROOM_SENSOR): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Optional(CONF_OUTSIDE_SENSOR): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Optional(CONF_AVERAGE_SENSOR): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)),
            vol.Optional(CONF_DOOR_SENSOR): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
            vol.Optional(CONF_HEAT_PUMP_CONTACT): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
            vol.Optional(CONF_PRESENCE_TRACKER): selector.EntitySelector(selector.EntitySelectorConfig()),
            vol.Optional(CONF_SOLAR_SENSOR): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power")),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartClimateOptionsFlowHandler()

class SmartClimateOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self) -> None:
        pass

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        def get_opt(key, default): return self.config_entry.options.get(key, self.config_entry.data.get(key, default))
        def get_list_opt(key): return self.config_entry.options.get(key, self.config_entry.data.get(key, []))

        schema = vol.Schema({
            # Hozzáadva az ablak és ajtó szenzorok a beállításokhoz
            vol.Optional(CONF_WINDOW_SENSORS, default=get_list_opt(CONF_WINDOW_SENSORS)): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)),
            vol.Optional(CONF_DOOR_SENSOR, default=get_opt(CONF_DOOR_SENSOR, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
            
            vol.Optional(CONF_COOLING_ECO_TEMP, default=get_opt(CONF_COOLING_ECO_TEMP, DEFAULT_COOLING_ECO_TEMP)): selector.NumberSelector(selector.NumberSelectorConfig(min=20, max=30, step=0.5, mode="slider", unit_of_measurement="°C")),
            vol.Optional(CONF_FAN_GROUP_A, default=get_list_opt(CONF_FAN_GROUP_A)): selector.EntitySelector(selector.EntitySelectorConfig(domain="fan", multiple=True)),
            vol.Optional(CONF_FAN_GROUP_B, default=get_list_opt(CONF_FAN_GROUP_B)): selector.EntitySelector(selector.EntitySelectorConfig(domain="fan", multiple=True)),
            vol.Optional(CONF_HUMIDITY_SENSOR_A, default=get_list_opt(CONF_HUMIDITY_SENSOR_A)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="humidity", multiple=True)),
            vol.Optional(CONF_HUMIDITY_SENSOR_B, default=get_list_opt(CONF_HUMIDITY_SENSOR_B)): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="humidity", multiple=True)),
            vol.Optional(CONF_SOLAR_SENSOR, default=get_opt(CONF_SOLAR_SENSOR, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power")),
            vol.Optional(CONF_WINDOW_DELAY, default=get_opt(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=60, step=1, mode="slider", unit_of_measurement="min")),
            vol.Optional(CONF_MIN_RUN_TIME, default=get_opt(CONF_MIN_RUN_TIME, DEFAULT_MIN_RUN_TIME)): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=120, step=5, mode="slider", unit_of_measurement="min")),
            vol.Optional(CONF_VENT_CYCLE_TIME, default=get_opt(CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME)): selector.NumberSelector(selector.NumberSelectorConfig(min=30, max=300, step=5, mode="slider", unit_of_measurement="sec")),
            vol.Optional(CONF_VENT_DURATION, default=get_opt(CONF_VENT_DURATION, DEFAULT_VENT_DURATION)): selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=240, step=5, mode="slider", unit_of_measurement="min")),
            vol.Optional(CONF_VENT_FAN_SPEED, default=get_opt(CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED)): selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=100, step=1, mode="slider", unit_of_measurement="%")),
        })
        return self.async_show_form(step_id="init", data_schema=schema)