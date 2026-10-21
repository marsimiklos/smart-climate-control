"""Integration tests against a real (test) Home Assistant instance."""
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.smart_climate_control.const import (
    CONF_HEAT_PUMP, CONF_MIN_RUN_TIME, CONF_PRESENCE_TRACKER, CONF_ROOM_SENSOR,
    CONF_WINDOW_DELAY, DOMAIN,
)

ROOM = "sensor.room_temperature"
HEAT_PUMP = "climate.heat_pump"


async def _setup(hass: HomeAssistant, **extra):
    hass.states.async_set(ROOM, "21.0", {"device_class": "temperature", "unit_of_measurement": "°C"})
    hass.states.async_set(HEAT_PUMP, "off", {"hvac_modes": ["off", "heat", "cool"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Smart Climate",
        data={"name": "Smart Climate", CONF_HEAT_PUMP: HEAT_PUMP, CONF_ROOM_SENSOR: ROOM, **extra},
        options={"boot_delay": 0, "window_delay": 1.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Mock after setup, the climate component registers its own services when it loads
    calls = async_mock_service(hass, "climate", "set_temperature")
    async_mock_service(hass, "climate", "turn_off")
    return entry, hass.data[DOMAIN][entry.entry_id]["coordinator"], calls


async def test_setup_creates_entities_and_services(hass: HomeAssistant):
    entry, coordinator, _ = await _setup(hass)

    assert hass.states.get("climate.smart_climate") is not None
    assert hass.states.get("sensor.smart_climate_status") is not None
    assert hass.states.get("switch.smart_climate_force_boost_mode") is not None
    assert hass.services.has_service(DOMAIN, "force_eco")
    assert hass.services.has_service(DOMAIN, "trigger_ventilation")

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, "force_eco")


async def test_heats_when_room_is_cold(hass: HomeAssistant):
    _, coordinator, calls = await _setup(hass)

    hass.states.async_set(ROOM, "18.0", {"device_class": "temperature"})
    with patch("custom_components.smart_climate_control.coordinator.asyncio.sleep", new=AsyncMock()):
        await coordinator.async_update()
        await coordinator._command_task

    assert coordinator.current_action == "on"
    assert calls[-1].data["temperature"] == 20.0
    assert calls[-1].data["hvac_mode"] == "heat"


async def test_sensor_change_triggers_an_update(hass: HomeAssistant):
    """Regression: the state listener used to be a never-awaited coroutine."""
    _, coordinator, _ = await _setup(hass)
    assert coordinator.current_action == "off"

    # The heat pump command keeps running in the background (and is cancelled on shutdown)
    hass.states.async_set(ROOM, "17.0", {"device_class": "temperature"})
    await hass.async_block_till_done()
    assert coordinator.current_action == "on"


async def test_away_switches_to_eco(hass: HomeAssistant):
    hass.states.async_set("person.me", "home")
    _, coordinator, _ = await _setup(hass, **{CONF_PRESENCE_TRACKER: "person.me"})

    assert coordinator._determine_base_temperature(False) == coordinator.comfort_temp
    hass.states.async_set("person.me", "not_home")
    assert coordinator._determine_base_temperature(False) == coordinator.eco_temp
    assert coordinator._determine_base_temperature(True) == coordinator.cooling_eco_temp

    coordinator.override_mode = True
    assert coordinator._determine_base_temperature(False) == coordinator.comfort_temp


async def test_boost_mode_uses_boost_temperature(hass: HomeAssistant):
    _, coordinator, _ = await _setup(hass)
    coordinator.boost_mode = True
    assert coordinator._determine_base_temperature(False) == coordinator.boost_temp
    assert coordinator._determine_base_temperature(True) == coordinator.cooling_temp


async def test_options_flow_keeps_zero_values(hass: HomeAssistant):
    """Regression: `value or default` turned a 0 into the default."""
    entry, coordinator, _ = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"enable_ventilation": False, CONF_MIN_RUN_TIME: 0, CONF_WINDOW_DELAY: 0}
    )
    assert result["type"] == "create_entry"
    assert entry.options[CONF_MIN_RUN_TIME] == 0
    assert entry.options[CONF_WINDOW_DELAY] == 0


async def test_options_update_does_not_reset_runtime_values(hass: HomeAssistant):
    """Regression: saving options reset numbers that are not part of the options form."""
    entry, coordinator, _ = await _setup(hass)
    coordinator.cooling_temp = 22.5
    coordinator.free_cooling_max_duration = 90

    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_WINDOW_DELAY: 3})
    await hass.async_block_till_done()

    assert coordinator.cooling_temp == 22.5
    assert coordinator.free_cooling_max_duration == 90


async def test_force_eco_service_validates_and_applies(hass: HomeAssistant):
    _, coordinator, _ = await _setup(hass)
    await hass.services.async_call(DOMAIN, "force_eco", {"enable": True}, blocking=True)
    assert coordinator.force_eco_mode is True
    await hass.services.async_call(DOMAIN, "force_eco", {"enable": False}, blocking=True)
    assert coordinator.force_eco_mode is False


async def test_trigger_ventilation_does_not_overwrite_default_duration(hass: HomeAssistant):
    _, coordinator, _ = await _setup(hass)
    default = coordinator.vent_run_duration
    await hass.services.async_call(DOMAIN, "trigger_ventilation", {"duration": 5}, blocking=True)
    assert coordinator.vent_is_running
    assert coordinator.vent_active_duration == 5
    assert coordinator.vent_run_duration == default


async def test_heat_mode_respects_the_deadband(hass: HomeAssistant):
    """HEAT used to bypass the deadband; only Force Heating does that now."""
    _, coordinator, _ = await _setup(hass)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": "climate.smart_climate", "hvac_mode": "heat"}, blocking=True
    )
    hass.states.async_set(ROOM, "19.8", {"device_class": "temperature"})  # inside the 19.5..20.5 deadband
    await coordinator.async_update()
    assert coordinator.current_action == "off"
    assert "deadband" in coordinator.debug_text.lower()

    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.smart_climate_force_heating"}, blocking=True)
    assert coordinator.force_heating is True
    assert coordinator.current_action == "on"
    assert "Forced heating" in coordinator.debug_text


async def _setup_with_schedule(hass: HomeAssistant, next_event, state="off", room="17.0"):
    hass.states.async_set("schedule.home", state, {"next_event": next_event})
    entry, coordinator, calls = await _setup(hass, schedule="schedule.home")
    hass.states.async_set(ROOM, room, {"device_class": "temperature"})
    return entry, coordinator, calls


async def test_schedule_off_means_eco(hass: HomeAssistant):
    _, coordinator, _ = await _setup_with_schedule(hass, dt_util.utcnow() + timedelta(hours=10))
    await coordinator.async_update()
    assert coordinator.schedule_eco_active is True
    assert coordinator.preheat_active is False
    assert coordinator._determine_base_temperature(False) == coordinator.eco_temp
    assert coordinator.preheat_start is not None  # predicted, in the future
    assert coordinator.preheat_start > dt_util.utcnow()


async def test_schedule_on_means_comfort(hass: HomeAssistant):
    _, coordinator, _ = await _setup_with_schedule(hass, dt_util.utcnow() + timedelta(hours=1), state="on")
    await coordinator.async_update()
    assert coordinator.schedule_eco_active is False
    assert coordinator._determine_base_temperature(False) == coordinator.comfort_temp


async def test_preheat_starts_in_time_and_stays_on(hass: HomeAssistant):
    event = dt_util.utcnow() + timedelta(minutes=60)
    _, coordinator, _ = await _setup_with_schedule(hass, event)
    coordinator.thermal.observe(5.0, 1.0)  # 1 °C/h -> 3 °C needs ~3.3 h, capped at 180 min

    await coordinator.async_update()
    assert coordinator.preheat_active is True
    assert coordinator._determine_base_temperature(False) == coordinator.comfort_temp

    # The room warms up, the estimate shrinks, pre-heating must not stop
    hass.states.async_set(ROOM, "19.9", {"device_class": "temperature"})
    await coordinator.async_update()
    assert coordinator.preheat_active is True

    # Comfort time reached: schedule turns on
    hass.states.async_set("schedule.home", "on", {"next_event": event + timedelta(hours=8)})
    await coordinator.async_update()
    assert coordinator.preheat_active is False and coordinator.schedule_eco_active is False
    assert coordinator._preheat_event is None


async def test_no_preheat_when_away_or_disabled(hass: HomeAssistant):
    event = dt_util.utcnow() + timedelta(minutes=30)
    _, coordinator, _ = await _setup_with_schedule(hass, event)
    coordinator.preheat_enabled = False
    await coordinator.async_update()
    assert coordinator.preheat_active is False
    assert coordinator.schedule_eco_active is True


async def test_unavailable_schedule_keeps_normal_behaviour(hass: HomeAssistant):
    _, coordinator, _ = await _setup_with_schedule(hass, None, state="unavailable")
    await coordinator.async_update()
    assert coordinator.schedule_eco_active is False
    assert coordinator._determine_base_temperature(False) == coordinator.comfort_temp


async def test_statistics_and_learning_are_exposed_and_persisted(hass: HomeAssistant):
    entry, coordinator, _ = await _setup(hass, rated_power=2000)
    with patch("custom_components.smart_climate_control.coordinator.asyncio.sleep", new=AsyncMock()):
        hass.states.async_set(ROOM, "17.0", {"device_class": "temperature"})
        await coordinator.async_update()
    assert coordinator.stats.today.cycles == 1

    assert hass.states.get("sensor.smart_climate_cycles_today").state == "1"
    assert hass.states.get("sensor.smart_climate_cycle_diagnosis").state == "no_data"
    assert hass.states.get("sensor.smart_climate_learned_heating_rate").state == "1.0"
    assert hass.states.get("sensor.smart_climate_estimated_energy_today") is not None
    assert hass.states.get("switch.smart_climate_preheat") is not None

    coordinator.thermal.observe(5.0, 2.5)
    await coordinator.async_save_state()
    restored = type(coordinator)(hass, entry)
    await restored.async_initialize()
    assert restored.thermal.rate_for(5.0) == 2.5
    assert restored.stats.today.cycles == 1
    await restored.async_shutdown()
