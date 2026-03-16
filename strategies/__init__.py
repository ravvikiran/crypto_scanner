"""
Strategy Engines
Implements all four trading strategy engines.
"""

from typing import List, Optional, Tuple
from loguru import logger

from models import (
    CoinData, OHLCV, TradingSignal, SignalDirection,
    StrategyType, TrendDirection
)
from config import get_config
from indicators import IndicatorEngine


class TrendContinuationEngine:
    """
    ENGINE 1 — Trend Continuation (Momentum)
    
    Entry conditions:
    - Price > EMA20 > EMA50 > EMA100 > EMA200 (bullish alignment)
    - Volume > Volume MA(30)
    - RSI between 55 and 70
    - Price retraces to EMA20 or EMA50 with volume contraction
    
    Entry: Break above previous candle high
    Stop: Below EMA50
    Target: Previous resistance or 2R
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        self.indicators = IndicatorEngine()
    
    def scan(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str = "1h") -> Optional[TradingSignal]:
        """Scan for trend continuation setups"""
        
        # Check trend alignment
        if coin.trend != TrendDirection.BULLISH:
            return None
        
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 50:
            return None
        
        # Check RSI momentum (between 55-70)
        if coin.rsi is None:
            return None
        
        if not (self.strategy.rsi_momentum_low <= coin.rsi <= self.strategy.rsi_momentum_high):
            return None
        
        # Check volume confirmation
        volume_confirmed = self.indicators.is_volume_expanding(coin, timeframe)
        if not volume_confirmed:
            return None
        
        # Check for pullback to EMA
        current_price = coin.current_price
        ema_20 = coin.ema_20
        ema_50 = coin.ema_50
        
        if ema_20 is None or ema_50 is None:
            return None
        
        # Check if price is at or near EMA pullback zone
        pullback_zone_min = min(ema_20, ema_50) * 0.98  # 2% buffer
        pullback_zone_max = max(ema_20, ema_50) * 1.02
        
        in_pullback = pullback_zone_min <= current_price <= pullback_zone_max
        
        if not in_pullback:
            return None
        
        # Check for breakout above previous candle
        prev_candle = candles[-2]
        
        # Entry: Break above previous high + small buffer
        entry_min = prev_candle.high * 1.002
        entry_max = prev_candle.high * 1.01
        
        # Stop: Below EMA50
        stop_loss = ema_50 * 0.98
        
        # Risk
        risk = entry_min - stop_loss
        
        # Target: 2R
        target_1 = entry_min + (risk * 2)
        target_2 = entry_min + (risk * 3)
        
        # Create signal
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.LONG,
            strategy_type=StrategyType.TREND_CONTINUATION,
            timeframe=timeframe,
            entry_zone_min=entry_min,
            entry_zone_max=entry_max,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=2.0,
            risk_amount=risk,
            current_price=current_price,
            btc_trend=btc_trend,
            trend_alignment=True,
            volume_confirmation=volume_confirmed,
            reasoning=f"Trend pullback to EMA{self.strategy.ema_short}/EMA{self.strategy.ema_medium}. RSI momentum at {coin.rsi:.1f}."
        )
        
        return signal


class BearishTrendEngine:
    """
    ENGINE 2 — Bearish Trend Short
    
    Entry conditions:
    - Price < EMA20 < EMA50 < EMA100 < EMA200 (bearish alignment)
    - Price retraces to EMA20 or EMA50
    
    Entry: Break below previous candle low
    Stop: Above EMA50
    Target: Previous support or 2R-3R
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        self.indicators = IndicatorEngine()
    
    def scan(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str = "1h") -> Optional[TradingSignal]:
        """Scan for bearish trend short setups"""
        
        # Check bearish trend
        if coin.trend != TrendDirection.BEARISH:
            return None
        
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 50:
            return None
        
        # Check for bounce/retracement to EMA
        current_price = coin.current_price
        ema_20 = coin.ema_20
        ema_50 = coin.ema_50
        
        if ema_20 is None or ema_50 is None:
            return None
        
        # Check if price is at EMA bounce zone
        bounce_zone_min = min(ema_20, ema_50) * 0.98
        bounce_zone_max = max(ema_20, ema_50) * 1.02
        
        at_bounce = bounce_zone_min <= current_price <= bounce_zone_max
        
        if not at_bounce:
            return None
        
        # Check for breakdown below previous candle
        prev_candle = candles[-2]
        
        # Entry: Break below previous low - small buffer
        entry_min = prev_candle.low * 0.99
        entry_max = prev_candle.low * 0.998
        
        # Stop: Above EMA50
        stop_loss = ema_50 * 1.02
        
        # Risk
        risk = stop_loss - entry_max
        
        # Target: 3R for better risk/reward
        target_1 = entry_max - (risk * 3)
        target_2 = entry_max - (risk * 4)
        
        # Create signal
        signal = TradingSignal(
            symbol=coin.symbol,
            name=coin.name,
            direction=SignalDirection.SHORT,
            strategy_type=StrategyType.BEARISH_SHORT,
            timeframe=timeframe,
            entry_zone_min=entry_min,
            entry_zone_max=entry_max,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_reward=3.0,
            risk_amount=risk,
            current_price=current_price,
            btc_trend=btc_trend,
            trend_alignment=True,
            reasoning=f"Bearish bounce to EMA{self.strategy.ema_short}/EMA{self.strategy.ema_medium} - short opportunity."
        )
        
        return signal


class LiquiditySweepEngine:
    """
    ENGINE 3 — Liquidity Sweep Reversal
    
    Detects fake breakouts (liquidity grabs).
    
    Conditions:
    - Price breaks previous high/low
    - Volume spike
    - Candle closes below/above breakout level
    
    This is common in crypto - liquidity sweeps often precede reversals.
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        self.indicators = IndicatorEngine()
    
    def scan(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str = "1h") -> Optional[TradingSignal]:
        """Scan for liquidity sweep setups"""
        
        candles = coin.candles.get(timeframe, [])
        if len(candles) < 10:
            return None
        
        # Detect liquidity sweeps
        bearish_sweep, bullish_sweep = self.indicators.detect_liquidity_sweep(coin, timeframe)
        
        if not (bearish_sweep or bullish_sweep):
            return None
        
        # Check for volume spike
        volume_ratio = self.indicators.calculate_volume_ratio(coin, timeframe)
        volume_spike = volume_ratio > 1.5
        
        current_price = coin.current_price
        prev_candle = candles[-2]
        
        if bearish_sweep:
            # Short opportunity after fake breakout
            entry_max = current_price * 0.995
            entry_min = current_price * 0.98
            
            # Stop above recent high
            stop_loss = max([c.high for c in candles[-5:]]) * 1.01
            
            risk = stop_loss - entry_max
            
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=SignalDirection.SHORT,
                strategy_type=StrategyType.LIQUIDITY_SWEEP,
                timeframe=timeframe,
                entry_zone_min=entry_min,
                entry_zone_max=entry_max,
                stop_loss=stop_loss,
                target_1=entry_max - (risk * 2),
                target_2=entry_max - (risk * 3),
                risk_reward=2.0,
                risk_amount=risk,
                current_price=current_price,
                btc_trend=btc_trend,
                liquidity_sweep=True,
                volume_confirmation=volume_spike,
                reasoning=f"Liquidity sweep detected - fake breakout to upside. Volume ratio: {volume_ratio:.1f}x"
            )
            
        elif bullish_sweep:
            # Long opportunity after fake breakdown
            entry_min = current_price * 1.005
            entry_max = current_price * 1.02
            
            # Stop below recent low
            stop_loss = min([c.low for c in candles[-5:]]) * 0.99
            
            risk = entry_min - stop_loss
            
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=SignalDirection.LONG,
                strategy_type=StrategyType.LIQUIDITY_SWEEP,
                timeframe=timeframe,
                entry_zone_min=entry_min,
                entry_zone_max=entry_max,
                stop_loss=stop_loss,
                target_1=entry_min + (risk * 2),
                target_2=entry_min + (risk * 3),
                risk_reward=2.0,
                risk_amount=risk,
                current_price=current_price,
                btc_trend=btc_trend,
                liquidity_sweep=True,
                volume_confirmation=volume_spike,
                reasoning=f"Liquidity sweep detected - fake breakdown to downside. Volume ratio: {volume_ratio:.1f}x"
            )
        
        return signal


class VolatilityBreakoutEngine:
    """
    ENGINE 4 — Volatility Breakout
    
    Detects compression before explosive moves.
    
    Conditions:
    - ATR lowest in 20 periods
    - Bollinger Band squeeze
    - Range contraction
    
    Entry: Breakout above/below range
    Stop: Middle of range
    Target: Measured move
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        self.indicators = IndicatorEngine()
    
    def scan(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str = "1h") -> Optional[TradingSignal]:
        """Scan for volatility breakout setups"""
        
        candles = coin.candles.get(timeframe, [])
        if len(candles) < self.strategy.volatility_lookback + 10:
            return None
        
        # Check for ATR compression
        atr_compressed = self.indicators.is_atr_lowest(coin, timeframe, self.strategy.volatility_lookback)
        
        if not atr_compressed:
            return None
        
        # Check for Bollinger Band squeeze
        if None in [coin.bb_upper, coin.bb_middle, coin.bb_lower]:
            return None
        
        current_price = coin.current_price
        
        # Calculate bandwidth (narrow = squeeze)
        bandwidth = (coin.bb_upper - coin.bb_lower) / coin.bb_middle
        
        # Get historical bandwidth to compare
        recent_bandwidths = []
        for i in range(-20, -1):
            if i >= -len(candles):
                df = self.indicators._candles_to_dataframe(candles[:i])
                if len(df) >= self.strategy.bollinger_period:
                    bb_u, bb_m, bb_l = self.indicators.calculate_bollinger_bands(
                        df["close"], self.strategy.bollinger_period, self.strategy.bollinger_std
                    )
                    if bb_u and bb_m and bb_l:
                        bw = (bb_u - bb_l) / bb_m
                        recent_bandwidths.append(bw)
        
        if not recent_bandwidths:
            return None
        
        # Check if current bandwidth is below average (squeeze)
        avg_bandwidth = sum(recent_bandwidths) / len(recent_bandwidths)
        is_squeeze = bandwidth < avg_bandwidth * 0.8
        
        if not is_squeeze:
            return None
        
        # Check for breakout direction
        recent_high = max([c.high for c in candles[-10:-1]])
        recent_low = min([c.low for c in candles[-10:-1]])
        range_middle = (recent_high + recent_low) / 2
        
        # Determine direction based on trend and recent momentum
        if coin.trend == TrendDirection.BULLISH and current_price > range_middle:
            # Bullish breakout
            entry_min = recent_high * 1.002
            entry_max = recent_high * 1.01
            stop_loss = range_middle
            
            risk = entry_min - stop_loss
            
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=SignalDirection.LONG,
                strategy_type=StrategyType.VOLATILITY_BREAKOUT,
                timeframe=timeframe,
                entry_zone_min=entry_min,
                entry_zone_max=entry_max,
                stop_loss=stop_loss,
                target_1=entry_min + (risk * 2),
                target_2=entry_min + (risk * 3),
                risk_reward=2.0,
                risk_amount=risk,
                current_price=current_price,
                btc_trend=btc_trend,
                volatility_expansion=True,
                reasoning=f"Volatility compression detected. ATR at lowest in {self.strategy.volatility_lookback} periods. Bollinger Band squeeze."
            )
            
        elif coin.trend == TrendDirection.BEARISH and current_price < range_middle:
            # Bearish breakout
            entry_max = recent_low * 0.998
            entry_min = recent_low * 0.99
            stop_loss = range_middle
            
            risk = stop_loss - entry_max
            
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=SignalDirection.SHORT,
                strategy_type=StrategyType.VOLATILITY_BREAKOUT,
                timeframe=timeframe,
                entry_zone_min=entry_min,
                entry_zone_max=entry_max,
                stop_loss=stop_loss,
                target_1=entry_max - (risk * 2),
                target_2=entry_max - (risk * 3),
                risk_reward=2.0,
                risk_amount=risk,
                current_price=current_price,
                btc_trend=btc_trend,
                volatility_expansion=True,
                reasoning=f"Volatility compression detected. ATR at lowest in {self.strategy.volatility_lookback} periods. Bollinger Band squeeze."
            )
        
        else:
            return None
        
        return signal


class StrategyEngine:
    """Orchestrates all strategy engines"""
    
    def __init__(self):
        self.trend_engine = TrendContinuationEngine()
        self.bearish_engine = BearishTrendEngine()
        self.liquidity_engine = LiquiditySweepEngine()
        self.volatility_engine = VolatilityBreakoutEngine()
    
    def scan_all_strategies(
        self,
        coin: CoinData,
        btc_trend: TrendDirection,
        timeframe: str = "1h"
    ) -> List[TradingSignal]:
        """Run all strategy engines on a coin"""
        
        signals = []
        
        # Run each strategy engine
        engines = [
            self.trend_engine,
            self.bearish_engine,
            self.liquidity_engine,
            self.volatility_engine
        ]
        
        for engine in engines:
            try:
                signal = engine.scan(coin, btc_trend, timeframe)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Strategy engine error: {e}")
        
        return signals
