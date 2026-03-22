"""
Crypto Scanner - Main Orchestrator
Coordinates all modules to scan markets and generate trading signals.
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
from ai import AISignalAnalyzer, AISignalGenerator


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
        
        # Store coins for AI analysis
        self._coins_cache: Dict[str, CoinData] = {}
        
        # State
        self.is_running = False
        self.last_scan_time: Optional[datetime] = None
        self.last_signals: List[TradingSignal] = []
        
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
        """Execute a complete market scan"""
        
        scan_start = time.time()
        all_signals = []
        
        logger.info("=" * 60)
        logger.info("🔍 Starting Market Scan")
        logger.info("=" * 60)
        
        try:
            # Step 1: Get Bitcoin trend first
            btc_trend = await self._get_btc_trend()
            market_regime = self.btc_filter.get_market_regime(btc_trend)
            
            # Step 2: Get top coins
            coins = await self._get_top_coins()
            
            if not coins:
                logger.warning("No coins fetched")
                return []
            
            # Step 3: Get candles for all coins
            logger.info(f"Fetching candles for {len(coins)} coins...")
            coins = await self._fetch_candles(coins)
            
            # Step 4: Calculate indicators and run strategies
            logger.info("Running strategy engines...")
            
            # Filter out stablecoins
            stablecoins = ["USDT", "USDC", "DAI", "BUSD", "USDS", "USD1", "USDG", "USDF", "TUSD", "USDD", "FRAX", "USDE"]
            coins = [c for c in coins if c.symbol not in stablecoins]
            
            for coin in coins:
                # Calculate indicators for primary timeframe
                primary_tf = self.config.scanner.timeframes[0] if self.config.scanner.timeframes else "1h"
                coin = self.indicator_engine.calculate_all_indicators(coin, primary_tf)
                
                # Run all strategy engines
                signals = self.strategy_engine.scan_all_strategies(coin, btc_trend, primary_tf)
                
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
            
            # Step 5: Filter signals by BTC trend
            all_signals = self.btc_filter.filter_signals_by_btc(all_signals, btc_trend)
            
            # Step 6: Filter by minimum score
            qualified_signals = self.scorer.filter_signals(all_signals)
            
            # Step 7: Filter by minimum risk/reward (3R or higher)
            min_r = 3.0
            qualified_signals = [s for s in qualified_signals if s.risk_reward >= min_r]
            
            # Step 8: Rank and deduplicate
            final_signals = self._deduplicate_signals(qualified_signals)
            
            # Step 8: Keep only top 3 signals
            max_signals = 3
            final_signals = final_signals[:max_signals]
            
            # Step 9: AI Analysis and Enhancement
            if self.ai_analyzer.is_available:
                logger.info("=" * 50)
                logger.info("🧠 Running AI Analysis...")
                logger.info("=" * 50)
                
                # Reset AI analysis count for this scan
                self.ai_analyzer.reset_analysis_count()
                
                # Build coins lookup dict
                coins_dict = {c.symbol: c for c in coins}
                
                # Run AI analysis on signals
                ai_results = await self.ai_analyzer.analyze_signals_batch(final_signals, coins_dict)
                
                if ai_results:
                    # Apply AI enhancements to signals
                    final_signals = self.ai_analyzer.apply_ai_enhancements(final_signals, ai_results)
                    
                    # Re-rank by updated confidence
                    final_signals = self.scorer.rank_signals(final_signals)
                    
                    # Re-filter by minimum score
                    final_signals = [s for s in final_signals if s.confidence_score >= self.config.scanner.min_signal_score]
                    
                    # Keep top 3
                    final_signals = final_signals[:3]
                    
                    logger.info(f"AI enhanced {len(final_signals)} signals")
                else:
                    logger.info("No AI analysis results available")
            else:
                logger.info("AI analysis not available - skipping (configure AI in .env)")
            
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
            
            # Print signal details
            if final_signals:
                logger.info("="*50)
                logger.info("TOP SIGNALS")
                logger.info("="*50)
                for i, sig in enumerate(final_signals, 1):
                    ai_indicator = "🤖" if "AI" in sig.reasoning and "AI GENERATED" in sig.reasoning else ""
                    logger.info(f"\n{i}. {sig.symbol} {sig.direction.value} {ai_indicator}")
                    logger.info(f"   Strategy: {sig.strategy_type.value}")
                    logger.info(f"   Timeframe: {sig.timeframe}")
                    logger.info(f"   Entry: ${sig.entry_zone_min:.2f} - ${sig.entry_zone_max:.2f}")
                    logger.info(f"   Stop Loss: ${sig.stop_loss:.2f}")
                    logger.info(f"   Targets: T1=${sig.target_1:.2f}, T2=${sig.target_2:.2f}")
                    logger.info(f"   Risk/Reward: 1:{sig.risk_reward:.1f}")
                    logger.info(f"   Confidence: {sig.confidence_score:.1f}/10")
                    # Show AI badge in confidence if enhanced
                    if sig.score_breakdown.get("ai_enhanced"):
                        logger.info(f"   🧠 AI Enhanced: Yes (AI conf: {sig.score_breakdown.get('ai_enhanced'):.1f}/10)")
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
            
            self.tracker.save_scan_result(
                final_signals,
                scan_duration,
                btc_trend.value,
                btc_price,
                market_regime
            )
            
            # Update state
            self.last_scan_time = datetime.now()
            self.last_signals = final_signals
            
            return final_signals
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
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
        """Send alerts for signals"""
        if signals:
            self.alert_manager.send_all_alerts(signals)
    
    def display_results(self, signals: List[TradingSignal]):
        """Display results in dashboard"""
        self.dashboard.print_signals(signals)
    
    async def run_continuous(self):
        """Run scanner continuously at configured interval"""
        self.is_running = True
        
        interval = self.config.scanner.scan_interval_minutes * 60
        
        logger.info(f"Starting continuous scan every {self.config.scanner.scan_interval_minutes} minutes")
        
        while self.is_running:
            try:
                signals = await self.run_scan()
                
                if signals:
                    self.display_results(signals)
                    self.send_alerts(signals)
                
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
