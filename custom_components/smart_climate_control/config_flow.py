"""Config and options flow for Smart Climate Control."""
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN, CONF_HEAT_PUMP, CONF_ROOM_SENSOR, CONF_OUTSIDE_SENSOR,
    CONF_AVERAGE_SENSOR, CONF_DOOR_SENSOR, CONF_WINDOW_SENSORS,
    CONF_WINDOW_DELAY, CONF_BED_SENSORS, CONF_PRESENCE_TRACKER,
    CONF_HEAT_PUMP_CONTACT, CONF_COMFORT_OFFSET, CONF_MIN_RUN_TIME, CONF_MIN_OFF_TIME,
    CONF_BOOT_DELAY, CONF_DEADBAND_BELOW, CONF_DEADBAND_ABOVE, CONF_MAX_HOUSE_TEMP,
    CONF_WEATHER_COMP_FACTOR, CONF_MAX_COMP_TEMP, CONF_MIN_COMP_TEMP,
    CONF_LOW_TEMP_THRESHOLD, CONF_SAFETY_CUTOFF, CONF_FAN_GROUP_A, CONF_FAN_GROUP_B,
    CONF_HUMIDITY_SENSOR_A, CONF_HUMIDITY_SENSOR_B, CONF_VENT_CYCLE_TIME,
    CONF_VENT_DURATION, CONF_VENT_MAX_DURATION, CONF_HUMIDITY_THRESHOLD,
    CONF_VENT_AUTO_INTERVAL, CONF_VENT_FAN_SPEED, CONF_SOLAR_SENSOR,
    CONF_COOLING_ECO_TEMP, CONF_ENABLE_VENTILATION, CONF_CIRCULATE_INTERVAL,
    CONF_CIRCULATE_DURATION, CONF_CIRCULATE_FAN_SPEED, CONF_SOLAR_DELAY,
    CONF_SOLAR_BASE_THRESHOLD, CONF_CONSUMPTION_SENSOR, CONF_CONSUMPTION_THRESHOLD,
    DEFAULT_DEADBAND, DEFAULT_MAX_HOUSE_TEMP, DEFAULT_WEATHER_COMP_FACTOR,
    DEFAULT_MAX_COMP_TEMP, DEFAULT_MIN_COMP_TEMP, DEFAULT_MIN_RUN_TIME,
    DEFAULT_MIN_OFF_TIME, DEFAULT_BOOT_DELAY, DEFAULT_LOW_TEMP_THRESHOLD,
    DEFAULT_SAFETY_CUTOFF, DEFAULT_VENT_CYCLE_TIME, DEFAULT_VENT_DURATION,
    DEFAULT_VENT_MAX_DURATION, DEFAULT_HUMIDITY_THRESHOLD, DEFAULT_VENT_AUTO_INTERVAL,
    DEFAULT_VENT_FAN_SPEED, DEFAULT_WINDOW_DELAY, DEFAULT_COOLING_ECO_TEMP,
    DEFAULT_CIRCULATE_INTERVAL, DEFAULT_CIRCULATE_DURATION, DEFAULT_CIRCULATE_FAN_SPEED,
    DEFAULT_ENABLE_VENTILATION, DEFAULT_SOLAR_DELAY, DEFAULT_SOLAR_BASE_THRESHOLD,
    DEFAULT_CONSUMPTION_THRESHOLD,
)

def _number(min_value: float, max_value: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=min_value, max=max_value, step=step,
        mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement=unit,
    ))


def _entity(multiple: bool = False, **kwargs: Any) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(multiple=multiple, **kwargs))


class SmartClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HEAT_PUMP])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input.get(CONF_NAME, "Smart Climate Control"), data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_NAME, default="Smart Climate"): str,
            vol.Required(CONF_HEAT_PUMP): _entity(domain="climate"),
            vol.Required(CONF_ROOM_SENSOR): _entity(domain="sensor", device_class="temperature"),
            vol.Optional(CONF_OUTSIDE_SENSOR): _entity(domain="sensor", device_class="temperature"),
            vol.Optional(CONF_AVERAGE_SENSOR): _entity(domain="sensor", device_class="temperature"),
            vol.Optional(CONF_WINDOW_SENSORS): _entity(multiple=True, domain="binary_sensor"),
            vol.Optional(CONF_DOOR_SENSOR): _entity(domain="binary_sensor"),
            vol.Optional(CONF_HEAT_PUMP_CONTACT): _entity(domain="binary_sensor"),
            vol.Optional(CONF_PRESENCE_TRACKER): _entity(domain=["person", "device_tracker", "binary_sensor", "input_boolean", "group"]),
            vol.Optional(CONF_BED_SENSORS): _entity(multiple=True, domain=["binary_sensor", "input_boolean"]),
            vol.Optional(CONF_SOLAR_SENSOR): _entity(domain="sensor", device_class="power"),
            vol.Optional(CONF_CONSUMPTION_SENSOR): _entity(domain="sensor", device_class="power"),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartClimateOptionsFlowHandler()


# (key, default, selector) for the numeric options
_BASE_NUMBERS = [
    (CONF_COOLING_ECO_TEMP, DEFAULT_COOLING_ECO_TEMP, _number(20, 30, 0.5, "°C")),
    (CONF_DEADBAND_BELOW, DEFAULT_DEADBAND, _number(0, 3, 0.1, "°C")),
    (CONF_DEADBAND_ABOVE, DEFAULT_DEADBAND, _number(0, 3, 0.1, "°C")),
    (CONF_MAX_HOUSE_TEMP, DEFAULT_MAX_HOUSE_TEMP, _number(18, 32, 0.5, "°C")),
    (CONF_LOW_TEMP_THRESHOLD, DEFAULT_LOW_TEMP_THRESHOLD, _number(-20, 15, 1, "°C")),
    (CONF_SAFETY_CUTOFF, DEFAULT_SAFETY_CUTOFF, _number(0, 5, 0.1, "°C")),
    (CONF_COMFORT_OFFSET, 0.0, _number(0, 3, 0.1, "°C")),
    (CONF_WEATHER_COMP_FACTOR, DEFAULT_WEATHER_COMP_FACTOR, _number(0, 2, 0.1, "")),
    (CONF_MAX_COMP_TEMP, DEFAULT_MAX_COMP_TEMP, _number(16, 35, 1, "°C")),
    (CONF_MIN_COMP_TEMP, DEFAULT_MIN_COMP_TEMP, _number(10, 25, 1, "°C")),
    (CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY, _number(0, 60, 1, "min")),
    (CONF_BOOT_DELAY, DEFAULT_BOOT_DELAY, _number(0, 10, 1, "min")),
    (CONF_MIN_RUN_TIME, DEFAULT_MIN_RUN_TIME, _number(0, 120, 5, "min")),
    (CONF_MIN_OFF_TIME, DEFAULT_MIN_OFF_TIME, _number(0, 60, 1, "min")),
    (CONF_SOLAR_DELAY, DEFAULT_SOLAR_DELAY, _number(0, 60, 1, "min")),
    (CONF_SOLAR_BASE_THRESHOLD, DEFAULT_SOLAR_BASE_THRESHOLD, _number(0, 10000, 100, "W")),
    (CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD, _number(0, 10000, 100, "W")),
]

_VENT_NUMBERS = [
    (CONF_CIRCULATE_INTERVAL, DEFAULT_CIRCULATE_INTERVAL, _number(1, 12, 1, "h")),
    (CONF_CIRCULATE_DURATION, DEFAULT_CIRCULATE_DURATION, _number(5, 60, 5, "min")),
    (CONF_CIRCULATE_FAN_SPEED, DEFAULT_CIRCULATE_FAN_SPEED, _number(10, 100, 1, "%")),
    (CONF_HUMIDITY_THRESHOLD, DEFAULT_HUMIDITY_THRESHOLD, _number(40, 100, 1, "%")),
    (CONF_VENT_CYCLE_TIME, DEFAULT_VENT_CYCLE_TIME, _number(30, 300, 5, "sec")),
    (CONF_VENT_DURATION, DEFAULT_VENT_DURATION, _number(10, 240, 5, "min")),
    (CONF_VENT_MAX_DURATION, DEFAULT_VENT_MAX_DURATION, _number(10, 480, 5, "min")),
    (CONF_VENT_AUTO_INTERVAL, DEFAULT_VENT_AUTO_INTERVAL, _number(0, 48, 1, "h")),
    (CONF_VENT_FAN_SPEED, DEFAULT_VENT_FAN_SPEED, _number(10, 100, 1, "%")),
]

# (key, multiple, entity selector config) for the optional entity pickers
_BASE_ENTITIES = [
    (CONF_OUTSIDE_SENSOR, False, {"domain": "sensor", "device_class": "temperature"}),
    (CONF_AVERAGE_SENSOR, False, {"domain": "sensor", "device_class": "temperature"}),
    (CONF_WINDOW_SENSORS, True, {"domain": "binary_sensor"}),
    (CONF_DOOR_SENSOR, False, {"domain": "binary_sensor"}),
    (CONF_HEAT_PUMP_CONTACT, False, {"domain": "binary_sensor"}),
    (CONF_PRESENCE_TRACKER, False, {"domain": ["person", "device_tracker", "binary_sensor", "input_boolean", "group"]}),
    (CONF_BED_SENSORS, True, {"domain": ["binary_sensor", "input_boolean"]}),
    (CONF_SOLAR_SENSOR, False, {"domain": "sensor", "device_class": "power"}),
    (CONF_CONSUMPTION_SENSOR, False, {"domain": "sensor", "device_class": "power"}),
]

_VENT_ENTITIES = [
    (CONF_FAN_GROUP_A, True, {"domain": "fan"}),
    (CONF_FAN_GROUP_B, True, {"domain": "fan"}),
    (CONF_HUMIDITY_SENSOR_A, True, {"domain": "sensor", "device_class": "humidity"}),
    (CONF_HUMIDITY_SENSOR_B, True, {"domain": "sensor", "device_class": "humidity"}),
]


class SmartClimateOptionsFlowHandler(config_entries.OptionsFlow):
    def _current(self, key: str, default: Any = None) -> Any:
        """Options win over the initial setup data. A stored 0 is a real value."""
        if key in self.config_entry.options:
            value = self.config_entry.options[key]
        else:
            value = self.config_entry.data.get(key)
        return default if value is None else value

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        vent_enabled = self._current(CONF_ENABLE_VENTILATION, DEFAULT_ENABLE_VENTILATION)
        numbers = _BASE_NUMBERS + (_VENT_NUMBERS if vent_enabled else [])
        entities = _BASE_ENTITIES + (_VENT_ENTITIES if vent_enabled else [])

        if user_input is not None:
            # A cleared entity picker is simply missing from the input. Store the empty
            # value explicitly, otherwise the value from the initial setup would come back.
            for key, multiple, _ in entities:
                user_input.setdefault(key, [] if multiple else None)
            return self.async_create_entry(title="", data=user_input)

        schema: Dict[Any, Any] = {
            vol.Required(CONF_ENABLE_VENTILATION, default=vent_enabled): selector.BooleanSelector(),
        }
        for key, default, number_selector in numbers:
            schema[vol.Optional(key, default=self._current(key, default))] = number_selector
        for key, multiple, config in entities:
            current = self._current(key)
            marker = vol.Optional(key, description={"suggested_value": current}) if current else vol.Optional(key)
            schema[marker] = _entity(multiple=multiple, **config)

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
