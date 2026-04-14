"""
PRD Signal Detection Engine
Implements the PRD-specified signal logic:
- Trend Detection (EMA 50 > EMA 200, Higher Highs/Higher Lows)
- Breakout Signals (resistance breakout + volume confirmation)
- Pullback Signals (EMA pullback + RSI 40-55 confirmation)
- Rejection Filters (price below EMA 200, low volume, choppy market)
- Risk Management (stops, 1-2% risk, R/R >= 1:2)
- AI Confidence Scoring (0-100)
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
from loguru import logger

from models import (
    CoinData, OHLCV, TradingSignal, SignalDirection,
    StrategyType, TrendDirection
)
from config import get_config


@dataclass
class SwingPoints:
    """Swing high/low points for structure detection"""
    swing_highs: List[float]
    swing_lows: List[float]
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    
    @property
    def has_structure(self) -> bool:
        return len(self.swing_highs) >= 2 and len(self.swing_lows) >= 2


@dataclass
class SupportResistance:
    """Support and resistance levels"""
    resistance: Optional[float]
    support: Optional[float]
    lookback_period: int = 20


class PRDSignalEngine:
    """
    PRD Signal Detection Engine
    Implements all PRD signal logic requirements
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        
        # PRD Parameters
        self.breakout_volume_multiplier = 1.5
        self.pullback_rsi_low = 40
        self.pullback_rsi_high = 55
        self.min_risk_reward = 2.0
        self.max_risk_per_trade = 0.02  # 2%
        self.stop_loss_buffer = 0.015  # 1.5%
        
    def detect_trend(self, coin: CoinData, timeframe: str = "4h") -> Tuple[TrendDirection, float]:
        """
        Detect trend using PRD rules:
        - Uptrend: Price > EMA 50 > EMA 200
        - Check: Last 3 swing highs increasing
        - Check: Last 3 swing lows increasing
        
        Returns: (trend_direction, trend_strength 0-100)
        """
        candles = coin.candles.get(timeframe, [])
        
        if len(candles) < 50:
            return TrendDirection.NEUTRAL, 0
        
        # Get current values
        current_price = coin.current_price
        ema_50 = coin.ema_50
        ema_200 = coin.ema_200
        
        if ema_50 is None or ema_200 is None:
            return TrendDirection.NEUTRAL, 0
        
        # Check EMA alignment: Price > EMA 50 > EMA 200
        if not (current_price > ema_50 > ema_200):
            # Check for downtrend
            if current_price < ema_50 < ema_200:
                swing_points = self._detect_swing_points(candles)
                if self._has_bearish_structure(swing_points):
                    return TrendDirection.BEARISH, self._calculate_trend_strength(
                        current_price, ema_50, ema_200, swing_points, is_bullish=False
                    )
            return TrendDirection.NEUTRAL, 0
        
        # Bullish alignment detected
        swing_points = self._detect_swing_points(candles)
        
        if not self._has_bullish_structure(swing_points):
            return TrendDirection.NEUTRAL, 0
        
        trend_strength = self._calculate_trend_strength(
            current_price, ema_50, ema_200, swing_points, is_bullish=True
        )
        
        return TrendDirection.BULLISH, trend_strength
    
    def _detect_swing_points(self, candles: List[OHLCV], lookback: int = 20) -> SwingPoints:
        """Detect swing highs and lows"""
        if len(candles) < lookback:
            return SwingPoints([], [])
        
        swing_highs = []
        swing_lows = []
        
        # Use 5-bar pivots
        for i in range(2, len(candles) - 2):
            # Swing high
            if (candles[i].high >= candles[i-2].high and
                candles[i].high >= candles[i-1].high and
                candles[i].high >= candles[i+1].high and
                candles[i].high >= candles[i+2].high):
                swing_highs.append(candles[i].high)
            
            # Swing low
            if (candles[i].low <= candles[i-2].low and
                candles[i].low <= candles[i-1].low and
                candles[i].low <= candles[i+1].low and
                candles[i].low <= candles[i+2].low):
                swing_lows.append(candles[i].low)
        
        # Get last N swing points
        recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs
        recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows
        
        return SwingPoints(
            swing_highs=recent_highs,
            swing_lows=recent_lows,
            last_high=recent_highs[-1] if recent_highs else None,
            last_low=recent_lows[-1] if recent_lows else None
        )
    
    def _has_bullish_structure(self, swings: SwingPoints) -> bool:
        """Check if price has bullish structure (HH/HL)"""
        if len(swings.swing_highs) < 2 or len(swings.swing_lows) < 2:
            return False
        
        # Last 3 swing highs should be increasing
        hh_ok = all(
            swings.swing_highs[i] < swings.swing_highs[i+1]
            for i in range(len(swings.swing_highs) - 1)
        )
        
        # Last 3 swing lows should be increasing
        hl_ok = all(
            swings.swing_lows[i] < swings.swing_lows[i+1]
            for i in range(len(swings.swing_lows) - 1)
        )
        
        return hh_ok and hl_ok
    
    def _has_bearish_structure(self, swings: SwingPoints) -> bool:
        """Check if price has bearish structure (LH/LL)"""
        if len(swings.swing_highs) < 2 or len(swings.swing_lows) < 2:
            return False
        
        # Last 3 swing highs should be decreasing
        lh_ok = all(
            swings.swing_highs[i] > swings.swing_highs[i+1]
            for i in range(len(swings.swing_highs) - 1)
        )
        
        # Last 3 swing lows should be decreasing
        ll_ok = all(
            swings.swing_lows[i] > swings.swing_lows[i+1]
            for i in range(len(swings.swing_lows) - 1)
        )
        
        return lh_ok and ll_ok
    
    def _calculate_trend_strength(
        self,
        price: float,
        ema_50: float,
        ema_200: float,
        swings: SwingPoints,
        is_bullish: bool
    ) -> float:
        """Calculate trend strength 0-100"""
        if swings.last_low is None:
            return 50  # Base score
        
        # EMA separation strength
        ema_sep = abs(ema_50 - ema_200) / ema_200 * 100
        
        # Structure strength based on HH/HL progression
        structure_strength = 0
        if is_bullish and len(swings.swing_highs) >= 3:
            # Higher highs progression
            hh_gain = (swings.swing_highs[-1] - swings.swing_highs[0]) / swings.swing_highs[0]
            structure_strength = min(50, hh_gain * 100 * 10)
        
        # Base 50 + EMA separation (max 25) + structure (max 25)
        score = 50 + min(25, ema_sep * 5) + structure_strength
        
        return min(100, max(0, score))
    
    def get_support_resistance(self, coin: CoinData, timeframe: str = "4h") -> SupportResistance:
        """Get support and resistance levels using lookback period"""
        candles = coin.candles.get(timeframe, [])
        lookback = 20
        
        if len(candles) < lookback:
            return SupportResistance(None, None)
        
        recent = candles[-lookback:]
        
        resistance = max(c.high for c in recent)
        support = min(c.low for c in recent)
        
        return SupportResistance(resistance, support, lookback)
    
    def check_breakout_signal(
        self,
        coin: CoinData,
        trend: TrendDirection,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """
        Check for breakout signal:
        - Bullish: Price breaks above resistance (last 20-period high)
        - Bearish: Price breaks below support (last 20-period low)
        - Volume >= 1.5x average volume
        - Candle closes through breakout level
        """
        if trend == TrendDirection.BEARISH:
            return self._check_bearish_breakout(coin, timeframe)
        elif trend == TrendDirection.BULLISH:
            return self._check_bullish_breakout(coin, timeframe)
        return None
    
    def _check_bullish_breakout(
        self,
        coin: CoinData,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """Check for bullish breakout signal (LONG)"""
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 30:
            return None
        
        current_price = coin.current_price
        sr = self.get_support_resistance(coin, timeframe)
        
        if sr.resistance is None:
            return None
        
        if current_price <= sr.resistance:
            return None
        
        volume_ratio = self._calculate_volume_ratio(candles)
        if volume_ratio < self.breakout_volume_multiplier:
            return None
        
        last_candle = candles[-1]
        if not (last_candle.close > sr.resistance and last_candle.is_bullish):
            return None
        
        swing_points = self._detect_swing_points(candles)
        
        stop_loss: float
        if swing_points.last_low:
            stop_loss = swing_points.last_low * (1 - self.stop_loss_buffer)
        else:
            stop_loss = current_price * 0.98
        
        entry = current_price * 1.002
        risk = entry - stop_loss
        
        if risk <= 0:
            return None
        
        if risk / entry > self.max_risk_per_trade:
            stop_loss = entry * (1 - self.max_risk_per_trade)
            risk = entry - stop_loss
        
        target_1 = entry + (risk * 2)
        target_2 = entry + (risk * 3)
        
        reward = target_1 - entry
        risk_reward = reward / risk if risk > 0 else 0
        
        if risk_reward < self.min_risk_reward:
            return None
        
        structure_quality = 50
        if swing_points.has_structure:
            structure_quality = 75 if self._has_bullish_structure(swing_points) else 50
        
        trend_strength, _ = self.detect_trend(coin, timeframe)
        volume_score = min(25, (volume_ratio / 2) * 15)
        ai_conf = self._calculate_ai_confidence(
            trend_strength=structure_quality,
            volume_confirmed=volume_ratio >= 1.5,
            structure_quality=structure_quality,
            volatility=coin.atr or 0,
            price=current_price
        )
        
        reasoning = self._build_breakout_reasoning(
            coin=coin,
            timeframe=timeframe,
            resistance=sr.resistance,
            volume_ratio=volume_ratio,
            structure_quality=structure_quality
        )
        
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.LONG,
            strategy_type=StrategyType.BREAKOUT,
            timeframe=timeframe,
            entry_zone_min=current_price * 1.001,
            entry_zone_max=current_price * 1.005,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            risk_amount=risk,
            current_price=current_price,
            trend_alignment=True,
            volume_confirmation=True,
            reasoning=reasoning,
            breakout_level=sr.resistance,
            volume_multiplier=volume_ratio,
            rsi_at_entry=coin.rsi or 0,
            trend_strength=structure_quality,
            structure_quality=structure_quality,
            ai_confidence_score=ai_conf
        )
        
        signal.confidence_score = ai_conf / 10
        
        return signal
    
    def _check_bearish_breakout(
        self,
        coin: CoinData,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """Check for bearish breakout signal (SHORT)"""
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 30:
            return None
        
        current_price = coin.current_price
        sr = self.get_support_resistance(coin, timeframe)
        
        if sr.support is None:
            return None
        
        if current_price >= sr.support:
            return None
        
        volume_ratio = self._calculate_volume_ratio(candles)
        if volume_ratio < self.breakout_volume_multiplier:
            return None
        
        last_candle = candles[-1]
        if not (last_candle.close < sr.support and not last_candle.is_bullish):
            return None
        
        swing_points = self._detect_swing_points(candles)
        
        stop_loss: float
        if swing_points.last_high:
            stop_loss = swing_points.last_high * (1 + self.stop_loss_buffer)
        else:
            stop_loss = current_price * 1.02
        
        entry = current_price * 0.998
        risk = stop_loss - entry
        
        if risk <= 0:
            return None
        
        if risk / entry > self.max_risk_per_trade:
            stop_loss = entry * (1 + self.max_risk_per_trade)
            risk = stop_loss - entry
        
        target_1 = entry - (risk * 2)
        target_2 = entry - (risk * 3)
        
        reward = entry - target_1
        risk_reward = reward / risk if risk > 0 else 0
        
        if risk_reward < self.min_risk_reward:
            return None
        
        structure_quality = 50
        if swing_points.has_structure:
            structure_quality = 75 if self._has_bearish_structure(swing_points) else 50
        
        trend_strength, _ = self.detect_trend(coin, timeframe)
        ai_conf = self._calculate_ai_confidence(
            trend_strength=structure_quality,
            volume_confirmed=volume_ratio >= 1.5,
            structure_quality=structure_quality,
            volatility=coin.atr or 0,
            price=current_price
        )
        
        reasoning = self._build_bearish_breakout_reasoning(
            coin=coin,
            timeframe=timeframe,
            support=sr.support,
            volume_ratio=volume_ratio,
            structure_quality=structure_quality
        )
        
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.SHORT,
            strategy_type=StrategyType.BREAKOUT,
            timeframe=timeframe,
            entry_zone_min=current_price * 0.995,
            entry_zone_max=current_price * 0.999,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            risk_amount=risk,
            current_price=current_price,
            trend_alignment=True,
            volume_confirmation=True,
            reasoning=reasoning,
            breakout_level=sr.support,
            volume_multiplier=volume_ratio,
            rsi_at_entry=coin.rsi or 0,
            trend_strength=structure_quality,
            structure_quality=structure_quality,
            ai_confidence_score=ai_conf
        )
        
        signal.confidence_score = ai_conf / 10
        
        return signal
    
    def check_pullback_signal(
        self,
        coin: CoinData,
        trend: TrendDirection,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """
        Check for pullback signal:
        - Bullish pullback: Uptrend + Price retraces to EMA + RSI 40-55 + Bullish candle
        - Bearish pullback: Downtrend + Price retraces to EMA + RSI 45-60 + Bearish candle
        """
        if trend == TrendDirection.BEARISH:
            return self._check_bearish_pullback(coin, timeframe)
        elif trend == TrendDirection.BULLISH:
            return self._check_bullish_pullback(coin, timeframe)
        return None
    
    def _check_bullish_pullback(
        self,
        coin: CoinData,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """Check for bullish pullback signal (LONG)"""
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 50:
            return None
        
        current_price = coin.current_price
        ema_20 = coin.ema_20
        ema_50 = coin.ema_50
        rsi = coin.rsi
        
        if ema_20 is None or ema_50 is None:
            return None
        
        if rsi is None or not (self.pullback_rsi_low <= rsi <= self.pullback_rsi_high):
            return None
        
        pullback_zone_min = min(ema_20, ema_50) * 0.98
        pullback_zone_max = max(ema_20, ema_50) * 1.02
        
        if not (pullback_zone_min <= current_price <= pullback_zone_max):
            return None
        
        last_candle = candles[-1]
        if not last_candle.is_bullish:
            return None
        
        entry_min = current_price * 1.001
        entry_max = current_price * 1.005
        
        swing_points = self._detect_swing_points(candles)
        stop_loss: float
        if swing_points.last_low:
            stop_loss = swing_points.last_low * (1 - self.stop_loss_buffer)
        else:
            stop_loss = ema_50 * 0.97
        
        risk = entry_min - stop_loss
        if risk <= 0:
            return None
        
        if risk / entry_min > self.max_risk_per_trade:
            stop_loss = entry_min * (1 - self.max_risk_per_trade)
            risk = entry_min - stop_loss
        
        target_1 = entry_max + (risk * 2)
        target_2 = entry_max + (risk * 3)
        
        reward = target_1 - entry_max
        risk_reward = reward / risk if risk > 0 else 0
        
        if risk_reward < self.min_risk_reward:
            return None
        
        structure_quality = 50
        if swing_points.has_structure and self._has_bullish_structure(swing_points):
            structure_quality = 70
        
        ai_conf = self._calculate_ai_confidence(
            trend_strength=70,
            volume_confirmed=True,
            structure_quality=structure_quality,
            volatility=coin.atr or 0,
            price=current_price
        )
        
        reasoning = self._build_pullback_reasoning(
            coin=coin,
            timeframe=timeframe,
            ema_20=ema_20,
            ema_50=ema_50,
            rsi=rsi,
            structure_quality=structure_quality
        )
        
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.LONG,
            strategy_type=StrategyType.PULLBACK,
            timeframe=timeframe,
            entry_zone_min=entry_min,
            entry_zone_max=entry_max,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            risk_amount=risk,
            current_price=current_price,
            trend_alignment=True,
            volume_confirmation=False,
            reasoning=reasoning,
            rsi_at_entry=rsi,
            trend_strength=70,
            structure_quality=structure_quality,
            ai_confidence_score=ai_conf
        )
        
        signal.confidence_score = ai_conf / 10
        
        return signal
    
    def _check_bearish_pullback(
        self,
        coin: CoinData,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """Check for bearish pullback signal (SHORT)"""
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 50:
            return None
        
        current_price = coin.current_price
        ema_20 = coin.ema_20
        ema_50 = coin.ema_50
        rsi = coin.rsi
        
        if ema_20 is None or ema_50 is None:
            return None
        
        if rsi is None or not (45 <= rsi <= 60):
            return None
        
        pullback_zone_min = max(ema_20, ema_50) * 0.98
        pullback_zone_max = max(ema_20, ema_50) * 1.02
        
        if not (pullback_zone_min <= current_price <= pullback_zone_max):
            return None
        
        last_candle = candles[-1]
        if last_candle.is_bullish:
            return None
        
        entry_min = current_price * 0.995
        entry_max = current_price * 0.999
        
        swing_points = self._detect_swing_points(candles)
        stop_loss: float
        if swing_points.last_high:
            stop_loss = swing_points.last_high * (1 + self.stop_loss_buffer)
        else:
            stop_loss = ema_50 * 1.03
        
        risk = stop_loss - entry_max
        if risk <= 0:
            return None
        
        if risk / entry_max > self.max_risk_per_trade:
            stop_loss = entry_max * (1 + self.max_risk_per_trade)
            risk = stop_loss - entry_max
        
        target_1 = entry_min - (risk * 2)
        target_2 = entry_min - (risk * 3)
        
        reward = entry_min - target_1
        risk_reward = reward / risk if risk > 0 else 0
        
        if risk_reward < self.min_risk_reward:
            return None
        
        structure_quality = 50
        if swing_points.has_structure and self._has_bearish_structure(swing_points):
            structure_quality = 70
        
        ai_conf = self._calculate_ai_confidence(
            trend_strength=70,
            volume_confirmed=True,
            structure_quality=structure_quality,
            volatility=coin.atr or 0,
            price=current_price
        )
        
        reasoning = self._build_bearish_pullback_reasoning(
            coin=coin,
            timeframe=timeframe,
            ema_20=ema_20,
            ema_50=ema_50,
            rsi=rsi,
            structure_quality=structure_quality
        )
        
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.SHORT,
            strategy_type=StrategyType.PULLBACK,
            timeframe=timeframe,
            entry_zone_min=entry_min,
            entry_zone_max=entry_max,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            risk_amount=risk,
            current_price=current_price,
            trend_alignment=True,
            volume_confirmation=False,
            reasoning=reasoning,
            rsi_at_entry=rsi,
            trend_strength=70,
            structure_quality=structure_quality,
            ai_confidence_score=ai_conf
        )
        
        signal.confidence_score = ai_conf / 10
        
        return signal
    
    def check_rejection(
        self,
        coin: CoinData,
        trend: TrendDirection,
        timeframe: str = "4h"
    ) -> Optional[TradingSignal]:
        """
        Check for rejection signals (avoid trading):
        - Price below EMA 200
        - Low volume environment
        - Choppy sideways market
        """
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 30:
            return None
        
        rejection_reasons = []
        
        # Check price below EMA 200
        if coin.ema_200 and coin.current_price < coin.ema_200:
            rejection_reasons.append("price_below_ema200")
        
        # Check low volume
        volume_ratio = self._calculate_volume_ratio(candles)
        if volume_ratio < 0.8:
            rejection_reasons.append("low_volume")
        
        # Check choppy/sideways market
        if self._is_choppy_market(candles):
            rejection_reasons.append("choppy_market")
        
        # Return rejection signal if any reason
        if rejection_reasons:
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=SignalDirection.NEUTRAL,
                strategy_type=StrategyType.REJECTION,
                timeframe=timeframe,
                reasoning=f"Rejection reasons: {', '.join(rejection_reasons)}",
                confidence_score=0,
                ai_confidence_score=0
            )
            return signal
        
        return None
    
    def _calculate_volume_ratio(self, candles: List[OHLCV], period: int = 30) -> float:
        """Calculate current volume vs average"""
        if len(candles) < period:
            return 1.0
        
        volumes = [c.volume for c in candles[-period:-1]]
        current_volume = candles[-1].volume
        
        avg_volume = sum(volumes) / len(volumes)
        return current_volume / avg_volume if avg_volume > 0 else 1.0
    
    def _is_choppy_market(self, candles: List[OHLCV], lookback: int = 20) -> bool:
        """Check for choppy/sideways market using ATR"""
        if len(candles) < lookback:
            return False
        
        # Calculate price range vs ATR
        recent = candles[-lookback:]
        price_range = (max(c.high for c in recent) - min(c.low for c in recent)) / min(c.low for c in recent)
        
        # If price range is very small relative to price, it's choppy
        return price_range < 0.02
    
    def _calculate_ai_confidence(
        self,
        trend_strength: float,
        volume_confirmed: bool,
        structure_quality: float,
        volatility: float,
        price: float
    ) -> float:
        """
        Calculate AI confidence score (0-100)
        Based on:
        - Trend strength (0-25)
        - Volume confirmation (0-25)
        - Clean structure (0-25)
        - Volatility (0-25)
        """
        # Trend strength score (0-25)
        trend_score = min(25, trend_strength * 0.25)
        
        # Volume score (0-25)
        volume_score = 25 if volume_confirmed else 10
        
        # Structure score (0-25)
        structure_score = min(25, structure_quality * 0.25)
        
        # Volatility score - prefer moderate volatility
        volatility_pct = (volatility / price * 100) if price > 0 else 0
        if 1.0 <= volatility_pct <= 5.0:
            volatility_score = 25
        elif 0.5 <= volatility_pct < 1.0 or 5.0 < volatility_pct <= 8.0:
            volatility_score = 15
        else:
            volatility_score = 5
        
        return trend_score + volume_score + structure_score + volatility_score
    
    def _build_breakout_reasoning(
        self,
        coin: CoinData,
        timeframe: str,
        resistance: float,
        volume_ratio: float,
        structure_quality: float
    ) -> str:
        """Build breakout signal reasoning"""
        return (
            f"Breakout on {timeframe} | "
            f"Resistance breakout at ${resistance:.2f} | "
            f"Volume spike ({volume_ratio:.1f}x avg) | "
            f"Strong bullish close | "
            f"Market in uptrend (EMA aligned) | "
            f"Structure quality: {structure_quality:.0f}%"
        )
    
    def _build_pullback_reasoning(
        self,
        coin: CoinData,
        timeframe: str,
        ema_20: float,
        ema_50: float,
        rsi: float,
        structure_quality: float
    ) -> str:
        """Build pullback signal reasoning"""
        return (
            f"Pullback on {timeframe} | "
            f"Price at EMA pullback zone | "
            f"RSI healthy at {rsi:.1f} (40-55 zone) | "
            f"Bullish reversal candle | "
            f"Structure quality: {structure_quality:.0f}%"
        )
    
    def _build_bearish_breakout_reasoning(
        self,
        coin: CoinData,
        timeframe: str,
        support: float,
        volume_ratio: float,
        structure_quality: float
    ) -> str:
        """Build bearish breakout signal reasoning"""
        return (
            f"Bearish Breakout on {timeframe} | "
            f"Support breakdown at ${support:.2f} | "
            f"Volume spike ({volume_ratio:.1f}x avg) | "
            f"Strong bearish close | "
            f"Market in downtrend (EMA aligned) | "
            f"Structure quality: {structure_quality:.0f}%"
        )
    
    def _build_bearish_pullback_reasoning(
        self,
        coin: CoinData,
        timeframe: str,
        ema_20: float,
        ema_50: float,
        rsi: float,
        structure_quality: float
    ) -> str:
        """Build bearish pullback signal reasoning"""
        return (
            f"Bearish Pullback on {timeframe} | "
            f"Price at EMA resistance zone | "
            f"RSI elevated at {rsi:.1f} (45-60 zone) | "
            f"Bearish reversal candle | "
            f"Structure quality: {structure_quality:.0f}%"
        )
    
    def scan_all_prd_signals(
        self,
        coin: CoinData,
        timeframe: str = "4h"
    ) -> List[TradingSignal]:
        """
        Scan for all PRD signals:
        1. First check for rejections
        2. Then check for breakout signals (bullish or bearish)
        3. Then check for pullback signals (bullish or bearish)
        """
        signals = []
        
        # Detect trend
        trend, trend_strength = self.detect_trend(coin, timeframe)
        
        if trend == TrendDirection.NEUTRAL:
            return signals
        
        # For bullish trend: skip if price below EMA 200
        # For bearish trend: allow signals (price below EMA 200 is expected)
        if trend == TrendDirection.BULLISH:
            if coin.ema_200 and coin.current_price < coin.ema_200:
                return signals
        
        # Check volume - skip low volume environments
        candles = coin.candles.get(timeframe, [])
        if candles:
            volume_ratio = self._calculate_volume_ratio(candles)
            if volume_ratio < 0.8:
                return signals
        
        # Check breakout (handles both bullish and bearish)
        breakout = self.check_breakout_signal(coin, trend, timeframe)
        if breakout and breakout.ai_confidence_score >= 70:
            signals.append(breakout)
        
        # Check pullback (handles both bullish and bearish)
        pullback = self.check_pullback_signal(coin, trend, timeframe)
        if pullback and pullback.ai_confidence_score >= 70:
            if not any(s.strategy_type == StrategyType.BREAKOUT for s in signals):
                signals.append(pullback)
        
        return signals
    
    def filter_by_confidence(
        self,
        signals: List[TradingSignal],
        min_confidence: float = 70
    ) -> List[TradingSignal]:
        """Filter signals by AI confidence score (0-100 scale)"""
        return [
            s for s in signals
            if s.ai_confidence_score >= min_confidence
        ]
    
    def filter_by_risk_reward(
        self,
        signals: List[TradingSignal],
        min_rr: float = 2.0
    ) -> List[TradingSignal]:
        """Filter signals by minimum risk/reward ratio"""
        return [
            s for s in signals
            if s.risk_reward >= min_rr
        ]