"""Learns how fast the house heats up and predicts the pre-heat time.

Pure Python, no Home Assistant imports.
"""
from __future__ import annotations

import math
from typing import Any, Optional

# Upper edges of the outside temperature bins (°C), the last bin is open ended
BIN_EDGES = (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0)

DEFAULT_RATE = 1.0  # °C/h, used until something has been learned
MIN_RATE = 0.1
EMA_ALPHA = 0.3     # weight of a new observation
SAFETY_MARGIN = 1.1

# A warm-up episode needs a real gap to the target and must last long enough to be meaningful
MIN_GAP = 0.8            # °C below the target when heating starts
REACHED_GAP = 0.2        # episode ends when the room is this close to the target
MIN_DURATION_H = 1 / 3
MAX_DURATION_H = 6.0
MIN_RISE = 0.3           # °C


def bin_index(outside_temp: float) -> int:
    for index, edge in enumerate(BIN_EDGES):
        if outside_temp < edge:
            return index
    return len(BIN_EDGES)


class ThermalModel:
    """Heating rate (°C/h) per outside temperature bin, as a moving average."""

    def __init__(self) -> None:
        self.rates: dict[int, float] = {}
        self.counts: dict[int, int] = {}

    @property
    def samples(self) -> int:
        return sum(self.counts.values())

    def observe(self, outside_temp: float, rate: float) -> None:
        index = bin_index(outside_temp)
        if index in self.rates:
            self.rates[index] += EMA_ALPHA * (rate - self.rates[index])
        else:
            self.rates[index] = rate
        self.counts[index] = self.counts.get(index, 0) + 1

    def rate_for(self, outside_temp: float) -> float:
        index = bin_index(outside_temp)
        if index in self.rates:
            return max(self.rates[index], MIN_RATE)
        if self.rates:
            nearest = min(self.rates, key=lambda known: abs(known - index))
            return max(self.rates[nearest], MIN_RATE)
        return DEFAULT_RATE

    def preheat_minutes(self, delta: float, outside_temp: float, max_minutes: float) -> int:
        """Minutes of heating needed to raise the room by ``delta`` °C."""
        if delta <= 0 or max_minutes <= 0:
            return 0
        minutes = round(delta / self.rate_for(outside_temp) * 60 * SAFETY_MARGIN, 6)
        return int(min(math.ceil(minutes), max_minutes))

    def bins(self) -> dict[str, dict[str, float]]:
        """Human readable view for diagnostics."""
        labels = {}
        lower = None
        for index in range(len(BIN_EDGES) + 1):
            upper = BIN_EDGES[index] if index < len(BIN_EDGES) else None
            if lower is None:
                label = f"< {upper:g}°C"
            elif upper is None:
                label = f">= {lower:g}°C"
            else:
                label = f"{lower:g}..{upper:g}°C"
            if index in self.rates:
                labels[label] = {"rate": round(self.rates[index], 2), "samples": self.counts[index]}
            lower = upper
        return labels

    def to_dict(self) -> dict[str, Any]:
        return {"rates": {str(k): v for k, v in self.rates.items()}, "counts": {str(k): v for k, v in self.counts.items()}}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "ThermalModel":
        model = cls()
        if data:
            model.rates = {int(k): float(v) for k, v in data.get("rates", {}).items()}
            model.counts = {int(k): int(v) for k, v in data.get("counts", {}).items()}
        return model


class WarmupTracker:
    """Detects warm-up episodes and measures their heating rate."""

    def __init__(self) -> None:
        self._start: Optional[tuple[float, float]] = None  # (time, room)
        self._last: Optional[tuple[float, float]] = None
        self._outside_sum = 0.0
        self._outside_count = 0

    def update(
        self, now: float, heating: bool, room: Optional[float], outside: float, target: float
    ) -> Optional[tuple[float, float]]:
        """Feed one sample. Returns (rate °C/h, mean outside °C) when an episode ended."""
        if not heating or room is None:
            return self._finish()

        if self._start is None:
            if target - room >= MIN_GAP:
                self._start = self._last = (now, room)
                self._outside_sum, self._outside_count = outside, 1
            return None

        self._last = (now, room)
        self._outside_sum += outside
        self._outside_count += 1
        if room >= target - REACHED_GAP:
            return self._finish()
        return None

    def _finish(self) -> Optional[tuple[float, float]]:
        start, last = self._start, self._last
        outside_mean = self._outside_sum / self._outside_count if self._outside_count else 0.0
        self._start = self._last = None
        self._outside_sum, self._outside_count = 0.0, 0
        if start is None or last is None:
            return None
        hours = (last[0] - start[0]) / 3600
        rise = last[1] - start[1]
        if hours < MIN_DURATION_H or hours > MAX_DURATION_H or rise < MIN_RISE:
            return None
        return rise / hours, outside_mean
