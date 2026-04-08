"""
Confluence Scoring Engine
Multi-signal confirmation to increase accuracy.
"""

from typing import List, Dict, Optional, Tuple
from loguru import logger

from models import TradingSignal, CoinData, TrendDirection, SignalDirection
from config import get_config


class ConfluenceEngine:
    """
    Calculate confluence score from multiple signals.
    
    Inputs:
    - EMA alignment
    - Volume spike
    - RSI strength
    - Liquidity sweep
    - Multi-timeframe agreement
    
    Output:
    - confluence_score: 0-10
    
    Rules:
    - 8+ → High confidence
    - 6-8 → Medium
    - <6 → Reject
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        
    def calculate_confluence(
        self,
        signal: TradingSignal,
        coin: CoinData,
        btc_trend: TrendDirection,
        market_regime: str = "NEUTRAL"
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate confluence score for a signal.
        
        Args:
            signal: Trading signal
            coin: Coin data with indicators
            btc_trend: Bitcoin trend
            market_regime: Current market regime
            
        Returns:
            (confluence_score, breakdown_dict)
        """
        breakdown = {}
        
        ema_score = self._score_ema_alignment(coin, signal.direction)
        breakdown["ema_alignment"] = ema_score
        
        volume_score = self._score_volume(coin, signal.timeframe)
        breakdown["volume"] = volume_score
        
        rsi_score = self._score_rsi(coin, signal.direction, market_regime)
        breakdown["rsi"] = rsi_score
        
        trend_score = self._score_trend_alignment(signal, btc_trend)
        breakdown["btc_alignment"] = trend_score
        
        signal_quality_score = self._score_signal_quality(signal)
        breakdown["signal_quality"] = signal_quality_score
        
        timeframe_score = self._score_timeframe_agreement(coin, signal.timeframe)
        breakdown["timeframe_agreement"] = timeframe_score
        
        total_score = (
            ema_score * 0.20 +
            volume_score * 0.15 +
            rsi_score * 0.15 +
            trend_score * 0.25 +
            signal_quality_score * 0.15 +
            timeframe_score * 0.10
        )
        
        final_score = min(10.0, total_score)
        
        logger.debug(
            f"{signal.symbol} confluence: {final_score:.1f} | "
            f"EMA:{ema_score:.1f} Vol:{volume_score:.1f} "
            f"RSI:{rsi_score:.1f} BTC:{trend_score:.1f} "
            f"Quality:{signal_quality_score:.1f} TF:{timeframe_score:.1f}"
        )
        
        return final_score, breakdown
    
    def _score_ema_alignment(self, coin: CoinData, direction: SignalDirection) -> float:
        """Score EMA alignment (0-10)"""
        if not all([coin.ema_20, coin.ema_50, coin.ema_100, coin.ema_200]):
            return 5.0
        
        ema_values = [coin.ema_20, coin.ema_50, coin.ema_100, coin.ema_200]
        
        if direction == SignalDirection.LONG:
            if ema_values == sorted(ema_values):
                return 10.0
            elif ema_values[0] > ema_values[-1]:
                return 7.0
            else:
                return 3.0
        else:
            if ema_values == sorted(ema_values, reverse=True):
                return 10.0
            elif ema_values[0] < ema_values[-1]:
                return 7.0
            else:
                return 3.0
    
    def _score_volume(self, coin: CoinData, timeframe: str) -> float:
        """Score volume conditions (0-10)"""
        candles = coin.candles.get(timeframe, [])
        
        if len(candles) < 20:
            return 5.0
        
        volumes = [c.volume for c in candles[-20:-1]]
        avg_volume = sum(volumes) / len(volumes)
        
        current_volume = candles[-1].volume
        
        ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        if ratio >= 2.0:
            return 10.0
        elif ratio >= 1.5:
            return 8.0
        elif ratio >= 1.2:
            return 6.0
        elif ratio >= 0.8:
            return 4.0
        else:
            return 2.0
    
    def _score_rsi(
        self,
        coin: CoinData,
        direction: SignalDirection,
        market_regime: str
    ) -> float:
        """Score RSI conditions (0-10)"""
        if coin.rsi is None:
            return 5.0
        
        rsi = coin.rsi
        
        regime_bounds = {
            "TRENDING": (55, 75) if direction == SignalDirection.LONG else (25, 45),
            "RANGING": (40, 60) if direction == SignalDirection.LONG else (40, 60),
            "HIGH_VOL": (45, 70) if direction == SignalDirection.LONG else (30, 55),
            "LOW_VOL": (30, 70),
            "NEUTRAL": (40, 60) if direction == SignalDirection.LONG else (40, 60)
        }
        
        low, high = regime_bounds.get(market_regime, (40, 60))
        
        if low <= rsi <= high:
            return 10.0
        elif rsi < low - 10 or rsi > high + 10:
            return 2.0
        else:
            return 6.0
    
    def _score_trend_alignment(
        self,
        signal: TradingSignal,
        btc_trend: TrendDirection
    ) -> float:
        """Score BTC trend alignment (0-10)"""
        if btc_trend == TrendDirection.NEUTRAL:
            return 6.0
        
        if signal.direction == SignalDirection.LONG:
            if btc_trend == TrendDirection.BULLISH:
                return 10.0
            else:
                return 3.0
        else:
            if btc_trend == TrendDirection.BEARISH:
                return 10.0
            else:
                return 3.0
    
    def _score_signal_quality(self, signal: TradingSignal) -> float:
        """Score overall signal quality (0-10)"""
        score = 0.0
        
        if signal.risk_reward >= 4.0:
            score += 4.0
        elif signal.risk_reward >= 3.0:
            score += 3.0
        else:
            score += 1.0
        
        if signal.trend_alignment:
            score += 3.0
        else:
            score += 1.0
        
        if signal.volume_confirmation:
            score += 2.0
        else:
            score += 1.0
        
        if signal.liquidity_sweep:
            score += 1.0
        
        return min(10.0, score)
    
    def _score_timeframe_agreement(
        self,
        coin: CoinData,
        primary_tf: str
    ) -> float:
        """Score multi-timeframe agreement (0-10)"""
        tf_weights = {
            "15m": 0.5,
            "1h": 0.7,
            "4h": 0.9,
            "daily": 1.0
        }
        
        base_score = tf_weights.get(primary_tf, 0.7) * 10
        
        agreement_count = 0
        total_tfs = 0
        
        for tf, candles in coin.candles.items():
            if tf == primary_tf:
                continue
            if len(candles) >= 20:
                total_tfs += 1
                tf_trend = self._get_timeframe_trend(candles)
                primary_trend = coin.trend
                if tf_trend == primary_trend:
                    agreement_count += 1
        
        if total_tfs > 0:
            agreement_ratio = agreement_count / total_tfs
            agreement_bonus = agreement_ratio * 2
            base_score = min(10.0, base_score + agreement_bonus)
        
        return base_score
    
    def _get_timeframe_trend(self, candles) -> TrendDirection:
        """Determine trend from candles"""
        if len(candles) < 20:
            return TrendDirection.NEUTRAL
        
        recent = candles[-20:]
        
        first_close = recent[0].close
        last_close = recent[-1].close
        
        change = (last_close - first_close) / first_close
        
        if change > 0.02:
            return TrendDirection.BULLISH
        elif change < -0.02:
            return TrendDirection.BEARISH
        else:
            return TrendDirection.NEUTRAL
    
    def apply_confluence_filter(
        self,
        signals: List[TradingSignal],
        min_confluence: float = 6.0
    ) -> List[TradingSignal]:
        """
        Filter signals by confluence score.
        
        Args:
            signals: List of trading signals
            min_confluence: Minimum confluence score
            
        Returns:
            Filtered signals
        """
        filtered = [s for s in signals if s.confidence_score >= min_confluence]
        
        logger.info(f"Confluence filter: {len(filtered)}/{len(signals)} signals pass (min: {min_confluence})")
        
        return filtered
    
    def rank_by_confluence(
        self,
        signals: List[TradingSignal]
    ) -> List[TradingSignal]:
        """Rank signals by confluence score"""
        return sorted(signals, key=lambda s: s.confidence_score, reverse=True)