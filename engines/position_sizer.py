"""
Position Sizing Engine
Adjust trade size based on confidence.
"""

from dataclasses import dataclass
from typing import Optional
from loguru import logger

from models import TradingSignal, SignalDirection
from config import get_config


@dataclass
class PositionSize:
    """Position size recommendation"""
    size_percent: float
    risk_percent: float
    adjusted_entry: float
    adjusted_sl: float
    adjusted_targets: tuple


class PositionSizerEngine:
    """
    Calculate position size based on confidence.
    
    Logic:
    - score >= 9 → 100% position
    - score >= 8 → 70%
    - score >= 7 → 50%
    - else → skip
    """
    
    def __init__(self):
        self.config = get_config()
        self.strategy = self.config.strategy
        
        self.base_risk_percent = 2.0
        
        self.position_size_map = {
            (9, 10): 1.0,
            (8, 9): 0.7,
            (7, 8): 0.5,
            (6, 7): 0.3,
            (0, 6): 0.0
        }
    
    def calculate_position(
        self,
        signal: TradingSignal,
        confidence: float,
        account_balance: Optional[float] = None
    ) -> PositionSize:
        """
        Calculate position size for a signal.
        
        Args:
            signal: Trading signal
            confidence: Confidence score (0-10)
            account_balance: Optional account balance for risk calculation
            
        Returns:
            PositionSize with all calculations
        """
        size_multiplier = self._get_size_multiplier(confidence)
        
        if size_multiplier == 0:
            return PositionSize(
                size_percent=0,
                risk_percent=0,
                adjusted_entry=0,
                adjusted_sl=0,
                adjusted_targets=(0, 0)
            )
        
        risk_amount = self.base_risk_percent * size_multiplier
        
        if account_balance and account_balance > 0:
            position_value = (account_balance * risk_amount / 100) / (risk_amount / 100)
            risk_per_unit = abs(signal.entry_zone_min - signal.stop_loss)
            if risk_per_unit > 0:
                position_value = (account_balance * risk_amount / 100) / (risk_per_unit / signal.entry_zone_min)
        else:
            position_value = 1.0
        
        entry = signal.entry_zone_min
        
        if signal.direction == SignalDirection.LONG:
            adjusted_sl = signal.stop_loss
            target_1 = signal.target_1
            target_2 = signal.target_2
        else:
            adjusted_sl = signal.stop_loss
            target_1 = signal.target_1
            target_2 = signal.target_2
        
        position = PositionSize(
            size_percent=size_multiplier * 100,
            risk_percent=risk_amount,
            adjusted_entry=entry,
            adjusted_sl=adjusted_sl,
            adjusted_targets=(target_1, target_2)
        )
        
        logger.debug(
            f"{signal.symbol} position: {position.size_percent:.0f}% "
            f"(conf: {confidence:.1f}, risk: {position.risk_percent:.1f}%)"
        )
        
        return position
    
    def _get_size_multiplier(self, confidence: float) -> float:
        """Get position size multiplier based on confidence"""
        for (low, high), multiplier in self.position_size_map.items():
            if low <= confidence < high:
                return multiplier
        return 0.0
    
    def adjust_for_market_regime(
        self,
        position: PositionSize,
        regime: str,
        base_confidence: float
    ) -> PositionSize:
        """
        Adjust position size based on market regime.
        
        Args:
            position: Current position size
            regime: Market regime (TRENDING, RANGING, HIGH_VOL, LOW_VOL)
            base_confidence: Original confidence score
            
        Returns:
            Adjusted position size
        """
        regime_multipliers = {
            "TRENDING": 1.0,
            "RANGING": 0.7,
            "HIGH_VOL": 0.8,
            "LOW_VOL": 0.3
        }
        
        multiplier = regime_multipliers.get(regime, 1.0)
        
        adjusted_size = position.size_percent * multiplier
        adjusted_risk = position.risk_percent * multiplier
        
        return PositionSize(
            size_percent=adjusted_size,
            risk_percent=adjusted_risk,
            adjusted_entry=position.adjusted_entry,
            adjusted_sl=position.adjusted_sl,
            adjusted_targets=position.adjusted_targets
        )
    
    def apply_confluence_boost(
        self,
        base_confidence: float,
        confluence_score: float
    ) -> float:
        """
        Apply confluence score to boost or reduce confidence.
        
        Args:
            base_confidence: Original confidence from signal
            confluence_score: Multi-signal confluence score
            
        Returns:
            Adjusted confidence
        """
        if confluence_score >= 8.0:
            boost = min(1.0, (confluence_score - 7) * 0.5)
            return min(10.0, base_confidence + boost)
        elif confluence_score < 5.0:
            penalty = (5.0 - confluence_score) * 0.3
            return max(0.0, base_confidence - penalty)
        
        return base_confidence
    
    def calculate_kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion for position sizing.
        
        Args:
            win_rate: Win rate (0-1)
            avg_win: Average win amount
            avg_loss: Average loss amount
            
        Returns:
            Kelly percentage
        """
        if avg_loss == 0:
            return 0
        
        win_loss_ratio = avg_win / avg_loss
        
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        kelly = max(0, min(kelly, 0.25))
        
        return kelly * 100
    
    def adjust_for_drawdown(
        self,
        base_size: float,
        current_drawdown: float,
        max_drawdown: float = 20.0
    ) -> float:
        """
        Reduce position size during drawdown.
        
        Args:
            base_size: Base position size
            current_drawdown: Current drawdown percentage
            max_drawdown: Maximum allowed drawdown
            
        Returns:
            Adjusted position size
        """
        if current_drawdown >= max_drawdown:
            return base_size * 0.25
        
        reduction_factor = 1 - (current_drawdown / max_drawdown)
        
        return base_size * max(0.25, reduction_factor)
    
    def get_position_recommendation(
        self,
        signal: TradingSignal,
        confidence: float,
        market_regime: str = "NEUTRAL",
        confluence_score: Optional[float] = None,
        journal_stats: Optional[dict] = None
    ) -> dict:
        """
        Get complete position recommendation.
        
        Args:
            signal: Trading signal
            confidence: Confidence score
            market_regime: Current market regime
            confluence_score: Optional confluence score
            journal_stats: Optional journal performance stats
            
        Returns:
            Dictionary with position recommendation
        """
        final_confidence = confidence
        
        if confluence_score is not None:
            final_confidence = self.apply_confluence_boost(confidence, confluence_score)
        
        if journal_stats:
            sample_size = journal_stats.get("sample_size", 0)
            win_rate = journal_stats.get("win_rate", 0.5)
            
            if sample_size < 20:
                final_confidence *= 0.8
            elif win_rate < 0.4:
                final_confidence = min(final_confidence, 5.0)
            elif win_rate > 0.6:
                final_confidence = min(10.0, final_confidence + 1.0)
        
        position = self.calculate_position(signal, final_confidence)
        
        position = self.adjust_for_market_regime(position, market_regime, final_confidence)
        
        return {
            "position_size_percent": position.size_percent,
            "risk_percent": position.risk_percent,
            "adjusted_entry": position.adjusted_entry,
            "adjusted_stop_loss": position.adjusted_sl,
            "adjusted_targets": position.adjusted_targets,
            "final_confidence": final_confidence,
            "recommendation": "EXECUTE" if position.size_percent > 0 else "SKIP",
            "reason": self._get_recommendation_reason(final_confidence, market_regime, position.size_percent)
        }
    
    def _get_recommendation_reason(
        self,
        confidence: float,
        regime: str,
        size_percent: float
    ) -> str:
        """Get recommendation reason string"""
        if size_percent == 0:
            return f"Low confidence ({confidence:.1f}) - skip trade"
        
        reasons = []
        
        if confidence >= 9:
            reasons.append("High confidence")
        elif confidence >= 7:
            reasons.append("Medium confidence")
        
        if regime == "LOW_VOL":
            reasons.append("Low volatility regime")
        elif regime == "TRENDING":
            reasons.append("Trending market favors continuation")
        
        return ", ".join(reasons) if reasons else "Standard position"