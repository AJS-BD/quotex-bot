# patterns.py
from dataclasses import dataclass
from typing import List, Optional
from database import Signal


@dataclass
class Candle:
    open: float
    close: float
    high: float
    low: float

    @property
    def color(self) -> str:
        if self.close > self.open:
            return "green"
        elif self.close < self.open:
            return "red"
        return "doji"

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def total_shadow(self) -> float:
        return self.upper_shadow + self.lower_shadow


def is_doji(candle: Candle, threshold: float = 0.002) -> bool:
    """Check if candle is a doji (open ~= close within threshold %)."""
    if candle.open == 0:
        return False
    return abs(candle.close - candle.open) / candle.open < threshold


def has_dominant_shadows(candle: Candle) -> bool:
    """Check if shadows are larger than body (spinning top, hammer, etc.)."""
    return candle.total_shadow > candle.body_size


def is_invalid_candle(candle: Candle) -> bool:
    """Check if a candle invalidates the pattern (doji OR shadow-dominant)."""
    return is_doji(candle) or has_dominant_shadows(candle)


def detect_pattern(candles: List[Candle], asset: str) -> Optional[Signal]:
    """
    Detect 4-candle-streak reversal pattern.

    Rules:
    - 4+ consecutive non-invalid candles in same direction
    - Counter-candle of opposite color (non-invalid) triggers signal
    - Doji or shadow-dominant candle at any point cancels the pattern entirely
    - Signal direction follows the trend (green streak -> BUY/CALL)
    """
    if len(candles) < 5:
        return None

    # Check last 5 candles for any invalid candle
    last_5 = candles[-5:]
    for c in last_5:
        if is_invalid_candle(c):
            return None

    # The counter-candle is the last one
    counter_candle = candles[-1]
    prev_candle = candles[-2]

    # Counter must be opposite color
    if counter_candle.color == prev_candle.color:
        return None

    # Count streak of prev_candle's color (going backwards)
    streak_color = prev_candle.color
    streak = 1
    for i in range(len(candles) - 3, -1, -1):
        if candles[i].color == streak_color:
            streak += 1
        else:
            break

    if streak < 4:
        return None

    # Calculate strength based on streak length and body sizes
    avg_body = sum(c.body_size for c in candles[-5:-1]) / 4
    base_strength = min(50 + streak * 5 + avg_body * 2, 100)

    # Direction follows the trend
    direction = "CALL" if streak_color == "green" else "PUT"

    return Signal(
        asset=asset,
        direction=direction,
        strength=round(base_strength, 1)
    )
