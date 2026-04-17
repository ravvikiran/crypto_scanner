"""
AI Signal Analyzer Module
Integrates LLMs for intelligent trade signal analysis and enhancement.
AI is the PRIMARY decision-maker, rule-based logic is the fallback.
"""

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional, Any

if TYPE_CHECKING:
    from config import AIConfig
from loguru import logger

from config import get_config
from models import TradingSignal, CoinData, TrendDirection, SignalDirection
from engines.optimization_engine import TradeJournal


# ==================== AI PROVIDER INTERFACES ====================

class AIClient(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        """Send chat request and get response"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available and configured"""
        pass


class OpenAIClient(AIClient):
    """OpenAI GPT client"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("OpenAI package not installed. Run: pip install openai")
                return None
        return self._client
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        client = self._get_client()
        if not client:
            return "Error: OpenAI client not available"
        
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return f"Error: {str(e)}"


class AnthropicClient(AIClient):
    """Anthropic Claude client"""
    
    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                logger.error("Anthropic package not installed. Run: pip install anthropic")
                return None
        return self._client
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        client = self._get_client()
        if not client:
            return "Error: Anthropic client not available"
        
        try:
            # Convert messages format for Anthropic
            system_message = ""
            anthropic_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    anthropic_messages.append(msg)
            
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=anthropic_messages
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return f"Error: {str(e)}"


class GroqClient(AIClient):
    """Groq client for fast inference"""
    
    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=self.api_key)
            except ImportError:
                logger.error("Groq package not installed. Run: pip install groq")
                return None
        return self._client
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        client = self._get_client()
        if not client:
            return "Error: Groq client not available"
        
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return f"Error: {str(e)}"


class GeminiClient(AIClient):
    """Google Gemini client using new google.genai SDK"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from google.genai import Client
                self._client = Client(api_key=self.api_key)
            except ImportError:
                logger.error("google.genai package not installed. Run: pip install google-genai")
                return None
        return self._client
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        client = self._get_client()
        if not client:
            return "Error: Gemini client not available"
        
        try:
            contents = []
            for msg in messages:
                if msg["role"] == "system":
                    contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
                else:
                    contents.append({"role": msg["role"], "parts": [{"text": msg["content"]}]})
            
            response = client.models.generate(
                model=self.model,
                contents=contents,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens
                }
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"Error: {str(e)}"


class MiniMaxClient(AIClient):
    """MiniMax client (free tier available)"""
    
    def __init__(self, api_key: str, model: str = "abab6.5s-chat"):
        self.api_key = api_key
        self.model = model
        self._client = None
        self.base_url = "https://api.minimax.chat/v1"
    
    def _get_client(self):
        if self._client is None:
            try:
                import aiohttp
                self._client = aiohttp
            except ImportError:
                logger.error("aiohttp package not installed")
                return None
        return self._client
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        client = self._get_client()
        if not client:
            return "Error: MiniMax client not available"
        
        try:
            import aiohttp
            
            system_message = ""
            user_message = ""
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    user_message = msg["content"]
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/text/chatcompletion_v2",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    else:
                        error_text = await response.text()
                        return f"Error: MiniMax API returned status {response.status}: {error_text}"
        except Exception as e:
            logger.error(f"MiniMax API error: {e}")
            return f"Error: {str(e)}"


class OllamaClient(AIClient):
    """Ollama local LLM client"""
    
    def __init__(self, base_url: str, model: str = "llama3"):
        self.base_url = base_url
        self.model = model
    
    def is_available(self) -> bool:
        return bool(self.base_url)
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                # Convert messages format for Ollama
                ollama_messages = []
                system_message = ""
                for msg in messages:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    else:
                        ollama_messages.append(msg)
                
                payload = {
                    "model": self.model,
                    "messages": ollama_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False
                }
                
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("message", {}).get("content", "")
                    else:
                        return f"Error: Ollama API returned status {response.status}"
        except Exception as e:
            logger.debug(f"Cannot connect to Ollama at {self.base_url}: {e}")
            return f"Error: {str(e)}"


# ==================== AI PROVIDER MANAGER (FALLBACK) ====================

# Error patterns that indicate provider failure and should trigger fallback
FALLBACK_ERROR_PATTERNS = [
    "rate_limit",
    "Rate limit",
    "RATE_LIMIT",
    "insufficient_quota",
    "InsufficientQuota",
    "429",
    "429 Too Many Requests",
    "quota",
    "exceeded",
    "EXCEEDED",
    "limit reached",
    "LIMIT REACHED",
    "monthly quota",
    "credit balance",
    "CREDIT BALANCE",
    "credit too low",
    "low balance",
    "insufficient credits",
    "not enough credit",
    "billing",
    "BILLING",
    "upgrade",
    "UPGRADE",
    "payment required",
]


class AIProviderManager:
    """
    Manages multiple AI providers with automatic fallback.
    
    When the primary provider fails (rate limit, quota exceeded, errors),
    the system automatically tries the next available provider in priority order.
    """
    
    def __init__(self, config: "AIConfig"):
        self.config = config
        self._providers: Dict[str, AIClient] = {}
        self._current_provider: Optional[AIClient] = None
        self._current_provider_name: str = ""
        self._failed_providers: Dict[str, float] = {}  # provider -> failure timestamp
        self._failure_cooldown_seconds: float = 60.0  # Try failed provider again after 60 seconds
        
        # Initialize all available providers
        self._initialize_providers()
        
        # Set initial provider based on priority
        self._set_current_provider()
    
    def _initialize_providers(self):
        """Initialize all configured AI providers"""
        
        # OpenAI
        if self.config.openai_api_key:
            self._providers["openai"] = OpenAIClient(
                api_key=self.config.openai_api_key,
                model=self.config.openai_model
            )
            logger.info("Registered OpenAI provider")
        
        # Anthropic
        if self.config.anthropic_api_key:
            self._providers["anthropic"] = AnthropicClient(
                api_key=self.config.anthropic_api_key,
                model=self.config.anthropic_model
            )
            logger.info("Registered Anthropic provider")
        
        # Groq
        if self.config.groq_api_key:
            self._providers["groq"] = GroqClient(
                api_key=self.config.groq_api_key,
                model=self.config.groq_model
            )
            logger.info("Registered Groq provider")
        
        # Gemini
        if self.config.gemini_api_key:
            self._providers["gemini"] = GeminiClient(
                api_key=self.config.gemini_api_key,
                model=self.config.gemini_model
            )
            logger.info("Registered Gemini provider")
        
        # MiniMax
        if self.config.minimax_api_key:
            self._providers["minimax"] = MiniMaxClient(
                api_key=self.config.minimax_api_key,
                model=self.config.minimax_model
            )
            logger.info("Registered MiniMax provider")
        
        # Ollama
        if self.config.ollama_base_url:
            self._providers["ollama"] = OllamaClient(
                base_url=self.config.ollama_base_url,
                model=self.config.ollama_model
            )
            logger.info("Registered Ollama provider")
        
        logger.info(f"AI Provider Manager initialized with {len(self._providers)} providers")
    
    def _get_priority_providers(self) -> List[str]:
        """Get list of providers in priority order from config"""
        priority_str = self.config.provider_priority.lower()
        providers = [p.strip() for p in priority_str.split(",")]
        return [p for p in providers if p]  # Filter empty strings
    
    def _set_current_provider(self):
        """Set the current provider based on priority order, skipping failed ones"""
        priority_providers = self._get_priority_providers()
        current_time = time.time()
        
        for provider_name in priority_providers:
            # Skip if provider not initialized
            if provider_name not in self._providers:
                continue
            
            # Skip if provider recently failed (within cooldown period)
            if provider_name in self._failed_providers:
                failure_time = self._failed_providers[provider_name]
                if current_time - failure_time < self._failure_cooldown_seconds:
                    logger.debug(f"Skipping {provider_name} - in cooldown period")
                    continue
                else:
                    # Cooldown expired, remove from failed list
                    logger.info(f"Cooldown expired for {provider_name}, will retry")
                    del self._failed_providers[provider_name]
            
            # Check if provider is available
            provider = self._providers[provider_name]
            if provider.is_available():
                self._current_provider = provider
                self._current_provider_name = provider_name
                logger.info(f"Using AI provider: {provider_name}")
                return
        
        # No available provider found
        self._current_provider = None
        self._current_provider_name = ""
        logger.warning("No available AI providers - all providers failed or not configured")
    
    def _should_fallback(self, error_message: str) -> bool:
        """Check if error should trigger fallback to next provider"""
        if not self.config.enable_fallback:
            return False
        
        error_lower = error_message.lower()
        for pattern in FALLBACK_ERROR_PATTERNS:
            if pattern.lower() in error_lower:
                return True
        return False
    
    def _mark_provider_failed(self, provider_name: str):
        """Mark a provider as failed"""
        self._failed_providers[provider_name] = time.time()
        logger.warning(f"Marked provider '{provider_name}' as failed")
    
    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1000) -> str:
        """
        Send chat request with automatic fallback.
        If primary provider fails, tries next available provider.
        """
        if not self._providers:
            return "Error: No AI providers configured"
        
        # Try each provider in priority order
        priority_providers = self._get_priority_providers()
        tried_providers = set()
        
        while priority_providers:
            # Get next provider from priority list that we haven't tried
            provider_name = None
            for p in priority_providers:
                if p not in tried_providers:
                    provider_name = p
                    break
            
            if provider_name is None:
                break
            
            tried_providers.add(provider_name)
            
            # Check if provider is available
            if provider_name not in self._providers:
                continue
            
            # Check cooldown
            if provider_name in self._failed_providers:
                current_time = time.time()
                failure_time = self._failed_providers[provider_name]
                if current_time - failure_time < self._failure_cooldown_seconds:
                    continue
                else:
                    del self._failed_providers[provider_name]
            
            provider = self._providers[provider_name]
            if not provider.is_available():
                continue
            
            # Try to use this provider
            self._current_provider = provider
            self._current_provider_name = provider_name
            
            try:
                response = await provider.chat(messages, temperature, max_tokens)
                
                # Check if response indicates an error that should trigger fallback
                if self._should_fallback(response):
                    logger.warning(f"Provider {provider_name} returned error: {response[:100]}")
                    self._mark_provider_failed(provider_name)
                    # Try next provider
                    continue
                
                # Success! Return response
                logger.debug(f"AI request successful with provider: {provider_name}")
                return response
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Provider {provider_name} failed with error: {error_msg}")
                
                if self._should_fallback(error_msg):
                    self._mark_provider_failed(provider_name)
                    # Try next provider
                    continue
                else:
                    # Non-fallback error, return error
                    return f"Error: {error_msg}"
        
        # All providers failed
        return "Error: All AI providers failed. Please check your API keys and quotas."
    
    def get_current_provider_name(self) -> str:
        """Get the name of the currently active provider"""
        return self._current_provider_name
    
    def is_available(self) -> bool:
        """Check if any provider is available"""
        return self._current_provider is not None and self._current_provider.is_available()
    
    def get_available_providers(self) -> List[str]:
        """Get list of currently available providers (not in failed state)"""
        available = []
        current_time = time.time()
        
        for name, provider in self._providers.items():
            # Skip if in failed state and within cooldown
            if name in self._failed_providers:
                failure_time = self._failed_providers[name]
                if current_time - failure_time < self._failure_cooldown_seconds:
                    continue
            
            if provider.is_available():
                available.append(name)
        
        return available


# ==================== AI SIGNAL ANALYZER ====================

@dataclass
class AIAnalysisResult:
    """Result of AI signal analysis"""
    signal_id: str
    ai_confidence: float  # AI's own confidence 0-10
    ai_reasoning: str
    market_context: str
    risk_assessment: str
    key_levels: Dict[str, float]
    trade_recommendation: str
    timestamp: datetime = field(default_factory=datetime.now)
    journal_reference: Dict[str, Any] = field(default_factory=dict)
    ai_decision: str = "APPROVE"  # APPROVE, REJECT, MODIFY


class AICache:
    """Simple in-memory cache for AI analysis"""
    
    def __init__(self, ttl_minutes: int = 60):
        self._cache: Dict[str, tuple[str, datetime]] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
    
    def _make_key(self, signal_data: str) -> str:
        """Generate cache key from signal data"""
        return hashlib.sha256(signal_data.encode()).hexdigest()
    
    def get(self, signal_data: str) -> Optional[str]:
        """Get cached analysis"""
        key = self._make_key(signal_data)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                logger.debug(f"Cache hit for signal")
                return result
            else:
                del self._cache[key]
        return None
    
    def set(self, signal_data: str, result: str):
        """Cache analysis result"""
        key = self._make_key(signal_data)
        self._cache[key] = (result, datetime.now())
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()


class AISignalAnalyzer:
    """
    AI-powered signal analyzer that uses LLMs to:
    - Analyze market conditions
    - Validate trading signals
    - Provide enhanced reasoning
    - Assess risk
    - Generate trade recommendations
    """
    
    SYSTEM_PROMPT = """You are an expert cryptocurrency trading analyst with deep knowledge of:
- Technical analysis (price action, indicators, chart patterns)
- Market microstructure and liquidity concepts
- Risk management and position sizing
- Market psychology and sentiment
- AI-first decision making

Your role is to analyze trading signals from a crypto scanner and provide:
1. AI confidence score (0-10)
2. Enhanced reasoning with market context
3. Risk assessment
4. Key support/resistance levels
5. Trade recommendation (STRONG BUY, BUY, HOLD, SELL, STRONG SELL)
6. AI Decision: APPROVE, REJECT, or MODIFY

CRITICAL - You MUST reference the Journal Statistics provided:
- If sample_size < 20 trades → reduce confidence
- If win_rate < 40% → REJECT or downgrade
- If win_rate > 60% → boost confidence

Journal stats are MANDATORY for all decisions. If not provided, assume neutral performance.

Respond in JSON format with the following structure:
{
    "ai_confidence": <float 0-10>,
    "ai_reasoning": "<detailed explanation>",
    "market_context": "<current market conditions>",
    "risk_assessment": "<risk factors>",
    "key_levels": {"support": <float>, "resistance": <float>},
    "trade_recommendation": "<STRONG BUY|BUY|HOLD|SELL|STRONG SELL>",
    "ai_decision": "<APPROVE|REJECT|MODIFY>",
    "adjusted_entry": <float or null>,
    "adjusted_sl": <float or null>,
    "adjusted_targets": [<float>, <float> or null],
    "position_size": <float 0-100>,
    "reasoning_with_journal": "<explain how journal stats affected your decision>"
}"""

    def __init__(self):
        self.config = get_config()
        self.ai_config = self.config.ai
        self._provider_manager: Optional[AIProviderManager] = None
        self._analysis_count = 0
        self._cache = AICache(ttl_minutes=self.ai_config.cache_ttl_minutes)
        
        # Initialize the AI provider manager (with fallback support)
        self._initialize_client()
        
        # Initialize Trade Journal for journal-aware decisions
        self._journal = TradeJournal()
        
        # Fallback mode flag
        self._fallback_mode = False
        self._fallback_reason = ""
    
    def _initialize_client(self):
        """Initialize the AI provider manager with automatic fallback"""
        
        # Use the AIProviderManager which handles multiple providers with fallback
        self._provider_manager = AIProviderManager(self.ai_config)
        
        if self._provider_manager.is_available():
            current_provider = self._provider_manager.get_current_provider_name()
            available = self._provider_manager.get_available_providers()
            logger.info(f"AI Provider Manager ready. Current: {current_provider}, Available: {available}")
        else:
            logger.warning("AI Provider Manager initialized but no providers available")
            logger.warning("Please set at least one AI API key in .env")
    
    @property
    def is_available(self) -> bool:
        """Check if AI analysis is available"""
        return (
            self.ai_config.enable_ai_analysis and 
            self._provider_manager is not None and 
            self._provider_manager.is_available()
        )
    
    @property
    def current_provider(self) -> str:
        """Get the name of the current AI provider"""
        if self._provider_manager:
            return self._provider_manager.get_current_provider_name()
        return ""
    
    def _format_signal_for_ai(self, signal: TradingSignal, coin: Optional[CoinData] = None, journal_stats: Optional[Dict] = None) -> str:
        """Format trading signal data for AI analysis"""
        
        # Get key levels from coin data if available
        support = "N/A"
        resistance = "N/A"
        rsi = "N/A"
        volume_ratio = "N/A"
        
        if coin and coin.candles.get(signal.timeframe):
            candles = coin.candles[signal.timeframe]
            if len(candles) >= 20:
                recent_highs = [c.high for c in candles[-20:]]
                recent_lows = [c.low for c in candles[-20:]]
                support = f"${min(recent_lows):.4f}"
                resistance = f"${max(recent_highs):.4f}"
        
        if coin and coin.rsi:
            rsi = f"{coin.rsi:.1f}"
        
        # Format journal stats section
        journal_section = ""
        if journal_stats:
            sample_size = journal_stats.get("sample_size", 0)
            win_rate = journal_stats.get("win_rate", 0.5)
            avg_rr = journal_stats.get("avg_rr", 0)
            by_regime = journal_stats.get("by_regime", {})
            
            regime_info = ", ".join([f"{k}: {v.get('win_rate', 0)*100:.0f}%" for k, v in by_regime.items()]) if by_regime else "N/A"
            
            journal_section = f"""
JOURNAL STATISTICS (MANDATORY REFERENCE):
- Sample Size: {sample_size} trades
- Win Rate: {win_rate*100:.1f}%
- Avg RR: {avg_rr:.2f}
- Performance by Regime: {regime_info}

CRITICAL DECISION RULES:
- If sample_size < 20 → REDUCE confidence by 20%
- If win_rate < 40% → REJECT signal or reduce confidence below 5.0
- If win_rate > 60% → BOOST confidence by up to 1.0
"""
        else:
            journal_section = """
JOURNAL STATISTICS: Not available - assume neutral performance (50% win rate)
"""
        
        # Format signal data
        signal_data = f"""
TRADING SIGNAL ANALYSIS REQUEST
==============================

SYMBOL: {signal.symbol}
DIRECTION: {signal.direction.value}
STRATEGY: {signal.strategy_type.value}
TIMEFRAME: {signal.timeframe}

PRICE DATA:
- Current Price: ${signal.current_price:.4f}
- Entry Zone: ${signal.entry_zone_min:.4f} - ${signal.entry_zone_max:.4f}
- Stop Loss: ${signal.stop_loss:.4f}
- Target 1: ${signal.target_1:.4f}
- Target 2: ${signal.target_2:.4f}

RISK/REWARD: 1:{signal.risk_reward:.1f}
CONFIDENCE SCORE: {signal.confidence_score:.1f}/10

TECHNICAL INDICATORS:
- Trend Alignment: {'Yes' if signal.trend_alignment else 'No'}
- Volume Confirmation: {'Yes' if signal.volume_confirmation else 'No'}
- BTC Alignment: {'Yes' if signal.btc_alignment else 'No'}
- Volatility Expansion: {'Yes' if signal.volatility_expansion else 'No'}
- Liquidity Sweep: {'Yes' if signal.liquidity_sweep else 'No'}

BTC TREND: {signal.btc_trend.value}

ORIGINAL REASONING: {signal.reasoning}

KEY LEVELS (from chart):
- Support: {support}
- Resistance: {resistance}
- RSI: {rsi}
{journal_section}

Analyze this signal and provide your assessment with MANDATORY reference to journal stats.
"""
        return signal_data
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse AI JSON response"""
        import re
        
        # Try to extract JSON from response
        try:
            # Find JSON block
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "ai_confidence": float(data.get("ai_confidence", 5.0)),
                    "ai_reasoning": data.get("ai_reasoning", ""),
                    "market_context": data.get("market_context", ""),
                    "risk_assessment": data.get("risk_assessment", ""),
                    "key_levels": data.get("key_levels", {}),
                    "trade_recommendation": data.get("trade_recommendation", "HOLD"),
                    "ai_decision": data.get("ai_decision", "APPROVE"),
                    "adjusted_entry": data.get("adjusted_entry"),
                    "adjusted_sl": data.get("adjusted_sl"),
                    "adjusted_targets": data.get("adjusted_targets", []),
                    "position_size": data.get("position_size", 100),
                    "reasoning_with_journal": data.get("reasoning_with_journal", "")
                }
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
        
        # Fallback parsing
        return {
            "ai_confidence": 5.0,
            "ai_reasoning": response[:500] if response else "No analysis available",
            "market_context": "",
            "risk_assessment": "",
            "key_levels": {},
            "trade_recommendation": "HOLD",
            "ai_decision": "APPROVE",
            "adjusted_entry": None,
            "adjusted_sl": None,
            "adjusted_targets": [],
            "position_size": 100,
            "reasoning_with_journal": ""
        }
    
    async def analyze_signal(self, signal: TradingSignal, coin: Optional[CoinData] = None, market_regime: str = "NEUTRAL") -> Optional[AIAnalysisResult]:
        """Analyze a trading signal with AI (Primary decision maker)"""
        
        # Check if AI is available
        if not self.is_available:
            logger.debug("AI analysis not available - falling back to rule-based")
            self._fallback_mode = True
            self._fallback_reason = "AI provider not available"
            return None
        
        # Check rate limiting
        if self._analysis_count >= self.ai_config.max_ai_calls_per_scan:
            logger.warning(f"Max AI calls per scan reached ({self.ai_config.max_ai_calls_per_scan})")
            return None
        
        # Get journal stats for this strategy/symbol/timeframe
        journal_stats = self._journal.get_journal_stats(
            strategy=signal.strategy_type.value,
            symbol=signal.symbol,
            timeframe=signal.timeframe
        )
        
        # Check cache first (include journal in cache key)
        signal_data = self._format_signal_for_ai(signal, coin, journal_stats)
        
        if self.ai_config.cache_analysis:
            cached = self._cache.get(signal_data)
            if cached:
                parsed = self._parse_ai_response(cached)
                return AIAnalysisResult(
                    signal_id=signal.id,
                    ai_confidence=parsed["ai_confidence"],
                    ai_reasoning=parsed["ai_reasoning"],
                    market_context=parsed["market_context"],
                    risk_assessment=parsed["risk_assessment"],
                    key_levels=parsed["key_levels"],
                    trade_recommendation=parsed["trade_recommendation"],
                    journal_reference=journal_stats,
                    ai_decision=parsed.get("ai_decision", "APPROVE")
                )
        
        # Prepare messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": signal_data}
        ]
        
        try:
            # Make API call with timeout (using provider manager for automatic fallback)
            response = await asyncio.wait_for(
                self._provider_manager.chat(
                    messages=messages,
                    temperature=self.ai_config.ai_temperature,
                    max_tokens=self.ai_config.ai_max_tokens
                ),
                timeout=self.ai_config.ai_timeout_seconds
            )
            
            self._analysis_count += 1
            
            # Cache result
            if self.ai_config.cache_analysis:
                self._cache.set(signal_data, response)
            
            # Parse response
            parsed = self._parse_ai_response(response)
            
            current_provider = self._provider_manager.get_current_provider_name()
            ai_decision = parsed.get("ai_decision", "APPROVE")
            logger.info(f"AI analyzed {signal.symbol} using {current_provider}: {parsed['trade_recommendation']} | Decision: {ai_decision} (confidence: {parsed['ai_confidence']}/10)")
            
            return AIAnalysisResult(
                signal_id=signal.id,
                ai_confidence=parsed["ai_confidence"],
                ai_reasoning=parsed["ai_reasoning"],
                market_context=parsed["market_context"],
                risk_assessment=parsed["risk_assessment"],
                key_levels=parsed["key_levels"],
                trade_recommendation=parsed["trade_recommendation"],
                journal_reference=journal_stats,
                ai_decision=ai_decision
            )
            
        except asyncio.TimeoutError:
            logger.error(f"AI request timeout for {signal.symbol} - using fallback")
            self._fallback_mode = True
            self._fallback_reason = "AI request timeout"
            return None
        except Exception as e:
            logger.error(f"AI analysis error for {signal.symbol}: {e} - using fallback")
            self._fallback_mode = True
            self._fallback_reason = str(e)
            return None
    
    async def analyze_signals_batch(self, signals: List[TradingSignal], coins: Dict[str, CoinData]) -> List[AIAnalysisResult]:
        """Analyze multiple signals with AI"""
        
        if not self.is_available:
            logger.warning("AI analysis not available")
            return []
        
        results = []
        
        # Limit to max AI calls
        signals_to_analyze = signals[:self.ai_config.max_ai_calls_per_scan]
        
        logger.info(f"Starting AI analysis for {len(signals_to_analyze)} signals...")
        
        for signal in signals_to_analyze:
            coin = coins.get(signal.symbol)
            result = await self.analyze_signal(signal, coin)
            if result:
                results.append(result)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        return results
    
    def apply_ai_enhancements(self, signals: List[TradingSignal], ai_results: List[AIAnalysisResult]) -> List[TradingSignal]:
        """Apply AI analysis results to trading signals (AI-first, rules fallback)
        
        PRD AI Decision Engine Rules:
        - AI cannot override low score signals (<60)
        - AI filters borderline trades (60-70)
        - Only signals with score 70+ are sent to AI
        """
        
        # Create lookup for AI results
        result_map = {r.signal_id: r for r in ai_results}
        
        enhanced_signals = []
        
        for signal in signals:
            ai_result = result_map.get(signal.id)
            
            if ai_result:
                # Get normalized confidence score (0-100)
                original_score = signal.normalized_confidence
                
                # PRD Rule: AI cannot override if score < 60 (REJECT zone)
                if original_score < 60:
                    logger.info(f"PRD Rule: AI cannot override low score signal {signal.symbol} (score: {original_score:.0f})")
                    signal.score_breakdown["ai_filtered"] = "REJECT_ZONE"
                    continue
                
                # PRD Rule: AI filters borderline (60-70) signals more strictly
                borderline = 60 <= original_score <= 70
                if borderline:
                    logger.info(f"PRD: Borderline signal {signal.symbol} (score: {original_score:.0f}) - AI extra filtering")
                
                # Check AI decision (APPROVE, REJECT, MODIFY)
                ai_decision = getattr(ai_result, 'ai_decision', 'APPROVE')
                
                # Apply REJECT decision - skip the signal
                if ai_decision == 'REJECT':
                    logger.info(f"AI REJECTED signal {signal.symbol} - removing from results")
                    signal.score_breakdown["ai_rejected"] = True
                    continue
                
                # For borderline signals, apply stricter standards
                if borderline and ai_decision == 'APPROVE':
                    # Check if AI confidence is high enough
                    if ai_result.ai_confidence < 7.0:
                        logger.info(f"Borderline signal {signal.symbol} rejected by AI (conf: {ai_result.ai_confidence:.1f})")
                        continue
                
                # Enhance signal with AI analysis
                # Combine original confidence with AI confidence (weighted average)
                original_confidence = signal.confidence_score
                ai_confidence = ai_result.ai_confidence
                
                # Weight: 40% original, 60% AI
                enhanced_confidence = (original_confidence * 0.4) + (ai_confidence * 0.6)
                signal.confidence_score = min(enhanced_confidence, 10.0)
                
                # Apply MODIFY decision - adjust entry/SL/targets
                if ai_decision == 'MODIFY':
                    if ai_result.key_levels:
                        if "adjusted_entry" in dir(ai_result) and ai_result.get("adjusted_entry"):
                            signal.entry_zone_min = ai_result["adjusted_entry"]
                        if "adjusted_sl" in dir(ai_result) and ai_result.get("adjusted_sl"):
                            signal.stop_loss = ai_result["adjusted_sl"]
                    logger.info(f"AI MODIFIED signal {signal.symbol}")
                
                # Enhance reasoning
                journal_ref = ai_result.journal_reference if hasattr(ai_result, 'journal_reference') else {}
                journal_info = ""
                if journal_ref:
                    sample_size = journal_ref.get("sample_size", 0)
                    win_rate = journal_ref.get("win_rate", 0)
                    journal_info = f"\n📓 Journal: {sample_size} trades, {win_rate*100:.0f}% win rate"
                
                # Add PRD classification
                prd_class = signal.score_breakdown.get("classification", "UNKNOWN")
                
                enhanced_reasoning = f"{signal.reasoning}\n\n🧠 PRD Class: {prd_class}\n"
                enhanced_reasoning += f"🧠 AI Decision: {ai_decision}\n"
                enhanced_reasoning += f"🧠 AI Analysis: {ai_result.ai_reasoning}\n"
                enhanced_reasoning += f"📊 Market Context: {ai_result.market_context}\n"
                enhanced_reasoning += f"⚠️ Risk Assessment: {ai_result.risk_assessment}\n"
                enhanced_reasoning += f"🎯 Recommendation: {ai_result.trade_recommendation}{journal_info}"
                
                signal.reasoning = enhanced_reasoning
                
                # Update key levels if available
                if ai_result.key_levels:
                    if "support" in ai_result.key_levels:
                        # Could update signal with AI-identified levels
                        pass
                
                # Mark as AI-enhanced
                signal.score_breakdown["ai_enhanced"] = ai_result.ai_confidence
                signal.score_breakdown["ai_decision"] = ai_decision
                signal.score_breakdown["journal_win_rate"] = journal_ref.get("win_rate", 0.5)
            
            enhanced_signals.append(signal)
        
        return enhanced_signals
    
    def reset_analysis_count(self):
        """Reset the analysis count for a new scan"""
        self._analysis_count = 0
    
    def clear_cache(self):
        """Clear the AI cache"""
        self._cache.clear()
        logger.info("AI cache cleared")


# ==================== AI SIGNAL GENERATOR ====================

class AISignalGenerator:
    """
    Generate new trading signals using AI analysis of market data.
    This goes beyond enhancing existing signals - it can identify opportunities
    that the rule-based systems might miss.
    """
    
    SYSTEM_PROMPT = """You are an expert crypto trading analyst AI. Your task is to analyze
market data and identify high-probability trading opportunities.

Analyze the provided market data and identify:
1. Trend direction (BULLISH, BEARISH, NEUTRAL)
2. Best entry zones
3. Stop loss levels
4. Take profit targets
5. Risk/reward ratio

Return your analysis as a structured signal if a high-confidence setup is found.
Otherwise, return NO_SIGNAL.

Output JSON format:
{
    "signal_found": true/false,
    "direction": "LONG/SHORT",
    "entry_min": <float>,
    "entry_max": <float>,
    "stop_loss": <float>,
    "target_1": <float>,
    "target_2": <float>,
    "risk_reward": <float>,
    "confidence": <float 0-10>,
    "reasoning": "<explanation>",
    "strategy_type": "<Trend Continuation|Bearish Short|Liquidity Sweep|Volatility Breakout>"
}
"""

    def __init__(self):
        self.config = get_config()
        self.ai_config = self.config.ai
        self._provider_manager = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the AI provider manager with fallback support"""
        self._provider_manager = AIProviderManager(self.ai_config)
        if self._provider_manager.is_available():
            logger.info(f"AISignalGenerator ready with provider: {self._provider_manager.get_current_provider_name()}")
    
    @property
    def is_available(self) -> bool:
        return (
            self.ai_config.enable_ai_analysis and 
            self._provider_manager is not None and 
            self._provider_manager.is_available()
        )
    
    def _format_market_data(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str) -> str:
        """Format coin market data for AI analysis"""
        
        candles = coin.candles.get(timeframe, [])
        
        # Get recent price data
        recent_candles = candles[-10:] if len(candles) >= 10 else candles
        
        price_data = []
        for c in recent_candles:
            trend_emoji = "🟢" if c.is_bullish else "🔴"
            price_data.append(f"{trend_emoji} O:${c.open:.4f} H:${c.high:.4f} L:${c.low:.4f} C:${c.close:.4f} V:{c.volume:.0f}")
        
        data_str = "\n".join(price_data)
        
        ema20_str = f"${coin.ema_20:.4f}" if coin.ema_20 else "N/A"
        ema50_str = f"${coin.ema_50:.4f}" if coin.ema_50 else "N/A"
        ema100_str = f"${coin.ema_100:.4f}" if coin.ema_100 else "N/A"
        ema200_str = f"${coin.ema_200:.4f}" if coin.ema_200 else "N/A"
        rsi_str = f"{coin.rsi:.1f}" if coin.rsi else "N/A"
        atr_str = f"{coin.atr:.4f}" if coin.atr else "N/A"
        
        bb_upper_str = f"${coin.bb_upper:.4f}" if coin.bb_upper else "N/A"
        bb_middle_str = f"${coin.bb_middle:.4f}" if coin.bb_middle else "N/A"
        bb_lower_str = f"${coin.bb_lower:.4f}" if coin.bb_lower else "N/A"
        
        market_data = f"""
CRYPTO MARKET ANALYSIS
=====================

SYMBOL: {coin.symbol} ({coin.name})
CURRENT PRICE: ${coin.current_price:.4f}
24H CHANGE: {coin.price_change_percent_24h:.2f}%

TECHNICAL INDICATORS:
- EMA20: {ema20_str}
- EMA50: {ema50_str}
- EMA100: {ema100_str}
- EMA200: {ema200_str}
- RSI (14): {rsi_str}
- ATR: {atr_str}

BOLLINGER BANDS:
- Upper: {bb_upper_str}
- Middle: {bb_middle_str}
- Lower: {bb_lower_str}

TREND: {coin.trend.value}
BTC TREND: {btc_trend.value}

RECENT PRICE ACTION (last 10 candles):
{data_str}

Analyze this data and identify any high-probability trading opportunities.
Return NO_SIGNAL if no clear setup exists.
"""
        return market_data
    
    async def generate_signal(self, coin: CoinData, btc_trend: TrendDirection, timeframe: str = "4h") -> Optional[TradingSignal]:
        """Generate a trading signal using AI analysis"""
        
        if not self.is_available:
            return None
        
        try:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": self._format_market_data(coin, btc_trend, timeframe)}
            ]
            
            response = await asyncio.wait_for(
                self._provider_manager.chat(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=800
                ),
                timeout=self.ai_config.ai_timeout_seconds
            )
            
            # Parse response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            
            if not json_match:
                return None
            
            data = json.loads(json_match.group())
            
            if not data.get("signal_found", False):
                return None
            
            # Create trading signal from AI response
            direction = SignalDirection.LONG if data.get("direction") == "LONG" else SignalDirection.SHORT
            
            # Map strategy type
            strategy_map = {
                "Trend Continuation": "Trend Continuation",
                "Bearish Short": "Bearish Trend Short",
                "Liquidity Sweep": "Liquidity Sweep Reversal",
                "Volatility Breakout": "Volatility Breakout"
            }
            strategy_type = data.get("strategy_type", "Trend Continuation")
            
            signal = TradingSignal(
                symbol=coin.symbol,
                name=coin.name,
                direction=direction,
                strategy_type=strategy_type,
                timeframe=timeframe,
                entry_zone_min=float(data.get("entry_min", 0)),
                entry_zone_max=float(data.get("entry_max", 0)),
                stop_loss=float(data.get("stop_loss", 0)),
                target_1=float(data.get("target_1", 0)),
                target_2=float(data.get("target_2", 0)),
                risk_reward=float(data.get("risk_reward", 0)),
                confidence_score=float(data.get("confidence", 5)),
                current_price=coin.current_price,
                btc_trend=btc_trend,
                reasoning=f"🤖 AI GENERATED SIGNAL:\n{data.get('reasoning', '')}"
            )
            
            logger.info(f"AI generated signal for {coin.symbol}: {direction.value} ({strategy_type})")
            return signal
            
        except Exception as e:
            logger.error(f"AI signal generation error for {coin.symbol}: {e}")
            return None


# Import signal validation agent
from .signal_validation_agent import AISignalValidationAgent, SignalValidationResult, SignalDecision
