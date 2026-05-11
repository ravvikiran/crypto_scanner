"""
Unit tests for RelativeStrengthEngine.

Tests RS calculation, percentile ranking, momentum acceleration,
and stale data handling.

Requirements: 5.1, 5.2, 5.3, 5.5, 5.6
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from streaming.models import OHLCV
from streaming.models import RelativeStrength
from engines.relative_strength_engine import RelativeStrengthEngine


def _make_candle(close: float, open_: float = 0.0, timestamp: datetime = None) -> OHLCV:
    """Helper to create an OHLCV candle with minimal required fields."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    if open_ == 0.0:
        open_ = close * 0.99  # default open slightly below close
    return OHLCV(
        timestamp=timestamp,
        open=open_,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=1000.0,
    )


def _make_candle_series(prices: list, start_time: datetime = None) -> list:
    """Create a series of candles from a list of close prices."""
    if start_time is None:
        start_time = datetime(2024, 1, 1, 0, 0, 0)
    candles = []
    for i, price in enumerate(prices):
        ts = start_time + timedelta(hours=4 * i)
        candles.append(_make_candle(price, timestamp=ts))
    return candles


class TestCalculate:
    """Tests for the calculate() method - Requirements 5.1, 5.2, 5.3."""

    def test_4h_rs_coin_outperforms_btc(self):
        """Coin with higher % change than BTC should have positive RS."""
        engine = RelativeStrengthEngine()

        # Coin goes from 100 to 110 (10% gain)
        coin_candles = _make_candle_series([100.0, 110.0])
        # BTC goes from 50000 to 51000 (2% gain)
        btc_candles = _make_candle_series([50000.0, 51000.0])

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        # RS_4H = 10% - 2% = 8%
        assert abs(result.rs_4h - 8.0) < 0.01

    def test_4h_rs_coin_underperforms_btc(self):
        """Coin with lower % change than BTC should have negative RS."""
        engine = RelativeStrengthEngine()

        # Coin goes from 100 to 101 (1% gain)
        coin_candles = _make_candle_series([100.0, 101.0])
        # BTC goes from 50000 to 52500 (5% gain)
        btc_candles = _make_candle_series([50000.0, 52500.0])

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        # RS_4H = 1% - 5% = -4%
        assert abs(result.rs_4h - (-4.0)) < 0.01

    def test_24h_rs_calculation(self):
        """24H RS uses 7 candles (6 periods of 4H = 24H)."""
        engine = RelativeStrengthEngine()

        # Coin: starts at 100, ends at 120 (20% gain over 24H)
        coin_prices = [100.0, 103.0, 106.0, 109.0, 112.0, 116.0, 120.0]
        coin_candles = _make_candle_series(coin_prices)

        # BTC: starts at 50000, ends at 55000 (10% gain over 24H)
        btc_prices = [50000.0, 51000.0, 52000.0, 53000.0, 53500.0, 54000.0, 55000.0]
        btc_candles = _make_candle_series(btc_prices)

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        # RS_24H = 20% - 10% = 10%
        assert abs(result.rs_24h - 10.0) < 0.01

    def test_24h_rs_insufficient_data(self):
        """With fewer than 7 candles, 24H RS should remain 0."""
        engine = RelativeStrengthEngine()

        coin_candles = _make_candle_series([100.0, 105.0, 110.0])
        btc_candles = _make_candle_series([50000.0, 51000.0, 52000.0])

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        assert result.rs_4h != 0.0  # 4H should be calculated
        assert result.rs_24h == 0.0  # 24H should be 0 (insufficient data)

    def test_insufficient_candles_returns_default(self):
        """With fewer than 2 candles, all RS values should be 0."""
        engine = RelativeStrengthEngine()

        coin_candles = _make_candle_series([100.0])
        btc_candles = _make_candle_series([50000.0])

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        assert result.rs_4h == 0.0
        assert result.rs_24h == 0.0
        assert result.acceleration == 0.0

    def test_momentum_acceleration(self):
        """Acceleration = current RS_4H - previous RS_4H."""
        engine = RelativeStrengthEngine()

        # First call: coin +5%, BTC +2% → RS = 3%
        coin_candles_1 = _make_candle_series([100.0, 105.0])
        btc_candles_1 = _make_candle_series([50000.0, 51000.0])
        result1 = engine.calculate_for_symbol("ETH", coin_candles_1, btc_candles_1)

        # First call has no previous, so acceleration = 0
        assert result1.acceleration == 0.0

        # Second call: coin +10%, BTC +1% → RS = 9%
        coin_candles_2 = _make_candle_series([100.0, 110.0])
        btc_candles_2 = _make_candle_series([50000.0, 50500.0])
        result2 = engine.calculate_for_symbol("ETH", coin_candles_2, btc_candles_2)

        # Acceleration = 9% - 3% = 6%
        # Previous RS was ~3%, current RS is ~9%
        expected_prev_rs = 5.0 - 2.0  # 3.0
        expected_curr_rs = 10.0 - 1.0  # 9.0
        expected_accel = expected_curr_rs - expected_prev_rs  # 6.0
        assert abs(result2.acceleration - expected_accel) < 0.01

    def test_zero_old_price_returns_zero_pct_change(self):
        """Division by zero should be handled gracefully."""
        engine = RelativeStrengthEngine()

        coin_candles = _make_candle_series([0.0, 100.0])
        btc_candles = _make_candle_series([50000.0, 51000.0])

        result = engine.calculate_for_symbol("ETH", coin_candles, btc_candles)
        # Should not raise, rs_4h should be 0 - btc_change
        assert result.rs_4h is not None


class TestRankAll:
    """Tests for the rank_all() method - Requirement 5.5."""

    def test_percentile_ranking_multiple_coins(self):
        """Coins should be ranked 0-100 based on RS position."""
        engine = RelativeStrengthEngine()

        scores = {
            "ETH": RelativeStrength(rs_4h=5.0),
            "SOL": RelativeStrength(rs_4h=10.0),
            "DOGE": RelativeStrength(rs_4h=-2.0),
            "ADA": RelativeStrength(rs_4h=3.0),
            "XRP": RelativeStrength(rs_4h=8.0),
        }

        percentiles = engine.rank_all(scores)

        # DOGE has lowest RS → 0 percentile
        # SOL has highest RS → 100 percentile
        assert percentiles["DOGE"] == 0.0
        assert percentiles["SOL"] == 100.0

        # Verify ordering: DOGE < ADA < ETH < XRP < SOL
        assert percentiles["ADA"] == 25.0
        assert percentiles["ETH"] == 50.0
        assert percentiles["XRP"] == 75.0

    def test_percentile_single_coin(self):
        """A single coin should get 50th percentile."""
        engine = RelativeStrengthEngine()

        scores = {"ETH": RelativeStrength(rs_4h=5.0)}
        percentiles = engine.rank_all(scores)

        assert percentiles["ETH"] == 50.0

    def test_percentile_empty_scores(self):
        """Empty input should return empty dict."""
        engine = RelativeStrengthEngine()
        percentiles = engine.rank_all({})
        assert percentiles == {}

    def test_percentile_updates_rs_objects(self):
        """rank_all should also update the percentile field in RelativeStrength objects."""
        engine = RelativeStrengthEngine()

        scores = {
            "ETH": RelativeStrength(rs_4h=5.0),
            "SOL": RelativeStrength(rs_4h=10.0),
        }

        engine.rank_all(scores)

        assert scores["ETH"].percentile == 0.0  # lower RS
        assert scores["SOL"].percentile == 100.0  # higher RS

    def test_percentile_two_coins(self):
        """Two coins: lowest gets 0, highest gets 100."""
        engine = RelativeStrengthEngine()

        scores = {
            "ETH": RelativeStrength(rs_4h=3.0),
            "SOL": RelativeStrength(rs_4h=7.0),
        }

        percentiles = engine.rank_all(scores)

        assert percentiles["ETH"] == 0.0
        assert percentiles["SOL"] == 100.0


class TestStaleStatus:
    """Tests for get_stale_status() - Requirement 5.6."""

    def test_stale_when_never_updated(self):
        """Should be stale if BTC data was never received."""
        engine = RelativeStrengthEngine()
        assert engine.get_stale_status() is True

    def test_not_stale_after_recent_update(self):
        """Should not be stale immediately after BTC price update."""
        engine = RelativeStrengthEngine()
        engine.update_btc_price(50000.0)
        assert engine.get_stale_status() is False

    def test_stale_after_60_seconds(self):
        """Should be stale if BTC data is older than 60 seconds."""
        engine = RelativeStrengthEngine()

        # Simulate update 61 seconds ago
        engine._btc_last_price = 50000.0
        engine._btc_last_update = time.time() - 61.0

        assert engine.get_stale_status() is True

    def test_not_stale_at_59_seconds(self):
        """Should not be stale if BTC data is 59 seconds old."""
        engine = RelativeStrengthEngine()

        engine._btc_last_price = 50000.0
        engine._btc_last_update = time.time() - 59.0

        assert engine.get_stale_status() is False

    def test_calculate_updates_btc_timestamp(self):
        """Calling calculate with BTC candles should refresh the timestamp."""
        engine = RelativeStrengthEngine()

        # Start stale
        assert engine.get_stale_status() is True

        coin_candles = _make_candle_series([100.0, 105.0])
        btc_candles = _make_candle_series([50000.0, 51000.0])

        engine.calculate_for_symbol("ETH", coin_candles, btc_candles)

        # Should no longer be stale
        assert engine.get_stale_status() is False

    def test_stale_flag_in_result_when_no_btc_data(self):
        """Result should have is_stale=True when BTC data was never set."""
        engine = RelativeStrengthEngine()

        # With empty btc_candles, stale flag should be True
        coin_candles = _make_candle_series([100.0, 105.0])
        result = engine.calculate_for_symbol("ETH", coin_candles, [])

        assert result.is_stale is True


class TestUpdateBtcPrice:
    """Tests for update_btc_price() helper."""

    def test_updates_price_and_timestamp(self):
        """update_btc_price should set both price and timestamp."""
        engine = RelativeStrengthEngine()

        engine.update_btc_price(65000.0)

        assert engine.btc_last_price == 65000.0
        assert engine.btc_last_update > 0.0
        assert engine.get_stale_status() is False
