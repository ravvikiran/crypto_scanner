"""
Signal Scoring Engine - Enhanced Version
Ranks signals by quality (0-100 score) across multiple factors.
"""

from typing import Dict, Optional
from loguru import logger


class SignalScorerEnhanced:
    """
    Enhanced signal scorer with multi-factor quality assessment.

    Scoring Factors (total 100 points):
    - EMA alignment quality: 30 points
    - Volume confirmation: 20 points
    - RSI positioning: 15 points
    - Volatility appropriateness (ATR): 15 points
    - Market context: 20 points
    """

    def __init__(self):
        self.min_score_threshold = 60.0

    def score_signal(self, signal: Dict, indicators: Dict) -> float:
        """
        Calculate comprehensive signal score (0-100).

        Args:
            signal: Signal dictionary with basic info
            indicators: Dictionary of technical indicators

        Returns:
            Quality score (0-100)
        """
        score = 0.0

        # 1. EMA alignment (0-30 pts)
        ema_score = self._ema_alignment_score(indicators)
        score += ema_score

        # 2. Volume confirmation (0-20 pts)
        vol_score = self._volume_score(indicators)
        score += vol_score

        # 3. RSI positioning (0-15 pts)
        rsi_score = self._rsi_score(indicators)
        score += rsi_score

        # 4. ATR/volatility appropriateness (0-15 pts)
        atr_score = self._volatility_score(indicators)
        score += atr_score

        # 5. Market context (0-20 pts)
        ctx_score = self._context_score(indicators, signal)
        score += ctx_score

        return round(score, 2)

    def _ema_alignment_score(self, ind: Dict) -> float:
        """
        Score EMA alignment quality (0-30).

        Perfect alignment: price > ema20 > ema50 > ema100 > ema200 (bullish)
        or price < ema20 < ema50 < ema100 < ema200 (bearish) → 30 points
        Partial alignment (3-tier) → 20 points
        Poor/crossing alignment → 10 points
        """
        price = ind.get('close', 0)
        ema20 = ind.get('ema20', 0)
        ema50 = ind.get('ema50', 0)
        ema100 = ind.get('ema100', 0)
        ema200 = ind.get('ema200', 0)

        if not all([price, ema20, ema50, ema100, ema200]):
            return 10.0  # Default low score if data missing

        # Check bullish alignment
        if price > ema20 > ema50 > ema100 > ema200:
            return 30.0
        # Check bearish alignment
        elif price < ema20 < ema50 < ema100 < ema200:
            return 30.0
        # Partial: price > ema20 > ema50 OR price < ema20 < ema50
        elif (price > ema20 > ema50) or (price < ema20 < ema50):
            return 20.0
        else:
            return 10.0  # Mixed/conflicting alignment

    def _volume_score(self, ind: Dict) -> float:
        """
        Score volume confirmation (0-20).

        volume / volume_ma ratio:
        >= 2.0 → 20 pts (strong confirmation)
        >= 1.5 → 16 pts
        >= 1.2 → 12 pts
        else → 6 pts
        """
        volume = ind.get('volume', 0)
        volume_ma = ind.get('volume_ma', 1)

        if volume_ma <= 0:
            return 6.0

        ratio = volume / volume_ma

        if ratio >= 2.0:
            return 20.0
        elif ratio >= 1.5:
            return 16.0
        elif ratio >= 1.2:
            return 12.0
        else:
            return 6.0

    def _rsi_score(self, ind: Dict) -> float:
        """
        Score RSI positioning (0-15).

        Ideal: 40-60 (nor overbought/oversold) → 15 pts
        Good: 30-70 → 12 pts
        Moderate: 20-80 → 8 pts
        Extreme: <20 or >80 → 3 pts
        """
        rsi = ind.get('rsi', 50)

        if 40 <= rsi <= 60:
            return 15.0
        elif 30 <= rsi <= 70:
            return 12.0
        elif 20 <= rsi <= 80:
            return 8.0
        else:
            return 3.0

    def _volatility_score(self, ind: Dict) -> float:
        """
        Score ATR/volatility appropriateness (0-15).

        Ideal ATR %: 1.0 - 3.0% daily → 15 pts
        Acceptable: 0.5 - 5.0% → 10 pts
        Too low/high: <0.5% or >5.0% → 5 pts
        """
        atr = ind.get('atr', 0)
        close = ind.get('close', 1)

        if close <= 0:
            return 5.0

        atr_pct = (atr / close) * 100

        if 1.0 <= atr_pct <= 3.0:
            return 15.0
        elif 0.5 <= atr_pct <= 5.0:
            return 10.0
        else:
            return 5.0

    def _context_score(self, ind: Dict, signal: Dict) -> float:
        """
        Score market context alignment (0-20).

        Factors:
        - BTC trend alignment
        - Market regime suitability
        - Sector strength
        """
        score = 10.0  # Base neutral

        btc_trend = ind.get('btc_trend', 'NEUTRAL')
        signal_direction = signal.get('direction', 'NEUTRAL')

        # BTC alignment: +5 if aligned, -5 if contrary
        if signal_direction == 'LONG' and btc_trend in ['BULLISH', 'VERY_BULLISH']:
            score += 5.0
        elif signal_direction == 'SHORT' and btc_trend in ['BEARISH', 'VERY_BEARISH']:
            score += 5.0
        elif btc_trend == 'NEUTRAL':
            score += 0.0  # Neutral, no adjustment
        else:
            score -= 3.0  # Contrary alignment

        # Market regime bonus
        market_regime = ind.get('market_regime', 'UNKNOWN')
        if market_regime in ['BULLISH', 'TRENDING_UP'] and signal_direction == 'LONG':
            score += 3.0
        elif market_regime in ['BEARISH', 'TRENDING_DOWN'] and signal_direction == 'SHORT':
            score += 3.0

        # Ensure within 0-20 range
        return max(0.0, min(20.0, score))

    def rank_signals(self, signals: list) -> list:
        """Rank signals by score descending."""
        return sorted(signals, key=lambda x: x.get('score', 0), reverse=True)

    def filter_qualified(self, signals: list, min_score: float = None) -> list:
        """Filter signals that meet minimum score threshold."""
        threshold = min_score or self.min_score_threshold
        qualified = [s for s in signals if s.get('score', 0) >= threshold]
        return self.rank_signals(qualified)
