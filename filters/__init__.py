"""
Bitcoin Market Filter
Analyzes Bitcoin trend to filter/prioritize altcoin signals.
"""

from typing import Optional
from loguru import logger

from models import CoinData, TrendDirection
from collectors import MarketDataCollector
from indicators import IndicatorEngine


class BitcoinFilter:
    """
    Bitcoin Market Filter
    
    Rules:
    - If BTC bullish → prioritize long setups
    - If BTC bearish → prioritize shorts
    - If BTC ranging → reduce signals
    
    This avoids trading against the market leader.
    """
    
    def __init__(self):
        self.indicator_engine = IndicatorEngine()
    
    async def get_btc_trend(self, timeframe: str = "4h") -> TrendDirection:
        """Get current Bitcoin trend direction"""
        try:
            async with MarketDataCollector() as collector:
                btc = await collector.get_btc_data()
                
                if not btc:
                    logger.warning("Could not fetch BTC data")
                    return TrendDirection.NEUTRAL
                
                # Get candles for trend analysis
                candles = await collector.get_candles("BTC", timeframe)
                
                if not candles or len(candles) < 50:
                    logger.warning("Insufficient BTC candle data")
                    return TrendDirection.NEUTRAL
                
                btc.candles[timeframe] = candles
                
                # Calculate indicators
                btc = self.indicator_engine.calculate_all_indicators(btc, timeframe)
                
                trend = btc.trend
                
                logger.info(f"BTC Trend: {trend.value} | Price: ${btc.current_price:,.0f} | RSI: {btc.rsi:.1f}")
                
                return trend
                
        except Exception as e:
            logger.error(f"Error getting BTC trend: {e}")
            return TrendDirection.NEUTRAL
    
    def filter_signals_by_btc(
        self,
        signals: list,
        btc_trend: TrendDirection
    ) -> list:
        """
        Filter signals based on BTC trend.
        
        If BTC is strongly trending, filter out contrarian signals.
        """
        if not signals:
            return []
        
        if btc_trend == TrendDirection.NEUTRAL:
            # Allow all signals when BTC is neutral/ranging
            return signals
        
        filtered = []
        
        for signal in signals:
            # Check alignment
            if btc_trend == TrendDirection.BULLISH:
                # Prefer longs, but allow shorts if very strong setup
                if signal.direction.value == "LONG":
                    filtered.append(signal)
                elif signal.confidence_score >= 8.5:  # High confidence shorts allowed
                    filtered.append(signal)
                    
            elif btc_trend == TrendDirection.BEARISH:
                # Prefer shorts, but allow longs if very strong setup
                if signal.direction.value == "SHORT":
                    filtered.append(signal)
                elif signal.confidence_score >= 8.5:  # High confidence longs allowed
                    filtered.append(signal)
        
        return filtered
    
    def get_market_regime(self, btc_trend: TrendDirection, btc_rsi: float = 50) -> str:
        """
        Determine overall market regime.
        
        Returns:
        - BULL: Strong bullish trend
        - BEAR: Strong bearish trend
        - NEUTRAL: Ranging/mixed
        - VOLATILE: High uncertainty
        """
        if btc_trend == TrendDirection.BULLISH:
            if btc_rsi > 70:
                return "VOLATILE"  # Overbought - could reverse
            elif btc_rsi > 55:
                return "BULL"  # Healthy bullish
            else:
                return "NEUTRAL"  # Weak momentum
                
        elif btc_trend == TrendDirection.BEARISH:
            if btc_rsi < 30:
                return "VOLATILE"  # Oversold - could reverse
            elif btc_rsi < 45:
                return "BEAR"  # Healthy bearish
            else:
                return "NEUTRAL"  # Weak momentum
        
        return "NEUTRAL"
