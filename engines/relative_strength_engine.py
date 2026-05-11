"""
Relative Strength Engine for the Crypto Momentum Scanner.

Calculates coin performance relative to BTC using rolling windows,
momentum acceleration, and percentile-based ranking.

Requirements: 5.1, 5.2, 5.3, 5.5, 5.6
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from streaming.models import OHLCV
from streaming.models import RelativeStrength


@dataclass
class _CoinRSHistory:
    """Internal tracking of per-coin RS history for acceleration calculation."""

    previous_rs_4h: Optional[float] = None
    current_rs_4h: Optional[float] = None


class RelativeStrengthEngine:
    """
    Calculates coin performance relative to BTC.

    RS = (coin_change_pct - btc_change_pct) over a rolling window.

    - 4H RS: performance over last 4 hours vs BTC
    - 24H RS: performance over last 24 hours vs BTC
    - Momentum acceleration: current_4h_rs - previous_4h_rs
    - rank_all(): normalizes all coin RS values to 0-100 percentile scale
    - Stale detection: if BTC price data is older than 60 seconds, mark as stale
    """

    def __init__(self) -> None:
        # BTC reference data
        self._btc_last_price: Optional[float] = None
        self._btc_last_update: float = 0.0  # timestamp from time.time()

        # Per-coin RS history for acceleration calculation
        self._coin_rs_history: Dict[str, _CoinRSHistory] = {}

    def calculate(
        self, coin_candles: List[OHLCV], btc_candles: List[OHLCV]
    ) -> RelativeStrength:
        """
        Calculate rolling RS metrics for a coin vs BTC.

        RS_4H = coin 4H change % - BTC 4H change %
        RS_24H = coin 24H change % - BTC 24H change %
        Acceleration = current RS_4H - previous RS_4H

        Args:
            coin_candles: List of OHLCV candles for the coin (most recent last).
                          Needs at least 2 candles for 4H RS, 7 for 24H RS (4H candles).
            btc_candles: List of OHLCV candles for BTC (most recent last, same timeframe).

        Returns:
            RelativeStrength dataclass with rs_4h, rs_24h, acceleration, and stale flag.
        """
        result = RelativeStrength()

        # Check for stale BTC data
        result.is_stale = self.get_stale_status()

        # Update BTC reference from the latest candle
        if btc_candles:
            self._btc_last_price = btc_candles[-1].close
            self._btc_last_update = time.time()
            # Re-check staleness after update
            result.is_stale = False

        # Need at least 2 candles (current + 1 prior) for 4H RS calculation
        if len(coin_candles) < 2 or len(btc_candles) < 2:
            return result

        # Calculate 4H RS: percentage change over the last candle period
        # Using the most recent candle close vs the prior candle close
        coin_change_4h = self._pct_change(
            coin_candles[-2].close, coin_candles[-1].close
        )
        btc_change_4h = self._pct_change(
            btc_candles[-2].close, btc_candles[-1].close
        )
        rs_4h = coin_change_4h - btc_change_4h
        result.rs_4h = rs_4h

        # Calculate 24H RS: percentage change over 6 candle periods (6 x 4H = 24H)
        # Need at least 7 candles (current + 6 prior)
        if len(coin_candles) >= 7 and len(btc_candles) >= 7:
            coin_change_24h = self._pct_change(
                coin_candles[-7].close, coin_candles[-1].close
            )
            btc_change_24h = self._pct_change(
                btc_candles[-7].close, btc_candles[-1].close
            )
            result.rs_24h = coin_change_24h - btc_change_24h

        # Calculate momentum acceleration
        # Get the coin symbol from context (use a hash of the first candle as key)
        # We use the coin's latest close as a proxy identifier
        coin_key = self._get_coin_key(coin_candles)
        if coin_key not in self._coin_rs_history:
            self._coin_rs_history[coin_key] = _CoinRSHistory()

        history = self._coin_rs_history[coin_key]

        # Shift current to previous, set new current
        history.previous_rs_4h = history.current_rs_4h
        history.current_rs_4h = rs_4h

        # Acceleration = current 4H RS - previous 4H RS
        if history.previous_rs_4h is not None:
            result.acceleration = rs_4h - history.previous_rs_4h

        return result

    def calculate_for_symbol(
        self,
        symbol: str,
        coin_candles: List[OHLCV],
        btc_candles: List[OHLCV],
    ) -> RelativeStrength:
        """
        Calculate rolling RS metrics for a named coin vs BTC.

        Same as calculate() but uses the symbol as the history key
        for accurate acceleration tracking across calls.

        Args:
            symbol: The coin symbol (e.g., "ETHUSDT").
            coin_candles: List of OHLCV candles for the coin (most recent last).
            btc_candles: List of OHLCV candles for BTC (most recent last, same timeframe).

        Returns:
            RelativeStrength dataclass with rs_4h, rs_24h, acceleration, and stale flag.
        """
        result = RelativeStrength()

        # Check for stale BTC data
        result.is_stale = self.get_stale_status()

        # Update BTC reference from the latest candle
        if btc_candles:
            self._btc_last_price = btc_candles[-1].close
            self._btc_last_update = time.time()
            result.is_stale = False

        # Need at least 2 candles for 4H RS
        if len(coin_candles) < 2 or len(btc_candles) < 2:
            return result

        # 4H RS
        coin_change_4h = self._pct_change(
            coin_candles[-2].close, coin_candles[-1].close
        )
        btc_change_4h = self._pct_change(
            btc_candles[-2].close, btc_candles[-1].close
        )
        rs_4h = coin_change_4h - btc_change_4h
        result.rs_4h = rs_4h

        # 24H RS (6 x 4H candles = 24H)
        if len(coin_candles) >= 7 and len(btc_candles) >= 7:
            coin_change_24h = self._pct_change(
                coin_candles[-7].close, coin_candles[-1].close
            )
            btc_change_24h = self._pct_change(
                btc_candles[-7].close, btc_candles[-1].close
            )
            result.rs_24h = coin_change_24h - btc_change_24h

        # Momentum acceleration using symbol as key
        if symbol not in self._coin_rs_history:
            self._coin_rs_history[symbol] = _CoinRSHistory()

        history = self._coin_rs_history[symbol]
        history.previous_rs_4h = history.current_rs_4h
        history.current_rs_4h = rs_4h

        if history.previous_rs_4h is not None:
            result.acceleration = rs_4h - history.previous_rs_4h

        return result

    def rank_all(self, scores: Dict[str, RelativeStrength]) -> Dict[str, float]:
        """
        Normalize all RS values to 0-100 percentile scale.

        Ranks all coins by their rs_4h value and assigns percentile scores
        based on their position in the ranked distribution.

        For N coins, the coin ranked #1 (highest RS) gets percentile 100,
        the coin ranked #N (lowest RS) gets percentile 0.
        For a single coin, percentile is 50.

        Args:
            scores: Dictionary mapping symbol to RelativeStrength.

        Returns:
            Dictionary mapping symbol to percentile (0-100).
        """
        if not scores:
            return {}

        # Sort symbols by rs_4h in ascending order
        sorted_symbols = sorted(scores.keys(), key=lambda s: scores[s].rs_4h)

        n = len(sorted_symbols)
        percentiles: Dict[str, float] = {}

        if n == 1:
            # Single coin gets 50th percentile
            percentiles[sorted_symbols[0]] = 50.0
        else:
            for rank_index, symbol in enumerate(sorted_symbols):
                # rank_index 0 = lowest RS → percentile 0
                # rank_index n-1 = highest RS → percentile 100
                percentile = (rank_index / (n - 1)) * 100.0
                percentiles[symbol] = percentile

        # Also update the percentile field in the RelativeStrength objects
        for symbol, percentile in percentiles.items():
            scores[symbol].percentile = percentile

        return percentiles

    def get_stale_status(self) -> bool:
        """
        Check if BTC price data is stale (older than 60 seconds).

        Returns:
            True if BTC data is stale or has never been set, False otherwise.
        """
        if self._btc_last_update == 0.0:
            # Never received BTC data
            return True

        elapsed = time.time() - self._btc_last_update
        return elapsed > 60.0

    def update_btc_price(self, price: float) -> None:
        """
        Manually update the BTC reference price and timestamp.

        Args:
            price: The latest BTC price.
        """
        self._btc_last_price = price
        self._btc_last_update = time.time()

    @property
    def btc_last_price(self) -> Optional[float]:
        """Get the last known BTC price."""
        return self._btc_last_price

    @property
    def btc_last_update(self) -> float:
        """Get the timestamp of the last BTC price update."""
        return self._btc_last_update

    @staticmethod
    def _pct_change(old_price: float, new_price: float) -> float:
        """
        Calculate percentage change between two prices.

        Args:
            old_price: The earlier price.
            new_price: The later price.

        Returns:
            Percentage change (e.g., 2.5 for a 2.5% increase).
            Returns 0.0 if old_price is zero to avoid division by zero.
        """
        if old_price == 0.0:
            return 0.0
        return ((new_price - old_price) / old_price) * 100.0

    @staticmethod
    def _get_coin_key(candles: List[OHLCV]) -> str:
        """
        Generate a stable key for a coin based on its candle data.

        Uses the first candle's timestamp as a proxy identifier.
        For proper tracking, use calculate_for_symbol() instead.
        """
        if candles:
            return f"coin_{candles[0].timestamp.isoformat()}_{candles[-1].close}"
        return "unknown"
