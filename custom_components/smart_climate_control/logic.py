"""Pure decision logic for Smart Climate Control.

Nothing in here imports Home Assistant, so it can be unit tested on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .const import AUTO_COOL_ABOVE_OUTSIDE, AUTO_HEAT_BELOW_OUTSIDE


def choose_logic_mode(
    hvac_mode: str,
    outside_temp: Optional[float],
    room_temp: Optional[float],
    cooling_temp: float,
) -> str:
    """Resolve the configured mode ("heat"/"cool"/"auto") into "heat" or "cool"."""
    if hvac_mode != "auto":
        return hvac_mode
    if outside_temp is not None:
        if outside_temp >= AUTO_COOL_ABOVE_OUTSIDE:
            return "cool"
        if outside_temp <= AUTO_HEAT_BELOW_OUTSIDE:
            return "heat"
    if room_temp is not None and room_temp >= cooling_temp:
        return "cool"
    return "heat"


def next_solar_state(
    state: str,
    below_since: Optional[float],
    now: float,
    *,
    enabled: bool,
    solar_power: float,
    consumption_power: Optional[float],
    offset_threshold: float,
    base_threshold: float,
    consumption_threshold: float,
    drop_delay_min: float,
) -> tuple[str, Optional[float]]:
    """Two-level solar state machine.

    "offset": high production and low consumption, target is shifted by the offset.
    "base":   medium production, the system runs at the normal target.
    "none":   not enough production. The drop back to "none" is delayed.

    Returns the new (state, below_since) pair.
    """
    if not enabled:
        return "none", None

    consumption_ok = consumption_power is None or consumption_power <= consumption_threshold
    if solar_power >= offset_threshold and consumption_ok:
        return "offset", None
    if solar_power >= base_threshold:
        return "base", None

    if state == "none":
        return "none", None
    if below_since is None:
        return state, now
    if (now - below_since) / 60 >= drop_delay_min:
        return "none", None
    return state, below_since


def weather_compensation_offset(outside_temp: float, factor: float, max_boost: float = 5.0) -> float:
    """Extra degrees added to the target when it is freezing outside."""
    if outside_temp >= 0:
        return 0.0
    return min(abs(outside_temp) * factor, max_boost)


@dataclass
class WindowTracker:
    """Delays reacting to open windows/doors and restoring after they close.

    The HVAC is paused once something has been open longer than ``delay_min``
    and stays paused for another ``delay_min`` after everything was closed.
    """

    open_start: Optional[float] = None
    cooldown_start: Optional[float] = None

    def update(self, any_open: bool, now: float, delay_min: float) -> bool:
        """Return True when the HVAC should currently be paused."""
        if any_open:
            self.cooldown_start = None
            if self.open_start is None:
                self.open_start = now
                return False
            return (now - self.open_start) / 60 > delay_min

        if self.open_start is None:
            self.cooldown_start = None
            return False

        if (now - self.open_start) / 60 < delay_min:
            # Short opening, never paused
            self.open_start = None
            self.cooldown_start = None
            return False

        if self.cooldown_start is None:
            self.cooldown_start = now
        if (now - self.cooldown_start) / 60 < delay_min:
            return True

        self.open_start = None
        self.cooldown_start = None
        return False
