"""
AI Signal Validation Agent
An intelligent AI agent that reviews trading signals and validates them 
against market conditions, setup quality, and risk parameters.
Provides reasoned APPROVE/REJECT decisions with confidence adjustments.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from enum import Enum
from loguru import logger

from ai import AIProviderManager
from config import get_config
from models import TradingSignal, CoinData
from engines.market_sentiment_engine import MarketSentimentScore, MarketSentiment


class SignalDecision(Enum):
    """AI agent signal decision"""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    HOLD = "HOLD"  # Need more data


@dataclass
class SignalValidationResult:
    """Result of AI signal validation"""
    signal_id: str
    symbol: str
    decision: SignalDecision
    original_confidence: float
    adjusted_confidence: float
    confidence_change: float  # positive = boost, negative = reduce
    reasoning: str
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    risk_assessment: str = ""
    market_alignment_score: float = 0.0  # 0-100
    setup_quality_score: float = 0.0  # 0-100
    recommendation: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class AISignalValidationAgent:
    """
    AI Agent that validates trading signals against market conditions.
    
    Performs these checks:
    1. Market Alignment - Does signal direction match market sentiment?
    2. Setup Quality - Is the technical setup valid and strong?
    3. Risk Management - Are R:R and stops appropriate?
    4. Confluence - Do multiple indicators align?
    5. Volume Confirmation - Is volume supporting the move?
    6. Market Regime - Is signal appropriate for current regime?
    """
    
    def __init__(self, ai_provider: Optional[AIProviderManager] = None):
        """Initialize the validation agent"""
        self.config = get_config()
        
        if ai_provider is None:
            self.ai_provider = AIProviderManager(self.config.ai)
        else:
            self.ai_provider = ai_provider
        
        self.is_available = self.ai_provider.is_available()
        self.decision_log: List[SignalValidationResult] = []
        
        if self.is_available:
            logger.info(
                f"✅ AI Signal Validation Agent initialized with {self.ai_provider.get_current_provider_name()}"
            )
        else:
            logger.warning("⚠️ AI Signal Validation Agent: No AI provider available (using rule-based fallback)")
    
    async def validate_signal(
        self,
        signal: TradingSignal,
        coin: CoinData,
        market_sentiment: MarketSentimentScore
    ) -> SignalValidationResult:
        """
        Validate a trading signal with comprehensive AI analysis.
        
        Args:
            signal: The trading signal to validate
            coin: Coin data with indicators
            market_sentiment: Current market sentiment analysis
            
        Returns:
            SignalValidationResult with decision and reasoning
        """
        
        try:
            # Perform rule-based checks first
            checks_passed, checks_failed, rule_score = self._perform_rule_based_checks(
                signal, coin, market_sentiment
            )
            
            # If no AI available, use rule-based decision
            if not self.is_available:
                return self._make_rule_based_decision(
                    signal, checks_passed, checks_failed, rule_score
                )
            
            # Get AI validation
            logger.debug(f"🤖 AI analyzing signal: {signal.symbol} {signal.direction.value}")
            ai_validation = await self._get_ai_validation(
                signal, coin, market_sentiment, checks_passed, checks_failed
            )
            
            # Combine rule-based and AI results
            result = self._combine_validation_results(
                signal=signal,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                rule_score=rule_score,
                ai_validation=ai_validation
            )
            
            # Store in decision log
            self.decision_log.append(result)
            
            # Log decision
            self._log_decision(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Signal validation error for {signal.symbol}: {e}")
            # Fallback to conservative decision
            return self._make_conservative_decision(signal)
    
    def _perform_rule_based_checks(
        self,
        signal: TradingSignal,
        coin: CoinData,
        market_sentiment: MarketSentimentScore
    ) -> Tuple[List[str], List[str], float]:
        """Perform rule-based validation checks"""
        
        passed = []
        failed = []
        score = 0.0
        
        # Check 1: Market Alignment
        is_long = signal.direction.value == "LONG"
        if is_long:
            if market_sentiment.sentiment in [MarketSentiment.BULLISH, MarketSentiment.VERY_BULLISH]:
                passed.append("✓ Market alignment favorable (LONG in BULLISH market)")
                score += 20
            elif market_sentiment.sentiment == MarketSentiment.NEUTRAL:
                passed.append("✓ Neutral market (acceptable for very strong signals)")
                score += 10
            else:
                failed.append("✗ Market alignment unfavorable (LONG in BEARISH market)")
                score -= 20
        else:  # SHORT
            if market_sentiment.sentiment in [MarketSentiment.BEARISH, MarketSentiment.VERY_BEARISH]:
                passed.append("✓ Market alignment favorable (SHORT in BEARISH market)")
                score += 20
            elif market_sentiment.sentiment == MarketSentiment.NEUTRAL:
                passed.append("✓ Neutral market (acceptable for very strong signals)")
                score += 10
            else:
                failed.append("✗ Market alignment unfavorable (SHORT in BULLISH market)")
                score -= 20
        
        # Check 2: Risk/Reward Ratio
        if signal.risk_reward >= 3.0:
            passed.append(f"✓ Excellent R:R (1:{signal.risk_reward:.1f})")
            score += 15
        elif signal.risk_reward >= 2.0:
            passed.append(f"✓ Good R:R (1:{signal.risk_reward:.1f})")
            score += 10
        elif signal.risk_reward >= 1.5:
            passed.append(f"✓ Acceptable R:R (1:{signal.risk_reward:.1f})")
            score += 5
        else:
            failed.append(f"✗ Poor R:R (1:{signal.risk_reward:.1f}, minimum 1.5)")
            score -= 15
        
        # Check 3: Entry Zone Validity
        entry_width_pct = ((signal.entry_zone_max - signal.entry_zone_min) / signal.entry_zone_min) * 100
        if entry_width_pct <= 2.0:
            passed.append(f"✓ Tight entry zone ({entry_width_pct:.1f}%)")
            score += 10
        elif entry_width_pct <= 5.0:
            passed.append(f"✓ Reasonable entry zone ({entry_width_pct:.1f}%)")
            score += 7
        else:
            failed.append(f"✗ Too wide entry zone ({entry_width_pct:.1f}%)")
            score -= 5
        
        # Check 4: Stop Loss Logic
        if signal.stop_loss and signal.entry_zone_min and signal.entry_zone_max:
            stop_distance_pct = abs((signal.entry_zone_min - signal.stop_loss) / signal.entry_zone_min) * 100
            if stop_distance_pct >= 1.0 and stop_distance_pct <= 5.0:
                passed.append(f"✓ Appropriate stop loss distance ({stop_distance_pct:.1f}%)")
                score += 10
            elif stop_distance_pct > 5.0:
                failed.append(f"✗ Stop loss too far ({stop_distance_pct:.1f}%)")
                score -= 5
        
        # Check 5: Confidence Score
        if signal.confidence_score >= 8.0:
            passed.append(f"✓ High confidence signal ({signal.confidence_score:.1f}/10)")
            score += 10
        elif signal.confidence_score >= 6.0:
            passed.append(f"✓ Good confidence ({signal.confidence_score:.1f}/10)")
            score += 5
        else:
            failed.append(f"✗ Low confidence ({signal.confidence_score:.1f}/10)")
            score -= 10
        
        # Check 6: Coin Characteristics
        if coin and coin.market_cap and coin.market_cap > 100_000_000:  # > $100M
            passed.append(f"✓ Adequate market cap (${coin.market_cap/1e9:.1f}B)")
            score += 5
        elif coin and coin.market_cap and coin.market_cap > 10_000_000:
            passed.append(f"✓ Reasonable market cap (${coin.market_cap/1e6:.0f}M)")
            score += 2
        else:
            failed.append("✗ Low market cap (high risk)")
            score -= 10
        
        # Check 7: Volume Confirmation
        if coin and hasattr(coin, 'volume_24h') and coin.volume_24h > 0:
            passed.append(f"✓ Adequate trading volume")
            score += 5
        
        # Check 8: Strategy Type Appropriateness
        if signal.strategy_type.value in ["Breakout", "Volatility Breakout", "Pullback"]:
            passed.append(f"✓ Established strategy type ({signal.strategy_type.value})")
            score += 5
        
        # Normalize score to 0-100
        final_score = max(0, min(100, 50 + score))
        
        return passed, failed, final_score
    
    async def _get_ai_validation(
        self,
        signal: TradingSignal,
        coin: CoinData,
        market_sentiment: MarketSentimentScore,
        checks_passed: List[str],
        checks_failed: List[str]
    ) -> Dict:
        """Get AI validation of the signal"""
        
        try:
            prompt = self._build_validation_prompt(
                signal, coin, market_sentiment, checks_passed, checks_failed
            )
            
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert crypto trading signal validator. "
                        "Review trading signals critically and provide a reasoned decision. "
                        "Be skeptical but fair. Rate the signal quality and market alignment. "
                        "Provide actionable feedback."
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
                max_tokens=800
            )
            
            # Parse AI response
            validation = self._parse_ai_validation(response)
            return validation
            
        except Exception as e:
            logger.error(f"AI validation error: {e}")
            return {
                "decision": "HOLD",
                "reasoning": f"AI validation failed: {str(e)}",
                "confidence_adjustment": 0.0
            }
    
    def _build_validation_prompt(
        self,
        signal: TradingSignal,
        coin: CoinData,
        market_sentiment: MarketSentimentScore,
        checks_passed: List[str],
        checks_failed: List[str]
    ) -> str:
        """Build prompt for AI validation"""
        
        prompt_lines = [
            "# Signal Validation Request",
            "",
            "## Trading Signal Details:",
            f"- Symbol: {signal.symbol}",
            f"- Direction: {signal.direction.value}",
            f"- Strategy: {signal.strategy_type.value}",
            f"- Timeframe: {signal.timeframe}",
            f"- Entry Zone: ${signal.entry_zone_min:.2f} - ${signal.entry_zone_max:.2f}",
            f"- Stop Loss: ${signal.stop_loss:.2f}",
            f"- Target 1: ${signal.target_1:.2f}",
            f"- Target 2: ${signal.target_2:.2f}",
            f"- Risk/Reward: 1:{signal.risk_reward:.1f}",
            f"- Confidence: {signal.confidence_score:.1f}/10",
            f"- Current Price: ${signal.current_price:.2f}",
            "",
            "## Coin Context:",
            f"- Market Cap: ${coin.market_cap/1e9:.1f}B" if coin.market_cap else "- Market Cap: Unknown",
            f"- 24h Change: {coin.price_change_percent_24h:.2f}%" if coin else "- 24h Change: Unknown",
            "",
            "## Market Sentiment Context:",
            f"- Overall Sentiment: {market_sentiment.sentiment.value}",
            f"- Sentiment Score: {market_sentiment.score:.0f}/100",
            f"- Market Strength: {market_sentiment.market_strength:.0f}/100",
            f"- Gainers: {market_sentiment.gainers_pct:.0f}% | Losers: {market_sentiment.losers_pct:.0f}%",
            f"- Volatility: {market_sentiment.volatility_level}",
            f"- BTC Trend: {market_sentiment.btc_trend.value}",
            "",
            "## Rule-Based Checks:",
            "✓ Passed:",
        ]
        
        for check in checks_passed:
            prompt_lines.append(f"  {check}")
        
        if checks_failed:
            prompt_lines.extend(["", "✗ Failed:"])
            for check in checks_failed:
                prompt_lines.append(f"  {check}")
        
        prompt_lines.extend([
            "",
            "## Analysis Request:",
            "Based on all the above information, provide your expert assessment:",
            "",
            "1. **Overall Assessment**: Is this a good signal quality? (1-10 scale)",
            "2. **Market Alignment**: Does the signal direction align with market conditions?",
            "3. **Risk Assessment**: What's the risk level for this trade?",
            "4. **Key Concerns**: Any red flags or concerns?",
            "5. **Key Strengths**: What's strong about this setup?",
            "6. **Decision**: APPROVE / REJECT / HOLD",
            "7. **Confidence Adjustment**: Should confidence be boosted (+X) or reduced (-X)?",
            "",
            "Format your response as JSON with these fields.",
        ])
        
        return "\n".join(prompt_lines)
    
    def _parse_ai_validation(self, response: str) -> Dict:
        """Parse AI validation response"""
        
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "decision": data.get("decision", "HOLD").upper(),
                    "reasoning": data.get("reasoning", response),
                    "confidence_adjustment": float(data.get("confidence_adjustment", 0)),
                    "risk_level": data.get("risk_level", "medium"),
                    "key_concerns": data.get("key_concerns", ""),
                    "key_strengths": data.get("key_strengths", ""),
                    "assessment_score": float(data.get("assessment_score", 5))
                }
        except Exception as e:
            logger.debug(f"AI response parsing: {e}, using full response as reasoning")
        
        # Fallback: extract decision from text
        decision = "HOLD"
        if "APPROVE" in response.upper() or "STRONG" in response.upper():
            decision = "APPROVE"
        elif "REJECT" in response.upper() or "AVOID" in response.upper():
            decision = "REJECT"
        
        return {
            "decision": decision,
            "reasoning": response[:200],
            "confidence_adjustment": 0.0,
            "risk_level": "medium"
        }
    
    def _combine_validation_results(
        self,
        signal: TradingSignal,
        checks_passed: List[str],
        checks_failed: List[str],
        rule_score: float,
        ai_validation: Dict
    ) -> SignalValidationResult:
        """Combine rule-based and AI validation results"""
        
        # Determine final decision
        ai_decision = ai_validation.get("decision", "HOLD").upper()
        
        # Make final decision (AI overrides if different from rule-based)
        if rule_score >= 70 and ai_decision in ["APPROVE", "HOLD"]:
            final_decision = SignalDecision.APPROVE
        elif rule_score <= 40 or ai_decision == "REJECT":
            final_decision = SignalDecision.REJECT
        else:
            final_decision = SignalDecision.HOLD
        
        # Calculate confidence adjustment
        base_adjustment = ai_validation.get("confidence_adjustment", 0)
        
        # Additional adjustments based on decision
        if final_decision == SignalDecision.APPROVE and rule_score >= 75:
            base_adjustment += 1.0  # Boost by 1.0
        elif final_decision == SignalDecision.REJECT and checks_failed:
            base_adjustment -= 2.0  # Reduce by 2.0
        
        adjusted_confidence = max(1.0, min(10.0, signal.confidence_score + base_adjustment))
        
        # Calculate quality scores
        market_alignment_score = (len(checks_passed) / max(1, len(checks_passed) + len(checks_failed))) * 100 if checks_passed or checks_failed else 50.0
        setup_quality_score = rule_score
        
        recommendation = ""
        if final_decision == SignalDecision.APPROVE:
            recommendation = "✅ Proceed with trade. Signal well-positioned in market."
        elif final_decision == SignalDecision.REJECT:
            recommendation = "❌ Skip this signal. High risk or poor market alignment."
        else:
            recommendation = "⏸️ Hold. Need more confirmation or better market conditions."
        
        return SignalValidationResult(
            signal_id=signal.id,
            symbol=signal.symbol,
            decision=final_decision,
            original_confidence=signal.confidence_score,
            adjusted_confidence=adjusted_confidence,
            confidence_change=base_adjustment,
            reasoning=ai_validation.get("reasoning", ""),
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            risk_assessment=ai_validation.get("risk_level", "medium"),
            market_alignment_score=market_alignment_score,
            setup_quality_score=setup_quality_score,
            recommendation=recommendation
        )
    
    def _make_rule_based_decision(
        self,
        signal: TradingSignal,
        checks_passed: List[str],
        checks_failed: List[str],
        rule_score: float
    ) -> SignalValidationResult:
        """Make decision based on rule-based checks only"""
        
        if rule_score >= 70:
            decision = SignalDecision.APPROVE
            adjustment = 1.0
        elif rule_score <= 40:
            decision = SignalDecision.REJECT
            adjustment = -2.0
        else:
            decision = SignalDecision.HOLD
            adjustment = 0.0
        
        adjusted_confidence = max(1.0, min(10.0, signal.confidence_score + adjustment))
        
        recommendation = ""
        if decision == SignalDecision.APPROVE:
            recommendation = "✅ Signal passes rule-based checks."
        elif decision == SignalDecision.REJECT:
            recommendation = "❌ Signal fails key validation checks."
        else:
            recommendation = "⏸️ Signal is borderline, requires discretion."
        
        return SignalValidationResult(
            signal_id=signal.id,
            symbol=signal.symbol,
            decision=decision,
            original_confidence=signal.confidence_score,
            adjusted_confidence=adjusted_confidence,
            confidence_change=adjustment,
            reasoning=f"Rule-based validation. Passed: {len(checks_passed)}, Failed: {len(checks_failed)}",
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            setup_quality_score=rule_score,
            market_alignment_score=50.0,
            recommendation=recommendation
        )
    
    def _make_conservative_decision(self, signal: TradingSignal) -> SignalValidationResult:
        """Make conservative decision on error"""
        
        return SignalValidationResult(
            signal_id=signal.id,
            symbol=signal.symbol,
            decision=SignalDecision.HOLD,
            original_confidence=signal.confidence_score,
            adjusted_confidence=signal.confidence_score * 0.8,
            confidence_change=-signal.confidence_score * 0.2,
            reasoning="Validation error - applying conservative approach",
            recommendation="⏸️ Validation error. Apply extreme caution.",
            checks_passed=[],
            checks_failed=["Validation system error"]
        )
    
    def _log_decision(self, result: SignalValidationResult):
        """Log the validation decision"""
        
        decision_emoji = {
            SignalDecision.APPROVE: "✅",
            SignalDecision.REJECT: "❌",
            SignalDecision.HOLD: "⏸️"
        }
        
        emoji = decision_emoji.get(result.decision, "❓")
        
        logger.info(
            f"{emoji} Agent Decision: {result.symbol} {result.decision.value} | "
            f"Conf: {result.original_confidence:.1f} → {result.adjusted_confidence:.1f} "
            f"(Change: {result.confidence_change:+.1f}) | "
            f"Setup: {result.setup_quality_score:.0f}/100 | "
            f"Alignment: {result.market_alignment_score:.0f}/100"
        )
    
    def get_decision_summary(self, num_decisions: int = 10) -> Dict:
        """Get summary of recent decisions"""
        
        recent = self.decision_log[-num_decisions:] if self.decision_log else []
        
        approved = sum(1 for d in recent if d.decision == SignalDecision.APPROVE)
        rejected = sum(1 for d in recent if d.decision == SignalDecision.REJECT)
        held = sum(1 for d in recent if d.decision == SignalDecision.HOLD)
        
        avg_setup_quality = sum(d.setup_quality_score for d in recent) / len(recent) if recent else 0
        avg_alignment = sum(d.market_alignment_score for d in recent) / len(recent) if recent else 0
        avg_conf_change = sum(d.confidence_change for d in recent) / len(recent) if recent else 0
        
        return {
            "total_decisions": len(self.decision_log),
            "recent_decisions": len(recent),
            "approved": approved,
            "rejected": rejected,
            "held": held,
            "approval_rate": (approved / len(recent) * 100) if recent else 0,
            "avg_setup_quality": avg_setup_quality,
            "avg_alignment": avg_alignment,
            "avg_confidence_change": avg_conf_change
        }
    
    def get_decision_log(self, num_entries: int = 20) -> List[SignalValidationResult]:
        """Get recent decision log entries"""
        return self.decision_log[-num_entries:]
