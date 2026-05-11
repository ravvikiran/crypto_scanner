"""
Unit tests for TrendFilter setup-type-specific evaluation.

Tests the routing logic based on setup_type parameter:
- MOMENTUM_BREAKOUT: only checks 1H close > EMA20
- COMPRESSION_BREAKOUT / PULLBACK_CONTINUATION: requires all 3 4H conditions with min 50 candles
- None (legacy): requires all 3 4H conditions with min 200 candles

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import pytest
from datetime import datetime, timedelta

from streaming.models import OHLCV, SetupType, TrendStatus
from filters.trend_filter import TrendFilter, TrendResult, TrendConditions


def _make_candles(
    count: int,
    base_price: float = 100.0,
    trend: float = 0.0,
    start_time: datetime = None,
    interval_hours: int = 4,
) -> list:
    """
    Generate a list of OHLCV candles for testing.

    Args:
        count: Number of candles to generate.
        base_price: Starting close price.
        trend: Price increment per candle (positive = uptrend).
        start_time: Starting timestamp.
        interval_hours: Hours between candles (4 for 4H, 1 for 1H).

    Returns:
        List of OHLCV candles.
    """
    if start_time is None:
        start_time = datetime(2024, 1, 1)

    candles = []
    for i in range(count):
        close = base_price + (trend * i)
        open_price = close - (trend * 0.5) if trend != 0 else close * 0.999
        high = max(close, open_price) * 1.005
        low = min(close, open_price) * 0.995
        volume = 1000.0 + (i * 10)

        candles.append(
            OHLCV(
                timestamp=start_time + timedelta(hours=interval_hours * i),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return candles


class TestEvaluateForMomentum:
    """Test evaluate_for_momentum() method (Req 4.1, 4.2)."""

    def test_passes_when_close_above_ema20(self):
        """1H close above EMA20 should pass for momentum."""
        tf = TrendFilter()
        # Strong uptrend on 1H - close will be above EMA20
        candles_1h = _make_candles(30, base_price=50.0, trend=1.0, interval_hours=1)
        result = tf.evaluate_for_momentum(candles_1h)

        assert result.passed is True
        assert result.status == TrendStatus.BULLISH
        assert result.rejection_reason is None

    def test_fails_when_close_below_ema20(self):
        """1H close below EMA20 should fail for momentum."""
        tf = TrendFilter()
        # Uptrend then sharp drop at end - close below EMA20
        candles_1h = _make_candles(30, base_price=50.0, trend=1.0, interval_hours=1)
        # Drop the last candle well below EMA20
        candles_1h[-1] = OHLCV(
            timestamp=candles_1h[-1].timestamp,
            open=40.0,
            high=41.0,
            low=39.0,
            close=40.0,  # Well below EMA20 which should be around 70+
            volume=1000.0,
        )
        result = tf.evaluate_for_momentum(candles_1h)

        assert result.passed is False
        assert result.status == TrendStatus.NOT_BULLISH
        assert "1H close below EMA20" in result.rejection_reason

    def test_insufficient_data_with_few_candles(self):
        """Fewer than 20 1H candles should return insufficient data."""
        tf = TrendFilter()
        candles_1h = _make_candles(10, base_price=50.0, trend=1.0, interval_hours=1)
        result = tf.evaluate_for_momentum(candles_1h)

        assert result.passed is False
        assert result.status == TrendStatus.INSUFFICIENT_DATA
        assert "Insufficient 1H data" in result.rejection_reason

    def test_does_not_require_4h_conditions(self):
        """Momentum evaluation should not check any 4H conditions."""
        tf = TrendFilter()
        # Only 1H candles needed, no 4H data
        candles_1h = _make_candles(25, base_price=50.0, trend=0.5, interval_hours=1)
        result = tf.evaluate_for_momentum(candles_1h)

        # Should pass based solely on 1H close > EMA20
        assert result.passed is True
        # EMA20_above_ema50 and ema200_rising should be True (not evaluated)
        assert result.conditions.ema20_above_ema50 is True
        assert result.conditions.ema200_rising is True


class TestEvaluateWithSetupType:
    """Test evaluate() routing based on setup_type parameter."""

    def test_momentum_breakout_delegates_to_momentum_eval(self):
        """MOMENTUM_BREAKOUT should use 1H evaluation logic."""
        tf = TrendFilter()
        # Provide 1H candles with uptrend (close > EMA20)
        candles_1h = _make_candles(30, base_price=50.0, trend=1.0, interval_hours=1)
        # 4H candles insufficient (less than 50) - should not matter for momentum
        candles_4h = _make_candles(10, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.MOMENTUM_BREAKOUT,
            candles_1h=candles_1h,
        )

        assert result.passed is True
        assert result.status == TrendStatus.BULLISH

    def test_momentum_breakout_fallback_to_4h_as_1h(self):
        """MOMENTUM_BREAKOUT without 1H candles should use 4H candles for EMA20 check."""
        tf = TrendFilter()
        # Provide enough 4H candles with uptrend
        candles_4h = _make_candles(30, base_price=50.0, trend=1.0, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.MOMENTUM_BREAKOUT,
        )

        # Should pass since close > EMA20 in uptrend
        assert result.passed is True
        assert result.status == TrendStatus.BULLISH

    def test_compression_breakout_requires_50_candles(self):
        """COMPRESSION_BREAKOUT should require 50 candles, not 200."""
        tf = TrendFilter()
        # 60 candles with strong uptrend - should pass with 50 min
        candles_4h = _make_candles(60, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.COMPRESSION_BREAKOUT,
        )

        # Should not be rejected for insufficient data
        assert result.status != TrendStatus.INSUFFICIENT_DATA

    def test_compression_breakout_rejects_fewer_than_50(self):
        """COMPRESSION_BREAKOUT with < 50 candles should reject with insufficient data."""
        tf = TrendFilter()
        candles_4h = _make_candles(49, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.COMPRESSION_BREAKOUT,
        )

        assert result.passed is False
        assert result.status == TrendStatus.INSUFFICIENT_DATA
        assert "49" in result.rejection_reason
        assert "50" in result.rejection_reason

    def test_pullback_continuation_requires_50_candles(self):
        """PULLBACK_CONTINUATION should require 50 candles, not 200."""
        tf = TrendFilter()
        candles_4h = _make_candles(60, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.PULLBACK_CONTINUATION,
        )

        assert result.status != TrendStatus.INSUFFICIENT_DATA

    def test_pullback_continuation_rejects_fewer_than_50(self):
        """PULLBACK_CONTINUATION with < 50 candles should reject."""
        tf = TrendFilter()
        candles_4h = _make_candles(45, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.PULLBACK_CONTINUATION,
        )

        assert result.passed is False
        assert result.status == TrendStatus.INSUFFICIENT_DATA

    def test_compression_breakout_requires_all_3_conditions(self):
        """COMPRESSION_BREAKOUT should still require all 3 4H conditions."""
        tf = TrendFilter()
        # Flat market with enough candles - conditions won't all pass
        candles_4h = _make_candles(60, base_price=100.0, trend=0.0, interval_hours=4)
        # Drop price at end to fail price > EMA200
        for i in range(5):
            candles_4h.append(
                OHLCV(
                    timestamp=candles_4h[-1].timestamp + timedelta(hours=4),
                    open=90.0,
                    high=91.0,
                    low=89.0,
                    close=90.0,
                    volume=1000.0,
                )
            )

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.COMPRESSION_BREAKOUT,
        )

        assert result.passed is False
        assert result.status == TrendStatus.NOT_BULLISH

    def test_no_setup_type_uses_legacy_200_candle_min(self):
        """No setup_type should use legacy MIN_CANDLES=200."""
        tf = TrendFilter()
        # 100 candles - enough for new min (50) but not legacy (200)
        candles_4h = _make_candles(100, base_price=50.0, trend=0.5, interval_hours=4)

        result = tf.evaluate(candles_4h)

        assert result.passed is False
        assert result.status == TrendStatus.INSUFFICIENT_DATA
        assert "100" in result.rejection_reason
        assert "200" in result.rejection_reason

    def test_momentum_breakout_ignores_4h_candle_count(self):
        """MOMENTUM_BREAKOUT should not care about 4H candle count."""
        tf = TrendFilter()
        # Only 5 4H candles (way below any minimum)
        candles_4h = _make_candles(5, base_price=50.0, trend=0.5, interval_hours=4)
        # But 30 1H candles with uptrend
        candles_1h = _make_candles(30, base_price=50.0, trend=1.0, interval_hours=1)

        result = tf.evaluate(
            candles_4h,
            setup_type=SetupType.MOMENTUM_BREAKOUT,
            candles_1h=candles_1h,
        )

        assert result.passed is True
        assert result.status == TrendStatus.BULLISH
