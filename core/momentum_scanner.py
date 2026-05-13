"""
Momentum Scanner Orchestrator.

The central orchestrator that wires together all components of the
event-driven momentum scanning pipeline:
  WebSocket → EventBus → Regime Filter → Trend Filter → Setup Detection
  → Scoring → Alerting → Journal

Handles BTC events (regime filter), 4H events (trend filter), 1H events
(setup detection), and 15m events (trigger confirmation).

Requirements: 2.1, 2.3, 2.5, 2.6, 20.1, 20.2, 20.5
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from config.websocket_config import WebSocketStreamConfig
from core.state_manager import StateManager
from streaming.event_bus import EventBus
from streaming.models import (
    ActiveSetup,
    CandleCloseEvent,
    CoinState,
    ConnectionFailureEvent,
    JournalEntry,
    OIFundingData,
    PendingTrigger,
    ScoreInputs,
    ScoredSetup,
    SetupSignal,
    SetupState,
    SetupType,
    SignalDirection,
    TrendStatus,
)
from streaming.websocket_manager import WebSocketManager
from filters.market_regime_filter import MarketRegimeFilter
from filters.trend_filter import TrendFilter
from filters.volatility_gate import VolatilityGate
from engines.relative_strength_engine import RelativeStrengthEngine
from detectors.setup_detector import (
    detect_compression_breakout,
    detect_pullback_continuation,
    detect_momentum_breakout,
    detect_momentum_breakdown,
    check_15m_trigger,
)
from monitors.trailing_stop_monitor import TrailingStopMonitor
from monitors.status_reporter import StatusReporter
from scoring.scoring_engine import (
    score,
    score_breakout_quality,
    normalize_rvol,
    apply_oi_adjustments,
    calculate_risk_levels,
    rank_setups,
)
from alerts.momentum_alert_manager import MomentumAlertManager
from storage.journal_store import JournalStore
from streaming.models import OHLCV
from universe.universe_manager import UniverseManager
from health.health_server import HealthCheckServer

logger = logging.getLogger(__name__)

# BTC symbol constant
BTC_SYMBOL = "BTCUSDT"


class MomentumScanner:
    """
    Central orchestrator for the event-driven momentum scanning pipeline.

    Coordinates all components:
    - WebSocketManager: real-time data ingestion
    - EventBus: async event dispatch with deduplication
    - StateManager: per-coin stateful tracking with crash recovery
    - MarketRegimeFilter: BTC-based global market gate
    - TrendFilter: per-coin 4H trend assessment
    - RelativeStrengthEngine: coin vs BTC performance
    - SetupDetector: compression breakout + pullback continuation
    - ScoringEngine: deterministic composite scoring
    - MomentumAlertManager: dedup + Telegram delivery
    - JournalStore: signal/rejection persistence

    Requirements:
        2.1 - Incremental processing per coin/timeframe on candle close
        2.3 - Async processing for up to 50 concurrent coin updates
        2.5 - Propagate state changes through filter chain within 100ms
        2.6 - Log errors, skip affected coin, continue processing
        20.1 - Sub-500ms pipeline from event to scored result
        20.2 - Support up to 300 coin pairs
        20.5 - Crash recovery via state persistence
    """

    def __init__(
        self,
        config: Optional[WebSocketStreamConfig] = None,
        symbols: Optional[List[str]] = None,
        ai_enabled: bool = False,
    ) -> None:
        """
        Initialize the MomentumScanner.

        Args:
            config: WebSocket streaming configuration. Defaults to
                    WebSocketStreamConfig() with env-var-driven values.
            symbols: List of trading pair symbols to monitor.
                     Defaults to empty list.
            ai_enabled: Whether optional AI integration points are active.
                        When False (default), all AI stub methods are no-ops.
                        When True, AI stubs may delegate to an external provider.
                        IMPORTANT: The core pipeline (filter → detect → score → alert)
                        NEVER calls AI regardless of this flag. AI is limited to
                        post-signal tasks only (EOD summary, journal commentary,
                        analytics narrative, message formatting).
        """
        self._config = config or WebSocketStreamConfig()
        self._symbols = symbols or []
        self._ai_enabled = ai_enabled
        self._running = False

        # Core infrastructure
        self._event_bus = EventBus(max_size=self._config.event_queue_max_size)
        self._state_manager = StateManager(max_coins=self._config.max_coins)
        self._ws_manager = WebSocketManager(
            config=self._config,
            event_bus=self._event_bus,
            symbols=self._symbols,
        )

        # Processing pipeline components
        self._regime_filter = MarketRegimeFilter()
        self._trend_filter = TrendFilter()
        self._volatility_gate = VolatilityGate(
            min_ratio_pct=self._config.volatility_min_pct,
            max_ratio_pct=self._config.volatility_max_pct,
        )
        self._rs_engine = RelativeStrengthEngine()

        # Scoring and alerting
        self._alert_manager = MomentumAlertManager(
            cooldown_hours=self._config.alert_cooldown_hours,
            max_entries=500,
        )
        self._journal = JournalStore()

        # Trailing stop monitoring (Requirement 6.1)
        self._trailing_stop_monitor = TrailingStopMonitor(
            alert_manager=self._alert_manager,
            journal=self._journal,
        )

        # Status reporting (Requirements 7.1, 7.2, 7.3)
        self._status_reporter = StatusReporter(
            alert_manager=self._alert_manager,
            journal_store=self._journal,
            regime_filter=self._regime_filter,
        )

        # Universe management (Requirement 2.1, 2.6, 2.7)
        self._universe_manager = UniverseManager(
            min_volume_usd=self._config.universe_min_volume_usd,
            min_price=self._config.universe_min_price,
        )
        self._universe_refresh_task: Optional[asyncio.Task] = None

        # Health check server (Requirement 9.5, 9.9)
        self._health_server = HealthCheckServer(scanner=self)

        # Internal tracking
        self._active_scored_setups: List[ScoredSetup] = []
        self._ranked_top5: List[ScoredSetup] = []
        self._processing_semaphore = asyncio.Semaphore(
            self._config.max_concurrent_coin_updates
        )
        self._event_loop_task: Optional[asyncio.Task] = None
        self._last_signal_time: Optional[datetime] = None

        # Scheduled tasks for status reporter
        self._idle_check_task: Optional[asyncio.Task] = None
        self._daily_summary_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        """Whether the scanner is currently running."""
        return self._running

    @property
    def state_manager(self) -> StateManager:
        """Access the state manager (for external inspection/testing)."""
        return self._state_manager

    @property
    def regime_filter(self) -> MarketRegimeFilter:
        """Access the market regime filter."""
        return self._regime_filter

    @property
    def alert_manager(self) -> MomentumAlertManager:
        """Access the alert manager."""
        return self._alert_manager

    @property
    def universe_manager(self) -> UniverseManager:
        """Access the universe manager."""
        return self._universe_manager

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """
        Start the momentum scanner.

        Initialization sequence:
        1. Restore persisted state (crash recovery)
        2. Initialize universe (fetch active symbols from Binance)
        3. Establish WebSocket connections to configured exchanges
        4. Begin consuming events from the EventBus
        5. Schedule periodic universe refresh

        Requirements: 2.1, 2.6, 2.7, 20.5
        """
        if self._running:
            logger.warning("MomentumScanner is already running")
            return

        logger.info(
            "Starting MomentumScanner: symbols=%d, exchanges=%s, timeframes=%s",
            len(self._symbols),
            self._config.enabled_exchanges,
            self._config.timeframes,
        )

        # Step 1: Restore state from persistence (Requirement 20.5)
        restored = self._state_manager.restore_state()
        if restored:
            logger.info("State restored from previous session")
        else:
            logger.info("Starting with fresh state")

        # Step 2: Initialize universe to get dynamic symbol list (Requirement 2.1)
        try:
            logger.info("Attempting universe initialization from Bybit API...")
            universe_symbols = await asyncio.wait_for(
                self._universe_manager.initialize(),
                timeout=45.0,
            )
            if universe_symbols:
                self._symbols = universe_symbols
                # Update WebSocketManager symbols before starting connections
                self._ws_manager._symbols = self._symbols
                logger.info(
                    "Universe initialized with %d symbols", len(self._symbols)
                )
            else:
                logger.warning(
                    "Universe returned empty list, using configured symbols (%d)",
                    len(self._symbols),
                )
        except asyncio.TimeoutError:
            logger.warning(
                "Universe initialization timed out (45s), using configured symbols (%d)",
                len(self._symbols),
            )
        except Exception as e:
            logger.warning(
                "Universe initialization failed, using configured symbols (%d): %s",
                len(self._symbols),
                str(e),
            )

        # Step 3: Establish WebSocket connections
        await self._ws_manager.start()

        # Step 3b: Register failure callback for exchange failover
        self._register_failure_callback()

        # Step 4: Begin event processing loop
        self._running = True
        self._event_loop_task = asyncio.create_task(self._event_loop())

        # Step 5: Schedule periodic universe refresh (Requirements 2.6, 2.7)
        self._universe_refresh_task = asyncio.create_task(
            self._universe_refresh_loop()
        )

        # Step 6: Send startup status message (Requirement 7.1)
        await self._status_reporter.send_startup_message(len(self._symbols))

        # Step 7: Schedule periodic status reporter tasks (Requirements 7.2, 7.3)
        self._idle_check_task = asyncio.create_task(
            self._idle_check_loop()
        )
        self._daily_summary_task = asyncio.create_task(
            self._daily_summary_loop()
        )

        # Step 8: Start health check server if PORT is set (Requirement 9.5)
        await self._health_server.start()

        logger.info("MomentumScanner started successfully")

    async def stop(self) -> None:
        """
        Gracefully stop the momentum scanner.

        Shutdown sequence:
        1. Stop the event processing loop
        2. Cancel universe refresh timer
        3. Save current state for crash recovery
        4. Close all WebSocket connections
        5. Close universe manager resources

        Requirements: 20.5, 20.6
        """
        if not self._running:
            return

        logger.info("Stopping MomentumScanner...")
        self._running = False

        # Stop the event bus consumer
        self._event_bus.stop()

        # Cancel the event loop task
        if self._event_loop_task and not self._event_loop_task.done():
            self._event_loop_task.cancel()
            try:
                await self._event_loop_task
            except asyncio.CancelledError:
                pass

        # Cancel universe refresh timer (Requirement 2.6)
        if self._universe_refresh_task and not self._universe_refresh_task.done():
            self._universe_refresh_task.cancel()
            try:
                await self._universe_refresh_task
            except asyncio.CancelledError:
                pass

        # Cancel status reporter scheduled tasks
        if self._idle_check_task and not self._idle_check_task.done():
            self._idle_check_task.cancel()
            try:
                await self._idle_check_task
            except asyncio.CancelledError:
                pass

        if self._daily_summary_task and not self._daily_summary_task.done():
            self._daily_summary_task.cancel()
            try:
                await self._daily_summary_task
            except asyncio.CancelledError:
                pass

        # Save state for crash recovery (Requirement 20.5)
        self._state_manager.save_state()
        logger.info("State saved for crash recovery")

        # Close WebSocket connections
        await self._ws_manager.stop()

        # Close universe manager resources
        await self._universe_manager.close()

        # Stop health check server (Requirement 9.5)
        await self._health_server.stop()

        logger.info("MomentumScanner stopped")

    # ─── Event Loop ───────────────────────────────────────────────────────────

    async def _event_loop(self) -> None:
        """
        Main event processing loop.

        Consumes events from the EventBus and dispatches them through
        the processing pipeline. Uses a semaphore to limit concurrent
        coin updates to the configured maximum (default 50).

        Requirements: 2.1, 2.3, 2.7
        """
        try:
            async for event in self._event_bus.consume():
                if not self._running:
                    break

                # Process each event concurrently with bounded parallelism
                asyncio.create_task(self._process_event_bounded(event))

        except asyncio.CancelledError:
            logger.debug("Event loop cancelled")
        except Exception as e:
            logger.error("Unexpected error in event loop: %s", str(e))

    async def _process_event_bounded(self, event: CandleCloseEvent) -> None:
        """
        Process an event with semaphore-bounded concurrency.

        Ensures no more than max_concurrent_coin_updates are processed
        simultaneously (Requirement 2.3).
        """
        async with self._processing_semaphore:
            await self._process_event(event)

    # ─── Universe Refresh ─────────────────────────────────────────────────────

    async def _universe_refresh_loop(self) -> None:
        """
        Periodic universe refresh loop.

        Runs every UNIVERSE_REFRESH_MINUTES (default 60) minutes. On each
        refresh, fetches the updated symbol list and subscribes/unsubscribes
        from WebSocket streams for added/removed symbols within 30 seconds.

        Requirements: 2.2, 2.6, 2.7
        """
        refresh_interval_seconds = self._config.universe_refresh_minutes * 60

        try:
            while self._running:
                await asyncio.sleep(refresh_interval_seconds)

                if not self._running:
                    break

                await self._refresh_universe()

        except asyncio.CancelledError:
            logger.debug("Universe refresh loop cancelled")
        except Exception as e:
            logger.error("Unexpected error in universe refresh loop: %s", str(e))

    async def _refresh_universe(self) -> None:
        """
        Perform a single universe refresh cycle.

        Calls UniverseManager.refresh() to get added/removed symbols,
        then subscribes to new symbols and unsubscribes from removed
        symbols via the WebSocketManager within 30 seconds.

        Requirements: 2.6, 2.7
        """
        try:
            added, removed = await self._universe_manager.refresh()

            if added or removed:
                logger.info(
                    "Universe changed: +%d added, -%d removed",
                    len(added),
                    len(removed),
                )

                # Subscribe to new symbols (Requirement 2.6)
                if added:
                    await asyncio.wait_for(
                        self._ws_manager.subscribe(added),
                        timeout=30.0,
                    )
                    # Update internal symbol list
                    for symbol in added:
                        if symbol not in self._symbols:
                            self._symbols.append(symbol)

                # Unsubscribe from removed symbols (Requirement 2.7)
                if removed:
                    await asyncio.wait_for(
                        self._ws_manager.unsubscribe(removed),
                        timeout=30.0,
                    )
                    # Update internal symbol list
                    self._symbols = [
                        s for s in self._symbols if s not in removed
                    ]
            else:
                logger.debug("Universe refresh: no changes")

        except asyncio.TimeoutError:
            logger.error(
                "Universe refresh subscribe/unsubscribe timed out (30s limit)"
            )
        except Exception as e:
            logger.error("Error during universe refresh: %s", str(e))

    # ─── Status Reporter Scheduling ─────────────────────────────────────────

    async def _idle_check_loop(self) -> None:
        """
        Periodic idle status check loop.

        Runs every 30 minutes. Calls status_reporter.check_idle_status()
        with the last signal time to determine if an idle message should
        be sent.

        Requirements: 7.3, 7.4
        """
        try:
            while self._running:
                await asyncio.sleep(30 * 60)  # 30 minutes

                if not self._running:
                    break

                await self._status_reporter.check_idle_status(self._last_signal_time)

        except asyncio.CancelledError:
            logger.debug("Idle check loop cancelled")
        except Exception as e:
            logger.error("Unexpected error in idle check loop: %s", str(e))

    async def _daily_summary_loop(self) -> None:
        """
        Schedule daily summary at 00:00 UTC.

        Calculates the time until the next 00:00 UTC and sleeps until then.
        After sending the summary, waits another 24 hours.

        Requirements: 7.2
        """
        try:
            while self._running:
                # Calculate seconds until next 00:00 UTC
                now = datetime.utcnow()
                tomorrow_midnight = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                if tomorrow_midnight <= now:
                    # Already past midnight today, schedule for tomorrow
                    from datetime import timedelta
                    tomorrow_midnight += timedelta(days=1)

                seconds_until_midnight = (tomorrow_midnight - now).total_seconds()
                await asyncio.sleep(seconds_until_midnight)

                if not self._running:
                    break

                await self._status_reporter.send_daily_summary()

        except asyncio.CancelledError:
            logger.debug("Daily summary loop cancelled")
        except Exception as e:
            logger.error("Unexpected error in daily summary loop: %s", str(e))

    # ─── Event Processing Pipeline ───────────────────────────────────────────

    async def _process_event(self, event: CandleCloseEvent) -> None:
        """
        Route a candle close event through the full processing pipeline.

        Routing logic by symbol and timeframe:
        - BTC + 4H: Update market regime filter
        - Any coin + 4H: Update trend filter for that coin
        - Any coin + 1H: Run setup detection (compression breakout, pullback)
        - Any coin + 15m: Check pending 15m trigger confirmation

        On error, logs the issue and skips the coin for this event cycle
        (Requirement 2.6).

        Args:
            event: The CandleCloseEvent to process.
        """
        try:
            symbol = event.symbol
            timeframe = event.timeframe

            # Update candle buffer in state manager
            self._state_manager.update_candle(symbol, timeframe, event.candle)

            # Route based on symbol and timeframe
            if symbol == BTC_SYMBOL and timeframe == "4h":
                await self._handle_btc_4h(event)

            # Update BTC 1H candles for crash detection
            if symbol == BTC_SYMBOL and timeframe == "1h":
                btc_state = self._state_manager.get_state(BTC_SYMBOL)
                btc_candles_1h = btc_state.candle_buffers.get("1h", [])
                self._regime_filter.update_btc_candles_1h(btc_candles_1h)

            if timeframe == "4h":
                await self._handle_4h_event(event)
            elif timeframe == "1h":
                await self._handle_1h_event(event)
            elif timeframe == "15m":
                await self._handle_15m_event(event)

        except Exception as e:
            # Requirement 2.6: log error, skip coin, continue
            logger.error(
                "Error processing event for %s/%s: %s",
                event.symbol,
                event.timeframe,
                str(e),
            )

    async def _handle_btc_4h(self, event: CandleCloseEvent) -> None:
        """
        Handle BTC 4H candle close — update market regime filter.

        Evaluates all 5 BTC conditions to determine if LONG setups
        should be allowed.

        Args:
            event: BTC 4H CandleCloseEvent.
        """
        state = self._state_manager.get_state(BTC_SYMBOL)
        btc_candles = state.candle_buffers.get("4h", [])

        if not btc_candles:
            return

        # Get universe coins for breadth calculation
        # Use all tracked coin states as the universe
        all_states = self._state_manager.get_all_states()
        universe_coins = self._build_universe_coin_data(all_states)

        # Evaluate regime
        self._regime_filter.evaluate(btc_candles, universe_coins)

        regime_status = "bullish" if self._regime_filter.should_allow_longs() else "not_bullish"
        logger.info("Market regime updated: %s", regime_status)

    async def _handle_4h_event(self, event: CandleCloseEvent) -> None:
        """
        Handle any coin's 4H candle close — update trend filter.

        Evaluates the 3 trend conditions for the coin and updates
        its trend status in the state manager.

        Args:
            event: 4H CandleCloseEvent for any coin.
        """
        symbol = event.symbol
        state = self._state_manager.get_state(symbol)
        candles_4h = state.candle_buffers.get("4h", [])

        if not candles_4h:
            return

        # Evaluate trend (use COMPRESSION_BREAKOUT to get the 50-candle minimum)
        trend_result = self._trend_filter.evaluate(
            candles_4h, setup_type=SetupType.COMPRESSION_BREAKOUT
        )

        # Update state
        self._state_manager.set_trend_status(symbol, trend_result.status)

        if not trend_result.passed:
            # Log rejection to journal
            self._journal.log_rejection(
                symbol=symbol,
                reason=trend_result.rejection_reason or "Trend not bullish",
                stage="Trend_Filter",
                indicator_values={},
            )

    async def _handle_1h_event(self, event: CandleCloseEvent) -> None:
        """
        Handle 1H candle close — run setup detection.

        Pipeline:
        1. Check market regime (must be bullish for LONG setups)
        2. Check volatility gate (ATR14/price ratio within bounds)
        3. Check coin trend status (must be bullish for compression/pullback)
        4. Detect compression breakout, pullback continuation, or momentum breakout
        5. Validate trend filter with setup_type for momentum breakout
        6. If setup detected, score it and create pending trigger

        Args:
            event: 1H CandleCloseEvent for any coin.
        """
        symbol = event.symbol

        # Gate 1: Market regime check
        # For LONG setups, regime must allow longs
        # For SHORT setups, we proceed even when regime is NOT bullish
        regime_allows_longs = self._regime_filter.should_allow_longs()

        # Gate 2: Volatility gate — ATR14/price ratio must be within bounds
        state = self._state_manager.get_state(symbol)
        candles_1h = state.candle_buffers.get("1h", [])

        if candles_1h and len(candles_1h) >= 15:
            # Calculate ATR14 from 1H candle buffer
            import pandas as pd
            df = pd.DataFrame([
                {"high": c.high, "low": c.low, "close": c.close}
                for c in candles_1h
            ])
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["close"].shift()).abs()
            tr3 = (df["low"] - df["close"].shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_series = tr.rolling(window=14).mean()
            atr14 = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0

            if atr14 > 0:
                current_price = candles_1h[-1].close
                passed, ratio_pct = self._volatility_gate.evaluate(atr14, current_price)

                if not passed:
                    self._journal.log_rejection(
                        symbol=symbol,
                        reason=f"Volatility gate rejected: ATR14/price ratio {ratio_pct:.2f}% outside [1.5%, 8.0%]",
                        stage="Volatility_Gate",
                        indicator_values={
                            "atr14": atr14,
                            "price": current_price,
                            "ratio_pct": ratio_pct,
                        },
                    )
                    return

        if not candles_1h:
            return

        # Skip if there's already an active setup or pending trigger
        if state.active_setup is not None or state.pending_trigger is not None:
            return

        setup = None

        # --- LONG detection (only when regime allows longs) ---
        if regime_allows_longs:
            # Gate 3: For compression/pullback, coin trend must be bullish (4H-based)
            if state.trend_status == TrendStatus.BULLISH:
                # Try compression breakout detection
                setup = detect_compression_breakout(candles_1h)
                if setup is None:
                    # Try pullback continuation detection
                    setup = detect_pullback_continuation(candles_1h)

            # Try momentum breakout detection (uses 1H trend filter, Requirement 4.1)
            if setup is None:
                setup = detect_momentum_breakout(candles_1h)
                if setup is not None:
                    # Validate trend for momentum breakout using 1H-based evaluation
                    trend_result = self._trend_filter.evaluate(
                        coin_candles_4h=state.candle_buffers.get("4h", []),
                        setup_type=SetupType.MOMENTUM_BREAKOUT,
                        candles_1h=candles_1h,
                    )
                    if not trend_result.passed:
                        self._journal.log_rejection(
                            symbol=symbol,
                            reason=trend_result.rejection_reason or "Momentum trend not bullish",
                            stage="Trend_Filter",
                            indicator_values={},
                        )
                        setup = None

        # --- SHORT detection (momentum breakdown) ---
        # Shorts are allowed even when market regime is NOT bullish
        # (shorts are good when market is crashing)
        if setup is None:
            setup = detect_momentum_breakdown(candles_1h)
            if setup is not None:
                # For shorts, trend should NOT be bullish (we want bearish)
                trend_result = self._trend_filter.evaluate_for_momentum(candles_1h)
                if trend_result.passed:
                    # Trend is bullish = bad for shorts, reject
                    self._journal.log_rejection(
                        symbol=symbol,
                        reason="Trend is bullish, rejecting SHORT setup",
                        stage="Trend_Filter",
                        indicator_values={},
                    )
                    setup = None

        if setup is None:
            return

        # Fill in the symbol
        setup.symbol = symbol

        # Score the setup
        scored = await self._score_setup(symbol, setup, candles_1h)
        if scored is None:
            return

        # Create pending trigger for 15m confirmation
        pending = PendingTrigger(
            symbol=symbol,
            setup_type=setup.setup_type,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            target_1=setup.target_1,
            target_2=setup.target_2,
            candles_remaining=4,
        )

        # Update state
        self._state_manager.add_active_setup(symbol, setup)
        state.pending_trigger = pending
        state.last_signal_score = scored.composite_score

        # Track last signal time for idle status reporting
        self._last_signal_time = datetime.utcnow()

        # Start trailing stop monitoring (Requirement 6.1)
        signal = scored.signal
        signal_id = f"{symbol}_{setup.setup_type.value}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self._trailing_stop_monitor.start_monitoring(signal, signal_id)

        # Add to active scored setups and re-rank (Requirement 12.5, 20.1)
        self._active_scored_setups.append(scored)
        self._update_rankings()
        await self._emit_alerts()

        logger.info(
            "Setup detected: %s %s | entry=%.4f stop=%.4f score=%.2f",
            symbol,
            setup.setup_type.value,
            setup.entry_price,
            setup.stop_loss,
            scored.composite_score,
        )

    async def _handle_15m_event(self, event: CandleCloseEvent) -> None:
        """
        Handle 15m candle close — check pending trigger confirmation and
        route to trailing stop monitor.

        If a pending trigger exists for this coin, evaluate whether
        the 15m candle confirms the entry. On confirmation, emit alert.
        Also routes the candle to the trailing stop monitor for position tracking.

        Args:
            event: 15m CandleCloseEvent for any coin.
        """
        symbol = event.symbol

        # Route 15m candle to trailing stop monitor (Requirement 6.1)
        await self._trailing_stop_monitor.on_15m_candle(symbol, event.candle)

        state = self._state_manager.get_state(symbol)

        if state.pending_trigger is None:
            return

        pending = state.pending_trigger
        candles_15m = state.candle_buffers.get("15m", [])

        # Check if the parent 1H setup has been invalidated
        setup_invalidated = (
            state.trend_status != TrendStatus.BULLISH
            or not self._regime_filter.should_allow_longs()
        )

        # For SHORT setups, invalidation logic is inverted:
        # A SHORT is invalidated if trend becomes bullish (not bearish)
        if state.active_setup and state.active_setup.direction == SignalDirection.SHORT:
            # SHORT invalidated if trend is bullish (good for longs, bad for shorts)
            trend_result = self._trend_filter.evaluate_for_momentum(
                state.candle_buffers.get("1h", [])
            )
            setup_invalidated = trend_result.passed  # bullish = bad for shorts

        # Check 15m trigger
        confirmed_setup = check_15m_trigger(
            candle_15m=event.candle,
            pending=pending,
            candles_15m=candles_15m,
            setup_invalidated=setup_invalidated,
        )

        if confirmed_setup is not None:
            # Trigger confirmed — emit alert
            logger.info(
                "15m trigger CONFIRMED for %s (%s)",
                symbol,
                confirmed_setup.setup_type.value,
            )

            # Update state
            state.active_setup = confirmed_setup
            state.pending_trigger = None

            # Score and alert
            candles_1h = state.candle_buffers.get("1h", [])
            scored = await self._score_setup(symbol, confirmed_setup, candles_1h)
            if scored is not None:
                await self._try_emit_alert(scored, state)

        elif pending.candles_remaining <= 0:
            # Trigger expired — clean up
            logger.info(
                "15m trigger expired for %s (%s)",
                symbol,
                pending.setup_type.value,
            )
            self._state_manager.expire_setup(symbol, reason="15m_trigger_expired")
            state.pending_trigger = None

            # Log expiry to journal
            self._journal.log_rejection(
                symbol=symbol,
                reason="15m trigger expired: 4-candle window exhausted",
                stage="Setup_Detector",
                indicator_values={
                    "entry_price": pending.entry_price,
                    "candles_remaining": 0,
                },
            )

    # ─── Scoring ──────────────────────────────────────────────────────────────

    async def _score_setup(
        self,
        symbol: str,
        setup: ActiveSetup,
        candles_1h: List[OHLCV],
    ) -> Optional[ScoredSetup]:
        """
        Score a detected setup using the deterministic scoring engine.

        Calculates all 5 scoring inputs:
        - Relative strength (30%)
        - Relative volume (25%)
        - Breakout quality (20%)
        - Trend quality (15%)
        - Market alignment (10%)

        Applies OI/funding adjustments and validates risk-reward ratio.

        Args:
            symbol: The coin symbol.
            setup: The detected ActiveSetup.
            candles_1h: The coin's 1H candle buffer.

        Returns:
            ScoredSetup if valid, None if rejected (e.g., RR < 2.0).
        """
        state = self._state_manager.get_state(symbol)
        btc_state = self._state_manager.get_state(BTC_SYMBOL)
        btc_candles_4h = btc_state.candle_buffers.get("4h", [])
        coin_candles_4h = state.candle_buffers.get("4h", [])

        # Calculate relative strength
        rs_result = self._rs_engine.calculate_for_symbol(
            symbol=symbol,
            coin_candles=coin_candles_4h,
            btc_candles=btc_candles_4h,
        )
        rs_percentile = rs_result.percentile

        # Calculate relative volume
        rvol_score = 50.0  # Default if insufficient data
        if candles_1h and len(candles_1h) >= 30:
            volumes = [c.volume for c in candles_1h[-30:]]
            ma30_vol = sum(volumes) / len(volumes)
            if ma30_vol > 0:
                current_rvol = candles_1h[-1].volume / ma30_vol
                normalized = normalize_rvol(current_rvol, len(candles_1h))
                if normalized is not None:
                    rvol_score = normalized

        # Calculate breakout quality
        breakout_quality_score = 50.0  # Default
        if candles_1h:
            latest_candle = candles_1h[-1]
            # Calculate ATR14 for breakout quality
            if len(candles_1h) >= 15:
                import pandas as pd
                df = pd.DataFrame([
                    {"high": c.high, "low": c.low, "close": c.close}
                    for c in candles_1h
                ])
                tr1 = df["high"] - df["low"]
                tr2 = (df["high"] - df["close"].shift()).abs()
                tr3 = (df["low"] - df["close"].shift()).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr_series = tr.rolling(window=14).mean()
                atr14 = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0

                if atr14 > 0:
                    # Calculate RVOL for breakout quality sub-score
                    bq_rvol = 1.0
                    if len(candles_1h) >= 30:
                        vol_ma = sum(c.volume for c in candles_1h[-30:]) / 30
                        if vol_ma > 0:
                            bq_rvol = latest_candle.volume / vol_ma

                    bq_result = score_breakout_quality(latest_candle, atr14, bq_rvol)
                    breakout_quality_score = float(bq_result.total)

        # Trend quality: based on how many trend conditions pass
        trend_quality = 0.0
        if state.trend_status == TrendStatus.BULLISH:
            trend_quality = 100.0
        elif state.trend_status == TrendStatus.NOT_BULLISH:
            trend_quality = 30.0

        # Market alignment: proportional scoring based on regime conditions
        # Uses N × 20 where N is the number of bullish conditions (0-100)
        # Requirements: 1.4, 1.5, 1.6
        market_alignment = self._regime_filter.get_alignment_score()

        # Build score inputs
        inputs = ScoreInputs(
            relative_strength=rs_percentile,
            relative_volume=rvol_score,
            breakout_quality=breakout_quality_score,
            trend_quality=trend_quality,
            market_alignment=market_alignment,
        )

        # Calculate composite score
        composite = score(inputs)

        # Apply OI/funding adjustments (use default unavailable data)
        oi_data = OIFundingData(data_available=False)
        adjusted_score = apply_oi_adjustments(composite, oi_data)

        # Validate risk-reward
        risk_levels = calculate_risk_levels(
            entry_price=setup.entry_price,
            structure_stop=setup.stop_loss,
            atr14=setup.entry_price - setup.stop_loss,  # Use existing risk as ATR proxy
        )

        if risk_levels is None:
            # RR < 2.0 or invalid — reject
            self._journal.log_rejection(
                symbol=symbol,
                reason="Risk-reward ratio below 2.0",
                stage="Scoring_Engine",
                indicator_values={
                    "entry_price": setup.entry_price,
                    "stop_loss": setup.stop_loss,
                },
            )
            return None

        # Build SetupSignal for the ScoredSetup
        signal = SetupSignal(
            symbol=symbol,
            setup_type=setup.setup_type,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            target_1=setup.target_1,
            target_2=setup.target_2,
            target_3=setup.target_3,
            risk_reward=setup.risk_reward,
            timeframe=setup.timeframe,
            trigger_timeframe=setup.trigger_timeframe,
            direction=setup.direction,
        )

        # Build labels
        labels: List[str] = []
        if oi_data.is_overcrowded:
            labels.append("overcrowded")
        if oi_data.weak_oi_participation:
            labels.append("weak OI participation")

        scored_setup = ScoredSetup(
            signal=signal,
            composite_score=adjusted_score,
            inputs=inputs,
            oi_adjustment=oi_data.score_adjustment,
            labels=labels,
        )

        return scored_setup

    # ─── Alerting ─────────────────────────────────────────────────────────────

    async def _try_emit_alert(
        self, scored_setup: ScoredSetup, state: CoinState
    ) -> None:
        """
        Attempt to emit an alert for a scored setup.

        Checks deduplication/cooldown via the alert manager before sending.

        Args:
            scored_setup: The scored setup to potentially alert on.
            state: The coin's current state.
        """
        symbol = scored_setup.signal.symbol
        setup_type = scored_setup.signal.setup_type
        current_rvol = scored_setup.inputs.relative_volume
        current_score = scored_setup.composite_score
        trend_score = scored_setup.inputs.trend_quality

        should_send = self._alert_manager.should_send(
            symbol=symbol,
            setup_type=setup_type,
            current_rvol=current_rvol,
            current_score=current_score,
            trend_score=trend_score,
        )

        if should_send:
            # Mark as sent in the cache
            self._alert_manager.mark_sent(
                symbol=symbol,
                setup_type=setup_type,
                volume_ratio=current_rvol,
                score=current_score,
            )

            # Log signal to journal
            journal_entry = JournalEntry(
                symbol=symbol,
                setup_type=setup_type,
                entry_price=scored_setup.signal.entry_price,
                stop_loss=scored_setup.signal.stop_loss,
                composite_score=scored_setup.composite_score,
                relative_strength=scored_setup.inputs.relative_strength,
                relative_volume=scored_setup.inputs.relative_volume,
                btc_regime=self._regime_filter.last_result.status,
            )
            self._journal.log_signal(journal_entry)

            logger.info(
                "Alert emitted: %s %s | score=%.2f",
                symbol,
                setup_type.value,
                current_score,
            )

    # ─── Ranking & Alert Emission ────────────────────────────────────────────

    def _update_rankings(self) -> None:
        """
        Re-rank all active scored setups after each scoring update.

        Collects the current list of active ScoredSetups and applies
        rank_setups() to produce the top 5 by composite score (descending),
        with tie-breaking by relative_volume.

        The ranked top-5 list is stored for subsequent alert emission.

        Requirements: 12.5, 20.1
        """
        if not self._active_scored_setups:
            return

        # rank_setups returns top 5 sorted by composite_score desc,
        # tie-break by relative_volume desc
        self._ranked_top5 = rank_setups(self._active_scored_setups)

        logger.debug(
            "Rankings updated: %d active setups, top %d ranked",
            len(self._active_scored_setups),
            len(self._ranked_top5),
        )

    async def _emit_alerts(self) -> None:
        """
        Send alerts for top-5 setups that pass dedup/cooldown checks.

        Iterates through the ranked top-5 setups and for each one:
        1. Checks alert_manager.should_send() for dedup/cooldown
        2. If allowed, marks as sent and emits the alert via _try_emit_alert

        This ensures only the highest-ranked setups that haven't been
        recently alerted are sent to the user.

        Requirements: 2.3, 12.5, 20.1, 20.4
        """
        if not hasattr(self, "_ranked_top5") or not self._ranked_top5:
            return

        for scored_setup in self._ranked_top5:
            symbol = scored_setup.signal.symbol
            setup_type = scored_setup.signal.setup_type
            current_rvol = scored_setup.inputs.relative_volume
            current_score = scored_setup.composite_score
            trend_score = scored_setup.inputs.trend_quality

            should_send = self._alert_manager.should_send(
                symbol=symbol,
                setup_type=setup_type,
                current_rvol=current_rvol,
                current_score=current_score,
                trend_score=trend_score,
            )

            if should_send:
                # Mark as sent in the cache
                self._alert_manager.mark_sent(
                    symbol=symbol,
                    setup_type=setup_type,
                    volume_ratio=current_rvol,
                    score=current_score,
                )

                # Log signal to journal
                journal_entry = JournalEntry(
                    symbol=symbol,
                    setup_type=setup_type,
                    entry_price=scored_setup.signal.entry_price,
                    stop_loss=scored_setup.signal.stop_loss,
                    composite_score=scored_setup.composite_score,
                    relative_strength=scored_setup.inputs.relative_strength,
                    relative_volume=scored_setup.inputs.relative_volume,
                    btc_regime=self._regime_filter.last_result.status,
                )
                self._journal.log_signal(journal_entry)

                logger.info(
                    "Alert emitted (ranked): %s %s | score=%.2f | rank in top-5",
                    symbol,
                    setup_type.value,
                    current_score,
                )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _build_universe_coin_data(
        self, all_states: Dict[str, CoinState]
    ) -> list:
        """
        Build a list of CoinData-like objects for breadth calculation.

        The MarketRegimeFilter expects objects with a
        `price_change_percent_24h` attribute. We approximate this from
        the 4H candle buffers (6 candles = 24h).

        Args:
            all_states: All tracked coin states.

        Returns:
            List of objects with price_change_percent_24h attribute.
        """
        from streaming.models import CoinData

        universe: List[CoinData] = []
        for symbol, state in all_states.items():
            if symbol == BTC_SYMBOL:
                continue

            candles_4h = state.candle_buffers.get("4h", [])
            if len(candles_4h) >= 7:
                # 24h change = (current close - close 6 candles ago) / close 6 candles ago * 100
                old_close = candles_4h[-7].close
                new_close = candles_4h[-1].close
                if old_close > 0:
                    pct_change = ((new_close - old_close) / old_close) * 100.0
                else:
                    pct_change = 0.0

                coin_data = CoinData(
                    symbol=symbol,
                    name=symbol,
                    current_price=new_close,
                    market_cap=0.0,
                    volume_24h=0.0,
                    price_change_24h=new_close - old_close,
                    price_change_percent_24h=pct_change,
                )
                universe.append(coin_data)

        return universe

    # ─── Failover & Error Handling ────────────────────────────────────────────

    # Exchange priority order for failover (primary → secondary → tertiary)
    _EXCHANGE_PRIORITY = ["bybit", "binance", "okx"]

    # Maximum time allowed for failover promotion (seconds)
    _FAILOVER_TIMEOUT_SECONDS = 10.0

    def _register_failure_callback(self) -> None:
        """
        Register the exchange failure callback with the WebSocketManager.

        This connects the MomentumScanner's failover handler to the
        WebSocketManager so that ConnectionFailureEvents are forwarded
        to _handle_exchange_failure for failover processing.

        Should be called during start() after the WebSocketManager is created.

        Requirements: 20.3, 20.6
        """
        self._ws_manager.set_failure_callback(self._handle_exchange_failure)
        logger.info("Exchange failure callback registered with WebSocketManager")

    async def _handle_exchange_failure(
        self, event: ConnectionFailureEvent
    ) -> None:
        """
        Handle an exchange connection failure with failover logic.

        When an exchange connection fails (all reconnection attempts exhausted):
        1. If the failed exchange is primary (binance), attempt to promote
           the next available secondary exchange within 10 seconds.
        2. Events continue to queue in the EventBus during failover — no
           events are discarded.
        3. If ALL configured exchanges have failed, send a Telegram alert
           to notify the operator of total exchange failure.

        Args:
            event: The ConnectionFailureEvent from the failed exchange.

        Requirements: 2.6, 20.3, 20.6, 20.7
        """
        failed_exchange = event.exchange

        logger.warning(
            "Exchange failure detected: %s — reason: %s (attempts: %d)",
            failed_exchange,
            event.reason,
            event.attempts_made,
        )

        # Determine which exchanges are still connected
        connected = self._ws_manager.connected_exchanges
        available_secondaries = [
            ex for ex in self._EXCHANGE_PRIORITY
            if ex != failed_exchange and ex in connected
        ]

        if available_secondaries:
            # Attempt failover to the highest-priority available exchange
            target_exchange = available_secondaries[0]
            logger.info(
                "Attempting failover from %s to %s (timeout: %.1fs)",
                failed_exchange,
                target_exchange,
                self._FAILOVER_TIMEOUT_SECONDS,
            )

            # The secondary is already connected and streaming — events
            # continue to flow through the EventBus without interruption.
            # We just need to verify the secondary is healthy within the
            # timeout window.
            try:
                is_healthy = await asyncio.wait_for(
                    self._verify_exchange_health(target_exchange),
                    timeout=self._FAILOVER_TIMEOUT_SECONDS,
                )

                if is_healthy:
                    logger.info(
                        "Failover successful: %s promoted as active exchange "
                        "(replacing failed %s)",
                        target_exchange,
                        failed_exchange,
                    )
                    return
                else:
                    logger.warning(
                        "Failover target %s is not healthy", target_exchange
                    )
            except asyncio.TimeoutError:
                logger.error(
                    "Failover to %s timed out after %.1fs",
                    target_exchange,
                    self._FAILOVER_TIMEOUT_SECONDS,
                )

        # Check if ALL exchanges have failed
        all_connected = self._ws_manager.connected_exchanges
        if not all_connected:
            logger.critical(
                "TOTAL EXCHANGE FAILURE: All configured exchanges are down"
            )
            await self._send_total_failure_alert(event)

    async def _verify_exchange_health(self, exchange: str) -> bool:
        """
        Verify that a secondary exchange connection is healthy.

        Checks that the exchange connection exists and is currently
        connected (websocket is open and receiving messages).

        Args:
            exchange: The exchange name to verify.

        Returns:
            True if the exchange connection is healthy, False otherwise.
        """
        connections = self._ws_manager.connections
        connection = connections.get(exchange)

        if connection is None:
            return False

        return connection.is_connected

    async def _send_total_failure_alert(
        self, event: ConnectionFailureEvent
    ) -> None:
        """
        Send a Telegram alert when all exchange connections have failed.

        Uses the alert manager's _send_with_retry mechanism to deliver
        a critical notification to the operator.

        Args:
            event: The ConnectionFailureEvent that triggered total failure.

        Requirements: 20.6, 20.7
        """
        import os

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        if not bot_token or not chat_id:
            logger.error(
                "Cannot send total failure alert: TELEGRAM_BOT_TOKEN or "
                "TELEGRAM_CHAT_ID not configured"
            )
            return

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        message = (
            "🚨 <b>CRITICAL: Total Exchange Failure</b>\n\n"
            f"All configured exchange connections have failed.\n"
            f"Last failure: <b>{event.exchange}</b>\n"
            f"Reason: {event.reason}\n"
            f"Attempts exhausted: {event.attempts_made}\n\n"
            f"⚠️ The momentum scanner is no longer receiving live data.\n"
            f"Events queued in the EventBus are preserved.\n"
            f"Manual intervention or restart required.\n\n"
            f"Timestamp: {timestamp}"
        )

        success = await self._alert_manager._send_with_retry(
            message=message,
            chat_id=chat_id,
            bot_token=bot_token,
        )

        if success:
            logger.info("Total exchange failure alert sent via Telegram")
        else:
            logger.error("Failed to send total exchange failure alert via Telegram")

    # ═══════════════════════════════════════════════════════════════════════════
    # AI BOUNDARY ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # CRITICAL DESIGN CONSTRAINT (Requirements 19.1–19.6):
    #
    # The core pipeline (filter → detect → score → alert) is ENTIRELY
    # deterministic and rule-based. NO AI/LLM calls are permitted at any
    # point in the signal generation, scoring, ranking, or filtering path.
    #
    # Specifically, AI/LLM MUST NEVER:
    #   - Generate, score, or influence trading signals (Req 19.1)
    #   - Approve, reject, or modify the ranking of setups (Req 19.2)
    #   - Modify scoring weights, thresholds, or numeric parameters (Req 19.3)
    #   - Adjust strategy logic, filter conditions, or detection rules (Req 19.4)
    #
    # AI/LLM MAY ONLY be used for (Req 19.5):
    #   - End-of-day summary generation (_ai_generate_eod_summary)
    #   - Journal commentary (_ai_add_journal_commentary)
    #   - Analytics narrative formatting (_ai_format_analytics_narrative)
    #   - Telegram message formatting (cosmetic only, no signal alteration)
    #
    # DETERMINISM GUARANTEE (Req 19.6):
    #   Given identical input data, the scanner produces identical outputs
    #   (same signals, same scores, same rankings) regardless of whether
    #   ai_enabled is True or False. AI integration points are strictly
    #   post-pipeline and do not feed back into signal logic.
    #
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def ai_enabled(self) -> bool:
        """Whether optional AI integration points are active."""
        return self._ai_enabled

    def _ai_generate_eod_summary(self) -> Optional[str]:
        """
        Generate an optional end-of-day summary using AI.

        This is a POST-PIPELINE integration point. It summarizes the day's
        signals, rejections, and outcomes in natural language for the trader's
        journal. It does NOT influence signal generation or scoring.

        Returns:
            A natural-language summary string if ai_enabled is True and an
            AI provider is configured, otherwise None.

        Requirements: 19.5
        """
        if not self._ai_enabled:
            return None

        # Stub: wire to an AI provider (e.g., OpenAI, Anthropic) when ready.
        # The provider should receive the day's analytics dict and return
        # a human-readable narrative. No signal data is modified.
        logger.debug("AI EOD summary requested but no provider configured")
        return None

    def _ai_add_journal_commentary(self, signal_id: str) -> Optional[str]:
        """
        Add optional AI-generated commentary to a journal entry.

        This is a POST-PIPELINE integration point. It provides qualitative
        context (e.g., "strong breakout in low-volatility regime") for a
        specific signal after it has already been scored and emitted.
        It does NOT alter the signal, score, or ranking.

        Args:
            signal_id: The unique identifier of the journal signal entry.

        Returns:
            A commentary string if ai_enabled is True and an AI provider
            is configured, otherwise None.

        Requirements: 19.5
        """
        if not self._ai_enabled:
            return None

        # Stub: wire to an AI provider when ready.
        # The provider should receive the signal's context (entry, score,
        # market conditions) and return a brief commentary string.
        logger.debug(
            "AI journal commentary requested for signal %s but no provider configured",
            signal_id,
        )
        return None

    def _ai_format_analytics_narrative(self, analytics: dict) -> Optional[str]:
        """
        Format analytics data into a human-readable narrative using AI.

        This is a POST-PIPELINE integration point. It takes already-computed
        deterministic analytics (win rate, avg RR, best setup type, etc.)
        and produces a readable summary. It does NOT modify the underlying
        analytics values or feed back into scoring/filtering.

        Args:
            analytics: Dictionary of computed analytics metrics (win_rate,
                      avg_rr, best_setup_type, best_hour, etc.).

        Returns:
            A formatted narrative string if ai_enabled is True and an AI
            provider is configured, otherwise None.

        Requirements: 19.5
        """
        if not self._ai_enabled:
            return None

        # Stub: wire to an AI provider when ready.
        # The provider should receive the analytics dict and return a
        # narrative paragraph. The raw analytics remain unchanged.
        logger.debug("AI analytics narrative requested but no provider configured")
        return None
