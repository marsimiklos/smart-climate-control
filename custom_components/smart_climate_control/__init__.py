"""Smart Climate Control integration."""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import CONF_HEAT_PUMP, DOMAIN
from .coordinator import SmartClimateCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.NUMBER, Platform.SWITCH, Platform.SENSOR, Platform.SELECT, Platform.CLIMATE]

SERVICE_FORCE_ECO = "force_eco"
SERVICE_FORCE_COMFORT = "force_comfort"
SERVICE_RESET_TEMPERATURES = "reset_temperatures"
SERVICE_TRIGGER_VENTILATION = "trigger_ventilation"

ENABLE_SCHEMA = vol.Schema({vol.Optional("enable", default=True): cv.boolean})
VENTILATION_SCHEMA = vol.Schema({vol.Optional("duration"): vol.All(vol.Coerce(float), vol.Range(min=1, max=240))})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    coordinator = SmartClimateCoordinator(hass, entry)
    await coordinator.async_initialize()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _link_heat_pump_device(hass, entry, coordinator)
    _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(async_track_time_interval(hass, coordinator.async_update, timedelta(seconds=60)))
    entry.async_on_unload(async_track_time_interval(hass, coordinator.async_update_ventilation, timedelta(seconds=2)))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if data:
        await data["coordinator"].async_apply_options()


async def _link_heat_pump_device(hass: HomeAssistant, entry: ConfigEntry, coordinator: SmartClimateCoordinator) -> None:
    """Show the controlled heat pump entity under this integration's device.

    The original device is remembered so it can be restored when the entry is removed.
    """
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)

    our_device = device_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    heat_pump_entity_id = entry.data.get(CONF_HEAT_PUMP)
    heat_pump_entity = entity_reg.async_get(heat_pump_entity_id) if heat_pump_entity_id else None
    if not our_device or not heat_pump_entity or heat_pump_entity.device_id == our_device.id:
        return

    original_device_id = heat_pump_entity.device_id
    original_area = None
    if original_device_id:
        original_device = device_reg.async_get(original_device_id)
        if original_device:
            original_area = original_device.area_id

    try:
        entity_reg.async_update_entity(heat_pump_entity_id, device_id=our_device.id)
        if original_area:
            device_reg.async_update_device(our_device.id, suggested_area=original_area)
    except Exception:
        _LOGGER.exception("Failed to move heat pump entity %s", heat_pump_entity_id)
        return

    coordinator.original_heat_pump_device_id = original_device_id
    await coordinator.async_save_state()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)["coordinator"]
        await coordinator.async_shutdown()
        await coordinator._release_control()
        await coordinator.stop_ventilation("Unload")
        await coordinator.stop_airout("Unload")
        if not hass.data[DOMAIN]:
            for service in (SERVICE_FORCE_ECO, SERVICE_FORCE_COMFORT, SERVICE_RESET_TEMPERATURES, SERVICE_TRIGGER_VENTILATION):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Give the heat pump entity back to its original device and drop stored data."""
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    stored = await store.async_load() or {}
    original_device_id = stored.get("original_heat_pump_device_id")
    entity_reg = er.async_get(hass)
    heat_pump_entity_id = entry.data.get(CONF_HEAT_PUMP)
    if original_device_id and heat_pump_entity_id and entity_reg.async_get(heat_pump_entity_id):
        if dr.async_get(hass).async_get(original_device_id):
            entity_reg.async_update_entity(heat_pump_entity_id, device_id=original_device_id)
    await store.async_remove()


def _coordinators(hass: HomeAssistant) -> list[SmartClimateCoordinator]:
    return [data["coordinator"] for data in hass.data.get(DOMAIN, {}).values()]


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_FORCE_ECO):
        return

    async def handle_force_eco(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            coordinator.force_eco_mode = call.data["enable"]
            if coordinator.force_eco_mode:
                coordinator.force_comfort_mode = False
                coordinator.boost_mode = False
            await coordinator.async_update()

    async def handle_force_comfort(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            coordinator.force_comfort_mode = call.data["enable"]
            if coordinator.force_comfort_mode:
                coordinator.force_eco_mode = False
                coordinator.boost_mode = False
            await coordinator.async_update()

    async def handle_reset_temperatures(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.reset_temperatures()

    async def handle_trigger_ventilation(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.start_ventilation_cycle("Manual Service Call", duration=call.data.get("duration"))

    hass.services.async_register(DOMAIN, SERVICE_FORCE_ECO, handle_force_eco, schema=ENABLE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_COMFORT, handle_force_comfort, schema=ENABLE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET_TEMPERATURES, handle_reset_temperatures)
    hass.services.async_register(DOMAIN, SERVICE_TRIGGER_VENTILATION, handle_trigger_ventilation, schema=VENTILATION_SCHEMA)
