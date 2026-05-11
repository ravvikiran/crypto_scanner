"""
Universe Manager - Dynamic Trading Pair Selection.

Fetches and manages the set of actively monitored USDT trading pairs
from Binance, filtering by volume and price thresholds. Refreshes
periodically and handles API failures gracefully.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.9
"""

import asyncio
import os
from datetime import datetime
from typing import List, Optional, Tuple

import ccxt.async_support as ccxt
from loguru import logger

from streaming.models import UniversePair


class UniverseManager:
    """Dynamically selects and manages the set of monitored trading pairs.

    Fetches the top 100 USDT pairs by 24h volume from Binance REST API,
    applies volume and price filters, and always includes BTCUSDT.

    Args:
        min_volume_usd: Minimum 24h volume in USD to include a pair (default 50M).
        min_price: Minimum current price in USD to include a pair (default 0.10).
    """

    # Symbol that is always included regardless of filters
    ALWAYS_INCLUDE = "BTC/USDT"
    ALWAYS_INCLUDE_SYMBOL = "BTCUSDT"

    # Retry delay on API failure (seconds)
    RETRY_DELAY_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        min_volume_usd: float = 50_000_000,
        min_price: float = 0.10,
    ):
        self.min_volume_usd = min_volume_usd
        self.min_price = min_price

        # Current active symbols (Binance format, e.g. "BTCUSDT")
        self._active_symbols: List[str] = []

        # Detailed pair data for the current universe
        self._pairs: List[UniversePair] = []

        # Exchange instance (created on first use)
        self._exchange: Optional[ccxt.binance] = None

        # Track initialization state
        self._initialized: bool = False

    async def _get_exchange(self) -> ccxt.binance:
        """Get or create the ccxt Binance exchange instance."""
        if self._exchange is None:
            config = {
                "enableRateLimit": True,
            }
            # Use API keys if available (not required for public endpoints)
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if api_key and api_secret:
                config["apiKey"] = api_key
                config["secret"] = api_secret

            self._exchange = ccxt.binance(config)
        return self._exchange

    async def _close_exchange(self) -> None:
        """Close the exchange connection."""
        if self._exchange is not None:
            await self._exchange.close()
            self._exchange = None

    async def initialize(self) -> List[str]:
        """Fetch initial universe from Binance REST API.

        Returns:
            List of active symbol strings (e.g. ["BTCUSDT", "ETHUSDT", ...]).

        Raises:
            Exception: If the initial fetch fails and there is no previous list.
        """
        symbols = await self._fetch_and_filter()
        if symbols is not None:
            self._active_symbols = symbols
            self._initialized = True
            logger.info(
                f"Universe initialized with {len(self._active_symbols)} symbols"
            )
        else:
            # On initial failure with no previous data, raise
            if not self._active_symbols:
                logger.error(
                    "Universe initialization failed and no previous list available"
                )
                raise RuntimeError(
                    "Failed to initialize universe: Binance API unavailable"
                )
            # Otherwise retain previous (shouldn't happen on first init)
            logger.warning(
                "Universe initialization failed, retaining previous list "
                f"({len(self._active_symbols)} symbols)"
            )

        return list(self._active_symbols)

    async def refresh(self) -> Tuple[List[str], List[str]]:
        """Re-fetch universe and compute changes.

        Returns:
            Tuple of (added_symbols, removed_symbols).
            On API failure, returns ([], []) and retains previous list.
        """
        new_symbols = await self._fetch_and_filter()

        if new_symbols is None:
            # API failure: retain previous list, schedule retry after 5 minutes
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
        """Return current active symbol list.

        Returns:
            List of active symbol strings (e.g. ["BTCUSDT", "ETHUSDT", ...]).
        """
        return list(self._active_symbols)

    async def _fetch_and_filter(self) -> Optional[List[str]]:
        """Fetch top 100 USDT pairs by volume and apply filters.

        Returns:
            Filtered list of symbol strings, or None on API failure.
        """
        try:
            exchange = await self._get_exchange()

            # Fetch all tickers from Binance
            tickers = await exchange.fetch_tickers()

            # Filter to USDT pairs only
            usdt_tickers = {
                symbol: ticker
                for symbol, ticker in tickers.items()
                if symbol.endswith("/USDT")
                and ticker.get("quoteVolume") is not None
            }

            # Sort by 24h quote volume (USD) descending, take top 100
            sorted_pairs = sorted(
                usdt_tickers.items(),
                key=lambda x: float(x[1].get("quoteVolume", 0) or 0),
                reverse=True,
            )[:100]

            # Apply filters
            filtered_symbols: List[str] = []
            self._pairs = []

            for symbol, ticker in sorted_pairs:
                volume_usd = float(ticker.get("quoteVolume", 0) or 0)
                price = float(ticker.get("last", 0) or 0)

                # Convert ccxt symbol format (BTC/USDT) to exchange format (BTCUSDT)
                exchange_symbol = symbol.replace("/", "")

                # Always include BTCUSDT regardless of filters
                if exchange_symbol == self.ALWAYS_INCLUDE_SYMBOL:
                    filtered_symbols.append(exchange_symbol)
                    self._pairs.append(
                        UniversePair(
                            symbol=exchange_symbol,
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

                filtered_symbols.append(exchange_symbol)
                self._pairs.append(
                    UniversePair(
                        symbol=exchange_symbol,
                        volume_24h_usd=volume_usd,
                        current_price=price,
                        last_updated=datetime.utcnow(),
                    )
                )

            # Ensure BTCUSDT is always present even if not in top 100
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

            return filtered_symbols

        except Exception as e:
            logger.error(f"Failed to fetch universe from Binance API: {e}")
            return None

    def get_pairs(self) -> List[UniversePair]:
        """Return detailed pair data for the current universe."""
        return list(self._pairs)

    @staticmethod
    def filter_pairs(
        pairs: List[dict],
        min_volume_usd: float = 50_000_000,
        min_price: float = 0.10,
    ) -> List[str]:
        """Pure filtering logic for testability.

        Applies volume and price filters to a list of pair dicts,
        always including BTCUSDT.

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

            # Always include BTCUSDT
            if symbol == "BTCUSDT":
                filtered.append(symbol)
                continue

            # Apply volume filter
            if volume < min_volume_usd:
                continue

            # Apply price filter
            if price < min_price:
                continue

            filtered.append(symbol)

        # Ensure BTCUSDT is present even if not in input
        if "BTCUSDT" not in filtered:
            filtered.insert(0, "BTCUSDT")

        return filtered

    async def close(self) -> None:
        """Clean up resources."""
        await self._close_exchange()
