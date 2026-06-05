import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([
        SmartClimateOverrideSwitch(coordinator, config_entry),
        SmartClimateForceEcoSwitch(coordinator, config_entry),
        SmartClimateEnableSwitch(coordinator, config_entry),
        SmartClimateVentEnableSwitch(coordinator, config_entry),
        SmartClimateVentManualSwitch(coordinator, config_entry),
        SmartClimateAiroutSwitch(coordinator, config_entry),
        SmartClimateFreeCoolingSwitch(coordinator, config_entry),
        SmartClimateSolarSwitch(coordinator, config_entry),
        SmartClimateCirculateSwitch(coordinator, config_entry),
    ])

class SmartClimateBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, config_entry, switch_type, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_{switch_type}"
        self._attr_name = name
        self._attr_device_info = {"identifiers": {(DOMAIN, config_entry.entry_id)}, "name": config_entry.data.get("name", "Smart Climate")}
    @property
    def available(self): return True

class SmartClimateEnableSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "enable", "Climate Management")
        self._attr_icon = "mdi:robot"
    @property
    def is_on(self): return self.coordinator.smart_control_enabled
    async def async_turn_on(self, **kwargs): await self.coordinator.enable_smart_control(True)
    async def async_turn_off(self, **kwargs): await self.coordinator.enable_smart_control(False)

class SmartClimateOverrideSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "override", "Force Comfort Mode")
        self._attr_icon = "mdi:home-thermometer-outline"
    @property
    def is_on(self): return self.coordinator.override_mode
    async def async_turn_on(self, **kwargs):
        self.coordinator.override_mode, self.coordinator.force_eco_mode = True, False
        await self.coordinator.async_update()
    async def async_turn_off(self, **kwargs):
        self.coordinator.override_mode = False; await self.coordinator.async_update()

class SmartClimateForceEcoSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "force_eco", "Force Eco Mode")
        self._attr_icon = "mdi:leaf"
    @property
    def is_on(self): return self.coordinator.force_eco_mode
    async def async_turn_on(self, **kwargs):
        self.coordinator.force_eco_mode, self.coordinator.override_mode = True, False
        await self.coordinator.async_update()
    async def async_turn_off(self, **kwargs):
        self.coordinator.force_eco_mode = False; await self.coordinator.async_update()

class SmartClimateVentEnableSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_enable", "Ventilation Enabled")
        self._attr_icon = "mdi:fan-auto"
    @property
    def is_on(self): return self.coordinator.vent_enabled
    async def async_turn_on(self, **kwargs): await self.coordinator.enable_ventilation_control(True)
    async def async_turn_off(self, **kwargs): await self.coordinator.enable_ventilation_control(False)

class SmartClimateVentManualSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "vent_manual", "Ventilation Manual Run")
        self._attr_icon = "mdi:fan"
    @property
    def is_on(self): return self.coordinator.vent_is_running
    async def async_turn_on(self, **kwargs):
        self.coordinator.vent_manual_mode = True; await self.coordinator.start_ventilation_cycle("Manual Switch")
    async def async_turn_off(self, **kwargs):
        self.coordinator.vent_manual_mode = False; await self.coordinator.stop_ventilation("Manual Switch Off")

class SmartClimateAiroutSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "airout", "Airout (Ventilate)")
        self._attr_icon = "mdi:weather-windy"
    @property
    def is_on(self): return self.coordinator.airout_is_running and self.coordinator.vent_reason != "Free Cooling"
    async def async_turn_on(self, **kwargs): await self.coordinator.start_airout(reason="Manual Switch"); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs): await self.coordinator.stop_airout("Manual Switch Off"); self.async_write_ha_state()

class SmartClimateFreeCoolingSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "free_cooling", "Auto Free Cooling")
        self._attr_icon = "mdi:snowflake-thermometer"
    @property
    def is_on(self): return self.coordinator.free_cooling_enabled
    async def async_turn_on(self, **kwargs):
        self.coordinator.free_cooling_enabled = True; await self.coordinator.async_save_state(); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs):
        self.coordinator.free_cooling_enabled = False; await self.coordinator.async_save_state(); self.async_write_ha_state()

class SmartClimateSolarSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "solar_sync", "Solar Sync")
        self._attr_icon = "mdi:solar-power"
    @property
    def is_on(self): return self.coordinator.solar_sync_enabled
    async def async_turn_on(self, **kwargs):
        self.coordinator.solar_sync_enabled = True; await self.coordinator.async_save_state(); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs):
        self.coordinator.solar_sync_enabled = False; await self.coordinator.async_save_state(); self.async_write_ha_state()

class SmartClimateCirculateSwitch(SmartClimateBaseSwitch):
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry, "circulate_enable", "Periodic Fan Circulation")
        self._attr_icon = "mdi:fan-sync"
    @property
    def is_on(self): return self.coordinator.circulate_enabled
    async def async_turn_on(self, **kwargs):
        self.coordinator.circulate_enabled = True; await self.coordinator.async_save_state(); self.async_write_ha_state()
    async def async_turn_off(self, **kwargs):
        self.coordinator.circulate_enabled = False
        if self.coordinator.circulate_is_running:
            await self.coordinator._stop_circulation()
        await self.coordinator.async_save_state()
        self.async_write_ha_state()