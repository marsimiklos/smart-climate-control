"""Tests of the pure decision logic."""
from custom_components.smart_climate_control.logic import (
    WindowTracker,
    choose_logic_mode,
    next_solar_state,
    weather_compensation_offset,
)


class TestChooseLogicMode:
    def test_fixed_modes_are_kept(self):
        assert choose_logic_mode("heat", 30.0, 30.0, 24.0) == "heat"
        assert choose_logic_mode("cool", -5.0, 10.0, 24.0) == "cool"

    def test_auto_uses_outside_temperature(self):
        assert choose_logic_mode("auto", 25.0, 18.0, 24.0) == "cool"
        assert choose_logic_mode("auto", 10.0, 30.0, 24.0) == "heat"

    def test_auto_in_between_uses_room_temperature(self):
        assert choose_logic_mode("auto", 19.0, 24.5, 24.0) == "cool"
        assert choose_logic_mode("auto", 19.0, 21.0, 24.0) == "heat"

    def test_auto_without_outside_sensor_can_still_cool(self):
        assert choose_logic_mode("auto", None, 26.0, 24.0) == "cool"
        assert choose_logic_mode("auto", None, 20.0, 24.0) == "heat"

    def test_auto_without_any_data_defaults_to_heat(self):
        assert choose_logic_mode("auto", None, None, 24.0) == "heat"


SOLAR = dict(offset_threshold=2000, base_threshold=1200, consumption_threshold=500, drop_delay_min=10)


class TestSolarState:
    def test_disabled_resets(self):
        assert next_solar_state("offset", 5.0, 100.0, enabled=False, solar_power=9000, consumption_power=0, **SOLAR) == ("none", None)

    def test_high_production_low_consumption_is_offset(self):
        assert next_solar_state("none", None, 100.0, enabled=True, solar_power=2500, consumption_power=100, **SOLAR) == ("offset", None)

    def test_high_production_without_consumption_sensor_is_offset(self):
        assert next_solar_state("none", None, 100.0, enabled=True, solar_power=2500, consumption_power=None, **SOLAR) == ("offset", None)

    def test_high_consumption_limits_to_base(self):
        assert next_solar_state("none", None, 100.0, enabled=True, solar_power=2500, consumption_power=900, **SOLAR) == ("base", None)

    def test_medium_production_is_base(self):
        assert next_solar_state("offset", 50.0, 100.0, enabled=True, solar_power=1500, consumption_power=0, **SOLAR) == ("base", None)

    def test_drop_is_delayed(self):
        state, since = next_solar_state("offset", None, 1000.0, enabled=True, solar_power=0, consumption_power=0, **SOLAR)
        assert (state, since) == ("offset", 1000.0)
        # 9 minutes later: still active
        state, since = next_solar_state(state, since, 1000.0 + 9 * 60, enabled=True, solar_power=0, consumption_power=0, **SOLAR)
        assert state == "offset"
        # 10 minutes later: released
        state, since = next_solar_state(state, since, 1000.0 + 10 * 60, enabled=True, solar_power=0, consumption_power=0, **SOLAR)
        assert (state, since) == ("none", None)

    def test_recovery_cancels_drop_timer(self):
        state, since = next_solar_state("base", 1000.0, 1100.0, enabled=True, solar_power=1300, consumption_power=0, **SOLAR)
        assert (state, since) == ("base", None)

    def test_none_stays_none_below_threshold(self):
        assert next_solar_state("none", None, 100.0, enabled=True, solar_power=0, consumption_power=0, **SOLAR) == ("none", None)


class TestWeatherCompensation:
    def test_no_compensation_when_not_freezing(self):
        assert weather_compensation_offset(0.0, 0.5) == 0.0
        assert weather_compensation_offset(8.0, 0.5) == 0.0

    def test_scales_with_cold(self):
        assert weather_compensation_offset(-4.0, 0.5) == 2.0

    def test_is_capped(self):
        assert weather_compensation_offset(-30.0, 0.5) == 5.0


class TestWindowTracker:
    DELAY = 1.0  # minutes

    def test_short_opening_never_pauses(self):
        tracker = WindowTracker()
        assert tracker.update(True, 0, self.DELAY) is False
        assert tracker.update(True, 30, self.DELAY) is False
        assert tracker.update(False, 40, self.DELAY) is False
        assert tracker.open_start is None

    def test_pauses_after_delay(self):
        tracker = WindowTracker()
        tracker.update(True, 0, self.DELAY)
        assert tracker.update(True, 61, self.DELAY) is True

    def test_stays_paused_for_cooldown_after_close(self):
        tracker = WindowTracker()
        tracker.update(True, 0, self.DELAY)
        assert tracker.update(True, 120, self.DELAY) is True
        assert tracker.update(False, 130, self.DELAY) is True   # cooldown starts
        assert tracker.update(False, 180, self.DELAY) is True   # 50 s into the cooldown
        assert tracker.update(False, 191, self.DELAY) is False  # 61 s: restored
        assert tracker.open_start is None and tracker.cooldown_start is None

    def test_reopen_during_cooldown_cancels_it(self):
        tracker = WindowTracker()
        tracker.update(True, 0, self.DELAY)
        tracker.update(True, 120, self.DELAY)
        tracker.update(False, 130, self.DELAY)
        assert tracker.update(True, 140, self.DELAY) is True
        assert tracker.cooldown_start is None

    def test_zero_delay_pauses_immediately_on_second_tick(self):
        tracker = WindowTracker()
        assert tracker.update(True, 0, 0) is False
        assert tracker.update(True, 1, 0) is True
