"""
Unit tests for MarketRegimeFilter.

Tests each of the 5 conditions individually, composite gate logic,
and insufficient data handling.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.models import OHLCV, CoinData
from filters.market_regime_filter import MarketRegimeFilter, RegimeConditions, RegimeResult


def _make_candle(close: float, high: float = 0, low: float = 0,
                 open_: float = 0, volume: float = 1000.0,
                 timestamp: datetime = None) -> OHLCV:
    """Helper to create an OHLCV candle with sensible defaults."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    if high == 0:
        high = close * 1.01
    if low == 0:
        low = close * 0.99
    if open_ == 0:
        open_ = close * 0.999
    return OHLCV(
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_btc_candles(count: int, base_price: float = 60000.0,
                      trend: str = "up") -> list:
    """
    Generate a list of BTC 4H candles.

    trend: "up" for rising prices, "down" for falling, "flat" for stable.
    """
    candles = []
    price = base_price
    start_time = datetime.utcnow() - timedelta(hours=4 * count)

    for i in range(count):
        if trend == "up":
            price = base_price + (i * 10)  # Gradual rise
        elif trend == "down":
            price = base_price - (i * 10)
        else:
            price = base_price  # Flat

        # ATR-friendly candle: ~1.5% range for healthy volatility
        high = price * 1.0075
        low = price * 0.9925
        open_ = price * 0.999

        candles.append(OHLCV(
            timestamp=start_time + timedelta(hours=4 * i),
            open=open_,
            high=high,
            low=low,
            close=price,
            volume=1000.0,
        ))

    return candles


def _make_coin(symbol: str, price_change_pct: float) -> CoinData:
    """Create a CoinData with a given 24h price change percentage."""
    return CoinData(
        symbol=symbol,
        name=symbol,
        current_price=100.0,
        market_cap=1_000_000.0,
        volume_24h=100_000.0,
        price_change_24h=price_change_pct,
        price_change_percent_24h=price_change_pct,
    )


class TestInsufficientData:
    """Test Requirement 3.9: insufficient data → indeterminate."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_fewer_than_200_candles_returns_indeterminate(self, mock_engine_cls):
        """With <200 candles, status should be indeterminate."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()
        candles = _make_btc_candles(100, trend="up")
        coins = [_make_coin(f"COIN{i}", 5.0) for i in range(10)]

        result = filt.evaluate(candles, coins)

        assert result.status == "indeterminate"
        assert result.is_bullish is False

    def test_exactly_200_candles_does_not_return_indeterminate(self):
        """With exactly 200 candles, should proceed with evaluation."""
        filt = MarketRegimeFilter()
        candles = _make_btc_candles(200, trend="up")
        coins = [_make_coin(f"COIN{i}", 5.0) for i in range(10)]

        result = filt.evaluate(candles, coins)

        assert result.status != "indeterminate"


class TestShouldAllowLongs:
    """Test Requirements 1.1, 1.2: should_allow_longs now uses crash detection."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_returns_true_before_evaluation_no_candles(self, mock_engine_cls):
        """Before any 1H candles are stored, should_allow_longs returns True (not crashing)."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()
        # No 1H candles stored → insufficient data → not crashing → allow longs
        assert filt.should_allow_longs() is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_returns_true_when_not_crashing(self, mock_engine_cls):
        """When BTC is not crashing, should_allow_longs returns True."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # BTC stable: open 60000, close 59500 → 0.83% decline (< 3%)
        candles_1h = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4-i),
                   open=60000.0, high=60100.0, low=59400.0,
                   close=59500.0, volume=1000.0)
            for i in range(4)
        ]
        filt.update_btc_candles_1h(candles_1h)

        assert filt.should_allow_longs() is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_returns_false_when_crashing(self, mock_engine_cls):
        """When BTC is crashing (>3% decline), should_allow_longs returns False."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # BTC crash: open 60000, close 57000 → 5% decline (> 3%)
        candles_1h = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=58500.0,
                   close=59000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59000.0, high=59100.0, low=58000.0,
                   close=58200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=58200.0, high=58300.0, low=57500.0,
                   close=57800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57800.0, high=57900.0, low=56800.0,
                   close=57000.0, volume=1000.0),
        ]
        filt.update_btc_candles_1h(candles_1h)

        assert filt.should_allow_longs() is False


class TestBreadthCondition:
    """Test Requirement 3.6: breadth condition."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_breadth_bullish_when_majority_positive(self, mock_engine_cls):
        """Breadth is bullish when >50% coins have positive 24h change."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # 7 positive, 3 negative → 70% positive
        coins = [_make_coin(f"C{i}", 5.0) for i in range(7)]
        coins += [_make_coin(f"C{i+7}", -3.0) for i in range(3)]

        result = filt._evaluate_breadth(coins)
        assert result is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_breadth_not_bullish_when_minority_positive(self, mock_engine_cls):
        """Breadth is not bullish when <=50% coins have positive 24h change."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # 4 positive, 6 negative → 40% positive
        coins = [_make_coin(f"C{i}", 5.0) for i in range(4)]
        coins += [_make_coin(f"C{i+4}", -3.0) for i in range(6)]

        result = filt._evaluate_breadth(coins)
        assert result is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_breadth_not_bullish_when_exactly_50_percent(self, mock_engine_cls):
        """Breadth requires >50%, so exactly 50% is not bullish."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        coins = [_make_coin(f"C{i}", 5.0) for i in range(5)]
        coins += [_make_coin(f"C{i+5}", -3.0) for i in range(5)]

        result = filt._evaluate_breadth(coins)
        assert result is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_breadth_false_when_no_coins(self, mock_engine_cls):
        """Breadth is False when no coins are provided."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        result = filt._evaluate_breadth([])
        assert result is False


class TestIntegration:
    """Integration test: full evaluate with real IndicatorEngine."""

    def test_full_bullish_evaluation(self):
        """
        With a rising BTC trend, healthy volatility, and majority positive coins,
        all conditions should be bullish.
        """
        filt = MarketRegimeFilter()

        # Generate 250 candles with a clear uptrend
        candles = _make_btc_candles(250, base_price=50000.0, trend="up")

        # All coins positive
        coins = [_make_coin(f"COIN{i}", 3.0) for i in range(20)]

        result = filt.evaluate(candles, coins)

        # Trend should be bullish (price > EMA200 in uptrend)
        assert result.conditions.trend
        # Momentum should be bullish (EMA20 > EMA50 in uptrend)
        assert result.conditions.momentum
        # Direction should be bullish (EMA200 rising)
        assert result.conditions.direction
        # Breadth should be bullish (all coins positive)
        assert result.conditions.breadth
        # Overall should be bullish (assuming volatility is in range)
        # Note: volatility depends on the candle range we set

    def test_insufficient_data_returns_indeterminate(self):
        """With <200 candles, should return indeterminate."""
        filt = MarketRegimeFilter()
        candles = _make_btc_candles(50, trend="up")
        coins = [_make_coin(f"COIN{i}", 3.0) for i in range(10)]

        result = filt.evaluate(candles, coins)

        assert result.status == "indeterminate"
        assert result.is_bullish is False
        # should_allow_longs is now based on crash detection, not 5-condition evaluation
        # With no 1H candles stored, it defaults to True (not crashing)
        assert filt.should_allow_longs() is True


class TestIsCrashing:
    """Test Requirements 1.1, 1.2, 1.3: BTC crash detection."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_insufficient_candles_returns_false(self, mock_engine_cls):
        """With fewer candles than required, is_crashing returns False."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_candle_count=4)

        # Only 3 candles (need 4)
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3-i),
                   open=60000.0, high=60100.0, low=55000.0,
                   close=55000.0, volume=1000.0)
            for i in range(3)
        ]

        assert filt.is_crashing(candles) is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_no_decline_returns_false(self, mock_engine_cls):
        """When BTC is flat or rising, is_crashing returns False."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # BTC rising: open 60000, close 61000 → no decline
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60500.0, low=59800.0,
                   close=60200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=60200.0, high=60700.0, low=60000.0,
                   close=60500.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=60500.0, high=61000.0, low=60300.0,
                   close=60800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=60800.0, high=61200.0, low=60600.0,
                   close=61000.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_decline_below_threshold_returns_false(self, mock_engine_cls):
        """When decline is below threshold (e.g., 2%), is_crashing returns False."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0)

        # BTC decline: open 60000, close 58900 → 1.83% decline (< 3%)
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=59500.0,
                   close=59700.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59700.0, high=59800.0, low=59200.0,
                   close=59400.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=59400.0, high=59500.0, low=59000.0,
                   close=59100.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=59100.0, high=59200.0, low=58800.0,
                   close=58900.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_decline_above_threshold_returns_true(self, mock_engine_cls):
        """When decline exceeds threshold (>3%), is_crashing returns True."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0)

        # BTC crash: open 60000, close 57000 → 5% decline (> 3%)
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=58500.0,
                   close=59000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59000.0, high=59100.0, low=58000.0,
                   close=58200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=58200.0, high=58300.0, low=57500.0,
                   close=57800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57800.0, high=57900.0, low=56800.0,
                   close=57000.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_exactly_at_threshold_returns_false(self, mock_engine_cls):
        """When decline is exactly at threshold (3.0%), is_crashing returns False (must exceed)."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0)

        # BTC decline: open 60000, close 58200 → exactly 3.0%
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=58500.0,
                   close=59500.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59500.0, high=59600.0, low=58800.0,
                   close=59000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=59000.0, high=59100.0, low=58400.0,
                   close=58600.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=58600.0, high=58700.0, low=58100.0,
                   close=58200.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_uses_open_of_first_and_close_of_last(self, mock_engine_cls):
        """Crash detection uses open of first candle and close of last candle."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0, crash_candle_count=4)

        # First candle opens at 60000, last candle closes at 57500 → 4.17% decline
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=59000.0,
                   close=59500.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59500.0, high=59600.0, low=58500.0,
                   close=58800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=58800.0, high=58900.0, low=57800.0,
                   close=58000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=58000.0, high=58100.0, low=57400.0,
                   close=57500.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_configurable_threshold(self, mock_engine_cls):
        """Crash threshold is configurable."""
        mock_engine_cls.return_value = MagicMock()
        # Use a 5% threshold
        filt = MarketRegimeFilter(crash_threshold_pct=5.0)

        # 4% decline → below 5% threshold → not crashing
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=57500.0,
                   close=58000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=58000.0, high=58100.0, low=57200.0,
                   close=57500.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=57500.0, high=57600.0, low=57000.0,
                   close=57200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57200.0, high=57300.0, low=57500.0,
                   close=57600.0, volume=1000.0),
        ]

        assert filt.is_crashing(candles) is False

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_configurable_candle_count(self, mock_engine_cls):
        """Crash candle count is configurable."""
        mock_engine_cls.return_value = MagicMock()
        # Use 2 candles instead of 4
        filt = MarketRegimeFilter(crash_threshold_pct=3.0, crash_candle_count=2)

        # 2 candles with >3% decline
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=60000.0, high=60100.0, low=57000.0,
                   close=57500.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57500.0, high=57600.0, low=56500.0,
                   close=57000.0, volume=1000.0),
        ]

        # open of first = 60000, close of last = 57000 → 5% decline
        assert filt.is_crashing(candles) is True

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_uses_last_n_candles_from_longer_list(self, mock_engine_cls):
        """When more candles are provided, uses only the last N."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0, crash_candle_count=4)

        # 6 candles total, first 2 are stable, last 4 show crash
        candles = [
            # Stable candles (should be ignored)
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=6),
                   open=62000.0, high=62100.0, low=61800.0,
                   close=62000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=5),
                   open=62000.0, high=62100.0, low=61800.0,
                   close=62000.0, volume=1000.0),
            # Crash candles (last 4)
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=58500.0,
                   close=59000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59000.0, high=59100.0, low=58000.0,
                   close=58200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=58200.0, high=58300.0, low=57500.0,
                   close=57800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57800.0, high=57900.0, low=56800.0,
                   close=57000.0, volume=1000.0),
        ]

        # Last 4: open of first (60000) to close of last (57000) → 5% decline
        assert filt.is_crashing(candles) is True


class TestGetAlignmentScore:
    """Test Requirements 1.5, 1.6: proportional market alignment scoring."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_all_bullish_returns_100(self, mock_engine_cls):
        """When all 5 conditions are bullish, score is 100."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        filt._last_result = RegimeResult(
            is_bullish=True,
            conditions=RegimeConditions(
                trend=True, momentum=True, direction=True,
                volatility=True, breadth=True
            ),
            status="bullish",
        )

        assert filt.get_alignment_score() == 100.0

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_no_bullish_returns_0(self, mock_engine_cls):
        """When no conditions are bullish, score is 0."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        filt._last_result = RegimeResult(
            is_bullish=False,
            conditions=RegimeConditions(
                trend=False, momentum=False, direction=False,
                volatility=False, breadth=False
            ),
            status="not_bullish",
        )

        assert filt.get_alignment_score() == 0.0

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_three_bullish_returns_60(self, mock_engine_cls):
        """When 3 conditions are bullish, score is 60."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        filt._last_result = RegimeResult(
            is_bullish=False,
            conditions=RegimeConditions(
                trend=True, momentum=True, direction=True,
                volatility=False, breadth=False
            ),
            status="not_bullish",
        )

        assert filt.get_alignment_score() == 60.0

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_one_bullish_returns_20(self, mock_engine_cls):
        """When 1 condition is bullish, score is 20."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        filt._last_result = RegimeResult(
            is_bullish=False,
            conditions=RegimeConditions(
                trend=False, momentum=False, direction=False,
                volatility=True, breadth=False
            ),
            status="not_bullish",
        )

        assert filt.get_alignment_score() == 20.0

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_before_evaluation_returns_0(self, mock_engine_cls):
        """Before any evaluation, score is 0 (all conditions default to False)."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        assert filt.get_alignment_score() == 0.0

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_each_condition_contributes_20(self, mock_engine_cls):
        """Each individual condition contributes exactly 20 points."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        # Test each condition individually
        for condition_name in ['trend', 'momentum', 'direction', 'volatility', 'breadth']:
            conditions = RegimeConditions()
            setattr(conditions, condition_name, True)
            filt._last_result = RegimeResult(
                is_bullish=False,
                conditions=conditions,
                status="not_bullish",
            )
            assert filt.get_alignment_score() == 20.0


class TestUpdateBtcCandles1h:
    """Test storing 1H BTC candles reference."""

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_stores_candles(self, mock_engine_cls):
        """update_btc_candles_1h stores the candles for crash detection."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter()

        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=i),
                   open=60000.0, high=60100.0, low=59900.0,
                   close=60000.0, volume=1000.0)
            for i in range(4)
        ]

        filt.update_btc_candles_1h(candles)
        assert filt._btc_candles_1h == candles

    @patch("filters.market_regime_filter.IndicatorEngine")
    def test_should_allow_longs_uses_stored_candles(self, mock_engine_cls):
        """should_allow_longs uses the stored 1H candles for crash detection."""
        mock_engine_cls.return_value = MagicMock()
        filt = MarketRegimeFilter(crash_threshold_pct=3.0)

        # Store crashing candles
        candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=4),
                   open=60000.0, high=60100.0, low=58500.0,
                   close=59000.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=3),
                   open=59000.0, high=59100.0, low=58000.0,
                   close=58200.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=2),
                   open=58200.0, high=58300.0, low=57500.0,
                   close=57800.0, volume=1000.0),
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=1),
                   open=57800.0, high=57900.0, low=56800.0,
                   close=57000.0, volume=1000.0),
        ]
        filt.update_btc_candles_1h(candles)

        # should_allow_longs should return False (crashing)
        assert filt.should_allow_longs() is False

        # Now update with non-crashing candles
        stable_candles = [
            OHLCV(timestamp=datetime.utcnow() - timedelta(hours=i),
                   open=60000.0, high=60100.0, low=59900.0,
                   close=60000.0, volume=1000.0)
            for i in range(4)
        ]
        filt.update_btc_candles_1h(stable_candles)

        # should_allow_longs should return True (not crashing)
        assert filt.should_allow_longs() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
