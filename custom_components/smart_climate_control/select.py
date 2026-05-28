import logging

from homeassistant.components.select import SelectEntity
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
    """Set up Smart Climate Control select entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    entities = [
        SmartClimateAiroutDirectionSelect(coordinator, config_entry)
    ]
    
    async_add_entities(entities)


class SmartClimateAiroutDirectionSelect(SelectEntity):
    """Select entity for choosing the direction of the Airout ventilation."""

    _attr_has_entity_name = True
    _attr_options = ["forward", "reverse"]

    def __init__(self, coordinator, config_entry):
        """Initialize the select entity."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_airout_direction"
        self._attr_name = "Airout Direction"
        self._attr_icon = "mdi:fan-chevron-up"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data.get("name", "Smart Climate Control"),
            "manufacturer": "Custom",
            "model": "Smart Climate Controller",
        }

    @property
    def current_option(self):
        """Return the current selected option."""
        return self.coordinator.airout_direction

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self.coordinator.airout_direction = option
        
        # Ha a Kiszellőztetés jelenleg fut, azonnal alkalmazzuk az új irányt!
        if self.coordinator.airout_is_running:
            await self.coordinator._apply_airout_direction()
            
        await self.coordinator.async_save_state()
        self.async_write_ha_state()