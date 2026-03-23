"""
Resolution Checker Module
Scheduled checking of signal resolution against current market prices.
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import List, Optional, Any

from loguru import logger

from models import TradingSignal, SignalOutcome, SignalResolution, SignalDirection
from config import get_config
from learning.signal_tracker import SignalTracker
from learning.accuracy_scorer import AccuracyScorer
from learning.notifier import send_resolution_alert


class ResolutionChecker:
    """
    Scheduled resolution checking for active trading signals.
    
    Periodically checks all active signals against current market prices
    to detect resolution and record outcomes.
    """
    
    def __init__(
        self,
        config: Optional[Any] = None,
        signal_tracker: Optional[SignalTracker] = None,
        accuracy_scorer: Optional[AccuracyScorer] = None,
        market_data_collector: Optional[Any] = None
    ):
        """
        Initialize the ResolutionChecker.
        
        Args:
            config: Optional config object. If not provided, uses get_config()
            signal_tracker: Optional SignalTracker instance
            accuracy_scorer: Optional AccuracyScorer instance
            market_data_collector: Optional MarketDataCollector instance
        """
        self._config = config or get_config()
        self._signal_tracker = signal_tracker or SignalTracker(self._config)
        self._accuracy_scorer = accuracy_scorer or AccuracyScorer(self._config)
        self._market_data_collector = market_data_collector
        
        logger.info("ResolutionChecker initialized")
    
    def set_market_data_collector(self, collector: Any) -> None:
        """
        Set the market data collector.
        
        Args:
            collector: MarketDataCollector instance
        """
        self._market_data_collector = collector
    
    async def _fetch_current_price(self, symbol: str) -> Optional[float]:
        """
        Fetch current price for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., BTC)
            
        Returns:
            Current price or None if unavailable
        """
        if self._market_data_collector is None:
            logger.warning("No market data collector available")
            return None
        
        try:
            # Use the market data collector to get price
            if hasattr(self._market_data_collector, 'get_top_coins'):
                # This is the main MarketDataCollector
                coins = await self._market_data_collector.get_top_coins(limit=1)
                for coin in coins:
                    if coin.symbol.upper() == symbol.upper():
                        return coin.current_price
            elif hasattr(self._market_data_collector, 'get_price'):
                # Simple price fetcher
                return await self._market_data_collector.get_price(symbol)
            
            # Fallback: try to get from Binance directly
            if hasattr(self._market_data_collector, 'session'):
                import aiohttp
                symbol_pair = f"{symbol}USDT" if not symbol.endswith("USDT") else symbol
                url = f"https://api.binance.com/api/v3/ticker/price"
                params = {"symbol": symbol_pair}
                
                async with self._market_data_collector.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return float(data.get('price', 0))
            
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
        
        return None
    
    async def check_all_signals(self) -> List[SignalOutcome]:
        """
        Check all active signals for resolution.
        
        Returns:
            List of resolved SignalOutcome objects
        """
        active_signals = self._signal_tracker.get_active_signals()
        
        if not active_signals:
            logger.debug("No active signals to check")
            return []
        
        logger.info(f"Checking {len(active_signals)} active signals for resolution")
        
        resolved_outcomes = []
        
        for signal in active_signals:
            outcome = await self.resolve_signal(signal)
            if outcome:
                self.handle_resolved(outcome)
                resolved_outcomes.append(outcome)
        
        if resolved_outcomes:
            logger.info(f"Resolved {len(resolved_outcomes)} signals")
        
        return resolved_outcomes
    
    async def resolve_signal(self, signal: TradingSignal) -> Optional[SignalOutcome]:
        """
        Check a single signal for resolution.
        
        Args:
            signal: TradingSignal to check
            
        Returns:
            SignalOutcome if resolved, None if still active
        """
        # Fetch current price
        current_price = await self._fetch_current_price(signal.symbol)
        
        if current_price is None:
            logger.warning(f"Could not fetch current price for {signal.symbol}")
            return None
        
        # Calculate outcome using the accuracy scorer
        outcome = self._accuracy_scorer.calculate_outcome(signal, current_price)
        
        if outcome:
            logger.info(
                f"Signal {signal.id} ({signal.symbol}) resolved: "
                f"{outcome.resolution.value} at ${current_price:.2f}"
            )
        
        return outcome
    
    def handle_resolved(self, outcome: SignalOutcome) -> None:
        """
        Process a resolved signal.
        
        Args:
            outcome: SignalOutcome to process
        """
        # Record the outcome
        self._accuracy_scorer.record_outcome(outcome)
        
        # Remove from active tracking
        self._signal_tracker.remove_signal(outcome.signal_id)
        
        # Send notification if enabled
        if self._config.learning.notify_on_resolution:
            try:
                send_resolution_alert(
                    outcome,
                    self._accuracy_scorer.calculate_overall_accuracy(),
                    self._accuracy_scorer.calculate_accuracy_by_strategy()
                )
            except Exception as e:
                logger.error(f"Failed to send resolution alert: {e}")
        
        # Log the resolution
        pnl_emoji = "✅" if outcome.pnl_percent > 0 else "❌"
        logger.info(
            f"{pnl_emoji} {outcome.symbol} {outcome.direction.value} "
            f"resolved: {outcome.resolution.value} "
            f"PnL: {outcome.pnl_percent:.2f}%"
        )
    
    async def run_check(self) -> None:
        """
        Main method to run all resolution checks.
        
        This is the entry point for scheduled checks.
        """
        logger.info("Running scheduled resolution check")
        
        try:
            outcomes = await self.check_all_signals()
            
            # Log summary
            if outcomes:
                wins = sum(1 for o in outcomes 
                          if o.resolution in [SignalResolution.TARGET_1_HIT, 
                                            SignalResolution.TARGET_2_HIT])
                total = len(outcomes)
                logger.info(
                    f"Resolution check complete: {wins}/{total} wins "
                    f"({(wins/total*100):.1f}% win rate)"
                )
            else:
                logger.debug("No signals resolved in this check")
                
        except Exception as e:
            logger.error(f"Error during resolution check: {e}")
    
    def run_check_sync(self) -> None:
        """
        Synchronous wrapper for run_check.
        
        Use this for non-async contexts.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop in a thread if already in async context
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.run_check())
                    future.result()
            else:
                asyncio.run(self.run_check())
        except Exception as e:
            logger.error(f"Error running sync resolution check: {e}")
