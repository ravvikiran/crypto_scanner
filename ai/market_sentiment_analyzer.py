"""
AI Market Sentiment Analyzer
Uses AI to analyze and interpret market sentiment patterns.
Provides enhanced market insights and recommendations.
"""

import asyncio
from typing import Optional, Dict, List
from loguru import logger

from ai import AIProviderManager
from config import get_config
from models import CoinData
from engines.market_sentiment_engine import MarketSentimentScore, MarketSentiment


class AIMarketSentimentAnalyzer:
    """
    Uses AI to provide deeper market sentiment analysis and insights.
    Complements the rule-based MarketSentimentEngine with AI interpretation.
    """
    
    def __init__(self, ai_provider: Optional[AIProviderManager] = None):
        """Initialize with AI provider"""
        self.config = get_config()
        
        if ai_provider is None:
            self.ai_provider = AIProviderManager(self.config.ai)
        else:
            self.ai_provider = ai_provider
        
        self.is_available = self.ai_provider.is_available()
        
        if self.is_available:
            logger.info(
                f"AIMarketSentimentAnalyzer initialized with provider: "
                f"{self.ai_provider.get_current_provider_name()}"
            )
        else:
            logger.warning("AIMarketSentimentAnalyzer: No AI provider available")
    
    async def analyze_sentiment_with_ai(
        self,
        sentiment_score: MarketSentimentScore,
        btc_coin: Optional[CoinData] = None,
        top_gainers: Optional[List[CoinData]] = None,
        top_losers: Optional[List[CoinData]] = None
    ) -> Dict[str, str]:
        """
        Use AI to provide enhanced market sentiment analysis.
        
        Args:
            sentiment_score: MarketSentimentScore from rule-based analysis
            btc_coin: Bitcoin coin data (optional)
            top_gainers: Top performing coins (optional)
            top_losers: Bottom performing coins (optional)
            
        Returns:
            Dictionary with:
            - 'insight': AI market insight
            - 'risk_level': Risk assessment
            - 'recommendation': Trading recommendation
        """
        
        if not self.is_available:
            return {
                'insight': sentiment_score.reason,
                'risk_level': 'medium',
                'recommendation': 'Monitor market conditions'
            }
        
        try:
            prompt = self._build_sentiment_analysis_prompt(
                sentiment_score=sentiment_score,
                btc_coin=btc_coin,
                top_gainers=top_gainers,
                top_losers=top_losers
            )
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert cryptocurrency market analyst. "
                        "Analyze market sentiment and provide actionable insights for traders. "
                        "Be concise, specific, and focus on key opportunities and risks."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = await self.ai_provider.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=500
            )
            
            # Parse AI response
            result = self._parse_ai_response(response)
            
            logger.debug(f"AI Sentiment Analysis: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"AI sentiment analysis error: {e}")
            return {
                'insight': sentiment_score.reason,
                'risk_level': 'medium',
                'recommendation': 'Unable to get AI analysis'
            }
    
    def _build_sentiment_analysis_prompt(
        self,
        sentiment_score: MarketSentimentScore,
        btc_coin: Optional[CoinData] = None,
        top_gainers: Optional[List[CoinData]] = None,
        top_losers: Optional[List[CoinData]] = None
    ) -> str:
        """Build prompt for AI sentiment analysis"""
        
        prompt_lines = [
            "# Cryptocurrency Market Analysis Request",
            "",
            "## Current Market Metrics:",
            f"- Overall Sentiment: {sentiment_score.sentiment.value}",
            f"- Sentiment Score: {sentiment_score.score:.1f}/100",
            f"- Bitcoin Trend: {sentiment_score.btc_trend.value}",
            f"- Market Breadth: {sentiment_score.gainers_pct:.1f}% gainers, {sentiment_score.losers_pct:.1f}% losers",
            f"- Market Strength: {sentiment_score.market_strength:.1f}/100",
            f"- Altcoin Strength: {sentiment_score.altcoin_strength:.1f}/100",
            f"- BTC Dominance Trend: {sentiment_score.btc_dominance_trend}",
            f"- Volatility Level: {sentiment_score.volatility_level}",
        ]
        
        if btc_coin:
            prompt_lines.extend([
                "",
                "## Bitcoin Analysis:",
                f"- Current Price: ${btc_coin.current_price:,.2f}",
                f"- 24h Change: {btc_coin.price_change_percent_24h:.2f}%",
                f"- 24h Volume: ${btc_coin.volume_24h:,.0f}",
            ])
            
            if btc_coin.rsi:
                prompt_lines.append(f"- RSI (4h): {btc_coin.rsi:.1f}")
        
        if top_gainers:
            prompt_lines.append("")
            prompt_lines.append("## Top Gainers (24h):")
            for i, coin in enumerate(top_gainers[:5], 1):
                prompt_lines.append(
                    f"{i}. {coin.symbol}: +{coin.price_change_percent_24h:.2f}%"
                )
        
        if top_losers:
            prompt_lines.append("")
            prompt_lines.append("## Top Losers (24h):")
            for i, coin in enumerate(top_losers[:5], 1):
                prompt_lines.append(
                    f"{i}. {coin.symbol}: {coin.price_change_percent_24h:.2f}%"
                )
        
        prompt_lines.extend([
            "",
            "## Analysis Request:",
            "Based on the above metrics:",
            "1. What is your assessment of the current market condition?",
            "2. What is the risk level (low/medium/high)?",
            "3. What trading opportunities or cautions do you identify?",
            "4. Should traders focus on longs, shorts, or be cautious?",
            "",
            "Format your response as concise bullet points."
        ])
        
        return "\n".join(prompt_lines)
    
    def _parse_ai_response(self, response: str) -> Dict[str, str]:
        """
        Parse AI response to extract structured insights.
        Falls back to defaults if parsing fails.
        """
        
        result = {
            'insight': response,
            'risk_level': self._extract_risk_level(response),
            'recommendation': self._extract_recommendation(response)
        }
        
        return result
    
    def _extract_risk_level(self, response: str) -> str:
        """Extract risk level from AI response"""
        response_lower = response.lower()
        
        if 'high risk' in response_lower or 'very risky' in response_lower:
            return 'high'
        elif 'low risk' in response_lower or 'safe' in response_lower:
            return 'low'
        else:
            return 'medium'
    
    def _extract_recommendation(self, response: str) -> str:
        """Extract trading recommendation from AI response"""
        response_lower = response.lower()
        
        if 'long' in response_lower and 'bullish' in response_lower:
            return 'Focus on LONG breakouts'
        elif 'short' in response_lower and 'bearish' in response_lower:
            return 'Focus on SHORT opportunities'
        elif 'caution' in response_lower or 'avoid' in response_lower:
            return 'Trade with caution - consolidation expected'
        else:
            return 'Monitor market conditions'


class MarketSentimentMonitor:
    """
    Continuously monitors and tracks market sentiment over time.
    Detects sentiment shifts and provides alerts.
    """
    
    def __init__(self):
        self.config = get_config()
        self.previous_sentiment: Optional[MarketSentimentScore] = None
        self.sentiment_shift_threshold = 15  # Score points to trigger shift alert
    
    def check_sentiment_shift(
        self,
        current_sentiment: MarketSentimentScore
    ) -> Optional[str]:
        """
        Check if there's a significant sentiment shift.
        
        Returns:
            Alert message if shift detected, None otherwise
        """
        
        if self.previous_sentiment is None:
            self.previous_sentiment = current_sentiment
            return None
        
        score_diff = current_sentiment.score - self.previous_sentiment.score
        
        # Significant bullish shift
        if score_diff >= self.sentiment_shift_threshold:
            message = (
                f"🟢 BULLISH SENTIMENT SHIFT: Market sentiment improved from "
                f"{self.previous_sentiment.sentiment.value} to {current_sentiment.sentiment.value} "
                f"(Score: {self.previous_sentiment.score:.0f} → {current_sentiment.score:.0f})"
            )
            self.previous_sentiment = current_sentiment
            return message
        
        # Significant bearish shift
        if score_diff <= -self.sentiment_shift_threshold:
            message = (
                f"🔴 BEARISH SENTIMENT SHIFT: Market sentiment deteriorated from "
                f"{self.previous_sentiment.sentiment.value} to {current_sentiment.sentiment.value} "
                f"(Score: {self.previous_sentiment.score:.0f} → {current_sentiment.score:.0f})"
            )
            self.previous_sentiment = current_sentiment
            return message
        
        # Update without shift
        self.previous_sentiment = current_sentiment
        return None
