"""
Multi-Timeframe EMA + Volume Breakout Strategy Engine

This module implements the enhanced strategy with:
- Multi-timeframe analysis (1D, 1H, 15m)
- Market structure detection (Higher Highs/Lower Lows)
- EMA alignment validation
- Pullback detection
- Volume spike confirmation
- Trade validator with rejection reasons
- Standardized signal output

Strategy Logic:
1. Trend Identification (1D) - Price vs EMA 200
2. Structure Confirmation (1H) - Higher Highs + Higher Lows
3. Pullback Detection (1H) - Price retraces to EMA 50/100
4. Entry Trigger (15m) - Strong breakout candle
5. Volume Confirmation - Current volume > Volume MA(30)
6. EMA Alignment Filter - 20 > 50 > 100 > 200
7. Trade Entry - Execute only if ALL conditions pass
8. Stop Loss Logic - Below/above recent swing low/high
9. Target Logic - Risk:Reward = 1:2
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import pandas as pd
from loguru import logger

from models import (
    CoinData, OHLCV, TradingSignal, SignalDirection,
    StrategyType, TrendDirection
)
from config import get_config
from indicators import IndicatorEngine


class MarketStructure(Enum):
    """Market structure types"""
    HIGHER_HIGHS = "HIGHER_HIGHS"      # Bullish structure
    LOWER_LOWS = "LOWER_LOWS"          # Bearish structure
    CONSOLIDATION = "CONSOLIDATION"     # Sideways/neutral
    UNCERTAIN = "UNCERTAIN"


class EMAAlignment(Enum):
    """EMA alignment states"""
    BULLISH_ALIGNED = "BULLISH_ALIGNED"     # 20 > 50 > 100 > 200
    BEARISH_ALIGNED = "BEARISH_ALIGNED"     # 20 < 50 < 100 < 200
    FLAT = "FLAT"                          # EMAs tangled/flat
    MIXED = "MIXED"                        # Mixed alignment


@dataclass
class ValidationResult:
    """Result of trade validation"""
    is_valid: bool
    signal: Optional[TradingSignal] = None
    rejection_reason: str = ""
    validation_details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "is_valid": self.is_valid,
            "rejection_reason": self.rejection_reason,
            "validation_details": self.validation_details
        }


@dataclass
class MultiTimeframeData:
    """Data from multiple timeframes"""
    # 1D data (trend identification)
    daily_trend: TrendDirection = TrendDirection.NEUTRAL
    daily_ema_200: Optional[float] = None
    
    # 1H data (structure + pullback)
    hourly_structure: MarketStructure = MarketStructure.UNCERTAIN
    hourly_trend: TrendDirection = TrendDirection.NEUTRAL
    hourly_ema_20: Optional[float] = None
    hourly_ema_50: Optional[float] = None
    hourly_ema_100: Optional[float] = None
    hourly_ema_200: Optional[float] = None
    pullback_level: Optional[str] = None  # "EMA50", "EMA100", or None
    
    # 15m data (entry trigger)
    entry_trend: TrendDirection = TrendDirection.NEUTRAL
    entry_ema_alignment: EMAAlignment = EMAAlignment.MIXED
    
    # Volume data
    volume_spike: bool = False
    volume_ratio: float = 1.0
    
    # Structure points
    recent_swing_high: Optional[float] = None
    recent_swing_low: Optional[float] = None


class StructureDetector:
    """
    Detects market structure (Higher Highs/Lower Lows)
    """
    
    def __init__(self):
        self.config = get_config()
    
    def detect_structure(
        self,
        candles: List[OHLCV],
        lookback: int = 20
    ) -> Tuple[MarketStructure, Optional[float], Optional[float]]:
        """
        Detect market structure from candles.
        Returns: (structure_type, recent_swing_high, recent_swing_low)
        """
        if len(candles) < lookback:
            return MarketStructure.UNCERTAIN, None, None
        
        try:
            # Find swing highs and lows
            swing_highs = []
            swing_lows = []
            
            for i in range(2, len(candles) - 2):
                # Swing high: highest of 5 candles
                if (candles[i].high >= candles[i-2].high and
                    candles[i].high >= candles[i-1].high and
                    candles[i].high >= candles[i+1].high and
                    candles[i].high >= candles[i+2].high):
                    swing_highs.append(candles[i].high)
                
                # Swing low: lowest of 5 candles
                if (candles[i].low <= candles[i-2].low and
                    candles[i].low <= candles[i-1].low and
                    candles[i].low <= candles[i+1].low and
                    candles[i].low <= candles[i+2].low):
                    swing_lows.append(candles[i].low)
            
            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return MarketStructure.CONSOLIDATION, None, None
            
            # Check for Higher Highs + Higher Lows (Bullish)
            if (swing_highs[-1] > swing_highs[-2] and
                swing_lows[-1] > swing_lows[-2]):
                return MarketStructure.HIGHER_HIGHS, swing_highs[-1], swing_lows[-1]
            
            # Check for Lower Highs + Lower Lows (Bearish)
            if (swing_highs[-1] < swing_highs[-2] and
                swing_lows[-1] < swing_lows[-2]):
                return MarketStructure.LOWER_LOWS, swing_highs[-1], swing_lows[-1]
            
            return MarketStructure.CONSOLIDATION, swing_highs[-1] if swing_highs else None, swing_lows[-1] if swing_lows else None
            
        except Exception as e:
            logger.debug(f"Structure detection error: {e}")
            return MarketStructure.UNCERTAIN, None, None
    
    def get_all_swing_levels(
        self,
        candles: List[OHLCV],
        lookback: int = 20
    ) -> Tuple[List[float], List[float]]:
        """Get all swing highs and lows for target calculation"""
        if len(candles) < lookback:
            return [], []
        
        swing_highs = []
        swing_lows = []
        
        try:
            for i in range(2, len(candles) - 2):
                if (candles[i].high >= candles[i-2].high and
                    candles[i].high >= candles[i-1].high and
                    candles[i].high >= candles[i+1].high and
                    candles[i].high >= candles[i+2].high):
                    swing_highs.append(candles[i].high)
                
                if (candles[i].low <= candles[i-2].low and
                    candles[i].low <= candles[i-1].low and
                    candles[i].low <= candles[i+1].low and
                    candles[i].low <= candles[i+2].low):
                    swing_lows.append(candles[i].low)
        except Exception as e:
            logger.debug(f"Error getting swing levels: {e}")
        
        return swing_highs[-5:] if len(swing_highs) > 5 else swing_highs, swing_lows[-5:] if len(swing_lows) > 5 else swing_lows
    
    def calculate_targets_from_swing_levels(
        self,
        swing_levels: List[float],
        entry: float,
        is_long: bool = True
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate targets from actual swing levels on chart"""
        if not swing_levels:
            return None, None
        
        targets = []
        for level in swing_levels:
            if is_long and level > entry:
                targets.append(level)
            elif not is_long and level < entry:
                targets.append(level)
        
        if len(targets) >= 2:
            return targets[0], targets[1]
        elif len(targets) == 1:
            return targets[0], None
        
        return None, None


class EMAAlignmentChecker:
    """
    Validates EMA alignment and detects sideways conditions
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
    
    def check_alignment(
        self,
        ema_20: Optional[float],
        ema_50: Optional[float],
        ema_100: Optional[float],
        ema_200: Optional[float]
    ) -> Tuple[EMAAlignment, str]:
        """
        Check EMA alignment.
        Returns: (alignment_type, description)
        """
        if None in [ema_20, ema_50, ema_100, ema_200]:
            return EMAAlignment.MIXED, "Insufficient EMA data"
        
        ema_values = [ema_20, ema_50, ema_100, ema_200]
        
        # Check bullish alignment
        if ema_values == sorted(ema_values):
            return EMAAlignment.BULLISH_ALIGNED, "Bullish: EMA 20 > 50 > 100 > 200"
        
        # Check bearish alignment
        if ema_values == sorted(ema_values, reverse=True):
            return EMAAlignment.BEARISH_ALIGNED, "Bearish: EMA 20 < 50 < 100 < 200"
        
        # Check for flat/tangled (sideways)
        # If EMAs are within 1% of each other, consider them flat
        ema_range = max(ema_values) - min(ema_values)
        ema_avg = sum(ema_values) / len(ema_values)
        
        if ema_range / ema_avg < 0.01:
            return EMAAlignment.FLAT, "EMAs are flat - sideways market"
        
        return EMAAlignment.MIXED, "EMAs are tangled/mixed"


class PullbackDetector:
    """
    Detects pullback to EMA 50 or EMA 100
    """
    
    def __init__(self):
        self.config = get_config()
    
    def detect_pullback(
        self,
        current_price: float,
        ema_50: Optional[float],
        ema_100: Optional[float],
        tolerance: float = 0.03  # 3% tolerance
    ) -> Tuple[Optional[str], bool]:
        """
        Detect if price is at pullback to EMA.
        Returns: (pullback_level, is_at_pullback)
        """
        if ema_50 is None and ema_100 is None:
            return None, False
        
        # Check pullback to EMA 50
        if ema_50 is not None:
            if abs(current_price - ema_50) / ema_50 <= tolerance:
                return "EMA50", True
        
        # Check pullback to EMA 100
        if ema_100 is not None:
            if abs(current_price - ema_100) / ema_100 <= tolerance:
                return "EMA100", True
        
        return None, False


class VolumeAnalyzer:
    """
    Analyzes volume and detects volume spikes
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
    
    def analyze_volume(
        self,
        candles: List[OHLCV],
        period: int = 30,
        spike_threshold: float = 1.5
    ) -> Tuple[bool, float]:
        """
        Analyze volume and detect spikes.
        Returns: (is_volume_spike, volume_ratio)
        """
        if len(candles) < period:
            return False, 1.0
        
        try:
            volumes = [c.volume for c in candles[:-1]]
            current_volume = candles[-1].volume
            
            # Calculate volume MA
            volume_ma = sum(volumes[-period:]) / period
            
            # Calculate ratio
            ratio = current_volume / volume_ma if volume_ma > 0 else 1.0
            
            # Check for spike
            is_spike = ratio >= spike_threshold
            
            return is_spike, ratio
            
        except Exception as e:
            logger.debug(f"Volume analysis error: {e}")
            return False, 1.0


class BreakoutDetector:
    """
    Detects breakout candles and validates entry triggers
    """
    
    def __init__(self):
        self.config = get_config()
    
    def detect_breakout(
        self,
        candles: List[OHLCV],
        direction: TrendDirection,
        resistance_level: Optional[float] = None,
        support_level: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Detect strong breakout candle.
        Returns: (is_valid_breakout, reason)
        """
        if len(candles) < 3:
            return False, "Insufficient candles"
        
        try:
            current = candles[-1]
            prev = candles[-2]
            
            if direction == TrendDirection.BULLISH:
                # Bullish breakout: price breaks above resistance
                if resistance_level:
                    # Must close above resistance (not just wick)
                    if current.close > resistance_level:
                        # Check for strong bullish candle
                        body_size = current.close - current.open
                        total_range = current.high - current.low
                        
                        # Body should be at least 60% of range
                        if body_size / total_range >= 0.6:
                            return True, "Bullish breakout above resistance"
                    
                    return False, "No breakout above resistance"
                
                # Alternative: break above previous high
                if current.close > prev.high:
                    body_size = current.close - current.open
                    total_range = current.high - current.low
                    
                    if body_size / total_range >= 0.6:
                        return True, "Bullish breakout above previous high"
                    
                    return False, "Weak breakout candle"
                
                return False, "No bullish breakout"
            
            elif direction == TrendDirection.BEARISH:
                # Bearish breakout: price breaks below support
                if support_level:
                    if current.close < support_level:
                        body_size = current.open - current.close
                        total_range = current.high - current.low
                        
                        if body_size / total_range >= 0.6:
                            return True, "Bearish breakout below support"
                    
                    return False, "No breakout below support"
                
                # Alternative: break below previous low
                if current.close < prev.low:
                    body_size = current.open - current.close
                    total_range = current.high - current.low
                    
                    if body_size / total_range >= 0.6:
                        return True, "Bearish breakout below previous low"
                    
                    return False, "Weak breakout candle"
                
                return False, "No bearish breakout"
            
            return False, "No clear direction"
            
        except Exception as e:
            logger.debug(f"Breakout detection error: {e}")
            return False, f"Error: {str(e)}"


class MultiTimeframeEngine:
    """
    Main multi-timeframe strategy engine
    Implements the complete Trend + Pullback + Confirmation system
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        self.indicators = IndicatorEngine()
        
        # Initialize sub-engines
        self.structure_detector = StructureDetector()
        self.ema_checker = EMAAlignmentChecker()
        self.pullback_detector = PullbackDetector()
        self.volume_analyzer = VolumeAnalyzer()
        self.breakout_detector = BreakoutDetector()
        
        # Risk:Reward ratio
        self.risk_reward_ratio = 2.0
    
    def analyze(
        self,
        coin: CoinData
    ) -> ValidationResult:
        """
        Run complete multi-timeframe analysis on a coin.
        Returns ValidationResult with signal or rejection reason.
        """
        # Get data from all timeframes
        daily_candles = coin.candles.get("daily", [])
        hourly_candles = coin.candles.get("1h", [])
        minute15_candles = coin.candles.get("15m", [])
        
        # Step 1: Trend Identification (1D)
        daily_trend, daily_ema_200 = self._analyze_daily_trend(daily_candles, coin)
        
        if daily_trend == TrendDirection.NEUTRAL:
            return ValidationResult(
                is_valid=False,
                rejection_reason="No clear trend on daily timeframe",
                validation_details={"daily_trend": "NEUTRAL"}
            )
        
        # Step 2: Structure Confirmation (1H)
        hourly_structure, swing_high, swing_low = self._analyze_hourly_structure(hourly_candles)
        
        if hourly_structure == MarketStructure.UNCERTAIN:
            return ValidationResult(
                is_valid=False,
                rejection_reason="No clear market structure on 1H",
                validation_details={"hourly_structure": "UNCERTAIN"}
            )
        
        # Structure must align with daily trend
        if daily_trend == TrendDirection.BULLISH and hourly_structure != MarketStructure.HIGHER_HIGHS:
            return ValidationResult(
                is_valid=False,
                rejection_reason="1H structure does not confirm daily bullish trend",
                validation_details={"daily_trend": daily_trend.value, "hourly_structure": hourly_structure.value}
            )
        
        if daily_trend == TrendDirection.BEARISH and hourly_structure != MarketStructure.LOWER_LOWS:
            return ValidationResult(
                is_valid=False,
                rejection_reason="1H structure does not confirm daily bearish trend",
                validation_details={"daily_trend": daily_trend.value, "hourly_structure": hourly_structure.value}
            )
        
        # Step 3: Pullback Detection (1H)
        hourly_emas = self._calculate_hourly_emas(hourly_candles)
        pullback_level, is_at_pullback = self._detect_pullback(
            coin.current_price,
            hourly_emas
        )
        
        if not is_at_pullback:
            return ValidationResult(
                is_valid=False,
                rejection_reason="Price not at pullback to EMA 50/100",
                validation_details={"pullback_level": pullback_level, "is_at_pullback": is_at_pullback}
            )
        
        # Step 4: EMA Alignment Filter (15m)
        entry_ema_alignment, ema_description = self._check_ema_alignment(minute15_candles)
        
        if entry_ema_alignment == EMAAlignment.FLAT:
            return ValidationResult(
                is_valid=False,
                rejection_reason="EMAs are flat - sideways market, no trade",
                validation_details={"ema_alignment": "FLAT"}
            )
        
        if entry_ema_alignment == EMAAlignment.MIXED:
            return ValidationResult(
                is_valid=False,
                rejection_reason="EMAs are tangled/mixed",
                validation_details={"ema_alignment": "MIXED"}
            )
        
        # EMA alignment must match trend direction
        if daily_trend == TrendDirection.BULLISH and entry_ema_alignment != EMAAlignment.BULLISH_ALIGNED:
            return ValidationResult(
                is_valid=False,
                rejection_reason="15m EMA alignment does not confirm bullish trend",
                validation_details={"ema_alignment": entry_ema_alignment.value}
            )
        
        if daily_trend == TrendDirection.BEARISH and entry_ema_alignment != EMAAlignment.BEARISH_ALIGNED:
            return ValidationResult(
                is_valid=False,
                rejection_reason="15m EMA alignment does not confirm bearish trend",
                validation_details={"ema_alignment": entry_ema_alignment.value}
            )
        
        # Step 5: Volume Confirmation
        volume_spike, volume_ratio = self._analyze_volume(minute15_candles)
        
        if not volume_spike:
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"No volume spike (ratio: {volume_ratio:.2f}x, need 1.5x)",
                validation_details={"volume_ratio": volume_ratio, "volume_spike": volume_spike}
            )
        
        # Step 6: Breakout Confirmation (15m)
        breakout_valid, breakout_reason = self._check_breakout(
            minute15_candles,
            daily_trend,
            swing_high,
            swing_low
        )
        
        if not breakout_valid:
            return ValidationResult(
                is_valid=False,
                rejection_reason=breakout_reason,
                validation_details={"breakout_reason": breakout_reason}
            )
        
        # Step 7: Generate Signal
        signal = self._generate_signal(
            coin=coin,
            daily_trend=daily_trend,
            daily_ema_200=daily_ema_200,
            hourly_structure=hourly_structure,
            swing_high=swing_high,
            swing_low=swing_low,
            pullback_level=pullback_level,
            volume_ratio=volume_ratio,
            ema_description=ema_description,
            breakout_reason=breakout_reason,
            hourly_candles=hourly_candles
        )
        
        return ValidationResult(
            is_valid=True,
            signal=signal,
            validation_details={
                "daily_trend": daily_trend.value,
                "hourly_structure": hourly_structure.value,
                "pullback_level": pullback_level,
                "volume_ratio": volume_ratio,
                "ema_alignment": entry_ema_alignment.value,
                "breakout": breakout_reason
            }
        )
    
    def _analyze_daily_trend(
        self,
        candles: List[OHLCV],
        coin: CoinData
    ) -> Tuple[TrendDirection, Optional[float]]:
        """Step 1: Analyze daily trend"""
        if len(candles) < 50:
            return TrendDirection.NEUTRAL, None
        
        # Calculate EMA 200 on daily
        df = pd.DataFrame([
            {"close": c.close}
            for c in candles
        ])
        
        ema_200 = self.indicators.calculate_ema(df["close"], 200)
        
        if ema_200 is None:
            return TrendDirection.NEUTRAL, None
        
        # Trend: price vs EMA 200
        if coin.current_price > ema_200:
            return TrendDirection.BULLISH, ema_200
        else:
            return TrendDirection.BEARISH, ema_200
    
    def _analyze_hourly_structure(
        self,
        candles: List[OHLCV]
    ) -> Tuple[MarketStructure, Optional[float], Optional[float]]:
        """Step 2: Analyze hourly market structure"""
        return self.structure_detector.detect_structure(candles)
    
    def _calculate_hourly_emas(
        self,
        candles: List[OHLCV]
    ) -> Dict[str, Optional[float]]:
        """Calculate EMAs for hourly timeframe"""
        if len(candles) < 50:
            return {"ema_50": None, "ema_100": None}
        
        df = pd.DataFrame([
            {"close": c.close}
            for c in candles
        ])
        
        return {
            "ema_50": self.indicators.calculate_ema(df["close"], 50),
            "ema_100": self.indicators.calculate_ema(df["close"], 100)
        }
    
    def _detect_pullback(
        self,
        current_price: float,
        ema_values: Dict[str, Optional[float]]
    ) -> Tuple[Optional[str], bool]:
        """Step 3: Detect pullback to EMA"""
        return self.pullback_detector.detect_pullback(
            current_price,
            ema_values.get("ema_50"),
            ema_values.get("ema_100")
        )
    
    def _check_ema_alignment(
        self,
        candles: List[OHLCV]
    ) -> Tuple[EMAAlignment, str]:
        """Step 6: Check EMA alignment on entry timeframe"""
        if len(candles) < 50:
            return EMAAlignment.MIXED, "Insufficient data"
        
        df = pd.DataFrame([
            {"close": c.close}
            for c in candles
        ])
        
        ema_20 = self.indicators.calculate_ema(df["close"], 20)
        ema_50 = self.indicators.calculate_ema(df["close"], 50)
        ema_100 = self.indicators.calculate_ema(df["close"], 100)
        ema_200 = self.indicators.calculate_ema(df["close"], 200)
        
        return self.ema_checker.check_alignment(ema_20, ema_50, ema_100, ema_200)
    
    def _analyze_volume(
        self,
        candles: List[OHLCV]
    ) -> Tuple[bool, float]:
        """Step 5: Analyze volume"""
        return self.volume_analyzer.analyze_volume(candles)
    
    def _check_breakout(
        self,
        candles: List[OHLCV],
        direction: TrendDirection,
        resistance: Optional[float],
        support: Optional[float]
    ) -> Tuple[bool, str]:
        """Step 4 & 6: Check breakout confirmation"""
        if direction == TrendDirection.BULLISH:
            return self.breakout_detector.detect_breakout(
                candles, direction, resistance_level=resistance
            )
        else:
            return self.breakout_detector.detect_breakout(
                candles, direction, support_level=support
            )
    
    def _generate_signal(
        self,
        coin: CoinData,
        daily_trend: TrendDirection,
        daily_ema_200: Optional[float],
        hourly_structure: MarketStructure,
        swing_high: Optional[float],
        swing_low: Optional[float],
        pullback_level: Optional[str],
        volume_ratio: float,
        ema_description: str,
        breakout_reason: str,
        hourly_candles: Optional[List[OHLCV]] = None
    ) -> TradingSignal:
        """Generate final trading signal"""
        
        current_price = coin.current_price
        
        if daily_trend == TrendDirection.BULLISH:
            # LONG setup
            direction = SignalDirection.LONG
            
            # Entry: slightly above current price
            entry_min = current_price * 1.001
            entry_max = current_price * 1.005
            
            # Stop loss: below recent swing low
            if swing_low:
                stop_loss = swing_low * 0.99
            else:
                logger.warning(f"{coin.symbol}: No swing low detected, using 3% stop loss fallback")
                stop_loss = current_price * 0.97
            
        else:
            # SHORT setup
            direction = SignalDirection.SHORT
            
            # Entry: slightly below current price
            entry_max = current_price * 0.999
            entry_min = current_price * 0.995
            
            # Stop loss: above recent swing high
            if swing_high:
                stop_loss = swing_high * 1.01
            else:
                logger.warning(f"{coin.symbol}: No swing high detected, using 3% stop loss fallback")
                stop_loss = current_price * 1.03
        
        # Calculate risk and target
        if direction == SignalDirection.LONG:
            risk = entry_min - stop_loss
            if risk <= 0:
                logger.warning(f"{coin.symbol}: Invalid LONG risk (risk={risk:.4f}), using 1% fallback")
                risk = current_price * 0.01
            
            t1, t2 = None, None
            if hourly_candles:
                swing_highs, swing_lows = self.structure_detector.get_all_swing_levels(hourly_candles)
                t1, t2 = self.structure_detector.calculate_targets_from_swing_levels(swing_highs, entry_max, is_long=True)
            
            if t1 and t2:
                target_1, target_2 = t1, t2
            else:
                target_1 = entry_max + (risk * self.risk_reward_ratio)
                target_2 = entry_max + (risk * self.risk_reward_ratio * 1.5)
        else:
            risk = stop_loss - entry_max
            if risk <= 0:
                logger.warning(f"{coin.symbol}: Invalid SHORT risk (risk={risk:.4f}), using 1% fallback")
                risk = current_price * 0.01
            
            t1, t2 = None, None
            if hourly_candles:
                swing_highs, swing_lows = self.structure_detector.get_all_swing_levels(hourly_candles)
                t1, t2 = self.structure_detector.calculate_targets_from_swing_levels(swing_lows, entry_min, is_long=False)
            
            if t1 and t2:
                target_1, target_2 = t1, t2
            else:
                target_1 = entry_min - (risk * self.risk_reward_ratio)
                target_2 = entry_min - (risk * self.risk_reward_ratio * 1.5)
        
        reward = abs(target_1 - entry_max)
        risk_reward = reward / risk if risk > 0 else 0
        
        # Build structured reasoning
        reasoning = self._build_reasoning(
            daily_trend=daily_trend,
            daily_ema_200=daily_ema_200,
            pullback_level=pullback_level,
            breakout=breakout_reason,
            volume_ratio=volume_ratio,
            ema_alignment=ema_description
        )
        
        # Create signal
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=direction,
            strategy_type=StrategyType.TREND_CONTINUATION,
            timeframe="15m",
            entry_zone_min=entry_min,
            entry_zone_max=entry_max,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=risk_reward,
            risk_amount=risk,
            current_price=current_price,
            trend_alignment=True,
            volume_confirmation=True,
            reasoning=reasoning
        )
        
        # Set confidence score based on validations
        signal.confidence_score = self._calculate_confidence(
            daily_trend=daily_trend,
            hourly_structure=hourly_structure,
            pullback_level=pullback_level,
            volume_ratio=volume_ratio
        )
        
        return signal
    
    def _build_reasoning(
        self,
        daily_trend: TrendDirection,
        daily_ema_200: Optional[float],
        pullback_level: Optional[str],
        breakout: str,
        volume_ratio: float,
        ema_alignment: str
    ) -> str:
        """Build structured reasoning for signal"""
        lines = [
            f"Trend: {daily_trend.value} (1D EMA 200: {daily_ema_200:.2f if daily_ema_200 else 'N/A'})",
            f"Pullback: To {pullback_level}",
            f"Breakout: {breakout}",
            f"Volume: {volume_ratio:.2f}x avg",
            f"EMA: {ema_alignment}"
        ]
        return " | ".join(lines)
    
    def _calculate_confidence(
        self,
        daily_trend: TrendDirection,
        hourly_structure: MarketStructure,
        pullback_level: Optional[str],
        volume_ratio: float
    ) -> float:
        """Calculate confidence score (0-10)"""
        score = 5.0  # Base score
        
        # Structure confirmation
        if hourly_structure == MarketStructure.HIGHER_HIGHS and daily_trend == TrendDirection.BULLISH:
            score += 2.0
        elif hourly_structure == MarketStructure.LOWER_LOWS and daily_trend == TrendDirection.BEARISH:
            score += 2.0
        
        # Pullback confirmation
        if pullback_level:
            score += 1.0
        
        # Volume confirmation
        if volume_ratio >= 2.0:
            score += 2.0
        elif volume_ratio >= 1.5:
            score += 1.0
        
        return min(score, 10.0)


class TradeValidatorEngine:
    """
    Final decision layer - combines all rules
    Outputs: VALID SIGNAL or REJECTED SIGNAL (with reason)
    """
    
    def __init__(self):
        self.mtf_engine = MultiTimeframeEngine()
    
    def validate(
        self,
        coin: CoinData
    ) -> ValidationResult:
        """
        Validate trade and return result with signal or rejection reason.
        """
        return self.mtf_engine.analyze(coin)
    
    def validate_batch(
        self,
        coins: List[CoinData]
    ) -> List[ValidationResult]:
        """
        Validate multiple coins.
        Returns list of validation results.
        """
        results = []
        for coin in coins:
            result = self.validate(coin)
            results.append(result)
        return results
    
    def get_valid_signals(
        self,
        coins: List[CoinData]
    ) -> List[TradingSignal]:
        """
        Get only valid signals from a list of coins.
        """
        valid_signals = []
        for coin in coins:
            result = self.validate(coin)
            if result.is_valid and result.signal:
                valid_signals.append(result.signal)
        return valid_signals
    
    def get_rejection_summary(
        self,
        coins: List[CoinData]
    ) -> Dict[str, int]:
        """
        Get summary of rejection reasons.
        """
        rejection_counts = {}
        for coin in coins:
            result = self.validate(coin)
            if not result.is_valid:
                reason = result.rejection_reason
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        return rejection_counts
