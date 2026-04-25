"""
LEGACY DATA FETCHER - NSE STOCK Market (Deprecated)
This file is kept for reference only. DO NOT USE for crypto scanner.
For crypto data, use src.crypto_data_fetcher.CryptoDataFetcher which fetches
from CoinGecko/Binance APIs for 24/7 cryptocurrency markets.
"""

import yfinance as yf
import pandas as pd
import logging
import time
import pytz
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Fetches historical stock data from Yahoo Finance.

    Attributes:
        period: Number of days of historical data to fetch
        interval: Timeframe for the data (default: 1D)
    """

    # Supported timeframes
    TIMEFRAMES = ["1D", "1H", "15m"]

    def __init__(self, period: int = 200, interval: str = "1D"):
        """
        Initialize the DataFetcher.

        Args:
            period: Number of days of historical data (default: 200 days for all EMAs)
            interval: Data interval (default: 1D for daily)
        """
        self.period = max(period, 200)  # Ensure at least 200 days for EMA200
        self.interval = interval
        # Cache for multi-timeframe data
        self._mtf_cache = {}

    def fetch_stock_data(
        self, ticker: str, interval: Optional[str] = None, days: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical data for a single stock with exponential backoff on errors.

        Args:
            ticker: Stock ticker symbol (e.g., 'RELIANCE')
            interval: Data interval (optional, uses default if not specified)
            days: Number of days (optional, uses default if not specified)

        Returns:
            DataFrame with OHLCV data or None if fetch fails
        """
        # Use instance defaults if not specified
        actual_interval = interval if interval else self.interval
        actual_days = days if days else self.period

        # Add .NS suffix for NSE stocks (only if not already present)
        ticker_clean = ticker.replace(".NS", "")
        nse_ticker = f"{ticker_clean}.NS"

        # Retry with exponential backoff
        for attempt in range(3):
            try:
                stock = yf.Ticker(nse_ticker)
                df = stock.history(
                    period=f"{actual_days}d",
                    interval=actual_interval,
                    auto_adjust=False,
                )

                if df.empty:
                    if attempt < 2:
                        time.sleep(2**attempt)
                        continue
                    return None

                # Minimum candles based on interval
                # 1D: 20 candles (20 days)
                # 1H: 50 candles
                # 15m: 50 candles
                min_candles = {
                    "1D": 20,
                    "1d": 20,
                    "1H": 30,
                    "1h": 30,
                    "15m": 30,
                    "15M": 30,
                }.get(actual_interval, 50)

                if len(df) < min_candles:
                    if attempt < 2:
                        time.sleep(2**attempt)
                        continue
                    return None

                # Normalize column names to lowercase
                df.columns = df.columns.str.lower()

                # Add ticker column for reference
                df["ticker"] = ticker

                logger.debug(
                    f"Fetched {len(df)} candles for {nse_ticker} ({actual_interval})"
                )
                return df

            except Exception as e:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    logger.debug(f"Failed to fetch {nse_ticker} after 3 attempts: {e}")
                    return None

        return None

    def fetch_multiple_stocks(
        self, tickers: list, max_workers: int = 3
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple stocks.

        Args:
            tickers: List of stock ticker symbols
            max_workers: Maximum number of parallel downloads

        Returns:
            Dictionary mapping ticker to DataFrame
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}

        logger.debug(f"Fetching data for {len(tickers)} stocks...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.fetch_stock_data, ticker): ticker
                for ticker in tickers
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    df = future.result()
                    if df is not None:
                        results[ticker] = df
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {str(e)}")

        logger.debug(
            f"Successfully fetched data for {len(results)}/{len(tickers)} stocks"
        )
        return results

    def is_market_open(self) -> bool:
        """
        Check if NSE market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        # Get current time in IST
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)

        # Market hours: 09:15 - 15:30 IST
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        # Check if weekday (Monday=0, Sunday=6)
        is_weekday = now.weekday() < 5
        is_market_hours = market_open <= now <= market_close

        return is_weekday and is_market_hours

    def get_live_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get live/recent data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with latest price data or None
        """
        try:
            ticker_clean = ticker.replace(".NS", "")
            nse_ticker = f"{ticker_clean}.NS"
            stock = yf.Ticker(nse_ticker)
            info = stock.info

            return {
                "ticker": ticker,
                "current_price": info.get(
                    "currentPrice", info.get("regularMarketPrice")
                ),
                "open": info.get("open"),
                "high": info.get("dayHigh"),
                "low": info.get("dayLow"),
                "volume": info.get("volume"),
                "market_cap": info.get("marketCap"),
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error fetching live data for {ticker}: {str(e)}")
            return None

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current price for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Current price or None if unavailable
        """
        live_data = self.get_live_data(ticker)
        if live_data:
            return live_data.get('current_price')
        return None

    def fetch_multi_timeframe(
        self, ticker: str, days: int = 30
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data from multiple timeframes for a single stock.

        Fetches: 1D (trend), 1H (structure), 15m (entry)

        Args:
            ticker: Stock ticker symbol
            days: Number of days of historical data

        Returns:
            Dictionary mapping timeframe to DataFrame
        """
        results = {}

        # Timeframe configurations
        timeframe_configs = {
            "1D": {"interval": "1D", "days": days},  # Trend identification
            "1H": {"interval": "1h", "days": days},  # Structure + Pullback
            "15m": {"interval": "15m", "days": 5},  # Entry trigger
        }

        for tf_name, config in timeframe_configs.items():
            df = self.fetch_stock_data(
                ticker, interval=config["interval"], days=config["days"]
            )
            if df is not None and not df.empty:
                results[tf_name] = df

        return results

    def fetch_multiple_stocks_multi_timeframe(
        self, tickers: list, max_workers: int = 3
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Fetch multi-timeframe data for multiple stocks.

        Args:
            tickers: List of stock ticker symbols
            max_workers: Maximum number of parallel downloads

        Returns:
            Dictionary mapping ticker to its multi-timeframe data
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {
                executor.submit(self.fetch_multi_timeframe, ticker): ticker
                for ticker in tickers
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    mtf_data = future.result()
                    if mtf_data:
                        results[ticker] = mtf_data
                except Exception as e:
                    logger.error(f"Error fetching MTF data for {ticker}: {str(e)}")

        return results
