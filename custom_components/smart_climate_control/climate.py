from typing import Any, Optional
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode, HVACAction
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .entity import SmartClimateEntity

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([SmartClimateThermostat(coordinator, config_entry)])

class SmartClimateThermostat(SmartClimateEntity, ClimateEntity):
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_climate"

    @property
    def current_temperature(self) -> Optional[float]:
        room_sensor = self.coordinator._get_config_value("room_sensor")
        if not room_sensor: return None
        state = self.hass.states.get(room_sensor)
        if state and state.state not in ["unknown", "unavailable"]:
            try: 
                # Round to 1 decimal place to prevent long float values in UI
                return round(float(state.state), 1)
            except ValueError: 
                return None
        return None

    @property
    def target_temperature(self) -> Optional[float]:
        target = self.coordinator.current_target_temp
        return round(target, 1) if target is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        if not self.coordinator.smart_control_enabled: return HVACMode.OFF
        if self.coordinator.current_hvac_mode == "cool": return HVACMode.COOL
        if self.coordinator.current_hvac_mode == "auto": return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if not self.coordinator.smart_control_enabled: return HVACAction.OFF
        if self.coordinator.current_action == "on": return HVACAction.COOLING if self.coordinator.active_logic_mode == "cool" else HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if ATTR_TEMPERATURE in kwargs:
            temp = kwargs[ATTR_TEMPERATURE]
            if self.coordinator.active_logic_mode == "cool":
                self.coordinator.cooling_temp = temp
            elif self.coordinator.boost_mode:
                self.coordinator.boost_temp = temp
            elif self.coordinator.force_eco_mode:
                self.coordinator.eco_temp = temp
            else:
                self.coordinator.comfort_temp = temp
            await self.coordinator.async_save_state()
            await self.coordinator.async_update()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.enable_smart_control(False)
        else:
            if not self.coordinator.smart_control_enabled:
                await self.coordinator.enable_smart_control(True)
            self.coordinator.boost_mode = False
            if hvac_mode == HVACMode.HEAT:
                self.coordinator.current_hvac_mode = "heat"
                self.coordinator.override_mode = True 
                self.coordinator.force_eco_mode = False
            elif hvac_mode == HVACMode.COOL:
                self.coordinator.current_hvac_mode = "cool"
                self.coordinator.override_mode = False
                self.coordinator.force_eco_mode = False
            elif hvac_mode == HVACMode.AUTO:
                self.coordinator.current_hvac_mode = "auto"
                self.coordinator.override_mode = False
                self.coordinator.force_eco_mode = False
        await self.coordinator.async_update()

    async def async_turn_on(self) -> None: 
        if not self.coordinator.smart_control_enabled:
            await self.coordinator.enable_smart_control(True)
            
    async def async_turn_off(self) -> None: 
        await self.async_set_hvac_mode(HVACMode.OFF)