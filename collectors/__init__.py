"""
Market Data Collector
Fetches market data from various exchanges and APIs.
Enhanced with data validation and caching per PRD spec.
"""

import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from loguru import logger
import pandas as pd
import numpy as np
from dataclasses import dataclass, field

from models import CoinData, OHLCV, Timeframe, TrendDirection
from config import get_config


@dataclass
class CandleCache:
    """Cache for candle data with TTL"""
    candles: List[OHLCV] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)
    symbol: str = ""
    timeframe: str = ""
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache is expired"""
        age = (datetime.now() - self.fetched_at).total_seconds()
        return age > ttl_seconds


class DataCache:
    """
    In-memory data cache with TTL per timeframe.
    PRD Spec:
    - 1m → 30 sec
    - 5m → 1 min
    - 15m → 2 min
    - 1h → 5 min
    """
    
    TTL_MAP = {
        "1m": 30,
        "5m": 60,
        "15m": 120,
        "1h": 300,
        "4h": 300,
        "daily": 600
    }
    
    def __init__(self):
        self._cache: Dict[str, CandleCache] = {}
    
    def _make_key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"
    
    def get(self, symbol: str, timeframe: str) -> Optional[List[OHLCV]]:
        """Get cached candles if not expired"""
        key = self._make_key(symbol, timeframe)
        cache = self._cache.get(key)
        
        if cache is None:
            return None
        
        ttl = self.TTL_MAP.get(timeframe, 300)
        
        if cache.is_expired(ttl):
            del self._cache[key]
            return None
        
        return cache.candles
    
    def set(self, symbol: str, timeframe: str, candles: List[OHLCV]):
        """Store candles in cache"""
        key = self._make_key(symbol, timeframe)
        self._cache[key] = CandleCache(
            candles=candles,
            fetched_at=datetime.now(),
            symbol=symbol,
            timeframe=timeframe
        )
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()


# Global cache instance
_data_cache = DataCache()


def get_data_cache() -> DataCache:
    """Get the global data cache"""
    return _data_cache


class MarketDataCollector:
    """Collects market data from multiple sources"""
    
    def __init__(self):
        self.config = get_config()
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Supported timeframes mapping to API format
        self.timeframe_map = {
            "15m": "15m",
            "1h": "1h", 
            "4h": "4h",
            "daily": "1d"
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def get_top_coins(self, limit: int = 500) -> List[CoinData]:
        """
        Get top coins by market cap using CoinGecko API.
        Applies filters for liquidity and market cap.
        """
        coins = []
        page = 1
        per_page = 250
        max_pages = (limit + per_page - 1) // per_page  # Calculate pages needed
        
        try:
            # CoinGecko markets endpoint
            url = "https://api.coingecko.com/api/v3/coins/markets"
            
            while page <= max_pages and len(coins) < limit:
                params = {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "page": page,
                    "sparkline": "false",
                    "price_change_percentage": "24h"
                }
                
                if self.config.api.coingecko_api_key:
                    params["x_cg_demo_api_key"] = self.config.api.coingecko_api_key
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if not data:
                            break  # No more data
                            
                        for item in data:
                            # Apply filters
                            mc_millions = item.get("market_cap", 0) / 1_000_000
                            vol_millions = item.get("total_volume", 0) / 1_000_000
                            
                            if (mc_millions >= self.config.scanner.min_market_cap_millions and
                                vol_millions >= self.config.scanner.min_volume_24h_millions):
                                
                                coin = CoinData(
                                    symbol=item.get("symbol", "").upper(),
                                    name=item.get("name", ""),
                                    current_price=item.get("current_price", 0),
                                    market_cap=item.get("market_cap", 0),
                                    volume_24h=item.get("total_volume", 0),
                                    price_change_24h=item.get("price_change_24h", 0),
                                    price_change_percent_24h=item.get("price_change_percentage_24h", 0),
                                    rank=item.get("market_cap_rank", 0)
                                )
                                coins.append(coin)
                                
                                if len(coins) >= limit:
                                    break
                                    
                    else:
                        logger.error(f"CoinGecko API error: {response.status}")
                        break
                        
                page += 1
                
        except Exception as e:
            logger.error(f"Error fetching top coins: {e}")
        
        logger.info(f"Fetched {len(coins)} coins meeting liquidity criteria")
        return coins[:limit]
    
    async def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[OHLCV]:
        """
        Fetch OHLCV candles for a symbol.
        Uses Binance API as primary source with caching.
        
        PRD Requirements:
        - Use cache when available and not expired
        - Validate data (reject volume=0, candle gaps, abnormal spikes >15%)
        - Maintain rolling window of min 200 candles
        """
        # Check cache first
        cache = get_data_cache()
        cached = cache.get(symbol, timeframe)
        if cached is not None and len(cached) >= limit // 2:
            logger.debug(f"Using cached candles for {symbol} {timeframe}")
            return cached
        
        candles = []
        
        try:
            # Binance klines endpoint
            binance_symbol = f"{symbol}USDT" if not symbol.endswith("USDT") else symbol
            url = f"https://api.binance.com/api/v3/klines"
            params = {
                "symbol": binance_symbol,
                "interval": self.timeframe_map.get(timeframe, "1h"),
                "limit": limit
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for item in data:
                        candle = OHLCV(
                            timestamp=datetime.fromtimestamp(item[0] / 1000),
                            open=float(item[1]),
                            high=float(item[2]),
                            low=float(item[3]),
                            close=float(item[4]),
                            volume=float(item[5])
                        )
                        candles.append(candle)
                    
                    # PRD: Data validation
                    if not self._validate_candles(candles):
                        logger.warning(f"Candle validation failed for {symbol} {timeframe}")
                        return []
                    
                    # Cache the validated candles
                    cache.set(symbol, timeframe, candles)
                    
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
        
        return candles
    
    def _validate_candles(self, candles: List[OHLCV]) -> bool:
        """
        Validate candle data per PRD spec:
        - Reject if volume = 0
        - Reject if abnormal spikes (>15% price change in single candle)
        - Reject if candle gaps detected
        """
        if not candles:
            return False
        
        for i, candle in enumerate(candles):
            # Check 1: Volume = 0
            if candle.volume <= 0:
                logger.warning(f"Invalid candle: zero volume at index {i}")
                return False
            
            # Check 2: Abnormal spikes (>15% price change)
            if candle.open > 0:
                price_change_pct = abs(candle.close - candle.open) / candle.open * 100
                if price_change_pct > 15:
                    logger.warning(f"Abnormal price spike: {price_change_pct:.1f}% at index {i}")
                    return False
            
            # Check 3: Candle gaps (for consecutive candles)
            if i > 0:
                prev_candle = candles[i - 1]
                # Gap up: current open significantly above previous close
                gap_up = candle.open > prev_candle.close * 1.05
                # Gap down: current open significantly below previous close
                gap_down = candle.open < prev_candle.close * 0.95
                
                if gap_up or gap_down:
                    logger.warning(f"Candle gap detected: {'gap_up' if gap_up else 'gap_down'} at index {i}")
                    return False
        
        return True
    
    async def get_candles_for_coins(self, coins: List[CoinData], timeframes: List[str]) -> List[CoinData]:
        """
        Fetch candles for multiple coins across multiple timeframes.
        """
        tasks = []
        
        for coin in coins:
            for tf in timeframes:
                task = self._fetch_and_store_candles(coin, tf)
                tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return coins
    
    async def _fetch_and_store_candles(self, coin: CoinData, timeframe: str):
        """Fetch and store candles for a single coin/timeframe"""
        try:
            candles = await self.get_candles(coin.symbol, timeframe)
            if candles:
                coin.candles[timeframe] = candles
        except Exception as e:
            logger.debug(f"Could not fetch {coin.symbol} {timeframe}: {e}")
    
    async def get_btc_data(self) -> Optional[CoinData]:
        """Get Bitcoin data specifically for market filter"""
        try:
            url = "https://api.coingecko.com/api/v3/coins/bitcoin"
            params = {}
            if self.config.api.coingecko_api_key:
                params["x_cg_demo_api_key"] = self.config.api.coingecko_api_key
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return CoinData(
                        symbol="BTC",
                        name="Bitcoin",
                        current_price=data.get("market_data", {}).get("current_price", {}).get("usd", 0),
                        market_cap=data.get("market_data", {}).get("market_cap", {}).get("usd", 0),
                        volume_24h=data.get("market_data", {}).get("total_volume", {}).get("usd", 0),
                        price_change_24h=data.get("market_data", {}).get("price_change_24h", 0),
                        price_change_percent_24h=data.get("market_data", {}).get("price_change_percentage_24h", 0),
                        rank=1
                    )
        except Exception as e:
            logger.error(f"Error fetching BTC data: {e}")
        
        return None


class BinanceCollector:
    """Binance-specific data collector"""
    
    def __init__(self):
        self.config = get_config()
        self.base_url = "https://api.binance.com"
    
    async def get_candles(self, symbol: str, interval: str, limit: int = 200) -> List[OHLCV]:
        """Get candles from Binance"""
        candles = []
        
        try:
            url = f"{self.base_url}/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for item in data:
                            candles.append(OHLCV(
                                timestamp=datetime.fromtimestamp(item[0] / 1000),
                                open=float(item[1]),
                                high=float(item[2]),
                                low=float(item[3]),
                                close=float(item[4]),
                                volume=float(item[5])
                            ))
                            
        except Exception as e:
            logger.error(f"Binance error: {e}")
        
        return candles
    
    def get_symbols(self, quote: str = "USDT") -> List[str]:
        """Get all available symbols for a quote asset"""
        try:
            url = f"{self.base_url}/api/v3/exchangeInfo"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                symbols = [
                    s["symbol"] for s in data["symbols"]
                    if s["quoteAsset"] == quote and s["status"] == "TRADING"
                ]
                return symbols
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
        
        return []
