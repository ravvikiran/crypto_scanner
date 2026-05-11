"""
Unit tests for score_breakout_quality() function.

Tests cover:
- Zero-range candle edge case (all scores = 0)
- Body ratio sub-score linear mapping
- Close position sub-score linear mapping
- Range expansion sub-score linear mapping (with ATR14)
- Momentum acceleration sub-score linear mapping
- RVOL sub-score linear mapping
- Total score is sum of 5 sub-scores
- Each sub-score is bounded 0-20

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
"""

import pytest
from datetime import datetime

from streaming.models import OHLCV
from streaming.models import BreakoutQualityScore
from scoring.scoring_engine import score_breakout_quality, _linear_map


def _make_candle(
    open: float = 100.0,
    high: float = 110.0,
    low: float = 95.0,
    close: float = 108.0,
    volume: float = 1000.0,
) -> OHLCV:
    """Helper to create an OHLCV candle for testing."""
    return OHLCV(
        timestamp=datetime(2024, 1, 1),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class TestZeroRangeCandle:
    """Requirement 13.7: Zero-range candle returns all zeros."""

    def test_zero_range_all_same_price(self):
        """When high == low (zero range), all sub-scores are 0."""
        candle = _make_candle(open=100.0, high=100.0, low=100.0, close=100.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=2.0)

        assert result.body_ratio_score == 0
        assert result.close_position_score == 0
        assert result.range_expansion_score == 0
        assert result.momentum_acceleration_score == 0
        assert result.relative_volume_score == 0
        assert result.total == 0

    def test_zero_range_returns_breakout_quality_score(self):
        """Zero-range candle returns a BreakoutQualityScore instance."""
        candle = _make_candle(open=50.0, high=50.0, low=50.0, close=50.0)
        result = score_breakout_quality(candle, atr14=3.0, rvol=1.5)
        assert isinstance(result, BreakoutQualityScore)


class TestBodyRatioScore:
    """Requirement 13.1: Body ratio linearly mapped 0.0-1.0 → 0-20."""

    def test_full_body_candle(self):
        """Body ratio = 1.0 (open=low, close=high) → score 20."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=110.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.body_ratio_score == 20

    def test_zero_body_candle(self):
        """Body ratio = 0.0 (open == close, doji) → score 0."""
        candle = _make_candle(open=105.0, high=110.0, low=100.0, close=105.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.body_ratio_score == 0

    def test_half_body_candle(self):
        """Body ratio = 0.5 → score 10."""
        # range = 10, body = 5 → ratio = 0.5
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=105.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.body_ratio_score == 10


class TestClosePositionScore:
    """Requirement 13.2: Close position linearly mapped 0.0-1.0 → 0-20."""

    def test_close_at_high(self):
        """Close at high → close position = 1.0 → score 20."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=110.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.close_position_score == 20

    def test_close_at_low(self):
        """Close at low → close position = 0.0 → score 0."""
        candle = _make_candle(open=110.0, high=110.0, low=100.0, close=100.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.close_position_score == 0

    def test_close_at_midpoint(self):
        """Close at midpoint → close position = 0.5 → score 10."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=105.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.close_position_score == 10


class TestRangeExpansionScore:
    """Requirement 13.3: Range expansion linearly mapped 1.0-3.0 → 0-20."""

    def test_range_equals_atr(self):
        """Range expansion = 1.0 (range == ATR14) → score 0."""
        # range = 10, atr14 = 10 → expansion = 1.0
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=10.0, rvol=1.0)
        assert result.range_expansion_score == 0

    def test_range_triple_atr(self):
        """Range expansion = 3.0 (range == 3*ATR14) → score 20."""
        # range = 15, atr14 = 5 → expansion = 3.0
        candle = _make_candle(open=100.0, high=115.0, low=100.0, close=112.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.range_expansion_score == 20

    def test_range_double_atr(self):
        """Range expansion = 2.0 → score 10 (midpoint)."""
        # range = 10, atr14 = 5 → expansion = 2.0
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.range_expansion_score == 10

    def test_range_below_atr(self):
        """Range expansion < 1.0 → score 0."""
        # range = 5, atr14 = 10 → expansion = 0.5
        candle = _make_candle(open=100.0, high=105.0, low=100.0, close=104.0)
        result = score_breakout_quality(candle, atr14=10.0, rvol=1.0)
        assert result.range_expansion_score == 0

    def test_range_above_3x_atr(self):
        """Range expansion > 3.0 → score capped at 20."""
        # range = 20, atr14 = 5 → expansion = 4.0
        candle = _make_candle(open=100.0, high=120.0, low=100.0, close=118.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.range_expansion_score == 20

    def test_zero_atr(self):
        """Zero ATR14 → range expansion = 0 → score 0."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=0.0, rvol=1.0)
        assert result.range_expansion_score == 0


class TestMomentumAccelerationScore:
    """Requirement 13.4: Momentum acceleration linearly mapped 0.0-10.0 → 0-20."""

    def test_large_momentum(self):
        """10% price change → score 20."""
        # (close - open) / open * 100 = (110 - 100) / 100 * 100 = 10%
        candle = _make_candle(open=100.0, high=112.0, low=100.0, close=110.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.momentum_acceleration_score == 20

    def test_zero_momentum(self):
        """0% price change (open == close) → score 0."""
        candle = _make_candle(open=100.0, high=110.0, low=95.0, close=100.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.momentum_acceleration_score == 0

    def test_5_percent_momentum(self):
        """5% price change → score 10 (midpoint)."""
        # (close - open) / open * 100 = (105 - 100) / 100 * 100 = 5%
        candle = _make_candle(open=100.0, high=107.0, low=100.0, close=105.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.momentum_acceleration_score == 10

    def test_above_10_percent_capped(self):
        """Above 10% → score capped at 20."""
        # (close - open) / open * 100 = (115 - 100) / 100 * 100 = 15%
        candle = _make_candle(open=100.0, high=116.0, low=100.0, close=115.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.momentum_acceleration_score == 20


class TestRelativeVolumeScore:
    """Requirement 13.5: RVOL linearly mapped 1.0-3.0 → 0-20."""

    def test_rvol_at_1(self):
        """RVOL = 1.0 → score 0."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=1.0)
        assert result.relative_volume_score == 0

    def test_rvol_at_3(self):
        """RVOL = 3.0 → score 20."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=3.0)
        assert result.relative_volume_score == 20

    def test_rvol_at_2(self):
        """RVOL = 2.0 → score 10 (midpoint)."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=2.0)
        assert result.relative_volume_score == 10

    def test_rvol_below_1(self):
        """RVOL < 1.0 → score 0."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=0.5)
        assert result.relative_volume_score == 0

    def test_rvol_above_3(self):
        """RVOL > 3.0 → score capped at 20."""
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=5.0)
        assert result.relative_volume_score == 20


class TestTotalScore:
    """Requirement 13.6: Total is sum of 5 sub-scores (0-100)."""

    def test_perfect_breakout(self):
        """A perfect breakout candle scores close to 100."""
        # Full body, close at high, 3x ATR range, 10%+ momentum, 3x RVOL
        candle = _make_candle(open=100.0, high=110.0, low=100.0, close=110.0)
        result = score_breakout_quality(candle, atr14=3.33, rvol=3.0)
        # body_ratio = 1.0 → 20
        # close_position = 1.0 → 20
        # range_expansion = 10/3.33 ≈ 3.0 → 20
        # momentum = 10% → 20
        # rvol = 3.0 → 20
        assert result.total == 100

    def test_weak_breakout(self):
        """A weak breakout candle scores low."""
        # Small body, close near low, range < ATR, low momentum, low volume
        candle = _make_candle(open=100.0, high=101.0, low=99.0, close=99.5)
        result = score_breakout_quality(candle, atr14=5.0, rvol=0.8)
        # body_ratio = 0.5/2 = 0.25 → 5
        # close_position = 0.5/2 = 0.25 → 5
        # range_expansion = 2/5 = 0.4 → 0
        # momentum = 0.5% → 1
        # rvol = 0.8 → 0
        assert result.total <= 20

    def test_total_equals_sum_of_subscores(self):
        """Total property equals sum of all 5 sub-scores."""
        candle = _make_candle(open=100.0, high=110.0, low=95.0, close=108.0)
        result = score_breakout_quality(candle, atr14=5.0, rvol=2.0)
        expected_total = (
            result.body_ratio_score
            + result.close_position_score
            + result.range_expansion_score
            + result.momentum_acceleration_score
            + result.relative_volume_score
        )
        assert result.total == expected_total


class TestLinearMap:
    """Tests for the _linear_map helper function."""

    def test_at_min(self):
        assert _linear_map(0.0, 0.0, 1.0) == 0

    def test_at_max(self):
        assert _linear_map(1.0, 0.0, 1.0) == 20

    def test_midpoint(self):
        assert _linear_map(0.5, 0.0, 1.0) == 10

    def test_below_min(self):
        assert _linear_map(-1.0, 0.0, 1.0) == 0

    def test_above_max(self):
        assert _linear_map(5.0, 0.0, 1.0) == 20

    def test_custom_range(self):
        """Linear map from 1.0-3.0 → 0-20."""
        assert _linear_map(1.0, 1.0, 3.0) == 0
        assert _linear_map(2.0, 1.0, 3.0) == 10
        assert _linear_map(3.0, 1.0, 3.0) == 20
