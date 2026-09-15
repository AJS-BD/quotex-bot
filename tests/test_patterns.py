# tests/test_patterns.py
import pytest
from patterns import Candle, is_doji, has_dominant_shadows, is_invalid_candle, detect_pattern


def make_candle(o, c, h=None, l=None):
    """Helper to create a candle with optional high/low."""
    if h is None:
        h = max(o, c) + 0.1  # small upper shadow
    if l is None:
        l = min(o, c) - 0.1  # small lower shadow
    return Candle(open=o, close=c, high=h, low=l)


class TestDoji:
    def test_is_doji_equal(self):
        assert is_doji(make_candle(100.0, 100.0)) is True

    def test_is_doji_small_range(self):
        assert is_doji(make_candle(100.0, 100.1)) is True  # 0.1% < 0.2%

    def test_is_not_doji(self):
        assert is_doji(make_candle(100.0, 105.0)) is False

    def test_green_candle(self):
        assert is_doji(make_candle(100.0, 110.0)) is False

    def test_red_candle(self):
        assert is_doji(make_candle(100.0, 90.0)) is False


class TestDominantShadows:
    def test_small_shadows_not_dominant(self):
        # Body=10, shadows=2 -> not dominant
        assert has_dominant_shadows(make_candle(100, 110, 110.1, 99.9)) is False

    def test_large_shadows_dominant(self):
        # Body=1, shadows=10 -> dominant
        assert has_dominant_shadows(make_candle(100, 101, 110, 91)) is True

    def test_equal_shadows_not_dominant(self):
        # Body=10, shadows=10 -> not strictly dominant
        assert has_dominant_shadows(make_candle(100, 110, 115, 95)) is False

    def test_only_upper_shadow_dominant(self):
        # Body=1, upper shadow=10, lower=0 -> dominant
        assert has_dominant_shadows(make_candle(100, 101, 111, 100)) is True

    def test_only_lower_shadow_dominant(self):
        # Body=1, lower shadow=10, upper=0 -> dominant
        assert has_dominant_shadows(make_candle(100, 101, 101, 90)) is True


class TestIsInvalidCandle:
    def test_doji_is_invalid(self):
        assert is_invalid_candle(make_candle(100, 100)) is True

    def test_shadow_dominant_is_invalid(self):
        assert is_invalid_candle(make_candle(100, 101, 110, 91)) is True

    def test_valid_green_candle(self):
        assert is_invalid_candle(make_candle(100, 110, 110.1, 99.9)) is False

    def test_valid_red_candle(self):
        assert is_invalid_candle(make_candle(110, 100, 110.1, 99.9)) is False

    def test_both_doji_and_shadow(self):
        # Perfect doji with huge shadows
        assert is_invalid_candle(make_candle(100, 100, 150, 50)) is True


class TestPatternDetection:
    def test_no_signal_insufficient_candles(self):
        candles = [make_candle(100, 101)] * 3
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_buy_signal_4green_then_red(self):
        # 4 green candles, then 1 red = BUY (CALL)
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
            make_candle(103, 104),  # green
            make_candle(104, 102),  # red
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is not None
        assert signal.direction == "CALL"
        assert signal.asset == "EURUSD_OTC"

    def test_sell_signal_4red_then_green(self):
        candles = [
            make_candle(104, 103),  # red
            make_candle(103, 102),  # red
            make_candle(102, 101),  # red
            make_candle(101, 100),  # red
            make_candle(100, 102),  # green
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is not None
        assert signal.direction == "PUT"

    def test_doji_cancels_pattern_during_streak(self):
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
            make_candle(103, 103, 103.1, 102.9),  # DOJI - cancels
            make_candle(103, 102),  # red
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_doji_cancels_as_counter_candle(self):
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
            make_candle(103, 104),  # green
            make_candle(104, 104, 104.1, 103.9),  # DOJI as counter - cancels
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_dominant_shadows_cancels_during_streak(self):
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
            make_candle(103, 104, 115, 92),  # DOMINANT SHADOWS - cancels
            make_candle(104, 102),  # red
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_dominant_shadows_cancels_as_counter_candle(self):
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
            make_candle(103, 104),  # green
            make_candle(104, 102, 115, 93),  # red but dominant shadows = cancels
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_no_signal_streak_broken_early(self):
        candles = [
            make_candle(100, 101),  # green
            make_candle(101, 102),  # green
            make_candle(102, 101),  # red - breaks streak
            make_candle(101, 102),  # green
            make_candle(102, 103),  # green
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None

    def test_signal_strength_higher_for_longer_streak(self):
        candles_5_green = [make_candle(100 + i, 101 + i) for i in range(5)] + [make_candle(105, 103)]
        candles_4_green = [make_candle(100 + i, 101 + i) for i in range(4)] + [make_candle(104, 102)]

        sig5 = detect_pattern(candles_5_green, "EURUSD_OTC")
        sig4 = detect_pattern(candles_4_green, "EURUSD_OTC")

        assert sig5.strength > sig4.strength

    def test_signal_has_valid_strength_range(self):
        candles = [
            make_candle(100, 101),
            make_candle(101, 102),
            make_candle(102, 103),
            make_candle(103, 104),
            make_candle(104, 102),
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is not None
        assert 50.0 <= signal.strength <= 100.0

    def test_no_signal_same_color_no_reversal(self):
        candles = [
            make_candle(100, 101),
            make_candle(101, 102),
            make_candle(102, 103),
            make_candle(103, 104),
            make_candle(104, 105),  # still green, no reversal
        ]
        signal = detect_pattern(candles, "EURUSD_OTC")
        assert signal is None
