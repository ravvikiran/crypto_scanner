"""
Hybrid Reasoner Module
Combines rule-based scoring with AI analysis for enhanced trading signals.
"""

import re
from typing import Optional
from loguru import logger

from ai import AIProviderManager
from config import get_config
from models import TradingSignal, CoinData, TrendDirection, SignalDirection


class HybridReasoner:
    """
    Hybrid Reasoner that combines rule-based analysis with AI-powered insights.
    
    This reasoner:
    - Takes a rule-based trading signal
    - Sends it to an AI model for analysis
    - Parses the AI response for confidence adjustments
    - Combines rule-based and AI reasoning into a unified output
    """
    
    def __init__(self, ai_provider: Optional[AIProviderManager] = None):
        """
        Initialize the HybridReasoner.
        
        Args:
            ai_provider: Optional AIProviderManager instance. If not provided,
                        will be created from config.
        """
        self.config = get_config()
        
        if ai_provider is None:
            # Create AI provider manager from config
            self.ai_provider = AIProviderManager(self.config.ai)
        else:
            self.ai_provider = ai_provider
        
        self.is_available = self.ai_provider.is_available()
        
        if not self.is_available:
            logger.warning("HybridReasoner: No AI providers available - hybrid reasoning disabled")
        else:
            logger.info(f"HybridReasoner initialized with provider: {self.ai_provider.get_current_provider_name()}")
    
    async def analyze_signal(self, signal: TradingSignal, coin: CoinData) -> str:
        """
        Analyze a trading signal with AI to get enhanced reasoning.
        
        Args:
            signal: The rule-based trading signal
            coin: The coin data with indicators
            
        Returns:
            AI response as string
        """
        if not self.is_available:
            return ""
        
        # Build the prompt with signal details
        prompt = self._build_analysis_prompt(signal, coin)
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert crypto trading analyst. Analyze trading signals and provide insights that enhance rule-based analysis. Be concise and actionable."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            response = await self.ai_provider.chat(
                messages=messages,
                temperature=self.config.ai.ai_temperature,
                max_tokens=self.config.ai.ai_max_tokens
            )
            
            if response.startswith("Error:"):
                logger.error(f"HybridReasoner AI error: {response}")
                return ""
            
            logger.debug(f"AI analysis received for {signal.symbol}")
            return response
            
        except Exception as e:
            logger.error(f"HybridReasoner analysis error: {e}")
            return ""
    
    def _build_analysis_prompt(self, signal: TradingSignal, coin: CoinData) -> str:
        """Build a structured prompt for AI analysis"""
        
        # Format score breakdown
        score_breakdown = ""
        if signal.score_breakdown:
            for key, value in signal.score_breakdown.items():
                score_breakdown += f"- {key}: {value}\n"
        
        # Format indicators
        indicators = []
        if coin.ema_20:
            indicators.append(f"EMA20: ${coin.ema_20:.2f}")
        if coin.ema_50:
            indicators.append(f"EMA50: ${coin.ema_50:.2f}")
        if coin.rsi:
            indicators.append(f"RSI: {coin.rsi:.1f}")
        if coin.atr:
            indicators.append(f"ATR: ${coin.atr:.2f}")
        if coin.bb_upper and coin.bb_lower:
            indicators.append(f"BB: ${coin.bb_lower:.2f} - ${coin.bb_upper:.2f}")
        
        indicators_str = ", ".join(indicators) if indicators else "N/A"
        
        # BTC trend
        btc_trend_str = signal.btc_trend.value if signal.btc_trend else "NEUTRAL"
        
        prompt = f"""Analyze this trading signal and provide:
1. Direction confirmation (LONG/SHORT/NO_TRADE)
2. Confidence adjustment (+/- points based on your analysis, range -2 to +2)
3. Key observations that rule-based might miss
4. Risk assessment
5. Suggested entry refinements

SIGNAL DETAILS:
- Symbol: {signal.symbol}
- Direction: {signal.direction.value}
- Strategy: {signal.strategy_type.value}
- Timeframe: {signal.timeframe}
- Entry Zone: ${signal.entry_zone_min:.2f} - ${signal.entry_zone_max:.2f}
- Stop Loss: ${signal.stop_loss:.2f}
- Targets: T1=${signal.target_1:.2f}, T2=${signal.target_2:.2f}
- Risk/Reward: 1:{signal.risk_reward:.1f}

SCORE BREAKDOWN (Rule-based):
{score_breakdown if score_breakdown else "No breakdown available"}

INDICATORS:
{indicators_str}

CURRENT PRICE: ${coin.current_price:.2f}
COIN TREND: {coin.trend.value}
BTC TREND: {btc_trend_str}

EXISTING REASONING:
{signal.reasoning if signal.reasoning else "No reasoning provided"}

Please provide your analysis in a structured format."""
        
        return prompt
    
    def get_confidence_adjustment(self, ai_response: str) -> float:
        """
        Parse AI response for confidence adjustment.
        
        Looks for patterns like:
        - "Confidence adjustment: +1" or "adjustment: +1"
        - "adjustment: -0.5"
        - Or extracts from numbered list format
        
        Args:
            ai_response: The AI response string
            
        Returns:
            Adjustment value between -2 and +2 (default 0)
        """
        if not ai_response:
            return 0.0
        
        # Try to find adjustment patterns
        patterns = [
            r'[Cc]onfidence [Aa]djustment[:\s]*([+-]?\d+\.?\d*)',
            r'[Aa]djustment[:\s]*([+-]?\d+\.?\d*)',
            r'([+-])\s*(\d+\.?\d*)\s*points?',
            r'([+-])\s*(\d+\.?\d*)\s*(?:to |for )?confidence',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ai_response)
            if match:
                groups = match.groups()
                if len(groups) == 1:
                    # Single group - just the number
                    try:
                        adjustment = float(groups[0])
                        return max(-2.0, min(2.0, adjustment))
                    except ValueError:
                        continue
                elif len(groups) == 2:
                    # Two groups - sign and number
                    sign = 1 if groups[0] == '+' else -1
                    try:
                        adjustment = sign * float(groups[1])
                        return max(-2.0, min(2.0, adjustment))
                    except ValueError:
                        continue
        
        # If no explicit adjustment found, look for direction indicators
        response_lower = ai_response.lower()
        
        # Strong positive indicators
        positive_words = ['strong buy', 'high confidence', 'excellent', 'very bullish', 'confirmed']
        negative_words = ['strong sell', 'low confidence', 'avoid', 'very bearish', 'rejected']
        
        positive_count = sum(1 for word in positive_words if word in response_lower)
        negative_count = sum(1 for word in negative_words if word in response_lower)
        
        if positive_count > negative_count:
            return min(1.0, positive_count * 0.5)
        elif negative_count > positive_count:
            return max(-1.0, -negative_count * 0.5)
        
        return 0.0
    
    def get_hybrid_reasoning(self, signal: TradingSignal, ai_response: str) -> str:
        """
        Combine rule-based and AI reasoning into a unified output.
        
        Args:
            signal: The original trading signal
            ai_response: The AI analysis response
            
        Returns:
            Combined reasoning string
        """
        if not ai_response:
            return signal.reasoning if signal.reasoning else "Rule-based analysis only"
        
        # Extract key parts from AI response
        lines = ai_response.split('\n')
        
        # Build hybrid reasoning
        parts = []
        
        # Add rule-based reasoning header
        parts.append("=== RULE-BASED ANALYSIS ===")
        if signal.reasoning:
            parts.append(signal.reasoning)
        
        # Add score info
        if signal.score_breakdown:
            breakdown_str = ", ".join([f"{k}: {v}" for k, v in signal.score_breakdown.items()])
            parts.append(f"Base Score: {signal.confidence_score:.1f}/10 ({breakdown_str})")
        
        # Add AI analysis
        parts.append("\n=== AI ENHANCED ANALYSIS ===")
        
        # Try to extract key sections from AI response
        direction_match = re.search(r'(?:1\.|Direction)[:\s]*(LONG|SHORT|NO_TRADE)', ai_response, re.IGNORECASE)
        if direction_match:
            parts.append(f"AI Direction: {direction_match.group(1)}")
        
        # Add the full AI response (truncated if too long)
        if len(ai_response) > 500:
            parts.append(ai_response[:500] + "...")
        else:
            parts.append(ai_response)
        
        return "\n".join(parts)
    
    async def apply_hybrid_analysis(
        self, 
        signal: TradingSignal, 
        coin: CoinData
    ) -> TradingSignal:
        """
        Apply full hybrid analysis to a signal.
        
        This method:
        1. Stores the rule-based confidence
        2. Gets AI analysis
        3. Parses confidence adjustment
        4. Applies adjustment to confidence score
        5. Combines reasoning
        
        Args:
            signal: The rule-based trading signal
            coin: The coin data with indicators
            
        Returns:
            Updated signal with hybrid reasoning applied
        """
        if not self.is_available:
            return signal
        
        # Store rule-based confidence
        signal.rule_based_confidence = signal.confidence_score
        
        # Get AI analysis
        ai_response = await self.analyze_signal(signal, coin)
        
        if ai_response:
            # Get confidence adjustment
            adjustment = self.get_confidence_adjustment(ai_response)
            signal.ai_reasoning_contribution = adjustment
            
            # Apply adjustment to confidence score
            new_confidence = signal.confidence_score + adjustment
            signal.confidence_score = max(0.0, min(10.0, new_confidence))
            
            # Combine reasoning
            signal.hybrid_reasoning = self.get_hybrid_reasoning(signal, ai_response)
            
            logger.info(
                f"Hybrid analysis for {signal.symbol}: "
                f"base={signal.rule_based_confidence:.1f}, "
                f"adjustment={adjustment:+.1f}, "
                f"final={signal.confidence_score:.1f}"
            )
        else:
            # AI analysis failed, keep rule-based
            signal.hybrid_reasoning = signal.reasoning
            signal.ai_reasoning_contribution = 0.0
            signal.rule_based_confidence = signal.confidence_score
        
        return signal
