"""
AI Signal Scorer
Calculates confidence scores for trading signals.
"""

from typing import Dict
from loguru import logger

from models import TradingSignal, SignalDirection, TrendDirection
from config import get_config


class SignalScorer:
    """
    Calculates confidence scores for trading signals.
    
    Scoring breakdown:
    - Trend alignment → +3
    - Volume expansion → +2
    - BTC alignment → +2
    - Volatility expansion → +2
    - Liquidity sweep → +1
    
    Score range: 0-10
    Minimum threshold: 7
    """
    
    def __init__(self):
        self.config = get_config()
        self.min_score = self.config.scanner.min_signal_score
    
    def score_signal(self, signal: TradingSignal) -> TradingSignal:
        """Calculate confidence score for a signal"""
        
        score = 0.0
        breakdown = {}
        
        # 1. Trend alignment (+3)
        if signal.trend_alignment:
            score += 3.0
            breakdown["trend_alignment"] = 3.0
        
        # 2. Volume confirmation (+2)
        if signal.volume_confirmation:
            score += 2.0
            breakdown["volume_confirmation"] = 2.0
        
        # 3. BTC alignment (+2)
        if signal.btc_alignment:
            score += 2.0
            breakdown["btc_alignment"] = 2.0
        
        # 4. Volatility expansion (+2)
        if signal.volatility_expansion:
            score += 2.0
            breakdown["volatility_expansion"] = 2.0
        
        # 5. Liquidity sweep (+1)
        if signal.liquidity_sweep:
            score += 1.0
            breakdown["liquidity_sweep"] = 1.0
        
        # Additional scoring based on RSI
        # Lower RSI for longs / Higher RSI for shorts = better setup
        # (This would require RSI data to be passed in, handled in enrich)
        
        # 6. Direction vs BTC trend alignment bonus
        if signal.btc_trend != TrendDirection.NEUTRAL:
            if signal.direction == SignalDirection.LONG and signal.btc_trend == TrendDirection.BULLISH:
                score += 1.0
                breakdown["btc_trend_bonus"] = 1.0
            elif signal.direction == SignalDirection.SHORT and signal.btc_trend == TrendDirection.BEARISH:
                score += 1.0
                breakdown["btc_trend_bonus"] = 1.0
        
        # Cap at 10
        score = min(score, 10.0)
        
        signal.confidence_score = score
        signal.score_breakdown = breakdown
        
        return signal
    
    def is_qualified(self, signal: TradingSignal) -> bool:
        """Check if signal meets minimum score threshold"""
        return signal.confidence_score >= self.min_score
    
    def enrich_with_btc_alignment(self, signal: TradingSignal, btc_trend: TrendDirection) -> TradingSignal:
        """Check and set BTC alignment"""
        signal.btc_trend = btc_trend
        
        # Check alignment
        if signal.direction == SignalDirection.LONG and btc_trend == TrendDirection.BULLISH:
            signal.btc_alignment = True
        elif signal.direction == SignalDirection.SHORT and btc_trend == TrendDirection.BEARISH:
            signal.btc_alignment = True
        elif btc_trend == TrendDirection.NEUTRAL:
            # Neutral BTC - allow both directions but no bonus
            signal.btc_alignment = False
        else:
            signal.btc_alignment = False
        
        return signal
    
    def rank_signals(self, signals: list) -> list:
        """Rank signals by confidence score (highest first)"""
        return sorted(signals, key=lambda s: s.confidence_score, reverse=True)
    
    def filter_signals(self, signals: list) -> list:
        """Filter signals that meet minimum threshold"""
        qualified = [s for s in signals if self.is_qualified(s)]
        return self.rank_signals(qualified)
