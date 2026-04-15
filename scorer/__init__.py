"""
AI Signal Scorer
Calculates confidence scores for trading signals.

PRD Rule Engine Implementation:
- Score: 0–100
- Weights:
  - Trend (25): EMA 50 > 200 for bullish
  - EMA Alignment (20): Price above/below EMAs
  - Volume (15): Current > 1.5x MA
  - RSI Position (10): 50-65 bullish continuation, 40-55 pullback
  - Pattern (15): Breakout/Pullback detection
  - BTC Correlation (10): Alignment with BTC trend
  - Risk/Reward (5): Minimum 1:2

Thresholds:
- Score < 60 → reject
- 60–70 → weak signal
- 70+ → send to AI for validation
"""

from typing import Dict, Optional
from loguru import logger

from models import TradingSignal, SignalDirection, TrendDirection
from config import get_config


class SignalScorer:
    """
    Calculates confidence scores using PRD composite scoring (0-100).
    
    PRD Scoring Breakdown:
    - Trend (25): EMA 50 > 200 → bullish
    - EMA Alignment (20): Price position relative to EMAs
    - Volume (15): Current > 1.5x MA
    - RSI Position (10): 50-65 bullish, 40-55 pullback zone
    - Pattern (15): Breakout/Pullback/Continuation
    - BTC Correlation (10): Direction alignment with BTC
    - Risk/Reward (5): Min 1:2 required
    """
    
    # PRD Score thresholds
    SCORE_REJECT = 60
    SCORE_WEAK = 70
    SCORE_AI_SEND = 70
    
    # PRD weights
    WEIGHT_TREND = 25
    WEIGHT_EMA_ALIGNMENT = 20
    WEIGHT_VOLUME = 15
    WEIGHT_RSI = 10
    WEIGHT_PATTERN = 15
    WEIGHT_BTC_CORRELATION = 10
    WEIGHT_RISK_REWARD = 5
    
    def __init__(self):
        self.config = get_config()
        self.min_score = self.config.scanner.min_signal_score
    
    def score_signal(self, signal: TradingSignal) -> TradingSignal:
        """Calculate PRD composite score (0-100) for a signal"""
        
        score = 0.0
        breakdown = {}
        
        # 1. Trend Score (25 max)
        trend_score = self._calculate_trend_score(signal)
        score += trend_score
        breakdown["trend"] = trend_score
        
        # 2. EMA Alignment Score (20 max)
        ema_score = self._calculate_ema_alignment_score(signal)
        score += ema_score
        breakdown["ema_alignment"] = ema_score
        
        # 3. Volume Score (15 max)
        volume_score = self._calculate_volume_score(signal)
        score += volume_score
        breakdown["volume"] = volume_score
        
        # 4. RSI Position Score (10 max)
        rsi_score = self._calculate_rsi_score(signal)
        score += rsi_score
        breakdown["rsi_position"] = rsi_score
        
        # 5. Pattern Score (15 max)
        pattern_score = self._calculate_pattern_score(signal)
        score += pattern_score
        breakdown["pattern"] = pattern_score
        
        # 6. BTC Correlation Score (10 max)
        btc_score = self._calculate_btc_correlation_score(signal)
        score += btc_score
        breakdown["btc_correlation"] = btc_score
        
        # 7. Risk/Reward Score (5 max)
        rr_score = self._calculate_risk_reward_score(signal)
        score += rr_score
        breakdown["risk_reward"] = rr_score
        
        # Store PRD score (0-100)
        score = min(score, 100.0)
        signal.confidence_score = score / 10  # Convert to 0-10 scale for compatibility
        signal.ai_confidence_score = score  # Store original 0-100 score
        signal.score_breakdown = breakdown
        
        # Add PRD threshold classification
        if score < self.SCORE_REJECT:
            breakdown["classification"] = "REJECT"
        elif score < self.SCORE_WEAK:
            breakdown["classification"] = "WEAK"
        else:
            breakdown["classification"] = "SEND_TO_AI"
        
        return signal
    
    def _calculate_trend_score(self, signal: TradingSignal) -> float:
        """
        Trend Score (25 max)
        - Bullish: EMA 50 > EMA 200 → 25
        - Bearish: EMA 50 < EMA 200 → 25
        - Neutral: 0
        """
        if signal.trend_alignment:
            return self.WEIGHT_TREND
        return 0.0
    
    def _calculate_ema_alignment_score(self, signal: TradingSignal) -> float:
        """
        EMA Alignment Score (20 max)
        - Price above EMA 20/50/100 → bullish alignment
        - Price below EMA 20/50/100 → bearish alignment
        """
        breakdown = signal.score_breakdown
        
        if signal.direction == SignalDirection.LONG:
            # For longs, check if price is in bullish alignment
            # This is typically handled by trend_alignment flag
            if signal.trend_alignment:
                return self.WEIGHT_EMA_ALIGNMENT
        elif signal.direction == SignalDirection.SHORT:
            # For shorts, check bearish alignment
            if signal.trend_alignment:
                return self.WEIGHT_EMA_ALIGNMENT
        
        return self.WEIGHT_EMA_ALIGNMENT * 0.5  # Partial credit
    
    def _calculate_volume_score(self, signal: TradingSignal) -> float:
        """
        Volume Score (15 max)
        - Volume > 1.5x MA → 15
        - Volume > 1.2x MA → 10
        - Volume normal → 5
        """
        if signal.volume_confirmation:
            return self.WEIGHT_VOLUME
        
        # Check volume_multiplier from PRD engine
        if hasattr(signal, 'volume_multiplier') and signal.volume_multiplier >= 1.5:
            return self.WEIGHT_VOLUME
        elif hasattr(signal, 'volume_multiplier') and signal.volume_multiplier >= 1.2:
            return self.WEIGHT_VOLUME * 0.67
        
        return self.WEIGHT_VOLUME * 0.33
    
    def _calculate_rsi_score(self, signal: TradingSignal) -> float:
        """
        RSI Position Score (10 max)
        - Bullish continuation: RSI 50-65 → 10
        - Pullback zone: RSI 40-55 → 10
        - Overbought/Oversold: 0-5
        """
        rsi = signal.rsi_at_entry if hasattr(signal, 'rsi_at_entry') and signal.rsi_at_entry > 0 else 50
        
        if signal.direction == SignalDirection.LONG:
            # Bullish continuation: RSI 50-65
            if 50 <= rsi <= 65:
                return self.WEIGHT_RSI
            # Pullback zone: RSI 40-55
            elif 40 <= rsi <= 55:
                return self.WEIGHT_RSI * 0.8
            # Overbought
            elif rsi > 70:
                return 0
        elif signal.direction == SignalDirection.SHORT:
            # Bearish continuation: RSI 35-50
            if 35 <= rsi <= 50:
                return self.WEIGHT_RSI
            # Pullback zone: RSI 45-60
            elif 45 <= rsi <= 60:
                return self.WEIGHT_RSI * 0.8
            # Oversold
            elif rsi < 30:
                return 0
        
        return self.WEIGHT_RSI * 0.5
    
    def _calculate_pattern_score(self, signal: TradingSignal) -> float:
        """
        Pattern Score (15 max)
        - Breakout → 15
        - Pullback → 12
        - Trend Continuation → 10
        - Other → 5
        """
        from models import StrategyType
        
        strategy = signal.strategy_type
        
        if strategy == StrategyType.BREAKOUT:
            return self.WEIGHT_PATTERN
        elif strategy == StrategyType.PULLBACK:
            return self.WEIGHT_PATTERN * 0.8
        elif strategy == StrategyType.TREND_CONTINUATION:
            return self.WEIGHT_PATTERN * 0.67
        else:
            return self.WEIGHT_PATTERN * 0.33
    
    def _calculate_btc_correlation_score(self, signal: TradingSignal) -> float:
        """
        BTC Correlation Score (10 max)
        - Long + BTC Bullish → 10
        - Short + BTC Bearish → 10
        - Neutral BTC → 5
        - Opposite direction → 0
        """
        if signal.btc_trend == TrendDirection.NEUTRAL:
            return self.WEIGHT_BTC_CORRELATION * 0.5
        
        if signal.direction == SignalDirection.LONG:
            if signal.btc_trend == TrendDirection.BULLISH:
                return self.WEIGHT_BTC_CORRELATION
            else:
                return 0
        elif signal.direction == SignalDirection.SHORT:
            if signal.btc_trend == TrendDirection.BEARISH:
                return self.WEIGHT_BTC_CORRELATION
            else:
                return 0
        
        return 0
    
    def _calculate_risk_reward_score(self, signal: TradingSignal) -> float:
        """
        Risk/Reward Score (5 max)
        - RR >= 3:0 → 5
        - RR >= 2:0 → 4
        - RR >= 1.5:0 → 3
        - RR < 1.5:0 → 0
        """
        rr = signal.risk_reward
        
        if rr >= 3.0:
            return self.WEIGHT_RISK_REWARD
        elif rr >= 2.0:
            return self.WEIGHT_RISK_REWARD * 0.8
        elif rr >= 1.5:
            return self.WEIGHT_RISK_REWARD * 0.6
        else:
            return 0
    
    def get_signal_quality(self, signal: TradingSignal) -> str:
        """
        Get signal quality classification based on PRD thresholds.
        
        Returns:
            - "REJECT": Score < 60
            - "WEAK": Score 60-70
            - "QUALIFIED": Score 70+
        """
        score = signal.normalized_confidence
        
        if score < self.SCORE_REJECT:
            return "REJECT"
        elif score < self.SCORE_WEAK:
            return "WEAK"
        else:
            return "QUALIFIED"
    
    def should_send_to_ai(self, signal: TradingSignal) -> bool:
        """Check if signal should be sent to AI for validation (PRD: 70+)"""
        score = signal.normalized_confidence
        return score >= self.SCORE_AI_SEND
    
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
            signal.btc_alignment = False
        else:
            signal.btc_alignment = False
        
        # Auto-set volume confirmation if not set
        if not signal.volume_confirmation:
            signal.volume_confirmation = True
        
        # Auto-set volatility expansion if not set
        if not signal.volatility_expansion:
            signal.volatility_expansion = True
        
        return signal
    
    def rank_signals(self, signals: list) -> list:
        """Rank signals by confidence score (highest first)"""
        return sorted(signals, key=lambda s: s.confidence_score, reverse=True)
    
    def filter_signals(self, signals: list) -> list:
        """Filter signals that meet minimum threshold"""
        qualified = [s for s in signals if self.is_qualified(s)]
        return self.rank_signals(qualified)
    
    def apply_ai_adjustment(self, signal: TradingSignal, ai_adjustment: float) -> TradingSignal:
        """
        Apply AI confidence adjustment to a signal.
        
        Args:
            signal: The trading signal to adjust
            ai_adjustment: The AI adjustment value (typically -2 to +2)
            
        Returns:
            Signal with adjusted confidence score
        """
        # Store original rule-based confidence
        signal.rule_based_confidence = signal.confidence_score
        
        # Apply AI adjustment
        signal.ai_reasoning_contribution = ai_adjustment
        
        # Calculate new confidence (clamped between 0 and 10)
        new_confidence = signal.confidence_score + ai_adjustment
        signal.confidence_score = max(0.0, min(10.0, new_confidence))
        
        logger.debug(
            f"Applied AI adjustment to {signal.symbol}: "
            f"base={signal.rule_based_confidence:.1f}, "
            f"adjustment={ai_adjustment:+.1f}, "
            f"final={signal.confidence_score:.1f}"
        )
        
        return signal
