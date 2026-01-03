import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Climate Control switches."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    entities = [
        SmartClimateOverrideSwitch(coordinator, config_entry),     # Force Comfort
        SmartClimateForceEcoSwitch(coordinator, config_entry),     # Force Eco
        SmartClimateForceCoolingSwitch(coordinator, config_entry), # Force Cooling
        SmartClimateEnableSwitch(coordinator, config_entry),       # Climate Management
        # Ventilation Switches
        SmartClimateVentEnableSwitch(coordinator, config_entry),   # Enable Vent Auto
        SmartClimateVentManualSwitch(coordinator, config_entry),   # Start Manual Vent
    ]
    
    async_add_entities(entities)


class SmartClimateBaseSwitch(SwitchEntity):
    """Base switch for Smart Climate Control."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry, switch_type, name):
        """Initialize the switch."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_{switch_type}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data.get("name", "Smart Climate Control"),
            "manufacturer": "Custom",
            "model": "Smart Climate Controller",
        }

    @property
    def available(self):
        return True


class SmartClimateEnableSwitch(SmartClimateBaseSwitch):
    """Master enable switch for Smart Climate Control."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "enable", "Climate Management")
        self._attr_icon = "mdi:robot"

    @property
    def is_on(self):
        return self.coordinator.smart_control_enabled

    @property
    def extra_state_attributes(self):
        heat_pump_state = self.coordinator.current_heat_pump_state
        return {
            "controlled_entity": self.coordinator.heat_pump_entity_id,
            "heat_pump_mode": heat_pump_state.get("hvac_mode"),
            "heat_pump_temperature": heat_pump_state.get("temperature"),
            "smart_control_active": self.coordinator.smart_control_active,
            "current_mode": self.coordinator.current_hvac_mode,
        }

    async def async_turn_on(self, **kwargs):
        await self.coordinator.enable_smart_control(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.enable_smart_control(False)


class SmartClimateOverrideSwitch(SmartClimateBaseSwitch):
    """Force comfort switch - forces comfort mode when on."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "override", "Force Comfort Mode")
        self._attr_icon = "mdi:home-thermometer-outline"

    @property
    def is_on(self):
        return self.coordinator.override_mode and self.coordinator.current_hvac_mode == "heat"

    @property
    def extra_state_attributes(self):
        attrs = {
            "force_comfort_mode": self.coordinator.override_mode,
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "current_hvac_mode": self.coordinator.current_hvac_mode,
        }
        if self.coordinator.current_hvac_mode == "cool":
            attrs["note"] = "Force comfort not available in cooling mode"
        elif self.coordinator.override_mode and not self.coordinator.smart_control_enabled:
            attrs["note"] = "Force comfort set but smart control is disabled"
        return attrs

    async def async_turn_on(self, **kwargs):
        self.coordinator.current_hvac_mode = "heat"
        self.coordinator.override_mode = True
        self.coordinator.force_eco_mode = False
        await self.coordinator.async_update()

    async def async_turn_off(self, **kwargs):
        self.coordinator.override_mode = False
        await self.coordinator.async_update()


class SmartClimateForceEcoSwitch(SmartClimateBaseSwitch):
    """Force eco switch."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "force_eco", "Force Eco Mode")
        self._attr_icon = "mdi:leaf"

    @property
    def is_on(self):
        return self.coordinator.force_eco_mode and self.coordinator.current_hvac_mode == "heat"

    @property
    def extra_state_attributes(self):
        attrs = {
            "force_eco_mode": self.coordinator.force_eco_mode,
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "current_hvac_mode": self.coordinator.current_hvac_mode,
            "eco_temp": self.coordinator.eco_temp,
        }
        if self.coordinator.current_hvac_mode == "cool":
            attrs["note"] = "Force eco not available in cooling mode"
        elif self.coordinator.force_eco_mode and not self.coordinator.smart_control_enabled:
            attrs["note"] = "Force eco set but smart control is disabled"
        return attrs

    async def async_turn_on(self, **kwargs):
        self.coordinator.current_hvac_mode = "heat"
        self.coordinator.force_eco_mode = True
        self.coordinator.override_mode = False
        await self.coordinator.async_update()

    async def async_turn_off(self, **kwargs):
        self.coordinator.force_eco_mode = False
        await self.coordinator.async_update()


class SmartClimateForceCoolingSwitch(SmartClimateBaseSwitch):
    """Force cooling switch."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "force_cooling", "Force Cooling Mode")
        self._attr_icon = "mdi:snowflake"

    @property
    def is_on(self):
        return self.coordinator.current_hvac_mode == "cool"

    @property
    def extra_state_attributes(self):
        attrs = {
            "cooling_mode": self.coordinator.current_hvac_mode == "cool",
            "smart_control_enabled": self.coordinator.smart_control_enabled,
            "cooling_temperature": self.coordinator.cooling_temp,
        }
        
        if not self.coordinator.smart_control_enabled:
            attrs["note"] = "Cooling mode set but smart control is disabled"
        elif self.coordinator.current_hvac_mode == "cool":
            attrs["note"] = "Cooling mode active"
        else:
            attrs["note"] = "Cooling mode not active"
            
        return attrs

    async def async_turn_on(self, **kwargs):
        _LOGGER.info("Force Cooling: Switching to cooling mode")
        self.coordinator.current_hvac_mode = "cool"
        self.coordinator.override_mode = False
        self.coordinator.force_eco_mode = False
        await self.coordinator.async_update()

    async def async_turn_off(self, **kwargs):
        _LOGGER.info("Force Cooling: Switching back to heating mode")
        self.coordinator.current_hvac_mode = "heat"
        await self.coordinator.async_update()

# --- VENTILATION SWITCHES ---

class SmartClimateVentEnableSwitch(SmartClimateBaseSwitch):
    """Master enable switch for Ventilation."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_enable", "Ventilation Enabled")
        self._attr_icon = "mdi:fan-auto"

    @property
    def is_on(self):
        return self.coordinator.vent_enabled

    async def async_turn_on(self, **kwargs):
        await self.coordinator.enable_ventilation_control(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.enable_ventilation_control(False)


class SmartClimateVentManualSwitch(SmartClimateBaseSwitch):
    """Manual run switch for Ventilation."""

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_manual", "Ventilation Manual Run")
        self._attr_icon = "mdi:fan"

    @property
    def is_on(self):
        return self.coordinator.vent_is_running

    @property
    def extra_state_attributes(self):
        return {
            "reason": self.coordinator.vent_reason,
            "phase": self.coordinator.vent_current_phase,
            "duration": self.coordinator.vent_run_duration
        }

    async def async_turn_on(self, **kwargs):
        self.coordinator.vent_manual_mode = True
        await self.coordinator.start_ventilation_cycle("Manual Switch")

    async def async_turn_off(self, **kwargs):
        self.coordinator.vent_manual_mode = False
        await self.coordinator.stop_ventilation("Manual Switch Off")