"""Tests of the run statistics and the thermal model."""
from custom_components.smart_climate_control.stats import RunStats
from custom_components.smart_climate_control.thermal import (
    DEFAULT_RATE, ThermalModel, WarmupTracker, bin_index,
)


class TestRunStats:
    def test_counts_runtime_and_cycles(self):
        stats = RunStats()
        stats.record(0, "d1", False)
        stats.record(60, "d1", True)    # cycle 1 starts
        stats.record(120, "d1", True)   # 60 s running
        stats.record(180, "d1", False)  # 60 s more
        stats.record(240, "d1", True)   # cycle 2
        assert stats.today.cycles == 2
        assert stats.today.run_seconds == 120

    def test_energy_from_power(self):
        stats = RunStats()
        stats.record(0, "d1", True, 2000)
        stats.record(60, "d1", True, 2000)
        assert abs(stats.today.energy_kwh - 2000 * 60 / 3600 / 1000) < 1e-9

    def test_long_gaps_are_capped(self):
        stats = RunStats()
        stats.record(0, "d1", True)
        stats.record(10_000, "d1", True)
        assert stats.today.run_seconds == 300

    def test_day_rollover_keeps_history(self):
        stats = RunStats()
        stats.record(0, "d1", True)
        stats.record(60, "d1", True)
        stats.record(120, "d2", False)
        assert stats.today.cycles == 0 and stats.today.run_seconds == 0
        assert stats.yesterday.cycles == 1 and stats.yesterday.run_seconds == 120

    def test_history_is_trimmed(self):
        stats = RunStats()
        for i in range(30):
            stats.record(i * 60, f"2026-01-{i + 1:02d}", False)
        assert len(stats.history) == 14

    def test_diagnosis(self):
        stats = RunStats()
        assert stats.diagnosis()[0] == "no_data"
        t = 0
        for _ in range(5):  # five 2-minute runs
            for running in (True, True, True, False):
                stats.record(t, "d1", running)
                t += 60
        state, avg, cycles = stats.diagnosis()
        assert (state, cycles) == ("short_cycling", 5) and avg < 10

    def test_healthy_cycles(self):
        stats = RunStats()
        t = 0
        for _ in range(4):
            for running in [True] * 5 + [False]:
                stats.record(t, "d1", running)
                t += 300
        assert stats.diagnosis()[0] == "ok"

    def test_roundtrip(self):
        stats = RunStats()
        stats.record(0, "d1", True, 1000)
        stats.record(60, "d2", True, 1000)
        restored = RunStats.from_dict(stats.to_dict())
        assert restored.day == "d2" and restored.history["d1"].cycles == 1


class TestThermalModel:
    def test_default_until_learned(self):
        assert ThermalModel().rate_for(3.0) == DEFAULT_RATE

    def test_first_observation_is_taken_as_is(self):
        model = ThermalModel()
        model.observe(2.0, 2.0)
        assert model.rate_for(3.0) == 2.0

    def test_moving_average(self):
        model = ThermalModel()
        model.observe(2.0, 2.0)
        model.observe(3.0, 1.0)
        assert 1.0 < model.rate_for(2.0) < 2.0

    def test_unlearned_bin_uses_nearest(self):
        model = ThermalModel()
        model.observe(-8.0, 0.5)
        assert model.rate_for(12.0) == 0.5

    def test_preheat_minutes(self):
        model = ThermalModel()
        model.observe(5.0, 2.0)
        # 3 °C at 2 °C/h = 90 min, plus 10 % margin
        assert model.preheat_minutes(3.0, 7.0, 240) == 99
        assert model.preheat_minutes(3.0, 7.0, 60) == 60
        assert model.preheat_minutes(0.0, 7.0, 240) == 0
        assert model.preheat_minutes(-1.0, 7.0, 240) == 0
        assert model.preheat_minutes(3.0, 7.0, 0) == 0

    def test_bins(self):
        assert bin_index(-20) == 0 and bin_index(-10) == 1 and bin_index(20) == 6

    def test_roundtrip(self):
        model = ThermalModel()
        model.observe(2.0, 1.5)
        restored = ThermalModel.from_dict(model.to_dict())
        assert restored.rate_for(2.0) == 1.5 and restored.samples == 1
        assert "0..5°C" in restored.bins()


class TestWarmupTracker:
    def test_measures_a_warmup(self):
        tracker = WarmupTracker()
        target = 21.0
        assert tracker.update(0, True, 18.0, 4.0, target) is None
        assert tracker.update(1800, True, 19.0, 4.0, target) is None
        result = tracker.update(3600, True, 20.9, 4.0, target)  # reached
        rate, outside = result
        assert abs(rate - 2.9) < 1e-9 and outside == 4.0

    def test_small_gap_is_not_a_warmup(self):
        tracker = WarmupTracker()
        assert tracker.update(0, True, 20.5, 4.0, 21.0) is None
        assert tracker.update(3600, False, 20.9, 4.0, 21.0) is None

    def test_too_short_is_ignored(self):
        tracker = WarmupTracker()
        tracker.update(0, True, 18.0, 4.0, 21.0)
        tracker.update(300, True, 18.5, 4.0, 21.0)
        assert tracker.update(600, False, 18.5, 4.0, 21.0) is None

    def test_interrupted_warmup_still_counts_when_long_enough(self):
        tracker = WarmupTracker()
        tracker.update(0, True, 18.0, 4.0, 21.0)
        tracker.update(3600, True, 19.5, 4.0, 21.0)
        rate, _ = tracker.update(3660, False, 19.5, 4.0, 21.0)
        assert abs(rate - 1.5) < 1e-9
