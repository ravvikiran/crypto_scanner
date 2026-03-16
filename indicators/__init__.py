"""
Indicator Engine
Calculates technical indicators for trading strategies.
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from loguru import logger

from models import CoinData, OHLCV, TrendDirection
from config import get_config


class IndicatorEngine:
    """Calculates technical indicators for market analysis"""
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
    
    def calculate_all_indicators(self, coin: CoinData, timeframe: str = "1h") -> CoinData:
        """
        Calculate all indicators for a coin's candles.
        Returns updated coin data with indicators.
        """
        candles = coin.candles.get(timeframe, [])
        
        if not candles:
            return coin
        
        # Convert to DataFrame for easier calculation
        df = self._candles_to_dataframe(candles)
        
        if len(df) < 50:
            return coin
        
        # Calculate EMAs
        coin.ema_20 = self.calculate_ema(df["close"], self.strategy.ema_short)
        coin.ema_50 = self.calculate_ema(df["close"], self.strategy.ema_medium)
        coin.ema_100 = self.calculate_ema(df["close"], self.strategy.ema_long)
        coin.ema_200 = self.calculate_ema(df["close"], self.strategy.ema_very_long)
        
        # Calculate RSI
        coin.rsi = self.calculate_rsi(df["close"], self.strategy.rsi_period)
        
        # Calculate ATR
        coin.atr = self.calculate_atr(df, self.strategy.atr_period)
        
        # Calculate Volume MA
        coin.volume_ma = self.calculate_sma(df["volume"], self.strategy.volume_ma_period)
        
        # Calculate Bollinger Bands
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
            df["close"],
            self.strategy.bollinger_period,
            self.strategy.bollinger_std
        )
        coin.bb_upper = bb_upper
        coin.bb_middle = bb_middle
        coin.bb_lower = bb_lower
        
        # Determine trend
        coin.trend = self.determine_trend(coin)
        
        return coin
    
    def _candles_to_dataframe(self, candles: List[OHLCV]) -> pd.DataFrame:
        """Convert list of OHLCV candles to DataFrame"""
        return pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume
            }
            for c in candles
        ])
    
    def calculate_ema(self, series: pd.Series, period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        try:
            if len(series) < period:
                return None
            ema = series.ewm(span=period, adjust=False).mean()
            return float(ema.iloc[-1])
        except Exception as e:
            logger.debug(f"EMA calculation error: {e}")
            return None
    
    def calculate_sma(self, series: pd.Series, period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        try:
            if len(series) < period:
                return None
            sma = series.rolling(window=period).mean()
            return float(sma.iloc[-1])
        except Exception as e:
            logger.debug(f"SMA calculation error: {e}")
            return None
    
    def calculate_rsi(self, series: pd.Series, period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        try:
            if len(series) < period + 1:
                return None
            
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        except Exception as e:
            logger.debug(f"RSI calculation error: {e}")
            return None
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        try:
            if len(df) < period + 1:
                return None
            
            high = df["high"]
            low = df["low"]
            close = df["close"]
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            return float(atr.iloc[-1])
        except Exception as e:
            logger.debug(f"ATR calculation error: {e}")
            return None
    
    def calculate_bollinger_bands(
        self,
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate Bollinger Bands"""
        try:
            if len(series) < period:
                return None, None, None
            
            sma = series.rolling(window=period).mean()
            std = series.rolling(window=period).std()
            
            upper = sma + (std * std_dev)
            lower = sma - (std * std_dev)
            
            return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])
        except Exception as e:
            logger.debug(f"Bollinger Bands calculation error: {e}")
            return None, None, None
    
    def determine_trend(self, coin: CoinData) -> TrendDirection:
        """
        Determine trend direction based on EMA alignment.
        Bullish: EMA20 > EMA50 > EMA100 > EMA200
        Bearish: EMA20 < EMA50 < EMA100 < EMA200
        """
        try:
            if None in [coin.ema_20, coin.ema_50, coin.ema_100, coin.ema_200]:
                return TrendDirection.NEUTRAL
            
            ema_values = [
                coin.ema_20,
                coin.ema_50,
                coin.ema_100,
                coin.ema_200
            ]
            
            # Check bullish alignment
            if ema_values == sorted(ema_values):
                return TrendDirection.BULLISH
            
            # Check bearish alignment (descending)
            if ema_values == sorted(ema_values, reverse=True):
                return TrendDirection.BEARISH
            
            return TrendDirection.NEUTRAL
            
        except Exception as e:
            logger.debug(f"Trend determination error: {e}")
            return TrendDirection.NEUTRAL
    
    def is_volume_expanding(self, coin: CoinData, timeframe: str = "1h") -> bool:
        """Check if volume is expanding"""
        try:
            candles = coin.candles.get(timeframe, [])
            if len(candles) < self.strategy.volume_ma_period + 1:
                return False
            
            current_volume = candles[-1].volume
            volume_ma = self.calculate_sma(
                pd.Series([c.volume for c in candles[:-1]]),
                self.strategy.volume_ma_period
            )
            
            return current_volume > volume_ma if volume_ma else False
            
        except Exception as e:
            logger.debug(f"Volume expansion check error: {e}")
            return False
    
    def is_atr_lowest(self, coin: CoinData, timeframe: str = "1h", lookback: int = 20) -> bool:
        """Check if ATR is at lowest in lookback period"""
        try:
            candles = coin.candles.get(timeframe, [])
            if len(candles) < lookback:
                return False
            
            # Calculate ATR for each candle
            atr_values = []
            for i in range(lookback, len(candles)):
                atr = self._calculate_single_atr(
                    candles[i-lookback:i]
                )
                if atr:
                    atr_values.append(atr)
            
            if not atr_values:
                return False
            
            current_atr = atr_values[-1]
            lowest_atr = min(atr_values[:-1]) if len(atr_values) > 1 else current_atr
            
            return current_atr < lowest_atr
            
        except Exception as e:
            logger.debug(f"ATR lowest check error: {e}")
            return False
    
    def _calculate_single_atr(self, candles: List[OHLCV]) -> Optional[float]:
        """Calculate ATR for a single period"""
        try:
            if len(candles) < 2:
                return None
            
            tr_values = []
            for i in range(1, len(candles)):
                high = candles[i].high
                low = candles[i].low
                prev_close = candles[i-1].close
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                tr_values.append(tr)
            
            return sum(tr_values) / len(tr_values) if tr_values else None
            
        except Exception as e:
            return None
    
    def detect_liquidity_sweep(
        self,
        coin: CoinData,
        timeframe: str = "1h"
    ) -> Tuple[bool, bool]:
        """
        Detect liquidity sweep (fake breakout).
        Returns (is_bearish_sweep, is_bullish_sweep)
        """
        try:
            candles = coin.candles.get(timeframe, [])
            if len(candles) < 5:
                return False, False
            
            recent = candles[-5:]
            
            # Check for bearish sweep (false breakout to upside)
            # Price breaks previous high but closes below
            prev_high = max([c.high for c in recent[:-1]])
            last_candle = candles[-1]
            
            # Bearish sweep: breaks high but closes lower
            bearish_sweep = (
                last_candle.high > prev_high and
                last_candle.close < prev_high
            )
            
            # Bullish sweep: breaks low but closes higher
            prev_low = min([c.low for c in recent[:-1]])
            bullish_sweep = (
                last_candle.low < prev_low and
                last_candle.close > prev_low
            )
            
            return bearish_sweep, bullish_sweep
            
        except Exception as e:
            logger.debug(f"Liquidity sweep detection error: {e}")
            return False, False
    
    def calculate_volume_ratio(self, coin: CoinData, timeframe: str = "1h") -> float:
        """Calculate current volume vs volume MA ratio"""
        try:
            candles = coin.candles.get(timeframe, [])
            if len(candles) < self.strategy.volume_ma_period:
                return 1.0
            
            current_volume = candles[-1].volume
            vol_ma = self.calculate_sma(
                pd.Series([c.volume for c in candles[:-1]]),
                self.strategy.volume_ma_period
            )
            
            return current_volume / vol_ma if vol_ma else 1.0
            
        except Exception as e:
            return 1.0
