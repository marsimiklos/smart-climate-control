"""Run statistics (runtime, cycles, energy) and short-cycling diagnosis.

Pure Python, no Home Assistant imports.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

# A gap longer than this between two samples is not counted (Home Assistant was down, ...)
MAX_STEP_SECONDS = 300
HISTORY_DAYS = 14

# Short-cycling thresholds: at least this many cycles with an average run shorter than this
MIN_CYCLES_FOR_DIAGNOSIS = 4
SHORT_RUN_MINUTES = 10


@dataclass
class DayStats:
    run_seconds: float = 0.0
    cycles: int = 0
    energy_kwh: float = 0.0

    @property
    def run_hours(self) -> float:
        return self.run_seconds / 3600

    @property
    def avg_run_minutes(self) -> Optional[float]:
        return self.run_seconds / self.cycles / 60 if self.cycles else None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DayStats":
        return cls(
            run_seconds=float(data.get("run_seconds", 0.0)),
            cycles=int(data.get("cycles", 0)),
            energy_kwh=float(data.get("energy_kwh", 0.0)),
        )


class RunStats:
    def __init__(self) -> None:
        self.day: Optional[str] = None
        self.today = DayStats()
        self.history: dict[str, DayStats] = {}
        self._last_ts: Optional[float] = None
        self._running = False

    def record(self, now: float, day: str, running: bool, power_w: Optional[float] = None) -> None:
        """Add a sample. ``running`` is the state at ``now``, the interval since the
        previous sample is attributed to the previous state."""
        if self.day is None:
            self.day = day

        # The interval that ends now belongs to the day it started on
        if self._last_ts is not None and self._running:
            step = min(max(now - self._last_ts, 0.0), MAX_STEP_SECONDS)
            self.today.run_seconds += step
            if power_w:
                self.today.energy_kwh += power_w * step / 3600 / 1000

        if day != self.day:
            self.history[self.day] = self.today
            for old in sorted(self.history)[:-HISTORY_DAYS]:
                del self.history[old]
            self.today = DayStats()
            self.day = day

        if running and not self._running:
            self.today.cycles += 1
        self._running = running
        self._last_ts = now

    @property
    def yesterday(self) -> Optional[DayStats]:
        if not self.history:
            return None
        return self.history[max(self.history)]

    def diagnosis(self) -> tuple[str, Optional[float], int]:
        """Return (state, average run minutes, cycles) over yesterday and today.

        state is "no_data", "ok" or "short_cycling".
        """
        days = [self.today] + ([self.yesterday] if self.yesterday else [])
        cycles = sum(d.cycles for d in days)
        run_seconds = sum(d.run_seconds for d in days)
        if cycles < MIN_CYCLES_FOR_DIAGNOSIS:
            return "no_data", None, cycles
        avg = run_seconds / cycles / 60
        return ("short_cycling" if avg < SHORT_RUN_MINUTES else "ok"), avg, cycles

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "today": asdict(self.today),
            "history": {day: asdict(stats) for day, stats in self.history.items()},
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "RunStats":
        stats = cls()
        if not data:
            return stats
        stats.day = data.get("day")
        stats.today = DayStats.from_dict(data.get("today", {}))
        stats.history = {day: DayStats.from_dict(d) for day, d in data.get("history", {}).items()}
        return stats
