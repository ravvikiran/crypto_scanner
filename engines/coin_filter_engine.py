"""
Coin Filter Engine
Filters and prioritizes coins based on volume, momentum, and strength vs BTC.
"""

from typing import List, Tuple, Optional
from loguru import logger

from models import CoinData, TrendDirection
from config import get_config


class CoinFilterEngine:
    """
    Filter coins to focus on strong setups.
    
    Filters:
    - Top 150 by volume
    - Momentum score
    - Strength vs BTC
    """
    
    def __init__(self):
        self.config = get_config()
        self._momentum_cache = {}
        self._strength_cache = {}
    
    def filter_coins(
        self,
        coins: List[CoinData],
        max_coins: int = 150
    ) -> List[CoinData]:
        """
        Filter coins based on multiple criteria.
        
        Args:
            coins: List of coin data
            max_coins: Maximum coins to return
            
        Returns:
            Filtered and sorted list of coins
        """
        if not coins:
            return []
        
        stablecoins = {
            "USDT", "USDC", "DAI", "BUSD", "USDS", "USD1", "USDG",
            "USDF", "TUSD", "USDD", "FRAX", "USDE", "USDP"
        }
        
        filtered = [c for c in coins if c.symbol not in stablecoins]
        
        scored = []
        for coin in filtered:
            score = self._calculate_momentum_score(coin)
            if score > 0:
                scored.append((coin, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        result = [c for c, _ in scored[:max_coins]]
        
        logger.info(f"Filtered {len(result)} coins from {len(coins)} (removed {len(coins) - len(result)} stablecoins/low quality)")
        
        return result
    
    def _calculate_momentum_score(self, coin: CoinData) -> float:
        """
        Calculate momentum score based on:
        - 24h price change
        - Volume relative to market cap
        - Trend alignment
        """
        score = 0.0
        
        price_change = abs(coin.price_change_percent_24h)
        if price_change > 0:
            score += min(price_change * 2, 30)
        
        if coin.volume_24h > 0 and coin.market_cap > 0:
            volume_ratio = coin.volume_24h / coin.market_cap
            score += min(volume_ratio * 1000, 20)
        
        if coin.trend == TrendDirection.BULLISH:
            score += 25
        elif coin.trend == TrendDirection.BEARISH:
            score += 15
        
        if coin.rsi is not None:
            if 40 <= coin.rsi <= 60:
                score += 10
            elif 30 <= coin.rsi <= 70:
                score += 5
        
        score += min(coin.price_change_24h * 3, 15) if coin.price_change_24h > 0 else 0
        
        return score
    
    def calculate_strength_vs_btc(
        self,
        coin: CoinData,
        btc_change_24h: float,
        timeframe: str = "1h"
    ) -> float:
        """
        Calculate coin strength vs BTC.
        
        Returns:
            Strength score (-1 to 1):
            - Positive = outperforming BTC
            - Negative = underperforming BTC
        """
        coin_change = coin.price_change_percent_24h
        
        relative_strength = coin_change - btc_change_24h
        
        candles = coin.candles.get(timeframe, [])
        if len(candles) >= 20:
            recent = candles[-20:]
            
            btc_like_change = (recent[-1].close - recent[0].close) / recent[0].close * 100
            
            if btc_like_change != 0:
                momentum = ((coin_change / abs(btc_like_change)) - 1) if btc_like_change != 0 else 0
                relative_strength += momentum * 5
        
        return max(-1, min(1, relative_strength / 50))
    
    def filter_by_strength(
        self,
        coins: List[CoinData],
        btc_coin: Optional[CoinData],
        min_strength: float = -0.5,
        max_coins: int = 50
    ) -> List[CoinData]:
        """
        Filter coins by strength vs BTC.
        
        Args:
            coins: List of coins
            btc_coin: Bitcoin data for comparison
            min_strength: Minimum strength score
            max_coins: Maximum coins to return
            
        Returns:
            Filtered coins sorted by strength
        """
        if not btc_coin:
            return coins[:max_coins]
        
        btc_change = btc_coin.price_change_percent_24h
        
        scored = []
        for coin in coins:
            strength = self.calculate_strength_vs_btc(coin, btc_change)
            if strength >= min_strength:
                scored.append((coin, strength))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        result = [c for c, _ in scored[:max_coins]]
        
        logger.info(f"Filtered {len(result)} coins by strength vs BTC (min: {min_strength})")
        
        return result
    
    def rank_coins(
        self,
        coins: List[CoinData],
        btc_coin: Optional[CoinData] = None
    ) -> List[Tuple[CoinData, float]]:
        """
        Rank coins by composite score.
        
        Returns:
            List of (coin, score) tuples sorted by score
        """
        if not coins:
            return []
        
        btc_change = btc_coin.price_change_percent_24h if btc_coin else 0
        
        scored = []
        for coin in coins:
            momentum = self._calculate_momentum_score(coin)
            strength = self.calculate_strength_vs_btc(coin, btc_change) if btc_coin else 0
            
            composite = (momentum * 0.6) + (strength * 100 * 0.4)
            scored.append((coin, composite))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored
    
    def get_top_movers(
        self,
        coins: List[CoinData],
        direction: str = "both",
        limit: int = 10
    ) -> List[CoinData]:
        """
        Get top moving coins.
        
        Args:
            coins: List of coins
            direction: "up", "down", or "both"
            limit: Number of coins to return
            
        Returns:
            List of top moving coins
        """
        if direction == "up":
            filtered = [c for c in coins if c.price_change_percent_24h > 0]
            sorted_coins = sorted(filtered, key=lambda c: c.price_change_percent_24h, reverse=True)
        elif direction == "down":
            filtered = [c for c in coins if c.price_change_percent_24h < 0]
            sorted_coins = sorted(filtered, key=lambda c: c.price_change_percent_24h)
        else:
            sorted_coins = sorted(coins, key=lambda c: abs(c.price_change_percent_24h), reverse=True)
        
        return sorted_coins[:limit]
    
    def is_tradeable(self, coin: CoinData) -> Tuple[bool, str]:
        """
        Check if a coin is tradeable based on basic criteria.
        
        Returns:
            (is_tradeable, reason)
        """
        if coin.current_price < 0.0001:
            return False, "Price too low"
        
        if coin.current_price > 50000:
            return False, "Price too high"
        
        if coin.volume_24h < 10000:
            return False, "Volume too low"
        
        if coin.market_cap < 100000:
            return False, "Market cap too low"
        
        return True, "Tradeable"
    
    def apply_all_filters(
        self,
        coins: List[CoinData],
        btc_coin: Optional[CoinData],
        max_coins: int = 150,
        min_strength: float = -0.5
    ) -> List[CoinData]:
        """
        Apply all filters in sequence.
        
        Args:
            coins: Raw coin data
            btc_coin: Bitcoin data
            max_coins: Maximum coins after filtering
            min_strength: Minimum strength vs BTC
            
        Returns:
            Filtered coins
        """
        filtered = self.filter_coins(coins, max_coins=max_coins * 2)
        
        filtered = self.filter_by_strength(filtered, btc_coin, min_strength=min_strength, max_coins=max_coins)
        
        tradeable = []
        for coin in filtered:
            is_ok, _ = self.is_tradeable(coin)
            if is_ok:
                tradeable.append(coin)
        
        logger.info(f"Final filtered: {len(tradeable)} coins from {len(coins)} original")
        
        return tradeable