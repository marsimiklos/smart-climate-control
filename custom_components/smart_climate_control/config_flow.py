import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

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
    CONF_PRESENCE_TRACKER,
    CONF_SCHEDULE_ENTITY,
    CONF_HEAT_PUMP_CONTACT,
    CONF_COMFORT_TEMP,
    CONF_ECO_TEMP,
    CONF_BOOST_TEMP,
    CONF_DEADBAND_BELOW,
    CONF_DEADBAND_ABOVE,
    CONF_MAX_HOUSE_TEMP,
    CONF_WEATHER_COMP_FACTOR,
    CONF_MAX_COMP_TEMP,
    CONF_MIN_COMP_TEMP,
    CONF_COMFORT_OFFSET,
    CONF_MIN_RUN_TIME,
    CONF_LOW_TEMP_THRESHOLD,
    CONF_SAFETY_CUTOFF,
    DEFAULT_COMFORT_TEMP,
    DEFAULT_ECO_TEMP,
    DEFAULT_BOOST_TEMP,
    DEFAULT_DEADBAND,
    DEFAULT_MAX_HOUSE_TEMP,
    DEFAULT_WEATHER_COMP_FACTOR,
    DEFAULT_MAX_COMP_TEMP,
    DEFAULT_MIN_COMP_TEMP,
    DEFAULT_COMFORT_OFFSET,
    DEFAULT_MIN_RUN_TIME,
    DEFAULT_LOW_TEMP_THRESHOLD,
    DEFAULT_SAFETY_CUTOFF,
    DEFAULT_WINDOW_DELAY,
)

_LOGGER = logging.getLogger(__name__)

class SmartClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Climate Control."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.data = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step."""
        errors = {}
    
        if user_input is not None:
            # Validate heat pump entity exists
            if not self.hass.states.get(user_input[CONF_HEAT_PUMP]):
                errors[CONF_HEAT_PUMP] = "entity_not_found"
            
            # Validate room sensor exists
            if not self.hass.states.get(user_input[CONF_ROOM_SENSOR]):
                errors[CONF_ROOM_SENSOR] = "entity_not_found"
            
            # Validate outside sensor exists (if provided)
            if user_input.get(CONF_OUTSIDE_SENSOR) and not self.hass.states.get(user_input[CONF_OUTSIDE_SENSOR]):
                errors[CONF_OUTSIDE_SENSOR] = "entity_not_found"
            
            if not errors:
                self.data = user_input
                return await self.async_step_options()
    
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="Smart Climate"): str,
                vol.Required(CONF_HEAT_PUMP): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_ROOM_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Optional(CONF_OUTSIDE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Optional(CONF_AVERAGE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                # ÚJ: Több elemű választó ablakoknak/ajtóknak
                vol.Optional(CONF_WINDOW_SENSORS): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean"],
                        multiple=True
                    )
                ),
                # Régi mező megtartása opcionálisként a biztonság kedvéért (vagy eltávolítható)
                vol.Optional(CONF_DOOR_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor", device_class="door")
                ),
                vol.Optional(CONF_HEAT_PUMP_CONTACT): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
                vol.Optional(CONF_SCHEDULE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Optional(CONF_PRESENCE_TRACKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["device_tracker", "person", "zone", "sensor", "input_boolean", "group"]
                    )
                ),                
            }),
            errors=errors,
        )

    async def async_step_options(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the options step."""
        if user_input is not None:
            self.data.update(user_input)
            return await self.async_step_beds()

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Optional(CONF_COMFORT_TEMP, default=DEFAULT_COMFORT_TEMP): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_ECO_TEMP, default=DEFAULT_ECO_TEMP): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_BOOST_TEMP, default=DEFAULT_BOOST_TEMP): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_DEADBAND_BELOW, default=DEFAULT_DEADBAND): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=2, step=0.1, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_DEADBAND_ABOVE, default=DEFAULT_DEADBAND): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=2, step=0.1, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_MAX_HOUSE_TEMP, default=DEFAULT_MAX_HOUSE_TEMP): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=20, max=30, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(CONF_WEATHER_COMP_FACTOR, default=DEFAULT_WEATHER_COMP_FACTOR): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=1, step=0.1, mode="slider")
                ),
            }),
        )

    async def async_step_beds(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the bed sensor step."""
        if user_input is not None:
            # Extract bed sensor if provided
            if user_input.get("bed_sensor"):
                self.data[CONF_BED_SENSORS] = [user_input["bed_sensor"]]
            
            # Create the config entry
            return self.async_create_entry(
                title=self.data[CONF_NAME],
                data=self.data,
            )
    
        return self.async_show_form(
            step_id="beds",
            data_schema=vol.Schema({
                vol.Optional("bed_sensor"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean", "sensor"]
                    )
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SmartClimateOptionsFlow(config_entry)


class SmartClimateOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Smart Climate Control."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_COMFORT_TEMP,
                    default=self._config_entry.options.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_ECO_TEMP,
                    default=self._config_entry.options.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_BOOST_TEMP,
                    default=self._config_entry.options.get(CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=16, max=25, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_DEADBAND_BELOW,
                    default=self._config_entry.options.get(CONF_DEADBAND_BELOW, DEFAULT_DEADBAND)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=2, step=0.1, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_DEADBAND_ABOVE,
                    default=self._config_entry.options.get(CONF_DEADBAND_ABOVE, DEFAULT_DEADBAND)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=2, step=0.1, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_MAX_HOUSE_TEMP,
                    default=self._config_entry.options.get(CONF_MAX_HOUSE_TEMP, DEFAULT_MAX_HOUSE_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=20, max=30, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_WEATHER_COMP_FACTOR,
                    default=self._config_entry.options.get(CONF_WEATHER_COMP_FACTOR, DEFAULT_WEATHER_COMP_FACTOR)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=1, step=0.1, mode="slider")
                ),
                vol.Optional(
                    CONF_MAX_COMP_TEMP,
                    default=self._config_entry.options.get(CONF_MAX_COMP_TEMP, DEFAULT_MAX_COMP_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=20, max=30, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_MIN_COMP_TEMP,
                    default=self._config_entry.options.get(CONF_MIN_COMP_TEMP, DEFAULT_MIN_COMP_TEMP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=14, max=20, step=0.5, mode="slider", unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_COMFORT_OFFSET,
                    default=self._config_entry.options.get(CONF_COMFORT_OFFSET, DEFAULT_COMFORT_OFFSET)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                     min=0, max=5, step=0.5, mode="slider", unit_of_measurement="°C"
                    )
                ),
                vol.Optional(
                    CONF_MIN_RUN_TIME,
                    default=self._config_entry.options.get(CONF_MIN_RUN_TIME, DEFAULT_MIN_RUN_TIME)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                     min=10, max=120, step=5, mode="slider", unit_of_measurement="min"
                    )
                ),
                vol.Optional(
                    CONF_LOW_TEMP_THRESHOLD,
                    default=self._config_entry.options.get(CONF_LOW_TEMP_THRESHOLD, DEFAULT_LOW_TEMP_THRESHOLD)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                     min=-20, max=15, step=0.5, mode="slider", unit_of_measurement="°C"
                    )
                ),
                vol.Optional(
                    CONF_SAFETY_CUTOFF,
                    default=self._config_entry.options.get(CONF_SAFETY_CUTOFF, DEFAULT_SAFETY_CUTOFF)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                     min=0.5, max=5, step=0.5, mode="slider", unit_of_measurement="°C"
                    )
                ),
                # ÚJ: Késleltetés beállítása
                vol.Optional(
                    CONF_WINDOW_DELAY,
                    default=self._config_entry.options.get(CONF_WINDOW_DELAY, DEFAULT_WINDOW_DELAY)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                     min=0, max=30, step=0.5, mode="slider", unit_of_measurement="min"
                    )
                ),
                vol.Optional(
                    CONF_SCHEDULE_ENTITY,
                    default=self._config_entry.data.get(CONF_SCHEDULE_ENTITY) or self._config_entry.options.get(CONF_SCHEDULE_ENTITY)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                # ÚJ: Itt is lehessen módosítani a szenzorokat
                vol.Optional(
                    CONF_WINDOW_SENSORS,
                    default=self._config_entry.options.get(CONF_WINDOW_SENSORS) or self._config_entry.data.get(CONF_WINDOW_SENSORS, [])
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean"],
                        multiple=True
                    )
                ),
            }),
        )