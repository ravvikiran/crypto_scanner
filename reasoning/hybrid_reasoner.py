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
        
        # REQ-004: Hybrid Decision Algorithm weights
        # Formula: Final_Score = (Rule_Score × Rule_Weight) + (AI_Score × AI_Weight)
        # Default: 60% Rule-Based + 40% AI
        self.rule_weight = self.config.ai.rule_weight
        self.ai_weight = self.config.ai.ai_weight
        
        # Validate weights add up to 1.0
        total_weight = self.rule_weight + self.ai_weight
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"Hybrid weights don't sum to 1.0 ({self.rule_weight} + {self.ai_weight} = {total_weight}). "
                "Normalizing weights."
            )
            self.rule_weight = self.rule_weight / total_weight
            self.ai_weight = self.ai_weight / total_weight
        
        if not self.is_available:
            logger.warning("HybridReasoner: No AI providers available - hybrid reasoning disabled")
        else:
            logger.info(
                f"HybridReasoner initialized with provider: {self.ai_provider.get_current_provider_name()}, "
                f"weights: {self.rule_weight:.0%} rule + {self.ai_weight:.0%} AI"
            )
    
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
        REQ-005: Combine rule-based and AI reasoning into unified output.
        
        Components:
        - Key factors that contributed to the score
        - AI insights and observations  
        - Risk factors identified
        
        Args:
            signal: The original trading signal
            ai_response: The AI analysis response
            
        Returns:
            Combined reasoning string with risk factors
        """
        if not ai_response:
            return signal.reasoning if signal.reasoning else "Rule-based analysis only"
        
        parts = []
        
        # === RULE-BASED ANALYSIS ===
        parts.append("=== RULE-BASED ANALYSIS ===")
        if signal.reasoning:
            parts.append(signal.reasoning)
        
        # Score breakdown - key factors
        if signal.score_breakdown:
            breakdown_str = ", ".join([f"{k}: {v}" for k, v in signal.score_breakdown.items()])
            parts.append(f"Base Score: {signal.confidence_score:.1f}/10 ({breakdown_str})")
        
        # === AI ENHANCED ANALYSIS ===
        parts.append("\n=== AI ENHANCED ANALYSIS ===")
        
        # Try to extract direction confirmation
        direction_match = re.search(r'(?:1\.|Direction)[:\s]*(LONG|SHORT|NO_TRADE)', ai_response, re.IGNORECASE)
        if direction_match:
            parts.append(f"AI Direction: {direction_match.group(1)}")
        
        # Key observations from AI
        key_obs_match = re.search(r'(?:3\.|Key observations?|Observations)[:\s]*(.+?)(?:\n\d+\.|$)', ai_response, re.IGNORECASE | re.DOTALL)
        if key_obs_match:
            parts.append(f"Key Observations: {key_obs_match.group(1).strip()}")
        
        # === RISK FACTORS (REQ-005) ===
        parts.append("\n=== RISK FACTORS ===")
        
        # Extract risk assessment from AI (item 4 in prompt)
        risk_match = re.search(r'(?:4\.|Risk assessment|Risks?)[:\s]*(.+?)(?:\n\d+\.|$)', ai_response, re.IGNORECASE | re.DOTALL)
        if risk_match:
            parts.append(f"Risk Assessment: {risk_match.group(1).strip()}")
        else:
            # Default risk factors based on signal properties
            risk_factors = []
            
            # Check R/R ratio
            if signal.risk_reward < 2.0:
                risk_factors.append(f"Low R/R ratio: 1:{signal.risk_reward:.1f}")
            
            # Check confidence
            if signal.confidence_score < 6.0:
                risk_factors.append(f"Lower confidence: {signal.confidence_score:.1f}/10")
            
            # Check stop loss distance
            if signal.stop_loss:
                entry = signal.entry_zone_min
                sl_distance = abs(entry - signal.stop_loss) / entry * 100
                if sl_distance > 3.0:
                    risk_factors.append(f"Wide stop loss: {sl_distance:.1f}% from entry")
            
            if risk_factors:
                parts.append("; ".join(risk_factors))
            else:
                parts.append("No significant risk factors identified")
        
        # Suggested refinements
        refine_match = re.search(r'(?:5\.|Suggested entry refinenments|Entry refinements?)[:\s]*(.+?)(?:\n\n|\n[^\d]|$)', ai_response, re.IGNORECASE | re.DOTALL)
        if refine_match:
            parts.append(f"Suggested Refinements: {refine_match.group(1).strip()}")
        
        # Truncate if too long
        result = "\n".join(parts)
        if len(result) > 1500:
            result = result[:1500] + "...\n(truncated)"
        
        return result
    
    async def apply_hybrid_analysis(
        self, 
        signal: TradingSignal, 
        coin: CoinData
    ) -> TradingSignal:
        """
        Apply full hybrid analysis to a signal using weighted scoring.
        
        REQ-004: Hybrid Decision Algorithm
        Formula: Final_Score = (Rule_Score × Rule_Weight) + (AI_Score × AI_Weight)
        Default: 60% Rule-Based + 40% AI
        
        1. Stores the rule-based confidence
        2. Gets AI analysis in parallel
        3. Combines using weighted formula
        4. Requires LLM to be enabled
        
        Args:
            signal: The rule-based trading signal
            coin: The coin data with indicators
            
        Returns:
            Updated signal with hybrid confidence
        """
        if not self.is_available:
            return signal
        
        # Store rule-based confidence for reference (scale to 0-100)
        signal.rule_based_confidence = signal.confidence_score * 10
        
        # Get AI analysis
        ai_response = await self.analyze_signal(signal, coin)
        
        if ai_response:
            # Extract AI confidence (scale 0-100)
            ai_confidence_raw = self._extract_ai_confidence(ai_response)
            
            if ai_confidence_raw > 0:
                # AI provided explicit confidence (scale from 0-10 to 0-100)
                ai_confidence = ai_confidence_raw * 10
            else:
                # Use adjustment-based approach + base AI confidence of 50
                adjustment = self.get_confidence_adjustment(ai_response)
                ai_confidence = 50 + (adjustment * 10)
            
            # REQ-004: Apply weighted formula
            # Final_Score = (Rule_Score × Rule_Weight) + (AI_Score × AI_Weight)
            final_score = (
                (signal.rule_based_confidence * self.rule_weight) + 
                (ai_confidence * self.ai_weight)
            )
            
            # Calculate contribution for logging
            signal.ai_reasoning_contribution = ai_confidence - signal.rule_based_confidence
            
            # Store the combined score (scale back to 0-10)
            signal.confidence_score = max(0.0, min(10.0, final_score / 10))
            
            # Combine reasoning with risk factors (REQ-005)
            signal.hybrid_reasoning = self.get_hybrid_reasoning(signal, ai_response)
            
            logger.info(
                f"Hybrid analysis for {signal.symbol}: "
                f"rule={signal.rule_based_confidence:.1f}×{self.rule_weight:.0%} + "
                f"ai={ai_confidence:.1f}×{self.ai_weight:.0%} = "
                f"final={final_score:.1f}"
            )
        else:
            # AI analysis failed, fall back to rule-based only
            signal.hybrid_reasoning = signal.reasoning
            signal.ai_reasoning_contribution = 0.0
            signal.confidence_score = signal.rule_based_confidence / 10
        
        return signal
    
    def _extract_ai_confidence(self, ai_response: str) -> float:
        """
        Extract absolute confidence score from AI response.
        
        Looks for patterns like:
        - "Confidence: 8/10" or "Confidence: 8"
        - "Confidence score: 7.5"
        - "Final confidence: 9"
        
        Returns:
            Confidence value between 0-10, or 0 if not found
        """
        if not ai_response:
            return 0.0
        
        # Try to find explicit confidence patterns
        patterns = [
            r'[Cc]onfidence[:\s]*(\d+\.?\d*)\s*(?:/|\s?out of\s?)?\s*10?',
            r'[Ff]inal [Cc]onfidence[:\s]*(\d+\.?\d*)',
            r'[Ss]core[:\s]*(\d+\.?\d*)\s*(?:/|\s?out of\s?)?\s*10?',
            r'(?:^|\n)\s*(\d+\.?\d*)\s*/\s*10\s*(?:\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ai_response)
            if match:
                try:
                    confidence = float(match.group(1))
                    return max(0.0, min(10.0, confidence))
                except ValueError:
                    continue
        
        return 0.0
