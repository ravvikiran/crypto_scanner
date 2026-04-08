"""
Market Regime Engine
Detects overall market condition and adjusts strategies dynamically.
"""

from enum import Enum
from typing import Optional, Tuple
from loguru import logger

from models import CoinData, TrendDirection
from config import get_config


class MarketRegime(Enum):
    """Market regime types"""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"


class MarketRegimeEngine:
    """
    Detect market regime using BTC as base.
    
    Indicators:
    - ATR (14) for volatility
    - EMA 50 slope for trend strength
    - Price range compression
    
    Output:
    - TRENDING → favor trend continuation
    - RANGING → favor reversals
    - HIGH_VOL → allow breakouts
    - LOW_VOL → avoid trades
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        
    def detect_regime(
        self,
        btc_coin: CoinData,
        timeframe: str = "4h"
    ) -> MarketRegime:
        """
        Detect market regime based on BTC analysis.
        
        Args:
            btc_coin: Bitcoin coin data with indicators calculated
            timeframe: Timeframe for analysis
            
        Returns:
            MarketRegime enum value
        """
        try:
            candles = btc_coin.candles.get(timeframe, [])
            if len(candles) < 50:
                return MarketRegime.RANGING
            
            volatility = self._calculate_volatility(candles)
            trend_strength = self._calculate_trend_strength(btc_coin)
            range_compression = self._calculate_range_compression(candles)
            
            regime = self._determine_regime(
                volatility=volatility,
                trend_strength=trend_strength,
                range_compression=range_compression,
                btc_rsi=btc_coin.rsi
            )
            
            logger.info(
                f"Market Regime: {regime.value} | "
                f"Vol: {volatility:.2f} | "
                f"Trend: {trend_strength:.2f} | "
                f"Compression: {range_compression:.2f}"
            )
            
            return regime
            
        except Exception as e:
            logger.error(f"Market regime detection error: {e}")
            return MarketRegime.RANGING
    
    def _calculate_volatility(self, candles, lookback: int = 20) -> float:
        """Calculate normalized volatility using ATR percentage"""
        if len(candles) < lookback + 1:
            return 1.0
        
        recent_candles = candles[-lookback:]
        current_price = recent_candles[-1].close
        
        atr_values = []
        for i in range(1, len(recent_candles)):
            high = recent_candles[i].high
            low = recent_candles[i].low
            prev_close = recent_candles[i-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            atr_values.append(tr)
        
        if not atr_values:
            return 1.0
        
        avg_tr = sum(atr_values) / len(atr_values)
        volatility = (avg_tr / current_price) * 100
        
        return volatility
    
    def _calculate_trend_strength(self, btc_coin: CoinData) -> float:
        """
        Calculate trend strength based on EMA alignment and slope.
        Returns value 0-1 where higher = stronger trend.
        """
        if not all([btc_coin.ema_20, btc_coin.ema_50, btc_coin.ema_100, btc_coin.ema_200]):
            return 0.5
        
        ema_values = [
            btc_coin.ema_20,
            btc_coin.ema_50,
            btc_coin.ema_100,
            btc_coin.ema_200
        ]
        
        current_price = btc_coin.current_price
        
        all_above = all(e > current_price * 0.99 for e in ema_values)
        all_below = all(e < current_price * 1.01 for e in ema_values)
        
        if all_above:
            ema_alignment = 1.0
        elif all_below:
            ema_alignment = 1.0
        else:
            ema_alignment = 0.3
        
        slope_factor = abs(btc_coin.ema_50 - btc_coin.ema_100) / btc_coin.ema_100
        slope_normalized = min(slope_factor * 100, 1.0)
        
        trend_strength = (ema_alignment * 0.7) + (slope_normalized * 0.3)
        
        return trend_strength
    
    def _calculate_range_compression(self, candles, lookback: int = 20) -> float:
        """
        Calculate range compression (lower = more compressed).
        Returns 0-1 where 1 = highly compressed.
        """
        if len(candles) < lookback:
            return 0.5
        
        recent = candles[-lookback:]
        
        ranges = []
        for c in recent:
            candle_range = (c.high - c.low) / c.close * 100
            ranges.append(candle_range)
        
        avg_range = sum(ranges) / len(ranges)
        
        current_range = ranges[-1]
        
        compression = 1 - (current_range / avg_range) if avg_range > 0 else 0
        
        return max(0, min(1, compression))
    
    def _determine_regime(
        self,
        volatility: float,
        trend_strength: float,
        range_compression: float,
        btc_rsi: Optional[float]
    ) -> MarketRegime:
        """Determine regime based on calculated metrics"""
        
        high_vol_threshold = 3.0
        low_vol_threshold = 1.0
        
        strong_trend_threshold = 0.6
        high_compression_threshold = 0.7
        
        if volatility > high_vol_threshold:
            return MarketRegime.HIGH_VOL
        
        if volatility < low_vol_threshold:
            return MarketRegime.LOW_VOL
        
        if trend_strength > strong_trend_threshold and range_compression < 0.3:
            return MarketRegime.TRENDING
        
        if range_compression > high_compression_threshold:
            return MarketRegime.RANGING
        
        if trend_strength > strong_trend_threshold:
            return MarketRegime.TRENDING
        
        return MarketRegime.RANGING
    
    def get_strategy_adjustment(self, regime: MarketRegime) -> dict:
        """
        Get strategy adjustments based on regime.
        
        Returns:
            Dictionary with adjustments for:
            - rsi_bounds: (low, high) for RSI
            - favor_strategies: list of strategy types to favor
            - min_confidence: minimum confidence threshold
            - max_position_size: maximum position size multiplier
        """
        adjustments = {
            MarketRegime.TRENDING: {
                "rsi_bounds": (55, 75),
                "favor_strategies": ["TREND_CONTINUATION", "VOLATILITY_BREAKOUT"],
                "min_confidence": 6.0,
                "max_position_size": 1.0,
                "description": "Favor trend continuation, allow breakouts"
            },
            MarketRegime.RANGING: {
                "rsi_bounds": (40, 60),
                "favor_strategies": ["LIQUIDITY_SWEEP", "BEARISH_SHORT"],
                "min_confidence": 7.0,
                "max_position_size": 0.7,
                "description": "Favor reversals, be more selective"
            },
            MarketRegime.HIGH_VOL: {
                "rsi_bounds": (45, 70),
                "favor_strategies": ["VOLATILITY_BREAKOUT", "TREND_CONTINUATION"],
                "min_confidence": 6.5,
                "max_position_size": 0.8,
                "description": "Allow breakouts, manage risk carefully"
            },
            MarketRegime.LOW_VOL: {
                "rsi_bounds": (30, 70),
                "favor_strategies": [],
                "min_confidence": 8.5,
                "max_position_size": 0.3,
                "description": "Avoid trades, wait for setup"
            }
        }
        
        return adjustments.get(regime, adjustments[MarketRegime.RANGING])