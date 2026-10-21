from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .entity import SmartClimateEntity

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    selects = [
        SmartClimateOperatingModeSelect(coordinator, config_entry)
    ]
    
    # Only load ventilation select if the feature is enabled in options
    if getattr(coordinator, "has_ventilation", True):
        selects.append(SmartClimateAiroutDirectionSelect(coordinator, config_entry))
        
    async_add_entities(selects)

class SmartClimateAiroutDirectionSelect(SmartClimateEntity, SelectEntity):
    _attr_options = ["forward", "reverse"]
    
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_airout_direction"
        self._attr_name = "Airout Direction"
        self._attr_icon = "mdi:fan-chevron-up"

    @property
    def current_option(self): 
        return self.coordinator.airout_direction

    async def async_select_option(self, option: str) -> None:
        self.coordinator.airout_direction = option
        if self.coordinator.airout_is_running:
            await self.coordinator._apply_airout_direction()
        await self.coordinator.async_save_state()


class SmartClimateOperatingModeSelect(SmartClimateEntity, SelectEntity):
    _attr_options = ["auto", "heat", "cool"]
    
    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_operating_mode"
        self._attr_name = "Operating Mode"
        self._attr_icon = "mdi:thermostat-box"

    @property
    def current_option(self): 
        return self.coordinator.current_hvac_mode

    async def async_select_option(self, option: str) -> None:
        self.coordinator.current_hvac_mode = option
        self.coordinator.override_mode = False
        self.coordinator.force_eco_mode = False
        self.coordinator.boost_mode = False

        await self.coordinator.async_save_state()
        await self.coordinator.async_update()
