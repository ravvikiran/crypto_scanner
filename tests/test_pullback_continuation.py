"""
Unit tests for Pullback Continuation detection in SetupDetector.

Tests pullback detection to EMA20/EMA50, bullish reclaim validation,
volume confirmation, entry/stop-loss calculation, and invalidation.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import pytest
from datetime import datetime, timedelta

import pandas as pd

from streaming.models import OHLCV
from streaming.models import SetupType, SetupState
from detectors.setup_detector import (
    detect_pullback_continuation,
    _calculate_ema,
    _calculate_atr14,
    _calculate_volume_ma30,
)


def _make_candle(
    timestamp: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> OHLCV:
    """Helper to create a single OHLCV candle."""
    return OHLCV(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_uptrend_candles(
    count: int,
    start_price: float = 90.0,
    trend_slope: float = 0.2,
    volatility: float = 1.5,
    base_volume: float = 1000.0,
    start_time: datetime = None,
) -> list:
    """
    Generate candles in an uptrend suitable for EMA20/EMA50 calculation.

    Creates a series of candles with a gradual upward trend so that
    EMA20 > EMA50 and price is above both EMAs.
    """
    if start_time is None:
        start_time = datetime(2024, 1, 1)

    candles = []
    for i in range(count):
        mid = start_price + (i * trend_slope)
        open_price = mid - volatility * 0.1
        close = mid + volatility * 0.1
        high = mid + volatility / 2
        low = mid - volatility / 2
        volume = base_volume + (i * 2)

        candles.append(
            _make_candle(
                timestamp=start_time + timedelta(hours=i),
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return candles


def _build_pullback_candles(
    pullback_to_ema: str = "ema20",
    trigger_volume_multiplier: float = 2.0,
    trigger_close_position: float = 0.75,
    close_below_ema: bool = False,
    close_below_ema_pct: float = 0.0,
    miss_ema_proximity: bool = False,
) -> list:
    """
    Build a candle sequence with an uptrend followed by a pullback trigger candle.

    Parameters
    ----------
    pullback_to_ema : str
        Which EMA to pull back to ("ema20" or "ema50").
    trigger_volume_multiplier : float
        Volume of trigger candle relative to MA30.
    trigger_close_position : float
        Where the close sits in the candle range (0.0 = low, 1.0 = high).
    close_below_ema : bool
        If True, the trigger candle closes below the EMA.
    close_below_ema_pct : float
        How far below the EMA the close is (as a percentage).
    miss_ema_proximity : bool
        If True, the candle low doesn't come within 0.5% of the EMA.
    """
    # Generate 55 uptrend candles (enough for EMA50 + some buffer)
    candles = _make_uptrend_candles(
        count=55,
        start_price=90.0,
        trend_slope=0.2,
        volatility=1.5,
        base_volume=1000.0,
    )

    # Calculate current EMAs to know where to place the pullback
    closes = pd.Series([c.close for c in candles])
    ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

    target_ema = ema20 if pullback_to_ema == "ema20" else ema50

    # Calculate volume MA30 for the trigger candle volume
    volumes = [c.volume for c in candles]
    vol_ma30 = sum(volumes[-30:]) / 30
    trigger_volume = vol_ma30 * trigger_volume_multiplier

    # Build the trigger candle
    # The low should touch or come within 0.5% of the target EMA
    if miss_ema_proximity:
        # Place low far from EMA (more than 0.5% away)
        candle_low = target_ema + target_ema * 0.02  # 2% above EMA
    else:
        # Place low right at the EMA (within 0.5%)
        candle_low = target_ema - target_ema * 0.001  # 0.1% below EMA

    # Calculate candle range and close based on close_position
    candle_range = 2.0  # Fixed range for predictability
    candle_high = candle_low + candle_range

    if close_below_ema:
        # Close below the EMA by the specified percentage
        candle_close = target_ema * (1 - close_below_ema_pct)
    else:
        # Close above EMA, at the specified position in the range
        candle_close = candle_low + candle_range * trigger_close_position
        # Ensure close is above the target EMA
        if candle_close <= target_ema:
            candle_close = target_ema + 0.1

    candle_open = candle_low + candle_range * 0.2

    # Adjust high to ensure close_position is correct
    # close_position = (close - low) / (high - low)
    # We want: trigger_close_position = (candle_close - candle_low) / (candle_high - candle_low)
    if not close_below_ema:
        actual_position = (candle_close - candle_low) / (candle_high - candle_low)
        if actual_position < trigger_close_position:
            # Adjust high down to get desired close position
            candle_high = candle_low + (candle_close - candle_low) / trigger_close_position

    trigger_candle = _make_candle(
        timestamp=datetime(2024, 3, 1),
        open_price=candle_open,
        high=candle_high,
        low=candle_low,
        close=candle_close,
        volume=trigger_volume,
    )

    return candles + [trigger_candle]


class TestEMACalculation:
    """Tests for EMA calculation helper."""

    def test_ema20_calculation(self):
        """EMA20 should be calculated correctly using pandas EWM."""
        values = pd.Series(range(1, 31), dtype=float)
        ema = _calculate_ema(values, span=20)
        assert len(ema) == 30
        # EMA should be less than the last value in an uptrend
        assert ema.iloc[-1] < values.iloc[-1]
        assert ema.iloc[-1] > values.iloc[0]

    def test_ema50_calculation(self):
        """EMA50 should lag more than EMA20 in an uptrend."""
        values = pd.Series(range(1, 61), dtype=float)
        ema20 = _calculate_ema(values, span=20)
        ema50 = _calculate_ema(values, span=50)
        # In an uptrend, EMA20 should be above EMA50
        assert ema20.iloc[-1] > ema50.iloc[-1]


class TestPullbackDetection:
    """Tests for pullback detection to EMA20/EMA50 (Requirement 7.1, 7.2)."""

    def test_valid_pullback_to_ema20_returns_setup(self):
        """A valid pullback to EMA20 with bullish reclaim should return a setup."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.setup_type == SetupType.PULLBACK_CONTINUATION
        assert result.state == SetupState.DETECTED

    def test_valid_pullback_to_ema50_returns_setup(self):
        """A valid pullback to EMA50 with bullish reclaim should return a setup."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema50",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.setup_type == SetupType.PULLBACK_CONTINUATION

    def test_no_detection_when_price_far_from_ema(self):
        """No pullback detected if price doesn't come within 0.5% of EMA."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
            miss_ema_proximity=True,
        )
        result = detect_pullback_continuation(candles)
        assert result is None


class TestBullishReclaimValidation:
    """Tests for bullish reclaim candle validation (Requirement 7.2)."""

    def test_no_detection_when_close_below_ema(self):
        """No setup if trigger candle closes below the EMA."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            close_below_ema=True,
            close_below_ema_pct=0.005,  # 0.5% below (not invalidation level)
        )
        result = detect_pullback_continuation(candles)
        assert result is None

    def test_no_detection_when_close_in_lower_half(self):
        """No setup if close is not in upper 50% of candle range."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.30,  # Lower 50%
        )
        result = detect_pullback_continuation(candles)
        assert result is None


class TestVolumeConfirmation:
    """Tests for volume confirmation (Requirement 7.3)."""

    def test_no_detection_when_volume_insufficient(self):
        """No setup if volume <= 1.5x MA30."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=1.0,  # Not enough volume
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is None

    def test_detection_with_high_volume(self):
        """Setup detected when volume > 1.5x MA30."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.5,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None


class TestEntryAndStopLoss:
    """Tests for entry price and stop-loss calculation (Requirements 7.4, 7.5)."""

    def test_entry_price_is_trigger_candle_high(self):
        """Entry should be set at the trigger candle's high (Req 7.4)."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.entry_price == candles[-1].high

    def test_stop_loss_is_min_of_candle_low_and_atr_stop(self):
        """Stop-loss should be min(trigger_low, entry - 1.2*ATR14) (Req 7.5)."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None

        atr14 = _calculate_atr14(candles)
        entry = candles[-1].high
        atr_stop = entry - 1.2 * atr14
        expected_stop = min(candles[-1].low, atr_stop)

        assert result.stop_loss == pytest.approx(expected_stop)

    def test_targets_calculated_correctly(self):
        """Target1 = entry + 1R, Target2 = entry + 2R."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None

        risk = result.entry_price - result.stop_loss
        assert risk > 0
        assert result.target_1 == pytest.approx(result.entry_price + risk)
        assert result.target_2 == pytest.approx(result.entry_price + 2 * risk)


class TestInvalidation:
    """Tests for setup invalidation (Requirement 7.6)."""

    def test_invalidation_when_close_below_ema_by_more_than_1pct(self):
        """Setup invalidated if price closes below EMA by > 1.0%."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            close_below_ema=True,
            close_below_ema_pct=0.015,  # 1.5% below EMA
        )
        result = detect_pullback_continuation(candles)
        assert result is None


class TestInsufficientData:
    """Tests for edge cases with insufficient data."""

    def test_returns_none_with_too_few_candles(self):
        """Should return None with fewer than 50 candles."""
        candles = _make_uptrend_candles(count=30)
        result = detect_pullback_continuation(candles)
        assert result is None

    def test_returns_none_with_exactly_50_candles_no_pullback(self):
        """Should return None when there's no pullback to EMA."""
        # 50 candles in a strong uptrend - price far above EMAs
        candles = _make_uptrend_candles(
            count=50,
            start_price=90.0,
            trend_slope=0.5,  # Strong trend keeps price far from EMAs
        )
        result = detect_pullback_continuation(candles)
        assert result is None


class TestSetupMetadata:
    """Tests for correct setup metadata."""

    def test_setup_type_is_pullback_continuation(self):
        """Setup type should be PULLBACK_CONTINUATION."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.setup_type == SetupType.PULLBACK_CONTINUATION

    def test_timeframe_is_1h(self):
        """Timeframe should be 1h."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.timeframe == "1h"
        assert result.trigger_timeframe == "15m"

    def test_risk_reward_is_2(self):
        """Risk-reward ratio should be 2.0 (target_2 / risk)."""
        candles = _build_pullback_candles(
            pullback_to_ema="ema20",
            trigger_volume_multiplier=2.0,
            trigger_close_position=0.75,
        )
        result = detect_pullback_continuation(candles)
        assert result is not None
        assert result.risk_reward == pytest.approx(2.0)
