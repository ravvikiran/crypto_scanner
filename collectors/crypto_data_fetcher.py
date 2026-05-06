"""
Data Fetcher for Crypto Scanner
Provides current price data for symbols using CoinGecko API.
"""

import time
import requests
from typing import Dict, Optional
from loguru import logger


class CryptoDataFetcher:
    """Fetches current prices for crypto symbols."""
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CryptoScanner/1.0"
        })
        self._max_retries = 2
        self._retry_delay = 1.0
    
    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., BTC, ETH)
            
        Returns:
            Current price in USD, or 0.0 if failed
        """
        for attempt in range(self._max_retries + 1):
            try:
                cg_id = symbol.lower().replace('-usd', '').replace('-usdt', '')
                url = f"{self.base_url}/simple/price"
                params = {
                    "ids": cg_id,
                    "vs_currencies": "usd"
                }
                resp = self.session.get(url, params=params, timeout=10)
                
                if resp.status_code == 429:
                    # Rate limited - wait and retry
                    if attempt < self._max_retries:
                        wait_time = self._retry_delay * (attempt + 1)
                        logger.debug(f"Rate limited fetching {symbol}, retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    return 0.0
                
                if resp.status_code == 200:
                    data = resp.json()
                    return float(data.get(cg_id, {}).get("usd", 0.0))
                    
            except requests.exceptions.Timeout:
                if attempt < self._max_retries:
                    logger.debug(f"Timeout fetching {symbol}, retry {attempt + 1}")
                    time.sleep(self._retry_delay)
                    continue
            except requests.exceptions.ConnectionError:
                if attempt < self._max_retries:
                    logger.debug(f"Connection error fetching {symbol}, retry {attempt + 1}")
                    time.sleep(self._retry_delay)
                    continue
            except Exception as e:
                logger.debug(f"Error fetching price for {symbol}: {e}")
                break
        
        return 0.0
    
    def close(self):
        """Close the HTTP session and release resources."""
        if self.session:
            self.session.close()
    
    def __del__(self):
        """Ensure session is closed on garbage collection."""
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
