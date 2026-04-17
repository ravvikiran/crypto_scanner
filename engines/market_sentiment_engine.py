"""
Market Sentiment Engine
Analyzes overall cryptocurrency market sentiment and conditions.
Provides sentiment scores and AI-powered market insights.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from enum import Enum
from loguru import logger

from config import get_config
from models import CoinData, TrendDirection


class MarketSentiment(Enum):
    """Market sentiment levels"""
    VERY_BEARISH = "VERY_BEARISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    VERY_BULLISH = "VERY_BULLISH"


@dataclass
class MarketSentimentScore:
    """Market sentiment analysis result"""
    sentiment: MarketSentiment
    score: float  # 0-100, 50 is neutral
    btc_trend: TrendDirection
    gainers_pct: float  # % of coins up
    losers_pct: float  # % of coins down
    avg_volume_change: float  # avg 24h volume change
    market_strength: float  # 0-100, how strong is the move
    btc_dominance_trend: str  # "increasing" or "decreasing"
    altcoin_strength: float  # 0-100, strength of alts vs btc
    volatility_level: str  # "low", "normal", "high"
    reason: str
    timestamp: datetime
    ai_insights: Optional[Dict] = field(default_factory=dict)  # Optional AI-generated insights


class MarketSentimentEngine:
    """
    Analyzes cryptocurrency market sentiment using:
    - Bitcoin trend and performance
    - Altcoin performance distribution
    - Market breadth (gainers vs losers)
    - Volume analysis
    - Volatility metrics
    - AI-powered interpretation
    """
    
    def __init__(self):
        self.config = get_config()
    
    def analyze_market_sentiment(
        self,
        btc_coin: CoinData,
        all_coins: List[CoinData],
        ai_provider=None
    ) -> MarketSentimentScore:
        """
        Analyze overall market sentiment.
        
        Args:
            btc_coin: Bitcoin coin data with indicators
            all_coins: List of all analyzed coins
            ai_provider: Optional AI provider for enhanced analysis
            
        Returns:
            MarketSentimentScore with sentiment analysis
        """
        try:
            if not btc_coin or not all_coins:
                return self._neutral_sentiment("Insufficient data")
            
            # Calculate sentiment components
            btc_trend = self._analyze_btc_trend(btc_coin)
            gainers_pct, losers_pct = self._analyze_market_breadth(all_coins)
            avg_volume_change = self._analyze_volume_patterns(all_coins)
            market_strength = self._calculate_market_strength(all_coins, btc_coin)
            btc_dominance_trend = self._analyze_btc_dominance(all_coins)
            altcoin_strength = self._analyze_altcoin_performance(all_coins, btc_coin)
            volatility_level = self._analyze_volatility(btc_coin, all_coins)
            
            # Combine metrics into sentiment score
            sentiment, score = self._calculate_sentiment_score(
                btc_trend=btc_trend,
                gainers_pct=gainers_pct,
                market_strength=market_strength,
                altcoin_strength=altcoin_strength,
                btc_dominance_trend=btc_dominance_trend,
                volatility_level=volatility_level
            )
            
            # Generate reason
            reason = self._generate_sentiment_reason(
                sentiment=sentiment,
                score=score,
                btc_trend=btc_trend,
                gainers_pct=gainers_pct,
                market_strength=market_strength,
                altcoin_strength=altcoin_strength,
                btc_dominance_trend=btc_dominance_trend
            )
            
            result = MarketSentimentScore(
                sentiment=sentiment,
                score=score,
                btc_trend=btc_trend,
                gainers_pct=gainers_pct,
                losers_pct=losers_pct,
                avg_volume_change=avg_volume_change,
                market_strength=market_strength,
                btc_dominance_trend=btc_dominance_trend,
                altcoin_strength=altcoin_strength,
                volatility_level=volatility_level,
                reason=reason,
                timestamp=datetime.now()
            )
            
            logger.info(
                f"📊 Market Sentiment: {sentiment.value} ({score:.1f}/100) | "
                f"BTC: {btc_trend.value} | Gainers: {gainers_pct:.1f}% | "
                f"Alt Strength: {altcoin_strength:.1f} | Vol: {volatility_level}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Market sentiment analysis error: {e}")
            return self._neutral_sentiment(f"Analysis error: {e}")
    
    def _analyze_btc_trend(self, btc_coin: CoinData) -> TrendDirection:
        """Determine Bitcoin's trend direction"""
        if not btc_coin.current_price or not all([
            btc_coin.ema_20, btc_coin.ema_50, btc_coin.ema_100, btc_coin.ema_200
        ]):
            return TrendDirection.NEUTRAL
        
        price = btc_coin.current_price
        
        # Strong bullish: price above all EMAs
        if all(price > ema for ema in [btc_coin.ema_20, btc_coin.ema_50, btc_coin.ema_100, btc_coin.ema_200]):
            return TrendDirection.BULLISH
        
        # Strong bearish: price below all EMAs
        if all(price < ema for ema in [btc_coin.ema_20, btc_coin.ema_50, btc_coin.ema_100, btc_coin.ema_200]):
            return TrendDirection.BEARISH
        
        # Price above 50-100 EMAs = bullish
        if price > btc_coin.ema_50 and price > btc_coin.ema_100:
            return TrendDirection.BULLISH
        
        # Price below 50-100 EMAs = bearish
        if price < btc_coin.ema_50 and price < btc_coin.ema_100:
            return TrendDirection.BEARISH
        
        return TrendDirection.NEUTRAL
    
    def _analyze_market_breadth(self, coins: List[CoinData]) -> Tuple[float, float]:
        """Calculate % of gainers vs losers in market"""
        if not coins:
            return 50.0, 50.0
        
        gainers = sum(1 for c in coins if c.price_change_percent_24h > 0)
        losers = sum(1 for c in coins if c.price_change_percent_24h < 0)
        
        total = gainers + losers
        if total == 0:
            return 50.0, 50.0
        
        gainers_pct = (gainers / total) * 100
        losers_pct = (losers / total) * 100
        
        return gainers_pct, losers_pct
    
    def _analyze_volume_patterns(self, coins: List[CoinData]) -> float:
        """Analyze average volume change across market"""
        if not coins:
            return 0.0
        
        volume_changes = [
            c.volume_change_24h for c in coins
            if hasattr(c, 'volume_change_24h') and c.volume_change_24h is not None
        ]
        
        if not volume_changes:
            return 0.0
        
        avg_change = sum(volume_changes) / len(volume_changes)
        return avg_change
    
    def _calculate_market_strength(self, coins: List[CoinData], btc_coin: CoinData) -> float:
        """Calculate overall market strength 0-100"""
        if not coins or not btc_coin:
            return 50.0
        
        # Component 1: Market breadth (gainers dominance)
        gainers = sum(1 for c in coins if c.price_change_percent_24h > 2)
        breadth_score = (gainers / max(len(coins), 1)) * 100
        
        # Component 2: Average price performance (how much are coins moving)
        avg_change = sum(abs(c.price_change_percent_24h) for c in coins) / max(len(coins), 1)
        movement_score = min(avg_change * 10, 100)  # Normalize
        
        # Component 3: Bitcoin momentum
        btc_change = btc_coin.price_change_percent_24h
        btc_score = min(max(50 + (btc_change / 2), 0), 100)  # -20% = 40, +20% = 60
        
        # Weighted combination
        strength = (breadth_score * 0.4) + (movement_score * 0.3) + (btc_score * 0.3)
        
        return min(max(strength, 0), 100)
    
    def _analyze_btc_dominance(self, coins: List[CoinData]) -> str:
        """Determine if BTC dominance is increasing or decreasing"""
        # BTC dominance increases when BTC outperforms alts
        # This is a simplified check based on recent performance
        
        btc_coin = next((c for c in coins if c.symbol == "BTC"), None)
        if not btc_coin:
            return "neutral"
        
        # Get average alt performance
        alt_coins = [c for c in coins if c.symbol != "BTC"]
        if not alt_coins:
            return "neutral"
        
        avg_alt_change = sum(c.price_change_percent_24h for c in alt_coins) / len(alt_coins)
        btc_change = btc_coin.price_change_percent_24h
        
        # If BTC outperforms alts by more than 2%, dominance is increasing
        if btc_change - avg_alt_change > 2:
            return "increasing"
        elif btc_change - avg_alt_change < -2:
            return "decreasing"
        return "stable"
    
    def _analyze_altcoin_performance(self, coins: List[CoinData], btc_coin: CoinData) -> float:
        """Calculate altcoin strength relative to BTC"""
        # Alt strength: how well are alts performing
        # 0-100 scale where 100 = alts performing well, 0 = alts weak
        
        alt_coins = [c for c in coins if c.symbol != "BTC"]
        if not alt_coins:
            return 50.0
        
        # Measure 1: How many alts are outperforming BTC
        if btc_coin and btc_coin.price_change_percent_24h is not None:
            btc_change = btc_coin.price_change_percent_24h
            alts_beating_btc = sum(
                1 for c in alt_coins if c.price_change_percent_24h > btc_change
            )
            alt_beat_pct = (alts_beating_btc / len(alt_coins)) * 100
        else:
            alt_beat_pct = 50.0
        
        # Measure 2: Positive altcoins
        positive_alts = sum(1 for c in alt_coins if c.price_change_percent_24h > 0)
        positive_pct = (positive_alts / len(alt_coins)) * 100 if alt_coins else 50.0
        
        # Combined
        alt_strength = (alt_beat_pct * 0.6) + (positive_pct * 0.4)
        
        return min(max(alt_strength, 0), 100)
    
    def _analyze_volatility(self, btc_coin: CoinData, coins: List[CoinData]) -> str:
        """Determine volatility level"""
        if not btc_coin:
            return "normal"
        
        # Use BTC's volatility as market proxy
        btc_change = abs(btc_coin.price_change_percent_24h)
        
        if btc_change < 2:
            return "low"
        elif btc_change > 5:
            return "high"
        else:
            return "normal"
    
    def _calculate_sentiment_score(
        self,
        btc_trend: TrendDirection,
        gainers_pct: float,
        market_strength: float,
        altcoin_strength: float,
        btc_dominance_trend: str,
        volatility_level: str
    ) -> Tuple[MarketSentiment, float]:
        """
        Calculate overall sentiment score 0-100.
        50 = neutral, 100 = maximum bullish, 0 = maximum bearish
        """
        
        # Start with market strength as base
        score = market_strength
        
        # Adjust for Bitcoin trend
        if btc_trend == TrendDirection.BULLISH:
            score += 10
        elif btc_trend == TrendDirection.BEARISH:
            score -= 10
        
        # Adjust for market breadth (gainers vs losers)
        breadth_adjustment = (gainers_pct - 50) * 0.4  # -20 to +20
        score += breadth_adjustment
        
        # Adjust for altcoin strength
        # If alts are strong, market is bullish. If weak, bearish.
        if altcoin_strength > 60:
            score += 5
        elif altcoin_strength < 40:
            score -= 5
        
        # Adjust for BTC dominance
        if btc_dominance_trend == "increasing":
            score -= 5  # Less bullish for alts
        elif btc_dominance_trend == "decreasing":
            score += 5  # More bullish for alts
        
        # Adjust for volatility
        if volatility_level == "high":
            score -= 5  # Lower confidence in high volatility
        elif volatility_level == "low":
            score -= 3  # Consolidation, less momentum
        
        # Clamp to 0-100
        score = min(max(score, 0), 100)
        
        # Convert score to sentiment
        if score >= 75:
            sentiment = MarketSentiment.VERY_BULLISH
        elif score >= 60:
            sentiment = MarketSentiment.BULLISH
        elif score >= 40:
            sentiment = MarketSentiment.NEUTRAL
        elif score >= 25:
            sentiment = MarketSentiment.BEARISH
        else:
            sentiment = MarketSentiment.VERY_BEARISH
        
        return sentiment, score
    
    def _generate_sentiment_reason(
        self,
        sentiment: MarketSentiment,
        score: float,
        btc_trend: TrendDirection,
        gainers_pct: float,
        market_strength: float,
        altcoin_strength: float,
        btc_dominance_trend: str
    ) -> str:
        """Generate human-readable sentiment reason"""
        
        reasons = []
        
        # BTC trend
        if btc_trend == TrendDirection.BULLISH:
            reasons.append("BTC in uptrend")
        else:
            reasons.append("BTC in downtrend")
        
        # Market breadth
        if gainers_pct > 60:
            reasons.append(f"Strong market breadth ({gainers_pct:.0f}% gainers)")
        elif gainers_pct < 40:
            reasons.append(f"Weak market breadth ({gainers_pct:.0f}% gainers)")
        
        # Altcoin performance
        if altcoin_strength > 65:
            reasons.append("Altcoins performing well")
        elif altcoin_strength < 35:
            reasons.append("Altcoins weak")
        
        # BTC dominance
        if btc_dominance_trend == "increasing":
            reasons.append("BTC dominance increasing")
        elif btc_dominance_trend == "decreasing":
            reasons.append("Altseason indicators")
        
        reason_text = " | ".join(reasons)
        return f"{sentiment.value} ({score:.0f}/100): {reason_text}"
    
    def _neutral_sentiment(self, reason: str) -> MarketSentimentScore:
        """Return neutral sentiment with reason"""
        return MarketSentimentScore(
            sentiment=MarketSentiment.NEUTRAL,
            score=50.0,
            btc_trend=TrendDirection.NEUTRAL,
            gainers_pct=50.0,
            losers_pct=50.0,
            avg_volume_change=0.0,
            market_strength=50.0,
            btc_dominance_trend="stable",
            altcoin_strength=50.0,
            volatility_level="normal",
            reason=reason,
            timestamp=datetime.now()
        )
    
    def is_sentiment_favorable_for_breakouts(
        self,
        sentiment_score: MarketSentimentScore
    ) -> bool:
        """
        Check if market sentiment is favorable for trading breakouts.
        
        Returns True if:
        - Market is in BULLISH or VERY_BULLISH sentiment
        - OR market is NEUTRAL but with good market strength
        """
        
        if sentiment_score.sentiment in [
            MarketSentiment.VERY_BULLISH,
            MarketSentiment.BULLISH
        ]:
            return True
        
        # Even in NEUTRAL sentiment, allow if strong enough
        if (sentiment_score.sentiment == MarketSentiment.NEUTRAL and
            sentiment_score.market_strength > 55):
            return True
        
        return False
    
    def is_sentiment_favorable_for_shorts(
        self,
        sentiment_score: MarketSentimentScore
    ) -> bool:
        """
        Check if market sentiment is favorable for short trades.
        
        Returns True if:
        - Market is in BEARISH or VERY_BEARISH sentiment
        - OR market is NEUTRAL with weak market strength
        """
        
        if sentiment_score.sentiment in [
            MarketSentiment.VERY_BEARISH,
            MarketSentiment.BEARISH
        ]:
            return True
        
        # Even in NEUTRAL sentiment, allow if weak enough
        if (sentiment_score.sentiment == MarketSentiment.NEUTRAL and
            sentiment_score.market_strength < 45):
            return True
        
        return False
