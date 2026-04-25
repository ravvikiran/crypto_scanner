"""
Data Fetcher for Crypto Scanner
Provides current price data for symbols using CoinGecko API.
"""

import requests
from typing import Dict, Optional


class CryptoDataFetcher:
    """Fetches current prices for crypto symbols."""
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.session = requests.Session()
    
    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., BTC, ETH)
            
        Returns:
            Current price in USD, or 0.0 if failed
        """
        try:
            # Ensure uppercase for CoinGecko compatibility
            cg_id = symbol.lower()
            url = f"{self.base_url}/simple/price"
            params = {
                "ids": cg_id,
                "vs_currencies": "usd"
            }
            resp = self.session.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get(cg_id, {}).get("usd", 0.0))
        except Exception as e:
            pass
        return 0.0