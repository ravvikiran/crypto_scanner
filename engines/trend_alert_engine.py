"""
Market Trend Alert Engine
Monitors market sentiment and alerts on significant trend changes.
Notifies when market enters BULLISH/BEARISH/VERY_BULLISH/VERY_BEARISH phases.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
from loguru import logger

from engines.market_sentiment_engine import MarketSentimentScore, MarketSentiment


class TrendAlertType(Enum):
    """Types of trend alerts"""
    ENTERING_VERY_BULLISH = "ENTERING_VERY_BULLISH"
    ENTERING_BULLISH = "ENTERING_BULLISH"
    ENTERING_NEUTRAL = "ENTERING_NEUTRAL"
    ENTERING_BEARISH = "ENTERING_BEARISH"
    ENTERING_VERY_BEARISH = "ENTERING_VERY_BEARISH"
    
    EXITING_VERY_BULLISH = "EXITING_VERY_BULLISH"
    EXITING_BULLISH = "EXITING_BULLISH"
    EXITING_BEARISH = "EXITING_BEARISH"
    EXITING_VERY_BEARISH = "EXITING_VERY_BEARISH"


@dataclass
class TrendAlert:
    """Market trend alert"""
    alert_type: TrendAlertType
    previous_sentiment: MarketSentiment
    current_sentiment: MarketSentiment
    previous_score: float
    current_score: float
    message: str
    timestamp: datetime
    impact_level: str  # "low", "medium", "high"


class MarketTrendAlertEngine:
    """
    Monitors market sentiment and generates alerts when trends change.
    
    Alerts on:
    - Entering VERY_BULLISH phase (great for longs)
    - Entering BULLISH phase
    - Entering BEARISH phase (good for shorts)
    - Entering VERY_BEARISH phase (risky market)
    - Exiting these phases (trend reversal)
    - Sentiment strength changes
    """
    
    def __init__(self):
        self.previous_sentiment: Optional[MarketSentimentScore] = None
        self.trend_alert_history: List[TrendAlert] = []
        
        # Thresholds for different alert types
        self.significant_change_threshold = 10  # Score point change
        self.major_change_threshold = 20  # Score point change
    
    def check_trend_alerts(
        self,
        current_sentiment: MarketSentimentScore
    ) -> List[TrendAlert]:
        """
        Check for market trend changes and generate alerts.
        
        Returns:
            List of TrendAlert if changes detected, empty list otherwise
        """
        
        alerts = []
        
        if self.previous_sentiment is None:
            self.previous_sentiment = current_sentiment
            return alerts  # First scan, no history
        
        # Check for sentiment phase changes
        phase_alerts = self._check_phase_changes(current_sentiment)
        alerts.extend(phase_alerts)
        
        # Check for strength changes within same phase
        strength_alerts = self._check_strength_changes(current_sentiment)
        alerts.extend(strength_alerts)
        
        # Store alerts in history
        self.trend_alert_history.extend(alerts)
        
        # Update previous sentiment
        self.previous_sentiment = current_sentiment
        
        return alerts
    
    def _check_phase_changes(self, current: MarketSentimentScore) -> List[TrendAlert]:
        """Check for market phase transitions"""
        
        alerts = []
        prev = self.previous_sentiment
        
        if not prev:
            return alerts
        
        # Different phases detected
        if current.sentiment != prev.sentiment:
            
            # Entering VERY_BULLISH
            if current.sentiment == MarketSentiment.VERY_BULLISH:
                alert = TrendAlert(
                    alert_type=TrendAlertType.ENTERING_VERY_BULLISH,
                    previous_sentiment=prev.sentiment,
                    current_sentiment=current.sentiment,
                    previous_score=prev.score,
                    current_score=current.score,
                    message=(
                        f"🚀 MARKET ENTERED VERY BULLISH PHASE!\n"
                        f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                        f"Gainers: {current.gainers_pct:.0f}% | Market Strength: {current.market_strength:.0f}/100\n"
                        f"This is an excellent time for LONG breakouts!"
                    ),
                    timestamp=datetime.now(),
                    impact_level="high"
                )
                alerts.append(alert)
            
            # Entering BULLISH
            elif current.sentiment == MarketSentiment.BULLISH:
                alert = TrendAlert(
                    alert_type=TrendAlertType.ENTERING_BULLISH,
                    previous_sentiment=prev.sentiment,
                    current_sentiment=current.sentiment,
                    previous_score=prev.score,
                    current_score=current.score,
                    message=(
                        f"📈 MARKET ENTERED BULLISH PHASE\n"
                        f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                        f"Gainers: {current.gainers_pct:.0f}% | Altcoin Strength: {current.altcoin_strength:.0f}/100\n"
                        f"Good conditions for LONG trades with proper risk management"
                    ),
                    timestamp=datetime.now(),
                    impact_level="high"
                )
                alerts.append(alert)
            
            # Entering BEARISH
            elif current.sentiment == MarketSentiment.BEARISH:
                alert = TrendAlert(
                    alert_type=TrendAlertType.ENTERING_BEARISH,
                    previous_sentiment=prev.sentiment,
                    current_sentiment=current.sentiment,
                    previous_score=prev.score,
                    current_score=current.score,
                    message=(
                        f"📉 MARKET ENTERED BEARISH PHASE\n"
                        f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                        f"Gainers: {current.gainers_pct:.0f}% | Losers: {current.losers_pct:.0f}%\n"
                        f"SHORT opportunities may emerge. LONGS are high risk."
                    ),
                    timestamp=datetime.now(),
                    impact_level="high"
                )
                alerts.append(alert)
            
            # Entering VERY_BEARISH
            elif current.sentiment == MarketSentiment.VERY_BEARISH:
                alert = TrendAlert(
                    alert_type=TrendAlertType.ENTERING_VERY_BEARISH,
                    previous_sentiment=prev.sentiment,
                    current_sentiment=current.sentiment,
                    previous_score=prev.score,
                    current_score=current.score,
                    message=(
                        f"🔴 MARKET ENTERED VERY BEARISH PHASE - CAUTION!\n"
                        f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                        f"Gainers: {current.gainers_pct:.0f}% | Market in distress\n"
                        f"High risk environment. Consider defensive positioning."
                    ),
                    timestamp=datetime.now(),
                    impact_level="high"
                )
                alerts.append(alert)
            
            # Entering NEUTRAL from extremes
            elif current.sentiment == MarketSentiment.NEUTRAL:
                if prev.sentiment in [MarketSentiment.VERY_BULLISH, MarketSentiment.VERY_BEARISH]:
                    alert = TrendAlert(
                        alert_type=TrendAlertType.ENTERING_NEUTRAL,
                        previous_sentiment=prev.sentiment,
                        current_sentiment=current.sentiment,
                        previous_score=prev.score,
                        current_score=current.score,
                        message=(
                            f"🟡 MARKET ENTERING NEUTRAL PHASE - CONSOLIDATION\n"
                            f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                            f"Market transitioning. Range-bound conditions expected.\n"
                            f"Be selective with entries. Require higher confirmation."
                        ),
                        timestamp=datetime.now(),
                        impact_level="medium"
                    )
                    alerts.append(alert)
        
        return alerts
    
    def _check_strength_changes(self, current: MarketSentimentScore) -> List[TrendAlert]:
        """Check for strength changes within same sentiment phase"""
        
        alerts = []
        prev = self.previous_sentiment
        
        if not prev or current.sentiment != prev.sentiment:
            return alerts  # Only check if in same phase
        
        score_change = current.score - prev.score
        
        # Major bullish strengthening
        if (current.sentiment == MarketSentiment.BULLISH and 
            score_change >= self.major_change_threshold):
            alert = TrendAlert(
                alert_type=TrendAlertType.ENTERING_VERY_BULLISH,  # Approaching VERY_BULLISH
                previous_sentiment=prev.sentiment,
                current_sentiment=current.sentiment,
                previous_score=prev.score,
                current_score=current.score,
                message=(
                    f"📈 BULLISH MOMENTUM INTENSIFYING\n"
                    f"Score jumped: {prev.score:.0f} → {current.score:.0f} (+{score_change:.0f})\n"
                    f"Market strength increasing: {prev.market_strength:.0f} → {current.market_strength:.0f}/100\n"
                    f"Approaching VERY BULLISH territory"
                ),
                timestamp=datetime.now(),
                impact_level="medium"
            )
            alerts.append(alert)
        
        # Major bearish strengthening
        elif (current.sentiment == MarketSentiment.BEARISH and 
              score_change <= -self.major_change_threshold):
            alert = TrendAlert(
                alert_type=TrendAlertType.ENTERING_VERY_BEARISH,  # Approaching VERY_BEARISH
                previous_sentiment=prev.sentiment,
                current_sentiment=current.sentiment,
                previous_score=prev.score,
                current_score=current.score,
                message=(
                    f"📉 BEARISH PRESSURE INTENSIFYING\n"
                    f"Score dropped: {prev.score:.0f} → {current.score:.0f} ({score_change:.0f})\n"
                    f"Market weakness increasing: {prev.market_strength:.0f} → {current.market_strength:.0f}/100\n"
                    f"Approaching VERY BEARISH territory"
                ),
                timestamp=datetime.now(),
                impact_level="medium"
            )
            alerts.append(alert)
        
        # Moderate changes
        elif abs(score_change) >= self.significant_change_threshold:
            if score_change > 0:
                direction = "STRENGTHENING"
                emoji = "📈"
            else:
                direction = "WEAKENING"
                emoji = "📉"
            
            alert = TrendAlert(
                alert_type=TrendAlertType.ENTERING_BULLISH if score_change > 0 else TrendAlertType.ENTERING_BEARISH,
                previous_sentiment=prev.sentiment,
                current_sentiment=current.sentiment,
                previous_score=prev.score,
                current_score=current.score,
                message=(
                    f"{emoji} Market sentiment {direction}\n"
                    f"Score: {prev.score:.0f} → {current.score:.0f}\n"
                    f"Current phase: {current.sentiment.value}\n"
                    f"Gainers: {current.gainers_pct:.0f}% | Market Strength: {current.market_strength:.0f}/100"
                ),
                timestamp=datetime.now(),
                impact_level="low"
            )
            alerts.append(alert)
        
        return alerts
    
    def get_current_phase_status(self) -> Optional[Dict]:
        """Get current market phase status"""
        
        if not self.previous_sentiment:
            return None
        
        sent = self.previous_sentiment
        
        return {
            "sentiment": sent.sentiment.value,
            "score": sent.score,
            "market_strength": sent.market_strength,
            "gainers_pct": sent.gainers_pct,
            "losers_pct": sent.losers_pct,
            "altcoin_strength": sent.altcoin_strength,
            "volatility": sent.volatility_level,
            "timestamp": sent.timestamp
        }
    
    def get_alert_summary(self, num_alerts: int = 10) -> Dict:
        """Get summary of recent alerts"""
        
        recent = self.trend_alert_history[-num_alerts:] if self.trend_alert_history else []
        
        very_bullish = sum(1 for a in recent if a.alert_type == TrendAlertType.ENTERING_VERY_BULLISH)
        bullish = sum(1 for a in recent if a.alert_type == TrendAlertType.ENTERING_BULLISH)
        bearish = sum(1 for a in recent if a.alert_type == TrendAlertType.ENTERING_BEARISH)
        very_bearish = sum(1 for a in recent if a.alert_type == TrendAlertType.ENTERING_VERY_BEARISH)
        
        return {
            "total_alerts": len(self.trend_alert_history),
            "recent_alerts": len(recent),
            "very_bullish_entered": very_bullish,
            "bullish_entered": bullish,
            "bearish_entered": bearish,
            "very_bearish_entered": very_bearish
        }
    
    def get_alert_history(self, num_entries: int = 20) -> List[TrendAlert]:
        """Get recent alert history"""
        return self.trend_alert_history[-num_entries:]
