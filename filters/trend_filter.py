"""
Trend Filter - Per-coin trend assessment with setup-type-specific evaluation.

Evaluates trend conditions before allowing a coin to proceed to setup detection.

For COMPRESSION_BREAKOUT and PULLBACK_CONTINUATION (4H timeframe):
  1. Price (close) above EMA200
  2. EMA20 above EMA50
  3. EMA200 rising over last 5 candles

For MOMENTUM_BREAKOUT (1H timeframe):
  1. Close > EMA20 (only condition required)

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
from loguru import logger

from streaming.models import OHLCV, SetupType, TrendStatus


@dataclass
class TrendConditions:
    """Individual trend condition results."""

    price_above_ema200: bool = False  # Req 4.1: Close > EMA200 (4H)
    ema20_above_ema50: bool = False  # Req 4.2: EMA20 > EMA50 (4H)
    ema200_rising: bool = False  # Req 4.3: EMA200 current > EMA200 5 candles ago


@dataclass
class TrendResult:
    """Result of trend filter evaluation for a coin."""

    passed: bool = False
    conditions: TrendConditions = None
    status: TrendStatus = TrendStatus.INSUFFICIENT_DATA
    rejection_reason: Optional[str] = None

    def __post_init__(self):
        if self.conditions is None:
            self.conditions = TrendConditions()


class TrendFilter:
    """
    Per-coin trend assessment before setup detection.

    Supports setup-type-specific evaluation:
    - MOMENTUM_BREAKOUT: Only requires 1H close > EMA20 (Req 4.1, 4.2)
    - COMPRESSION_BREAKOUT / PULLBACK_CONTINUATION: Requires all 3 existing
      4H conditions with a minimum of 50 candles (Req 4.3, 4.4, 4.5)

    Does NOT require EMA50 > EMA100 > EMA200 alignment (Req 4.6).
    """

    MIN_CANDLES = 200  # Legacy minimum 4H candles (kept for backward compat)
    MIN_CANDLES_STANDARD = 50  # Minimum 4H candles for COMPRESSION/PULLBACK (Req 4.4)
    MIN_CANDLES_MOMENTUM = 20  # Minimum 1H candles for EMA20 calculation
    EMA200_LOOKBACK = 5  # Candles to look back for EMA200 rising check

    def __init__(self):
        """Initialize TrendFilter."""
        pass

    def evaluate_for_momentum(self, candles_1h: List[OHLCV]) -> TrendResult:
        """
        Evaluate trend for MOMENTUM_BREAKOUT setup type.

        Only checks that the 1H close price is above EMA20 on the 1H timeframe.
        No 4H conditions are required (Req 4.1, 4.2).

        Args:
            candles_1h: List of 1H OHLCV candles (oldest first).

        Returns:
            TrendResult with pass/fail based on close > EMA20 condition.
        """
        if len(candles_1h) < self.MIN_CANDLES_MOMENTUM:
            logger.debug(
                f"Insufficient 1H data for momentum: {len(candles_1h)} candles "
                f"(need {self.MIN_CANDLES_MOMENTUM})"
            )
            return TrendResult(
                passed=False,
                conditions=TrendConditions(),
                status=TrendStatus.INSUFFICIENT_DATA,
                rejection_reason=(
                    f"Insufficient 1H data: {len(candles_1h)} candles "
                    f"(minimum {self.MIN_CANDLES_MOMENTUM} required for EMA20)"
                ),
            )

        # Calculate EMA20 on 1H closes
        closes = pd.Series([c.close for c in candles_1h])
        ema20_series = closes.ewm(span=20, adjust=False).mean()

        current_close = candles_1h[-1].close
        current_ema20 = float(ema20_series.iloc[-1])

        # Only condition: close > EMA20 on 1H
        close_above_ema20 = current_close > current_ema20

        # For momentum, we only track the EMA20 condition
        # Map it to price_above_ema200 field for consistency in the result
        conditions = TrendConditions(
            price_above_ema200=close_above_ema20,  # Repurposed: close > EMA20 (1H)
            ema20_above_ema50=True,  # Not evaluated for momentum
            ema200_rising=True,  # Not evaluated for momentum
        )

        if close_above_ema20:
            return TrendResult(
                passed=True,
                conditions=conditions,
                status=TrendStatus.BULLISH,
                rejection_reason=None,
            )

        return TrendResult(
            passed=False,
            conditions=conditions,
            status=TrendStatus.NOT_BULLISH,
            rejection_reason="Momentum trend not bullish: 1H close below EMA20",
        )

    def evaluate(
        self,
        coin_candles_4h: List[OHLCV],
        setup_type: Optional[SetupType] = None,
        candles_1h: Optional[List[OHLCV]] = None,
    ) -> TrendResult:
        """
        Evaluate trend conditions for a coin based on setup type.

        Routes evaluation based on setup_type:
        - MOMENTUM_BREAKOUT: delegates to evaluate_for_momentum() using 1H data
        - COMPRESSION_BREAKOUT / PULLBACK_CONTINUATION: requires all 3 existing
          4H conditions with MIN_CANDLES_STANDARD (50) candles
        - None (legacy): uses original MIN_CANDLES (200) for backward compatibility

        Args:
            coin_candles_4h: List of 4H OHLCV candles (oldest first).
            setup_type: Optional SetupType to determine evaluation logic.
            candles_1h: Optional list of 1H candles (required for MOMENTUM_BREAKOUT).

        Returns:
            TrendResult with pass/fail and individual condition status.
        """
        # Route MOMENTUM_BREAKOUT to the simplified 1H evaluation
        if setup_type == SetupType.MOMENTUM_BREAKOUT:
            if candles_1h is not None:
                return self.evaluate_for_momentum(candles_1h)
            # Fallback: if no 1H candles provided, use 4H candles for EMA20 check
            return self.evaluate_for_momentum(coin_candles_4h)

        # Determine minimum candles based on setup type
        if setup_type in (SetupType.COMPRESSION_BREAKOUT, SetupType.PULLBACK_CONTINUATION):
            min_candles = self.MIN_CANDLES_STANDARD
        else:
            # Legacy behavior (no setup_type specified)
            min_candles = self.MIN_CANDLES

        # Reject if fewer than required 4H candles
        if len(coin_candles_4h) < min_candles:
            logger.debug(
                f"Insufficient data: {len(coin_candles_4h)} candles "
                f"(need {min_candles})"
            )
            return TrendResult(
                passed=False,
                conditions=TrendConditions(),
                status=TrendStatus.INSUFFICIENT_DATA,
                rejection_reason=(
                    f"Insufficient data: {len(coin_candles_4h)} candles "
                    f"(minimum {min_candles} required)"
                ),
            )

        # Build close price series for EMA calculations
        closes = pd.Series([c.close for c in coin_candles_4h])

        # Calculate EMAs using pandas EWM (same approach as IndicatorEngine)
        ema200_series = closes.ewm(span=200, adjust=False).mean()
        ema20_series = closes.ewm(span=20, adjust=False).mean()
        ema50_series = closes.ewm(span=50, adjust=False).mean()

        # Get current values (last candle)
        current_close = coin_candles_4h[-1].close
        current_ema200 = float(ema200_series.iloc[-1])
        current_ema20 = float(ema20_series.iloc[-1])
        current_ema50 = float(ema50_series.iloc[-1])

        # Get EMA200 from 5 candles ago for rising check
        ema200_5_ago = float(ema200_series.iloc[-1 - self.EMA200_LOOKBACK])

        # Evaluate conditions
        # Req 4.1: Price above EMA200
        price_above_ema200 = current_close > current_ema200

        # Req 4.2: EMA20 above EMA50
        ema20_above_ema50 = current_ema20 > current_ema50

        # Req 4.3: EMA200 rising over last 5 candles
        ema200_rising = current_ema200 > ema200_5_ago

        conditions = TrendConditions(
            price_above_ema200=price_above_ema200,
            ema20_above_ema50=ema20_above_ema50,
            ema200_rising=ema200_rising,
        )

        # Req 4.4: All 3 must pass for coin to proceed
        # Req 4.5: Any condition not bullish → reject
        all_pass = price_above_ema200 and ema20_above_ema50 and ema200_rising

        if all_pass:
            return TrendResult(
                passed=True,
                conditions=conditions,
                status=TrendStatus.BULLISH,
                rejection_reason=None,
            )

        # Build rejection reason from failed conditions
        failed = []
        if not price_above_ema200:
            failed.append("price below EMA200")
        if not ema20_above_ema50:
            failed.append("EMA20 below EMA50")
        if not ema200_rising:
            failed.append("EMA200 not rising")

        rejection_reason = f"Trend not bullish: {', '.join(failed)}"

        return TrendResult(
            passed=False,
            conditions=conditions,
            status=TrendStatus.NOT_BULLISH,
            rejection_reason=rejection_reason,
        )
