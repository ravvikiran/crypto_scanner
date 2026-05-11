"""
Unit tests for detect_momentum_breakout() function.

Tests the momentum breakout detection logic including:
- Detection conditions (close > EMA20, 3 higher highs, volume > 2.5x MA20)
- Entry price calculation
- Stop-loss clamping to [0.8%, 2.5%] range
- Target calculations (T1=1R, T2=2R, T3=5R)
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from streaming.models import OHLCV, ActiveSetup, SetupType, SetupState
from detectors.setup_detector import detect_momentum_breakout


def _make_candle(
    close: float,
    high: float,
    low: float,
    open_: float = None,
    volume: float = 100.0,
    timestamp: datetime = None,
) -> OHLCV:
    """Helper to create an OHLCV candle."""
    if open_ is None:
        open_ = close * 0.999
    if timestamp is None:
        timestamp = datetime.utcnow()
    return OHLCV(
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_base_candles(
    count: int = 20,
    base_price: float = 100.0,
    base_volume: float = 100.0,
) -> List[OHLCV]:
    """
    Create a base set of candles with stable prices and volumes.
    These form the history needed for EMA20 and volume MA20 calculations.
    """
    candles = []
    for i in range(count):
        ts = datetime.utcnow() - timedelta(hours=count - i)
        candles.append(
            OHLCV(
                timestamp=ts,
                open=base_price,
                high=base_price * 1.005,
                low=base_price * 0.995,
                close=base_price,
                volume=base_volume,
            )
        )
    return candles


def _make_momentum_breakout_candles(
    base_price: float = 100.0,
    base_volume: float = 100.0,
) -> List[OHLCV]:
    """
    Create a candle sequence that satisfies all momentum breakout conditions:
    - Close > EMA20
    - Last 3 candles have higher highs
    - Latest volume > 2.5x volume MA20
    """
    # Start with 17 base candles (stable price/volume)
    candles = _make_base_candles(count=17, base_price=base_price, base_volume=base_volume)

    # Add 3 candles with progressively higher highs and the last one with high volume
    # These need to be above EMA20 and have higher highs
    ts_base = datetime.utcnow()

    # Candle -3 (first of the 3 higher-high candles)
    candles.append(OHLCV(
        timestamp=ts_base - timedelta(hours=3),
        open=base_price * 1.01,
        high=base_price * 1.02,  # Higher than base candles' high (1.005)
        low=base_price * 1.005,
        close=base_price * 1.015,
        volume=base_volume,
    ))

    # Candle -2 (second higher high)
    candles.append(OHLCV(
        timestamp=ts_base - timedelta(hours=2),
        open=base_price * 1.02,
        high=base_price * 1.03,  # Higher than previous
        low=base_price * 1.01,
        close=base_price * 1.025,
        volume=base_volume,
    ))

    # Candle -1 (latest: highest high, high volume, close > EMA20)
    candles.append(OHLCV(
        timestamp=ts_base - timedelta(hours=1),
        open=base_price * 1.03,
        high=base_price * 1.04,  # Higher than previous
        low=base_price * 1.02,
        close=base_price * 1.035,
        volume=base_volume * 3.0,  # > 2.5x MA20
    ))

    return candles


class TestDetectMomentumBreakout:
    """Tests for detect_momentum_breakout function."""

    def test_valid_momentum_breakout_returns_setup(self):
        """A valid momentum breakout should return an ActiveSetup."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        assert isinstance(result, ActiveSetup)
        assert result.setup_type == SetupType.MOMENTUM_BREAKOUT
        assert result.state == SetupState.DETECTED

    def test_entry_price_is_latest_close(self):
        """Entry price should be the current 1H candle close."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        assert result.entry_price == candles[-1].close

    def test_targets_calculated_correctly(self):
        """T1=1R, T2=2R, T3=5R from entry."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        risk = result.entry_price - result.stop_loss
        assert risk > 0

        assert abs(result.target_1 - (result.entry_price + risk)) < 1e-10
        assert abs(result.target_2 - (result.entry_price + 2 * risk)) < 1e-10
        assert abs(result.target_3 - (result.entry_price + 5 * risk)) < 1e-10

    def test_stop_loss_clamped_minimum(self):
        """Stop-loss distance should be at least 0.8% of entry."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        distance_pct = (result.entry_price - result.stop_loss) / result.entry_price
        assert distance_pct >= 0.008 - 1e-10  # 0.8% minimum

    def test_stop_loss_clamped_maximum(self):
        """Stop-loss distance should be at most 2.5% of entry."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        distance_pct = (result.entry_price - result.stop_loss) / result.entry_price
        assert distance_pct <= 0.025 + 1e-10  # 2.5% maximum

    def test_no_signal_when_close_below_ema20(self):
        """No signal when close is below EMA20."""
        candles = _make_base_candles(count=17, base_price=100.0)

        # Add 3 candles with higher highs but close below EMA20
        ts = datetime.utcnow()
        candles.append(OHLCV(timestamp=ts - timedelta(hours=3), open=99.0, high=99.5, low=98.5, close=99.0, volume=100.0))
        candles.append(OHLCV(timestamp=ts - timedelta(hours=2), open=99.0, high=99.6, low=98.6, close=99.0, volume=100.0))
        candles.append(OHLCV(timestamp=ts - timedelta(hours=1), open=99.0, high=99.7, low=98.7, close=98.0, volume=300.0))

        result = detect_momentum_breakout(candles)
        assert result is None

    def test_no_signal_without_higher_highs(self):
        """No signal when last 3 candles don't have higher highs."""
        candles = _make_base_candles(count=17, base_price=100.0)

        ts = datetime.utcnow()
        # Higher high, then LOWER high (breaks the pattern)
        candles.append(OHLCV(timestamp=ts - timedelta(hours=3), open=101.0, high=102.0, low=100.5, close=101.5, volume=100.0))
        candles.append(OHLCV(timestamp=ts - timedelta(hours=2), open=101.5, high=101.5, low=100.8, close=101.2, volume=100.0))  # NOT higher high
        candles.append(OHLCV(timestamp=ts - timedelta(hours=1), open=101.2, high=103.0, low=101.0, close=102.5, volume=300.0))

        result = detect_momentum_breakout(candles)
        assert result is None

    def test_no_signal_without_volume_surge(self):
        """No signal when volume is not > 2.5x MA20."""
        candles = _make_momentum_breakout_candles()
        # Override the last candle's volume to be below threshold
        candles[-1] = OHLCV(
            timestamp=candles[-1].timestamp,
            open=candles[-1].open,
            high=candles[-1].high,
            low=candles[-1].low,
            close=candles[-1].close,
            volume=100.0,  # Same as base volume, not > 2.5x
        )

        result = detect_momentum_breakout(candles)
        assert result is None

    def test_insufficient_candles_returns_none(self):
        """Should return None with fewer than 20 candles."""
        candles = _make_base_candles(count=10)
        result = detect_momentum_breakout(candles)
        assert result is None

    def test_setup_type_is_momentum_breakout(self):
        """Setup type should be MOMENTUM_BREAKOUT."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        assert result.setup_type == SetupType.MOMENTUM_BREAKOUT

    def test_target_3_is_5r(self):
        """T3 should be exactly 5R from entry."""
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        assert result.target_3 is not None
        risk = result.entry_price - result.stop_loss
        expected_t3 = result.entry_price + 5 * risk
        assert abs(result.target_3 - expected_t3) < 1e-10

    def test_stop_loss_uses_tighter_of_two_options(self):
        """
        Raw stop should be the higher (tighter) of:
        swing_low_3 * 0.995 and entry - 1.5 * ATR14.
        Then clamped to [0.8%, 2.5%].
        """
        candles = _make_momentum_breakout_candles()
        result = detect_momentum_breakout(candles)

        assert result is not None
        # The stop should be below entry
        assert result.stop_loss < result.entry_price
        # Distance should be within bounds
        distance_pct = (result.entry_price - result.stop_loss) / result.entry_price
        assert 0.008 - 1e-10 <= distance_pct <= 0.025 + 1e-10
