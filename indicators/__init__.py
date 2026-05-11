"""
Indicator Engine
Calculates technical indicators for trading strategies.
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from loguru import logger

from streaming.models import OHLCV


class IndicatorEngine:
    """Calculates technical indicators for market analysis"""

    def __init__(self):
        pass

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
