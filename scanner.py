"""
Crypto Scanner - Main Orchestrator
Coordinates all modules to scan markets and generate trading signals.
Enhanced with AI-first architecture and adaptive engines.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from loguru import logger

from config import get_config
from models import TradingSignal, MarketSummary, TrendDirection, SignalDirection, CoinData
from collectors import MarketDataCollector
from indicators import IndicatorEngine
from strategies import StrategyEngine
from scorer import SignalScorer
from filters import BitcoinFilter
from alerts import AlertManager
from dashboard import Dashboard
from storage import PerformanceTracker
from ai import AISignalAnalyzer, AISignalGenerator, AISignalValidationAgent
from ai.market_sentiment_analyzer import AIMarketSentimentAnalyzer, MarketSentimentMonitor
from reasoning import HybridReasoner
from learning import SignalTracker, AccuracyScorer, ResolutionChecker, LearningEngine, TradeJournal, SelfAdaptationEngine
from engines import (
    MarketRegimeEngine, MarketRegime,
    MarketSentimentEngine, MarketSentiment,
    MarketTrendAlertEngine,
    CoinFilterEngine,
    ConfluenceEngine,
    PositionSizerEngine,
    OptimizationEngine,
    RiskManagementEngine
)
from strategies.prd_signal_engine import PRDSignalEngine


class CryptoScanner:
    """Main scanner orchestrator"""
    
    def __init__(self):
        self.config = get_config()
        
        # Initialize modules
        self.collector: Optional[MarketDataCollector] = None
        self.indicator_engine = IndicatorEngine()
        self.strategy_engine = StrategyEngine()
        self.scorer = SignalScorer()
        self.btc_filter = BitcoinFilter()
        self.alert_manager = AlertManager()
        self.dashboard = Dashboard()
        self.tracker = PerformanceTracker()
        
        # Initialize AI modules
        self.ai_analyzer = AISignalAnalyzer()
        self.ai_generator = AISignalGenerator()
        self.hybrid_reasoner = HybridReasoner()
        
        # Initialize Learning System (Phase 4)
        self.signal_tracker = SignalTracker(self.config)
        self.accuracy_scorer = AccuracyScorer(self.config)
        self.resolution_checker = ResolutionChecker(
            self.config,
            self.signal_tracker,
            self.accuracy_scorer
        )
        self.learning_engine = LearningEngine(self.config, self.accuracy_scorer)
        self.trade_journal = TradeJournal(self.config)
        self.self_adaptation = SelfAdaptationEngine(self.config)
        
        # Initialize NEW Enhanced Engines
        self.market_regime_engine = MarketRegimeEngine()
        self.market_sentiment_engine = MarketSentimentEngine()
        self.ai_sentiment_analyzer = AIMarketSentimentAnalyzer()
        self.sentiment_monitor = MarketSentimentMonitor()
        self.trend_alert_engine = MarketTrendAlertEngine()
        self.signal_validation_agent = AISignalValidationAgent()
        self.coin_filter_engine = CoinFilterEngine()
        self.confluence_engine = ConfluenceEngine()
        self.position_sizer = PositionSizerEngine()
        self.optimization_engine = OptimizationEngine()
        
        # PRD: Risk Management Engine
        self.risk_engine = RiskManagementEngine()
        
        # Initialize PRD Signal Engine
        self.prd_engine = PRDSignalEngine()
        
        # Store coins for AI analysis
        self._coins_cache: Dict[str, CoinData] = {}
        
        # State
        self.is_running = False
        self.last_scan_time: Optional[datetime] = None
        self.last_signals: List[TradingSignal] = []
        self.current_market_regime = MarketRegime.RANGING
        self.current_market_sentiment = None  # Store latest market sentiment
        self.last_trend_alerts: List = []  # Store latest trend alerts
        
        # Configure logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_file = Path(self.config.logging.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            rotation="10 MB",
            retention="7 days",
            level=self.config.logging.log_level
        )
        logger.info("Crypto Scanner initialized")
    
    async def run_scan(self) -> List[TradingSignal]:
        """Execute a complete market scan with enhanced flow"""
        
        scan_start = time.time()
        all_signals = []
        
        logger.info("=" * 60)
        logger.info("🔍 Starting Enhanced Market Scan")
        logger.info("=" * 60)
        
        try:
            # Step 1: Get Bitcoin trend first
            btc_trend = await self._get_btc_trend()
            
            # NEW: Step 1b - Detect Market Regime using new engine
            btc_coin_data = None
            async with MarketDataCollector() as temp_collector:
                btc_candles = await temp_collector.get_candles("BTC", "4h")
                if btc_candles and len(btc_candles) >= 50:
                    from models import CoinData
                    btc_coin_data = CoinData(
                        symbol="BTC",
                        name="Bitcoin",
                        current_price=btc_candles[-1].close,
                        market_cap=0,
                        volume_24h=0,
                        price_change_24h=0,
                        price_change_percent_24h=0
                    )
                    btc_coin_data.candles["4h"] = btc_candles
                    btc_coin_data = self.indicator_engine.calculate_all_indicators(btc_coin_data, "4h")
            
            if btc_coin_data:
                self.current_market_regime = self.market_regime_engine.detect_regime(btc_coin_data, "4h")
                regime_str = self.current_market_regime.value
                logger.info(f"📊 Market Regime: {regime_str}")
            else:
                self.current_market_regime = MarketRegime.RANGING
                regime_str = "RANGING"
            
            # Legacy market regime for compatibility
            market_regime = self.btc_filter.get_market_regime(btc_trend)
            
            # Step 2: Get top coins
            coins = await self._get_top_coins()
            
            # NEW: Step 2a - Analyze Market Sentiment (before processing coins)
            logger.info("=" * 60)
            logger.info("📈 Analyzing Market Sentiment...")
            logger.info("=" * 60)
            
            if not coins:
                logger.warning("No coins fetched")
                return []
            
            # NEW: Step 2b - Filter coins using new engine
            coins = self.coin_filter_engine.filter_coins(coins, max_coins=150)
            coins = self.coin_filter_engine.filter_by_strength(coins, btc_coin_data, min_strength=-0.5, max_coins=100)
            logger.info(f"Filtered to {len(coins)} strong coins")
            
            # Step 3: Get candles for all coins
            logger.info(f"Fetching candles for {len(coins)} coins...")
            coins = await self._fetch_candles(coins)
            
            # Step 3b: Fetch multi-timeframe data for MTF strategy (if enabled)
            mtf_signals = []
            if getattr(self.config.scanner, 'enable_mtf_strategy', True):
                mtf_tfs = getattr(self.config.scanner, 'mtf_timeframes', ['daily', '1h', '15m'])
                mtf_min_confidence = getattr(self.config.scanner, 'mtf_min_confidence', 7.0)
                logger.info(f"Fetching MTF data for: {mtf_tfs}...")
                
                # Fetch additional timeframes for MTF strategy with proper async context
                async with MarketDataCollector() as mtf_collector:
                    # Update coins with MTF data - fetch with rate limiting
                    fetch_tasks = []
                    for coin in coins:
                        for tf in mtf_tfs:
                            if tf not in coin.candles or len(coin.candles.get(tf, [])) < 50:
                                fetch_tasks.append((coin, tf, mtf_collector.get_candles(coin.symbol, tf)))
                    
                    # Execute fetches with rate limiting (max 15 concurrent)
                    if fetch_tasks:
                        logger.info(f"Fetching {len(fetch_tasks)} MTF data points with rate limiting...")
                        semaphore = asyncio.Semaphore(15)
                        
                        async def bounded_fetch(coro):
                            async with semaphore:
                                return await coro
                        
                        bounded_tasks = [bounded_fetch(task[2]) for task in fetch_tasks]
                        results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
                        
                        for i, (coin, tf, _) in enumerate(fetch_tasks):
                            result = results[i]
                            if isinstance(result, Exception):
                                logger.warning(f"Failed to fetch {coin.symbol} {tf}: {result}")
                            elif result:
                                coin.candles[tf] = result
                
                # Run MTF strategy on each coin
                logger.info("Running Multi-Timeframe Strategy Engine...")
                for coin in coins:
                    mtf_results = self.strategy_engine.scan_mtf_strategies(coin)
                    for signal in mtf_results:
                        # Filter by MTF confidence threshold
                        if signal.confidence_score < mtf_min_confidence:
                            logger.debug(f"{signal.symbol}: MTF signal below confidence threshold ({signal.confidence_score:.1f} < {mtf_min_confidence})")
                            continue
                        
                        # Score and enrich MTF signals
                        signal = self.scorer.enrich_with_btc_alignment(signal, btc_trend)
                        signal = self.scorer.score_signal(signal)
                        mtf_signals.append(signal)
                
                logger.info(f"MTF Strategy: {len(mtf_signals)} signals generated")
            
            # NEW: Step 3c - Market Sentiment Analysis (using all coins data)
            logger.info("=" * 60)
            logger.info("🎯 Market Sentiment Analysis...")
            logger.info("=" * 60)
            
            # Calculate market sentiment
            try:
                market_sentiment_score = self.market_sentiment_engine.analyze_market_sentiment(
                    btc_coin=btc_coin_data,
                    all_coins=coins
                )
                self.current_market_sentiment = market_sentiment_score
                
                # Log sentiment details
                logger.info(f"Market Sentiment: {market_sentiment_score.sentiment.value}")
                logger.info(f"  Score: {market_sentiment_score.score:.1f}/100")
                logger.info(f"  Gainers: {market_sentiment_score.gainers_pct:.1f}% | Losers: {market_sentiment_score.losers_pct:.1f}%")
                logger.info(f"  Market Strength: {market_sentiment_score.market_strength:.1f}/100")
                logger.info(f"  Altcoin Strength: {market_sentiment_score.altcoin_strength:.1f}/100")
                logger.info(f"  Volatility: {market_sentiment_score.volatility_level}")
                logger.info(f"  Reason: {market_sentiment_score.reason}")
                
                # Try to get AI-powered insights if available
                if self.ai_sentiment_analyzer.is_available:
                    logger.info("Getting AI market insights...")
                    try:
                        # Get top gainers and losers for AI analysis
                        sorted_coins = sorted(coins, key=lambda c: c.price_change_percent_24h, reverse=True)
                        top_gainers = sorted_coins[:5] if len(sorted_coins) > 5 else sorted_coins
                        top_losers = sorted(coins, key=lambda c: c.price_change_percent_24h)[:5]
                        
                        ai_insights = await self.ai_sentiment_analyzer.analyze_sentiment_with_ai(
                            sentiment_score=market_sentiment_score,
                            btc_coin=btc_coin_data,
                            top_gainers=top_gainers,
                            top_losers=top_losers
                        )
                        
                        logger.info(f"🤖 AI Market Insight: {ai_insights.get('insight', 'N/A')[:100]}...")
                        logger.info(f"   Risk Level: {ai_insights.get('risk_level', 'unknown').upper()}")
                        logger.info(f"   Recommendation: {ai_insights.get('recommendation', 'Monitor')}")
                        
                        market_sentiment_score.ai_insights = ai_insights
                    except Exception as e:
                        logger.debug(f"AI sentiment analysis failed: {e}")
                
                # Check for sentiment shifts
                sentiment_shift = self.sentiment_monitor.check_sentiment_shift(market_sentiment_score)
                if sentiment_shift:
                    logger.warning(sentiment_shift)
                    # Could send alert about sentiment shift if needed
                
                # NEW: Check for Market Trend Alerts (BULLISH/BEARISH entries)
                logger.info("Checking for market trend alerts...")
                trend_alerts = self.trend_alert_engine.check_trend_alerts(market_sentiment_score)
                
                if trend_alerts:
                    logger.warning("=" * 60)
                    logger.warning("🚨 MARKET TREND ALERTS DETECTED")
                    logger.warning("=" * 60)
                    
                    for alert in trend_alerts:
                        logger.warning(f"{alert.alert_type.value}: {alert.message}")
                    
                    self.last_trend_alerts = trend_alerts
                    # Send trend alerts via alert manager
                    self.alert_manager.send_trend_alerts(trend_alerts)
                    
            except Exception as e:
                logger.error(f"Market sentiment analysis failed: {e}")
                self.current_market_sentiment = None
            
            # Step 4: Calculate indicators and run strategies
            logger.info("Running strategy engines...")
            
            # Filter out stablecoins
            stablecoins = ["USDT", "USDC", "DAI", "BUSD", "USDS", "USD1", "USDG", "USDF", "TUSD", "USDD", "FRAX", "USDE"]
            coins = [c for c in coins if c.symbol not in stablecoins]
            
            logger.info(f"Scanning {len(coins)} coins for signals...")
            
            for coin in coins:
                # Calculate indicators for primary timeframe
                primary_tf = self.config.scanner.timeframes[0] if self.config.scanner.timeframes else "1h"
                coin = self.indicator_engine.calculate_all_indicators(coin, primary_tf)
                
                # Run all strategy engines
                signals = self.strategy_engine.scan_all_strategies(coin, btc_trend, primary_tf)
                if signals:
                    logger.info(f"{coin.symbol}: Generated {len(signals)} signals on {primary_tf}")
                
                # Score and enrich signals
                for signal in signals:
                    signal = self.scorer.enrich_with_btc_alignment(signal, btc_trend)
                    signal = self.scorer.score_signal(signal)
                    all_signals.append(signal)
                
                # Also check other timeframes
                for tf in self.config.scanner.timeframes[1:]:
                    coin_tf = self.indicator_engine.calculate_all_indicators(coin, tf)
                    signals = self.strategy_engine.scan_all_strategies(coin_tf, btc_trend, tf)
                    
                    for signal in signals:
                        signal = self.scorer.enrich_with_btc_alignment(signal, btc_trend)
                        signal = self.scorer.score_signal(signal)
                        all_signals.append(signal)
            
            # Step 3c: Merge MTF signals with all signals
            if mtf_signals:
                all_signals.extend(mtf_signals)
                logger.info(f"Combined signals: {len(all_signals)} (including {len(mtf_signals)} MTF)")
            
            # Step 3d: Run PRD Signal Engine (if enabled)
            if getattr(self.config.scanner, 'enable_prd_strategy', True):
                prd_timeframes = getattr(self.config.scanner, 'prd_timeframes', ['4h', 'daily'])
                prd_min_confidence = getattr(self.config.scanner, 'prd_min_confidence', 70.0)
                
                logger.info(f"Running PRD Signal Engine for: {prd_timeframes}...")
                
                for coin in coins:
                    for tf in prd_timeframes:
                        # Calculate indicators for this timeframe
                        coin_tf = self.indicator_engine.calculate_all_indicators(coin, tf)
                        
                        # Scan for PRD signals
                        prd_signals = self.prd_engine.scan_all_prd_signals(coin_tf, tf)
                        
                        for signal in prd_signals:
                            # Filter by confidence threshold
                            if signal.ai_confidence_score < prd_min_confidence:
                                continue
                            
                            # Filter by risk/reward
                            if signal.risk_reward < self.prd_engine.min_risk_reward:
                                continue
                            
                            # Enrich with BTC alignment
                            signal = self.scorer.enrich_with_btc_alignment(signal, btc_trend)
                            all_signals.append(signal)
                
                logger.info(f"PRD signals: {len([s for s in all_signals if s.strategy_type.value in ['Breakout', 'Pullback']])}")
            
            # Step 5: Filter signals by BTC trend
            all_signals = self.btc_filter.filter_signals_by_btc(all_signals, btc_trend)
            
            # NEW: Step 5b - Apply Confluence Scoring
            logger.info("📊 Applying Confluence Scoring...")
            coins_dict = {c.symbol: c for c in coins}
            for signal in all_signals:
                coin = coins_dict.get(signal.symbol)
                if coin:
                    confluence_score, _ = self.confluence_engine.calculate_confluence(
                        signal, coin, btc_trend, regime_str
                    )
                    signal.score_breakdown["confluence_score"] = confluence_score
            
            # Step 6: Filter by minimum score
            qualified_signals = self.scorer.filter_signals(all_signals)
            
            # NEW: Step 6b - Apply Confluence Filter
            qualified_signals = self.confluence_engine.apply_confluence_filter(qualified_signals, min_confluence=6.0)
            
            # PRD: Step 6c - Apply Risk Management Check
            logger.info("📊 Running PRD Risk Management checks...")
            risk_filtered = []
            for signal in qualified_signals:
                # Use normalized confidence (0-100 scale)
                signal_score = signal.normalized_confidence
                
                can_take, reason = self.risk_engine.should_take_signal(signal_score)
                signal.score_breakdown["risk_check"] = reason
                
                if can_take:
                    risk_filtered.append(signal)
                else:
                    logger.debug(f"Risk rejected: {signal.symbol} - {reason}")
            
            qualified_signals = risk_filtered
            logger.info(f"Risk management: {len(qualified_signals)} signals passed")
            
            # Step 7: Filter by minimum risk/reward (3R or higher)
            min_r = 3.0
            qualified_signals = [s for s in qualified_signals if s.risk_reward >= min_r]
            
            # NEW: Step 7b - Check Optimization Engine for strategy weights
            for signal in qualified_signals:
                should_take, reason = self.optimization_engine.should_take_trade(
                    signal.strategy_type.value,
                    signal.confidence_score,
                    regime_str
                )
                signal.score_breakdown["optimization_check"] = reason
                if not should_take:
                    signal.confidence_score *= 0.5
            
            # NEW: Step 7c - Apply Self-Adaptation based on historical performance
            if self.config.learning.enable_learning:
                # Combine both automated signal outcomes and manual journal trades
                all_outcomes = self.accuracy_scorer._outcomes.copy()
                all_outcomes.extend(self.trade_journal.get_outcomes())
                if len(all_outcomes) >= 5:
                    for signal in qualified_signals:
                        original_conf = signal.confidence_score
                        adapted_conf = self.self_adaptation.apply_adaptations(
                            signal.confidence_score,
                            signal.strategy_type.value,
                            signal.timeframe,
                            signal.direction.value
                        )
                        signal.confidence_score = adapted_conf
                        if abs(adapted_conf - original_conf) > 0.1:
                            signal.score_breakdown["self_adaptation"] = f"{original_conf:.1f} → {adapted_conf:.1f}"
            
            # Re-filter after optimization check
            qualified_signals = [s for s in qualified_signals if s.confidence_score >= self.config.scanner.min_signal_score]
            
            # Step 8: Rank and deduplicate
            final_signals = self._deduplicate_signals(qualified_signals)
            
            # Step 8: Keep only top 3 signals
            max_signals = 3
            final_signals = final_signals[:max_signals]
            
            # Step 9: AI Analysis and Enhancement (AI-first)
            if self.ai_analyzer.is_available:
                logger.info("=" * 50)
                logger.info("🧠 Running AI Analysis (AI-first)...")
                logger.info("=" * 50)
                
                # Reset AI analysis count for this scan
                self.ai_analyzer.reset_analysis_count()
                
                # Build coins lookup dict
                coins_dict = {c.symbol: c for c in coins}
                
                # Run AI analysis on signals - pass market regime for journal-aware decisions
                # Modify the call to pass regime through individual signals
                for signal in final_signals:
                    signal.score_breakdown["market_regime"] = regime_str
                
                ai_results = await self.ai_analyzer.analyze_signals_batch(final_signals, coins_dict)
                
                if ai_results:
                    # Apply AI enhancements to signals (APPROVE/REJECT/MODIFY)
                    final_signals = self.ai_analyzer.apply_ai_enhancements(final_signals, ai_results)
                    
                    # Re-rank by updated confidence
                    final_signals = self.scorer.rank_signals(final_signals)
                    
                    # Re-filter by minimum score
                    final_signals = [s for s in final_signals if s.confidence_score >= self.config.scanner.min_signal_score]
                    
                    # Keep top 3
                    final_signals = final_signals[:3]
                    
                    logger.info(f"AI enhanced {len(final_signals)} signals")
                else:
                    logger.info("No AI analysis results available - using rule-based fallback")
            else:
                logger.info("AI analysis not available - using rule-based fallback (50% size reduction)")
                # Fallback mode - reduce position sizes
                for signal in final_signals:
                    signal.score_breakdown["fallback_mode"] = True
            
            # Step 9b: Hybrid Reasoning Enhancement (Phase 3) - 100% AI Reliance
            # Only run if LLM is enabled in config
            if (self.config.ai.enabled and 
                self.hybrid_reasoner.is_available and 
                final_signals):
                logger.info("=" * 50)
                logger.info("🔄 Running Hybrid Reasoning (100% AI Reliance)...")
                logger.info("=" * 50)
                
                # Build coins lookup dict if not already done
                if 'coins_dict' not in locals():
                    coins_dict = {c.symbol: c for c in coins}
                
                # Apply hybrid reasoning to each final signal
                for i, signal in enumerate(final_signals):
                    coin = coins_dict.get(signal.symbol)
                    if coin:
                        signal = await self.hybrid_reasoner.apply_hybrid_analysis(signal, coin)
                        final_signals[i] = signal
                
                # Re-rank by updated confidence (may have been adjusted by AI)
                final_signals = self.scorer.rank_signals(final_signals)
            else:
                logger.debug("Hybrid reasoning not available - using rule-based signals only")
            
            # Re-filter by minimum score
            final_signals = [s for s in final_signals if s.confidence_score >= self.config.scanner.min_signal_score]
            
            # Keep top 3
            final_signals = final_signals[:3]
            
            if self.hybrid_reasoner.is_available:
                logger.info(f"Hybrid reasoning applied to {len(final_signals)} signals")
            
            # Step 10: Optional AI Signal Generation
            if self.ai_generator.is_available and self.config.ai.enable_ai_analysis:
                logger.info("=" * 50)
                logger.info("🤖 Generating AI Signals...")
                logger.info("=" * 50)
                
                # Try to generate AI signals from top coins
                top_coins_for_ai = coins[:50]  # Limit to top 50 for speed
                
                for coin in top_coins_for_ai:
                    if len(final_signals) >= 5:  # Limit total signals
                        break
                    
                    primary_tf = self.config.scanner.timeframes[0] if self.config.scanner.timeframes else "4h"
                    ai_signal = await self.ai_generator.generate_signal(coin, btc_trend, primary_tf)
                    
                    if ai_signal:
                        # Score the AI-generated signal
                        ai_signal = self.scorer.enrich_with_btc_alignment(ai_signal, btc_trend)
                        ai_signal = self.scorer.score_signal(ai_signal)
                        
                        # Check if it meets quality thresholds
                        if (ai_signal.confidence_score >= 6.0 and 
                            ai_signal.risk_reward >= 3.0):
                            # Additional check for BTC alignment
                            if btc_trend.value == "NEUTRAL" or (
                                btc_trend.value == "BULLISH" and ai_signal.direction.value == "LONG"
                            ) or (
                                btc_trend.value == "BEARISH" and ai_signal.direction.value == "SHORT"
                            ):
                                final_signals.append(ai_signal)
                                logger.info(f"AI generated signal for {coin.symbol}: {ai_signal.direction.value}")
                
                # Re-rank and limit
                final_signals = self.scorer.rank_signals(final_signals)[:3]
            
            # NEW: Step 11 - AI Agent Signal Validation
            # Validate signals using AI agent against market conditions
            logger.info("=" * 60)
            logger.info("🤖 AI Agent Validating Signals...")
            logger.info("=" * 60)
            
            validated_signals = []
            coins_dict = {c.symbol: c for c in coins} if coins else {}
            
            for signal in final_signals:
                try:
                    coin = coins_dict.get(signal.symbol)
                    if coin and self.current_market_sentiment:
                        # Validate signal with AI agent
                        validation_result = await self.signal_validation_agent.validate_signal(
                            signal=signal,
                            coin=coin,
                            market_sentiment=self.current_market_sentiment
                        )
                        
                        # Apply agent's decision
                        if validation_result.decision.value == "APPROVE":
                            # Update signal confidence with agent's adjustment
                            signal.confidence_score = validation_result.adjusted_confidence
                            signal.score_breakdown["agent_decision"] = "APPROVE"
                            signal.score_breakdown["agent_confidence_adj"] = validation_result.confidence_change
                            signal.score_breakdown["agent_reasoning"] = validation_result.reasoning[:100]
                            validated_signals.append(signal)
                            logger.info(
                                f"✅ Agent APPROVED {signal.symbol}: "
                                f"Setup Quality {validation_result.setup_quality_score:.0f}/100 | "
                                f"Market Alignment {validation_result.market_alignment_score:.0f}/100"
                            )
                        elif validation_result.decision.value == "HOLD":
                            # Reduce confidence for HOLD decision
                            signal.confidence_score = validation_result.adjusted_confidence
                            signal.score_breakdown["agent_decision"] = "HOLD"
                            if signal.confidence_score >= self.config.scanner.min_signal_score:
                                validated_signals.append(signal)
                                logger.info(f"⏸️ Agent on HOLD for {signal.symbol} (reduced confidence)")
                        else:  # REJECT
                            logger.info(
                                f"❌ Agent REJECTED {signal.symbol}: {validation_result.reasoning[:100]}"
                            )
                    else:
                        # No validation data available, keep signal as-is
                        validated_signals.append(signal)
                        
                except Exception as e:
                    logger.error(f"Signal validation error for {signal.symbol}: {e}")
                    # On error, keep signal but mark it
                    signal.score_breakdown["agent_validation_error"] = str(e)
                    validated_signals.append(signal)
            
            # Use validated signals instead
            final_signals = validated_signals
            logger.info(f"Agent validation complete: {len(final_signals)} signals validated and approved")
            
            # Print signal details
            if final_signals:
                logger.info("="*50)
                logger.info("TOP SIGNALS (Enhanced)")
                logger.info("="*50)
                regime_str = self.current_market_regime.value
                for i, sig in enumerate(final_signals, 1):
                    ai_indicator = "🤖" if "AI" in sig.reasoning and "AI GENERATED" in sig.reasoning else ""
                    logger.info(f"\n{i}. {sig.symbol} {sig.direction.value} {ai_indicator}")
                    logger.info(f"   Strategy: {sig.strategy_type.value}")
                    logger.info(f"   Timeframe: {sig.timeframe}")
                    logger.info(f"   Market Regime: {regime_str}")
                    logger.info(f"   Entry: ${sig.entry_zone_min:.2f} - ${sig.entry_zone_max:.2f}")
                    logger.info(f"   Stop Loss: ${sig.stop_loss:.2f}")
                    logger.info(f"   Targets: T1=${sig.target_1:.2f}, T2=${sig.target_2:.2f}")
                    logger.info(f"   Risk/Reward: 1:{sig.risk_reward:.1f}")
                    logger.info(f"   Confidence: {sig.confidence_score:.1f}/10")
                    # Show Confluence Score
                    if sig.score_breakdown.get("confluence_score"):
                        logger.info(f"   📊 Confluence: {sig.score_breakdown.get('confluence_score'):.1f}/10")
                    # Show AI badge in confidence if enhanced
                    if sig.score_breakdown.get("ai_enhanced"):
                        ai_decision = sig.score_breakdown.get("ai_decision", "APPROVE")
                        logger.info(f"   🧠 AI: {ai_decision} (conf: {sig.score_breakdown.get('ai_enhanced'):.1f}/10)")
                    # Show optimization check
                    if sig.score_breakdown.get("optimization_check"):
                        logger.info(f"   ⚡ Opt: {sig.score_breakdown.get('optimization_check')}")
                    # Show hybrid reasoning contribution if available
                    if sig.ai_reasoning_contribution != 0:
                        logger.info(f"   🔄 Hybrid: Base {sig.rule_based_confidence:.1f} → Final {sig.confidence_score:.1f} ({sig.ai_reasoning_contribution:+.1f})")
                    logger.info(f"   Reason: {sig.reasoning[:200]}...")
            
            # Calculate scan duration
            scan_duration = time.time() - scan_start
            
            # Log results
            logger.info(f"Scan complete in {scan_duration:.1f}s")
            logger.info(f"Total signals: {len(all_signals)}")
            logger.info(f"Qualified signals: {len(final_signals)}")
            
            # Save to database
            btc_price = 0
            if coins:
                btc = next((c for c in coins if c.symbol == "BTC"), None)
                if btc:
                    btc_price = btc.current_price
            
            regime_value = self.current_market_regime.value if self.current_market_regime else "UNKNOWN"
            
            self.tracker.save_scan_result(
                final_signals,
                scan_duration,
                btc_trend.value,
                btc_price,
                market_regime,
                regime_value
            )
            
            # Phase 4: Add signals to learning tracker
            if self.config.learning.enable_learning and final_signals:
                for signal in final_signals:
                    self.signal_tracker.add_signal(signal)
                    logger.debug(f"Added signal {signal.id} to learning tracker")
            
            # Update state
            self.last_scan_time = datetime.now()
            self.last_signals = final_signals
            
            return final_signals
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def _get_btc_trend(self) -> TrendDirection:
        """Get Bitcoin trend"""
        try:
            return await self.btc_filter.get_btc_trend("4h")
        except Exception as e:
            logger.error(f"Error getting BTC trend: {e}")
            return TrendDirection.NEUTRAL
    
    async def _get_top_coins(self) -> List:
        """Get top coins by market cap"""
        try:
            async with MarketDataCollector() as collector:
                self.collector = collector
                coins = await collector.get_top_coins(self.config.scanner.max_coins_to_scan)
                return coins
        except Exception as e:
            logger.error(f"Error fetching top coins: {e}")
            return []
    
    async def _fetch_candles(self, coins: List) -> List:
        """Fetch candles for all coins"""
        try:
            async with MarketDataCollector() as collector:
                coins = await collector.get_candles_for_coins(
                    coins,
                    self.config.scanner.timeframes
                )
                return coins
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return coins
    
    def _deduplicate_signals(self, signals: List[TradingSignal]) -> List[TradingSignal]:
        """Remove duplicate signals for same coin/strategy"""
        seen = set()
        unique = []
        
        for signal in signals:
            key = (signal.symbol, signal.strategy_type.value, signal.timeframe)
            
            if key not in seen:
                seen.add(key)
                unique.append(signal)
        
        return unique
    
    def send_alerts(self, signals: List[TradingSignal]):
        """Send alerts for signals with market sentiment context"""
        if signals:
            self.alert_manager.send_all_alerts(signals, self.current_market_sentiment)
    
    def display_results(self, signals: List[TradingSignal]):
        """Display results in dashboard"""
        self.dashboard.print_signals(signals)
    
    async def run_continuous(self):
        """Run scanner continuously at configured interval"""
        self.is_running = True
        
        interval = self.config.scanner.scan_interval_minutes * 60
        learning_check_interval = self.config.learning.check_interval_minutes * 60
        last_learning_check = 0
        
        logger.info(f"Starting continuous scan every {self.config.scanner.scan_interval_minutes} minutes")
        
        while self.is_running:
            try:
                signals = await self.run_scan()
                
                if signals:
                    self.display_results(signals)
                    self.send_alerts(signals)
                
                # Periodic learning check
                current_time = time.time()
                if (self.config.learning.enable_learning and 
                    current_time - last_learning_check >= learning_check_interval):
                    logger.info("Running periodic learning check...")
                    await self.run_learning_check()
                    last_learning_check = current_time
                
                # Wait for next interval
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("Scanner stopped by user")
                break
            except Exception as e:
                logger.error(f"Continuous scan error: {e}")
                await asyncio.sleep(60)  # Wait 1 min on error
        
        self.is_running = False
    
    def stop(self):
        """Stop the scanner"""
        self.is_running = False
        logger.info("Scanner stopped")
    
    def get_status(self) -> dict:
        """Get scanner status"""
        return {
            "is_running": self.is_running,
            "last_scan": self.last_scan_time,
            "last_signal_count": len(self.last_signals),
            "config": {
                "interval": self.config.scanner.scan_interval_minutes,
                "min_score": self.config.scanner.min_signal_score,
                "max_coins": self.config.scanner.max_coins_to_scan
            }
        }
    
    async def run_learning_check(self) -> dict:
        """
        Run resolution check and generate insights.
        
        This can be called periodically to:
        - Check if any active signals have resolved
        - Record outcomes
        - Generate insights if enough data
        
        Returns:
            Dictionary with check results
        """
        if not self.config.learning.enable_learning:
            return {"enabled": False}
        
        logger.info("Running learning system check...")
        
        # Set market data collector if not set
        if self.collector:
            self.resolution_checker.set_market_data_collector(self.collector)
        
        # Check for resolved signals
        resolved = await self.resolution_checker.check_all_signals()
        
        self_adapted = False
        # Combine both automated signal outcomes and manual journal trades
        all_outcomes = self.accuracy_scorer._outcomes.copy()
        all_outcomes.extend(self.trade_journal.get_outcomes())
        if len(all_outcomes) >= 5:
            self.self_adaptation.generate_adaptations(all_outcomes)
            self_adapted = True
            logger.info("Self-adaptation applied based on outcomes")
        
        # Generate insights if enough data
        insights_generated = []
        if self.learning_engine.should_generate_insights():
            insights_generated = self.learning_engine.generate_insights()
            if insights_generated:
                logger.info(f"Generated {len(insights_generated)} new insights")
        
        # Get current accuracy stats
        accuracy_stats = self.learning_engine.get_accuracy_stats()
        
        result = {
            "enabled": True,
            "resolved_signals": len(resolved),
            "insights_generated": len(insights_generated),
            "self_adapted": self_adapted,
            "total_resolved": accuracy_stats.get('total_resolved', 0),
            "overall_win_rate": accuracy_stats.get('overall', 0),
            "quality_score": accuracy_stats.get('quality_score', 0),
            "active_signals": self.signal_tracker.get_count(),
            "journal_trades": self.trade_journal.get_outcomes_count()
        }
        
        logger.info(f"Learning check complete: {result}")
        
        return result
    
    def get_learning_stats(self) -> dict:
        """
        Get current learning system statistics.
        
        Returns:
            Dictionary with learning metrics
        """
        if not self.config.learning.enable_learning:
            return {"enabled": False}
        
        accuracy_stats = self.learning_engine.get_accuracy_stats()
        recent_insights = self.learning_engine.get_insights(limit=5)
        
        return {
            "enabled": True,
            "active_signals": self.signal_tracker.get_count(),
            "total_resolved": accuracy_stats.get('total_resolved', 0),
            "overall_win_rate": round(accuracy_stats.get('overall', 0), 1),
            "win_rate_by_strategy": accuracy_stats.get('by_strategy', {}),
            "win_rate_by_timeframe": accuracy_stats.get('by_timeframe', {}),
            "quality_score": accuracy_stats.get('quality_score', 0),
            "recent_insights_count": len(recent_insights),
            "insights_ready": self.learning_engine.should_generate_insights()
        }


# Main entry point
async def main():
    """Main entry point for the scanner"""
    
    # Initialize scanner
    scanner = CryptoScanner()
    
    # Run single scan
    signals = await scanner.run_scan()
    
    # Display results
    scanner.display_results(signals)
    
    # Send alerts
    if signals:
        scanner.send_alerts(signals)
    
    return signals


if __name__ == "__main__":
    asyncio.run(main())
