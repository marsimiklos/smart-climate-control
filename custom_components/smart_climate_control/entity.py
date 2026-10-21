"""Base entity shared by all platforms."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import SmartClimateCoordinator


class SmartClimateEntity(Entity):
    """Entity that is pushed a state write whenever the coordinator changes."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SmartClimateCoordinator, config_entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.data.get("name", "Smart Climate"),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
