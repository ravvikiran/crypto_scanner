"""
Volatility Gate - Per-coin ATR-based volatility pre-filter.

Validates that a coin's ATR14/price ratio falls within acceptable bounds
before allowing it to proceed to setup detection. Rejects dead coins
(too low volatility) and scam pump coins (too high volatility).

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import os
from typing import Tuple

from loguru import logger


class VolatilityGate:
    """
    Pre-detection filter that validates per-coin ATR-based volatility.

    Calculates ATR14 / current_price as a percentage and checks if it
    falls within configurable bounds (default 1.5% to 8.0%).

    Coins below the minimum are considered "dead" (insufficient movement).
    Coins above the maximum are considered "pump/dump" (excessive risk).
    """

    def __init__(
        self,
        min_ratio_pct: float = None,
        max_ratio_pct: float = None,
    ):
        """
        Initialize VolatilityGate with configurable thresholds.

        Args:
            min_ratio_pct: Minimum ATR14/price ratio percentage.
                           Defaults to VOLATILITY_MIN_PCT env var or 1.5.
            max_ratio_pct: Maximum ATR14/price ratio percentage.
                           Defaults to VOLATILITY_MAX_PCT env var or 8.0.
        """
        self.min_ratio_pct = min_ratio_pct if min_ratio_pct is not None else float(
            os.environ.get("VOLATILITY_MIN_PCT", "1.5")
        )
        self.max_ratio_pct = max_ratio_pct if max_ratio_pct is not None else float(
            os.environ.get("VOLATILITY_MAX_PCT", "8.0")
        )

    def evaluate(self, atr14: float, current_price: float) -> Tuple[bool, float]:
        """
        Check if ATR14/price ratio is within acceptable bounds.

        Args:
            atr14: The 14-period Average True Range value on the 1H timeframe.
            current_price: The current price of the coin.

        Returns:
            Tuple of (passed, ratio_pct) where:
                - passed: True if ratio is within [min_ratio_pct, max_ratio_pct]
                - ratio_pct: The calculated ATR14/price ratio as a percentage
        """
        ratio_pct = (atr14 / current_price) * 100

        passed = self.min_ratio_pct <= ratio_pct <= self.max_ratio_pct

        if not passed:
            if ratio_pct < self.min_ratio_pct:
                logger.debug(
                    f"Volatility too low: {ratio_pct:.2f}% "
                    f"(min {self.min_ratio_pct}%)"
                )
            else:
                logger.debug(
                    f"Volatility too high: {ratio_pct:.2f}% "
                    f"(max {self.max_ratio_pct}%)"
                )

        return (passed, ratio_pct)
