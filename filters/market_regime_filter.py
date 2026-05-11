"""
Market Regime Filter

Evaluates BTC 4H structure using 5 conditions to determine whether
the macro environment is suitable for LONG setup detection.

The hard gate (should_allow_longs) now only blocks when BTC is actively
crashing (>3% decline over 4 consecutive 1H candles). The 5-condition
evaluation becomes a soft scoring input via get_alignment_score().

Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
"""

import os
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
from loguru import logger

from streaming.models import CoinData, OHLCV
from indicators import IndicatorEngine


@dataclass
class RegimeConditions:
    """Individual condition results for the 5-condition BTC gate."""

    trend: bool = False  # BTC price > EMA200 (4H)
    momentum: bool = False  # BTC EMA20 > EMA50 (4H)
    direction: bool = False  # BTC EMA200 rising over last 5 candles (4H)
    volatility: bool = False  # BTC ATR(14)/price between 1.0%-3.0% (4H)
    breadth: bool = False  # >50% coins with positive 24h change


@dataclass
class RegimeResult:
    """Composite result of the market regime evaluation."""

    is_bullish: bool
    conditions: RegimeConditions
    status: str  # "bullish", "not_bullish", "indeterminate"


class MarketRegimeFilter:
    """
    BTC-based global market condition gate for LONG setups.

    Two-tier evaluation:
    - Hard gate (should_allow_longs): Only blocks when BTC is actively crashing
      (>3% decline over 4 consecutive 1H candles). This allows signals during
      sideways and mildly bearish markets.
    - Soft scoring (get_alignment_score): The 5-condition evaluation provides a
      proportional 0-100 score used as the market_alignment scoring component.

    The 5 conditions evaluated on BTC 4H data:
    1. Trend: BTC price > EMA200
    2. Momentum: EMA20 > EMA50
    3. Direction: EMA200 rising over last 5 candles
    4. Volatility: ATR(14) as % of price between 1.0% and 3.0%
    5. Breadth: >50% of tracked coins have positive 24h change

    If fewer than 200 candles are available for 4H evaluation, status is indeterminate.
    If fewer than crash_candle_count candles are available for 1H crash detection,
    defaults to "not crashing" (allow signals).
    """

    MIN_CANDLES = 200

    def __init__(
        self,
        crash_threshold_pct: Optional[float] = None,
        crash_candle_count: Optional[int] = None,
    ) -> None:
        """
        Initialize the MarketRegimeFilter.

        Args:
            crash_threshold_pct: BTC decline threshold (%) for crash detection.
                Defaults to BTC_CRASH_THRESHOLD_PCT env var or 3.0.
            crash_candle_count: Number of 1H candles to evaluate for crash.
                Defaults to BTC_CRASH_CANDLE_COUNT env var or 4.
        """
        self._indicator_engine = IndicatorEngine()
        self._last_result: RegimeResult = RegimeResult(
            is_bullish=False,
            conditions=RegimeConditions(),
            status="indeterminate",
        )

        # Crash detection configuration (configurable via constructor or env vars)
        if crash_threshold_pct is not None:
            self._crash_threshold_pct = crash_threshold_pct
        else:
            self._crash_threshold_pct = float(
                os.getenv("BTC_CRASH_THRESHOLD_PCT", "3.0")
            )

        if crash_candle_count is not None:
            self._crash_candle_count = crash_candle_count
        else:
            self._crash_candle_count = int(
                os.getenv("BTC_CRASH_CANDLE_COUNT", "4")
            )

        # Store 1H BTC candles reference for crash detection
        self._btc_candles_1h: List[OHLCV] = []

    @property
    def last_result(self) -> RegimeResult:
        """Return the most recent evaluation result."""
        return self._last_result

    def evaluate(
        self, btc_candles: List[OHLCV], universe_coins: List[CoinData]
    ) -> RegimeResult:
        """
        Evaluate all 5 BTC conditions.

        Args:
            btc_candles: BTC 4H OHLCV candles (most recent last).
            universe_coins: All tracked coins with 24h price change data.

        Returns:
            RegimeResult with composite bullish/not-bullish gate and
            individual condition statuses.
        """
        # Requirement 3.9: insufficient data → indeterminate
        if len(btc_candles) < self.MIN_CANDLES:
            result = RegimeResult(
                is_bullish=False,
                conditions=RegimeConditions(),
                status="indeterminate",
            )
            self._last_result = result
            logger.warning(
                f"Market regime indeterminate: only {len(btc_candles)} "
                f"BTC 4H candles available (need {self.MIN_CANDLES})"
            )
            return result

        # Build a pandas Series of close prices for indicator calculations
        closes = pd.Series([c.close for c in btc_candles])

        # --- Condition 1: Trend (Req 3.2) ---
        # BTC price > EMA200
        ema200_value = self._indicator_engine.calculate_ema(closes, 200)
        current_price = btc_candles[-1].close
        trend_bullish = (
            ema200_value is not None and current_price > ema200_value
        )

        # --- Condition 2: Momentum (Req 3.3) ---
        # EMA20 > EMA50
        ema20_value = self._indicator_engine.calculate_ema(closes, 20)
        ema50_value = self._indicator_engine.calculate_ema(closes, 50)
        momentum_bullish = (
            ema20_value is not None
            and ema50_value is not None
            and ema20_value > ema50_value
        )

        # --- Condition 3: Direction (Req 3.4) ---
        # EMA200 current > EMA200 from 5 candles ago
        direction_bullish = self._evaluate_direction(closes)

        # --- Condition 4: Volatility (Req 3.5) ---
        # ATR(14) as % of price between 1.0% and 3.0%
        volatility_healthy = self._evaluate_volatility(btc_candles)

        # --- Condition 5: Breadth (Req 3.6) ---
        # >50% of coins with positive 24h change
        breadth_bullish = self._evaluate_breadth(universe_coins)

        conditions = RegimeConditions(
            trend=trend_bullish,
            momentum=momentum_bullish,
            direction=direction_bullish,
            volatility=volatility_healthy,
            breadth=breadth_bullish,
        )

        # Requirement 3.7: all 5 must be bullish
        all_bullish = all(
            [trend_bullish, momentum_bullish, direction_bullish,
             volatility_healthy, breadth_bullish]
        )

        status = "bullish" if all_bullish else "not_bullish"

        result = RegimeResult(
            is_bullish=all_bullish,
            conditions=conditions,
            status=status,
        )
        self._last_result = result

        logger.info(
            f"Market regime: {status} | "
            f"trend={trend_bullish} momentum={momentum_bullish} "
            f"direction={direction_bullish} volatility={volatility_healthy} "
            f"breadth={breadth_bullish}"
        )

        return result

    def should_allow_longs(self) -> bool:
        """
        Return True when BTC is NOT actively crashing.

        The hard gate now only blocks signals when BTC has declined more
        than the crash threshold across the configured number of 1H candles.
        This allows signals during sideways and mildly bearish markets.

        If no 1H candles have been stored yet, defaults to allowing longs
        (not crashing).

        Requirements: 1.1, 1.2
        """
        return not self.is_crashing(self._btc_candles_1h)

    def is_crashing(self, btc_candles_1h: List[OHLCV]) -> bool:
        """
        Check if BTC is actively crashing.

        A crash is defined as a decline exceeding the configured threshold
        (default 3%) from the open of the first candle to the close of the
        last candle across the configured number of consecutive 1H candles
        (default 4).

        Args:
            btc_candles_1h: BTC 1H OHLCV candles (most recent last).

        Returns:
            True if BTC is crashing (decline > threshold), False otherwise.
            Returns False if insufficient candles are available.

        Requirements: 1.1, 1.2, 1.3
        """
        if len(btc_candles_1h) < self._crash_candle_count:
            # Insufficient data → default to "not crashing" (allow signals)
            logger.debug(
                f"BTC crash detection: insufficient 1H candles "
                f"({len(btc_candles_1h)} < {self._crash_candle_count}), "
                f"defaulting to not crashing"
            )
            return False

        # Take the last N candles
        recent_candles = btc_candles_1h[-self._crash_candle_count:]

        # Calculate percentage decline from open of first to close of last
        open_price = recent_candles[0].open
        close_price = recent_candles[-1].close

        if open_price <= 0:
            return False

        decline_pct = ((open_price - close_price) / open_price) * 100.0

        is_crash = decline_pct > self._crash_threshold_pct

        if is_crash:
            logger.warning(
                f"BTC CRASH DETECTED: {decline_pct:.2f}% decline over "
                f"{self._crash_candle_count} 1H candles "
                f"(threshold: {self._crash_threshold_pct}%)"
            )

        return is_crash

    def get_alignment_score(self) -> float:
        """
        Return a proportional market alignment score (0-100).

        Counts the number of bullish conditions from the last 5-condition
        evaluation and multiplies by 20. Each bullish condition contributes
        20 points to the score.

        Returns:
            Float score from 0.0 to 100.0 (in steps of 20).
            Returns 0.0 if no evaluation has been performed yet.

        Requirements: 1.5, 1.6
        """
        conditions = self._last_result.conditions
        bullish_count = sum([
            conditions.trend,
            conditions.momentum,
            conditions.direction,
            conditions.volatility,
            conditions.breadth,
        ])
        return float(bullish_count * 20)

    def update_btc_candles_1h(self, btc_candles_1h: List[OHLCV]) -> None:
        """
        Update the stored 1H BTC candles reference for crash detection.

        This should be called whenever new 1H BTC candle data is available.

        Args:
            btc_candles_1h: BTC 1H OHLCV candles (most recent last).
        """
        self._btc_candles_1h = btc_candles_1h

    # ─── Private Helpers ─────────────────────────────────────────────────

    def _evaluate_direction(self, closes: pd.Series) -> bool:
        """
        Check if EMA200 is rising over the last 5 candles.

        Compares the current EMA200 value to the EMA200 value
        5 candles prior. Rising means current > 5-candles-ago.
        """
        # Calculate full EMA200 series
        if len(closes) < 200:
            return False

        ema200_series = closes.ewm(span=200, adjust=False).mean()

        # Current EMA200 vs EMA200 from 5 candles ago
        current_ema200 = float(ema200_series.iloc[-1])
        ema200_5_ago = float(ema200_series.iloc[-6])  # 5 candles before the last

        return current_ema200 > ema200_5_ago

    def _evaluate_volatility(self, btc_candles: List[OHLCV]) -> bool:
        """
        Check if ATR(14) as a percentage of price is between 1.0% and 3.0%.

        ATR% = (ATR14 / current_price) * 100
        Healthy range: 1.0% <= ATR% <= 3.0%
        """
        # Build DataFrame for ATR calculation
        df = pd.DataFrame(
            [
                {
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                }
                for c in btc_candles
            ]
        )

        atr_value = self._indicator_engine.calculate_atr(df, period=14)
        if atr_value is None:
            return False

        current_price = btc_candles[-1].close
        if current_price <= 0:
            return False

        atr_percent = (atr_value / current_price) * 100.0
        return 1.0 <= atr_percent <= 3.0

    def _evaluate_breadth(self, universe_coins: List[CoinData]) -> bool:
        """
        Check if >50% of tracked coins have positive 24h price change.

        If no coins are provided, returns False (cannot confirm breadth).
        """
        if not universe_coins:
            return False

        positive_count = sum(
            1 for coin in universe_coins if coin.price_change_percent_24h > 0
        )
        total = len(universe_coins)

        breadth_pct = (positive_count / total) * 100.0
        return breadth_pct > 50.0
