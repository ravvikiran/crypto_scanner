"""
Universe Manager - Dynamic Trading Pair Selection.

Fetches and manages the set of actively monitored USDT trading pairs
from Bybit's public REST API, filtering by volume and price thresholds.
Refreshes periodically and handles API failures gracefully.

Uses direct HTTP calls (aiohttp) instead of ccxt for reliability.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.9
"""

import asyncio
import os
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp
from loguru import logger

from streaming.models import UniversePair


# Bybit public API endpoint for tickers (no auth required)
BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"


class UniverseManager:
    """Dynamically selects and manages the set of monitored trading pairs.

    Fetches the top USDT linear perpetual pairs by 24h volume from Bybit,
    applies volume and price filters, and always includes BTCUSDT.

    Args:
        min_volume_usd: Minimum 24h volume in USD to include a pair (default 10M).
        min_price: Minimum current price in USD to include a pair (default 0.10).
    """

    # Symbol that is always included regardless of filters
    ALWAYS_INCLUDE_SYMBOL = "BTCUSDT"

    # Retry delay on API failure (seconds)
    RETRY_DELAY_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        min_volume_usd: float = 10_000_000,
        min_price: float = 0.10,
    ):
        self.min_volume_usd = min_volume_usd
        self.min_price = min_price

        # Current active symbols (e.g. "BTCUSDT")
        self._active_symbols: List[str] = []

        # Detailed pair data for the current universe
        self._pairs: List[UniversePair] = []

        # Track initialization state
        self._initialized: bool = False

    async def initialize(self) -> List[str]:
        """Fetch initial universe from Bybit REST API.

        Returns:
            List of active symbol strings (e.g. ["BTCUSDT", "ETHUSDT", ...]).
            Returns empty list if API is unavailable (caller should use fallback).
        """
        symbols = await self._fetch_and_filter()
        if symbols is not None and len(symbols) > 0:
            self._active_symbols = symbols
            self._initialized = True
            logger.info(
                f"Universe initialized with {len(self._active_symbols)} symbols"
            )
        else:
            logger.warning(
                "Universe initialization failed (API unavailable or empty response). "
                "Caller should use fallback symbol list."
            )
            # Don't raise — let the caller use its fallback list
            return []

        return list(self._active_symbols)

    async def refresh(self) -> Tuple[List[str], List[str]]:
        """Re-fetch universe and compute changes.

        Returns:
            Tuple of (added_symbols, removed_symbols).
            On API failure, returns ([], []) and retains previous list.
        """
        new_symbols = await self._fetch_and_filter()

        if new_symbols is None:
            logger.warning(
                f"Universe refresh failed, retaining previous list "
                f"({len(self._active_symbols)} symbols). "
                f"Will retry in {self.RETRY_DELAY_SECONDS // 60} minutes."
            )
            return ([], [])

        old_set = set(self._active_symbols)
        new_set = set(new_symbols)

        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)

        self._active_symbols = new_symbols

        logger.info(
            f"Universe refreshed: {len(self._active_symbols)} symbols "
            f"(+{len(added)} added, -{len(removed)} removed)"
        )

        if added:
            logger.debug(f"Added symbols: {added}")
        if removed:
            logger.debug(f"Removed symbols: {removed}")

        return (added, removed)

    def get_active_symbols(self) -> List[str]:
        """Return current active symbol list."""
        return list(self._active_symbols)

    async def _fetch_and_filter(self) -> Optional[List[str]]:
        """Fetch top USDT linear pairs by volume from Bybit and apply filters.

        Uses Bybit's public /v5/market/tickers endpoint directly via aiohttp.
        No API key required.

        Returns:
            Filtered list of symbol strings, or None on API failure.
        """
        try:
            logger.info("Fetching tickers from Bybit API...")

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20.0)
            ) as session:
                async with session.get(
                    BYBIT_TICKERS_URL,
                    params={"category": "linear"},
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Bybit API returned status {response.status}"
                        )
                        return None

                    data = await response.json()

            # Bybit response format: {"retCode": 0, "result": {"list": [...]}}
            if data.get("retCode") != 0:
                logger.error(
                    f"Bybit API error: {data.get('retMsg', 'unknown')}"
                )
                return None

            tickers = data.get("result", {}).get("list", [])
            logger.info(f"Received {len(tickers)} tickers from Bybit")

            if not tickers:
                logger.warning("Bybit returned empty ticker list")
                return None

            # Each ticker has: symbol, lastPrice, volume24h, turnover24h
            # turnover24h = volume in USDT (quote volume)
            # Sort by turnover (USDT volume) descending, take top 200
            valid_tickers = []
            for t in tickers:
                symbol = t.get("symbol", "")
                # Only USDT pairs
                if not symbol.endswith("USDT"):
                    continue
                turnover = float(t.get("turnover24h", 0) or 0)
                price = float(t.get("lastPrice", 0) or 0)
                valid_tickers.append({
                    "symbol": symbol,
                    "turnover": turnover,
                    "price": price,
                })

            # Sort by 24h turnover descending
            valid_tickers.sort(key=lambda x: x["turnover"], reverse=True)
            top_pairs = valid_tickers[:200]

            # Apply filters
            filtered_symbols: List[str] = []
            self._pairs = []

            for pair in top_pairs:
                symbol = pair["symbol"]
                volume_usd = pair["turnover"]
                price = pair["price"]

                # Always include BTCUSDT regardless of filters
                if symbol == self.ALWAYS_INCLUDE_SYMBOL:
                    filtered_symbols.append(symbol)
                    self._pairs.append(
                        UniversePair(
                            symbol=symbol,
                            volume_24h_usd=volume_usd,
                            current_price=price,
                            last_updated=datetime.utcnow(),
                        )
                    )
                    continue

                # Apply volume filter
                if volume_usd < self.min_volume_usd:
                    continue

                # Apply price filter
                if price < self.min_price:
                    continue

                filtered_symbols.append(symbol)
                self._pairs.append(
                    UniversePair(
                        symbol=symbol,
                        volume_24h_usd=volume_usd,
                        current_price=price,
                        last_updated=datetime.utcnow(),
                    )
                )

            # Ensure BTCUSDT is always present
            if self.ALWAYS_INCLUDE_SYMBOL not in filtered_symbols:
                filtered_symbols.insert(0, self.ALWAYS_INCLUDE_SYMBOL)
                self._pairs.insert(
                    0,
                    UniversePair(
                        symbol=self.ALWAYS_INCLUDE_SYMBOL,
                        volume_24h_usd=0.0,
                        current_price=0.0,
                        last_updated=datetime.utcnow(),
                    ),
                )

            logger.info(
                f"Filtered to {len(filtered_symbols)} symbols "
                f"(min volume: ${self.min_volume_usd/1e6:.0f}M, min price: ${self.min_price})"
            )
            return filtered_symbols

        except asyncio.TimeoutError:
            logger.error("Bybit API request timed out (20s)")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch universe from Bybit API: {e}")
            return None

    def get_pairs(self) -> List[UniversePair]:
        """Return detailed pair data for the current universe."""
        return list(self._pairs)

    @staticmethod
    def filter_pairs(
        pairs: List[dict],
        min_volume_usd: float = 10_000_000,
        min_price: float = 0.10,
    ) -> List[str]:
        """Pure filtering logic for testability.

        Args:
            pairs: List of dicts with keys 'symbol', 'volume_24h_usd', 'current_price'.
            min_volume_usd: Minimum 24h volume threshold.
            min_price: Minimum price threshold.

        Returns:
            List of symbol strings that pass the filters.
        """
        filtered = []

        for pair in pairs:
            symbol = pair.get("symbol", "")
            volume = float(pair.get("volume_24h_usd", 0))
            price = float(pair.get("current_price", 0))

            if symbol == "BTCUSDT":
                filtered.append(symbol)
                continue

            if volume < min_volume_usd:
                continue

            if price < min_price:
                continue

            filtered.append(symbol)

        if "BTCUSDT" not in filtered:
            filtered.insert(0, "BTCUSDT")

        return filtered

    async def close(self) -> None:
        """Clean up resources (no-op since we use per-request sessions)."""
        pass
