"""
Historical Candle Backfill for the Momentum Scanner.

Fetches historical OHLCV candle data from Bybit REST API on startup
to populate candle buffers immediately, enabling signal detection
without waiting days for WebSocket data to accumulate.

Backfills:
- 4H: 200 candles (~33 days)
- 1H: 100 candles (~4 days)
- 15m: 50 candles (~12.5 hours)
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp

from streaming.models import OHLCV

logger = logging.getLogger(__name__)

# Bybit public kline endpoint (no auth required)
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"

# Timeframe to Bybit interval mapping
TIMEFRAME_TO_INTERVAL = {
    "4h": "240",
    "1h": "60",
    "15m": "15",
}

# How many candles to fetch per timeframe
BACKFILL_LIMITS = {
    "4h": 200,
    "1h": 100,
    "15m": 50,
}

# Rate limiting: max requests per second
MAX_REQUESTS_PER_SECOND = 5
REQUEST_DELAY = 1.0 / MAX_REQUESTS_PER_SECOND


async def backfill_symbol(
    symbol: str,
    timeframes: List[str],
    session: aiohttp.ClientSession,
) -> Dict[str, List[OHLCV]]:
    """
    Fetch historical candles for a single symbol across all timeframes.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT").
        timeframes: List of timeframes to backfill (e.g., ["4h", "1h", "15m"]).
        session: aiohttp session for HTTP requests.

    Returns:
        Dict mapping timeframe to list of OHLCV candles (oldest first).
    """
    result: Dict[str, List[OHLCV]] = {}

    for tf in timeframes:
        interval = TIMEFRAME_TO_INTERVAL.get(tf)
        if interval is None:
            continue

        limit = BACKFILL_LIMITS.get(tf, 100)
        candles = await _fetch_klines(session, symbol, interval, limit)
        if candles:
            result[tf] = candles

        # Rate limiting
        await asyncio.sleep(REQUEST_DELAY)

    return result


async def backfill_symbols(
    symbols: List[str],
    timeframes: List[str],
    max_concurrent: int = 3,
) -> Dict[str, Dict[str, List[OHLCV]]]:
    """
    Fetch historical candles for multiple symbols.

    Args:
        symbols: List of trading pair symbols.
        timeframes: List of timeframes to backfill.
        max_concurrent: Maximum concurrent HTTP requests.

    Returns:
        Dict mapping symbol to {timeframe: [OHLCV candles]}.
    """
    results: Dict[str, Dict[str, List[OHLCV]]] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    timeout = aiohttp.ClientTimeout(total=30.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for symbol in symbols:
            task = _backfill_with_semaphore(
                semaphore, symbol, timeframes, session, results
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    return results


async def _backfill_with_semaphore(
    semaphore: asyncio.Semaphore,
    symbol: str,
    timeframes: List[str],
    session: aiohttp.ClientSession,
    results: Dict[str, Dict[str, List[OHLCV]]],
) -> None:
    """Backfill a single symbol with semaphore-based concurrency control."""
    async with semaphore:
        try:
            data = await backfill_symbol(symbol, timeframes, session)
            if data:
                results[symbol] = data
        except Exception as e:
            logger.warning(f"Backfill failed for {symbol}: {e}")


async def _fetch_klines(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    limit: int,
) -> Optional[List[OHLCV]]:
    """
    Fetch kline data from Bybit REST API.

    Bybit returns candles in reverse chronological order (newest first),
    so we reverse them to get oldest-first ordering.

    Args:
        session: aiohttp session.
        symbol: Trading pair symbol (e.g., "BTCUSDT").
        interval: Bybit interval string (e.g., "240" for 4h).
        limit: Number of candles to fetch (max 200).

    Returns:
        List of OHLCV candles (oldest first), or None on failure.
    """
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": min(limit, 200),  # Bybit max is 200 per request
    }

    try:
        async with session.get(BYBIT_KLINE_URL, params=params) as response:
            if response.status != 200:
                logger.debug(
                    f"Bybit kline API returned {response.status} for {symbol}/{interval}"
                )
                return None

            data = await response.json()

        if data.get("retCode") != 0:
            logger.debug(
                f"Bybit kline API error for {symbol}/{interval}: {data.get('retMsg')}"
            )
            return None

        klines = data.get("result", {}).get("list", [])
        if not klines:
            return None

        # Bybit kline format: [timestamp_ms, open, high, low, close, volume, turnover]
        candles: List[OHLCV] = []
        for kline in klines:
            try:
                timestamp_ms = int(kline[0])
                candle = OHLCV(
                    timestamp=datetime.fromtimestamp(
                        timestamp_ms / 1000, tz=timezone.utc
                    ),
                    open=float(kline[1]),
                    high=float(kline[2]),
                    low=float(kline[3]),
                    close=float(kline[4]),
                    volume=float(kline[5]),
                )
                # Validate: skip zero-volume or invalid candles
                if candle.volume > 0 and candle.high >= candle.low:
                    candles.append(candle)
            except (IndexError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed kline for {symbol}: {e}")
                continue

        # Bybit returns newest first — reverse to get oldest first
        candles.reverse()

        logger.debug(
            f"Backfilled {len(candles)} {interval}-candles for {symbol}"
        )
        return candles

    except asyncio.TimeoutError:
        logger.debug(f"Timeout fetching klines for {symbol}/{interval}")
        return None
    except Exception as e:
        logger.debug(f"Error fetching klines for {symbol}/{interval}: {e}")
        return None
