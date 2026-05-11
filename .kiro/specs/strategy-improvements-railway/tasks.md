# Implementation Plan: Strategy Improvements + Railway Deployment

## Overview

This plan implements 8 strategy improvements to the existing crypto momentum scanner and adds Railway cloud deployment configuration. The implementation follows an incremental approach: core data model changes first, then new components, then modifications to existing components, and finally deployment configuration. Each task builds on previous work and ends with integration wiring.

## Tasks

- [x] 1. Data model updates and new enum values
  - [x] 1.1 Add MOMENTUM_BREAKOUT to SetupType enum and add target_3 field to ActiveSetup, SetupSignal, JournalEntry, and MonitoredPosition dataclass
    - Add `MOMENTUM_BREAKOUT = "momentum_breakout"` to `SetupType` enum in `streaming/models.py`
    - Add `target_3: Optional[float] = None` field to `ActiveSetup`, `SetupSignal`, and `JournalEntry` dataclasses
    - Add `MonitoredPosition` dataclass with fields: symbol, entry_price, stop_loss, current_stop, target_1, target_2, target_3, signal_id, started_at, highest_since_t2, t1_hit, t2_hit, t3_hit, last_data_at
    - Add `UniversePair` dataclass with fields: symbol, volume_24h_usd, current_price, last_updated
    - Add `HealthStatus` dataclass with fields: status, uptime_seconds, monitored_symbols, active_positions
    - _Requirements: 3.1, 8.1, 8.4, 6.1_

  - [x] 1.2 Update config.yaml and WebSocketStreamConfig to support new environment variables
    - Add universe management config section (refresh_minutes, min_volume_usd, min_price)
    - Add volatility gate config section (min_pct, max_pct)
    - Add BTC crash detection config (threshold_pct, candle_count)
    - Add trailing stop config section
    - Update `WebSocketStreamConfig` to read new env vars: `UNIVERSE_REFRESH_MINUTES`, `UNIVERSE_MIN_VOLUME_USD`, `UNIVERSE_MIN_PRICE`, `VOLATILITY_MIN_PCT`, `VOLATILITY_MAX_PCT`, `BTC_CRASH_THRESHOLD_PCT`, `BTC_CRASH_CANDLE_COUNT`
    - _Requirements: 9.4, 2.1, 5.1_

- [x] 2. Implement Relaxed BTC Regime Filter
  - [x] 2.1 Add `is_crashing()` method and `get_alignment_score()` method to MarketRegimeFilter
    - Add `is_crashing(btc_candles_1h: List[OHLCV]) -> bool` that checks if BTC declined > 3% across last 4 consecutive 1H candles (percentage from open of first to close of last)
    - Add `get_alignment_score() -> float` that returns count of bullish conditions × 20 (0-100 scale)
    - Modify `should_allow_longs()` to return `not self.is_crashing(btc_candles_1h)` instead of requiring all 5 conditions
    - Store 1H BTC candles reference for crash detection
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [ ]* 2.2 Write property test for BTC Crash Gate (Property 1)
    - **Property 1: BTC Crash Gate Correctness**
    - Use Hypothesis to generate random 4-candle sequences with varying open/close prices
    - Verify gate blocks iff decline from first open to last close exceeds 3%
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 2.3 Write property test for Market Alignment Proportional Scoring (Property 2)
    - **Property 2: Market Alignment Proportional Scoring**
    - Use Hypothesis to generate random boolean combinations of 5 regime conditions
    - Verify score equals count of True conditions × 20
    - **Validates: Requirements 1.4, 1.5, 1.6**

- [x] 3. Implement Dynamic Universe Selection
  - [x] 3.1 Create `universe/universe_manager.py` with UniverseManager class
    - Implement `__init__` with configurable min_volume_usd (default 50M) and min_price (default 0.10)
    - Implement `async initialize() -> List[str]` that fetches top 100 USDT pairs by 24h volume from Binance REST API using ccxt
    - Implement `async refresh() -> Tuple[List[str], List[str]]` returning (added, removed) symbols
    - Implement `get_active_symbols() -> List[str]`
    - Filter pairs: exclude volume < 50M USD, exclude price < 0.10 USD
    - Always include BTCUSDT regardless of filters
    - On API failure: retain previous list, retry after 5 minutes
    - Log each refresh with count of added/removed symbols
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.9_

  - [ ]* 3.2 Write property test for Universe Filtering Invariants (Property 3)
    - **Property 3: Universe Filtering Invariants**
    - Use Hypothesis to generate random pair lists with varying volume and price values
    - Verify filtered universe contains only pairs meeting volume/price thresholds plus BTCUSDT
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 3.3 Integrate UniverseManager into MomentumScanner orchestrator
    - Initialize UniverseManager in `MomentumScanner.__init__()`
    - Call `initialize()` during `start()` to get initial symbol list
    - Schedule `refresh()` every 60 minutes using asyncio task
    - On refresh: call `WebSocketManager.subscribe(added)` and `WebSocketManager.unsubscribe(removed)` within 30 seconds
    - _Requirements: 2.6, 2.7_

- [x] 4. Implement Simple Momentum Breakout Entry
  - [x] 4.1 Add `detect_momentum_breakout()` function to `detectors/setup_detector.py`
    - Implement detection logic: close > EMA20 (1H) AND last 3 candles have higher highs AND volume > 2.5× 20-period volume MA
    - Set entry price to current 1H candle close
    - Calculate raw stop-loss as tighter (higher) of: swing_low_3 × 0.995, or entry − 1.5 × ATR14
    - Enforce minimum stop distance of 0.8% from entry
    - Enforce maximum stop distance of 2.5% from entry
    - Clamp stop-loss to [0.8%, 2.5%] range if outside bounds
    - Calculate T1 (1R), T2 (2R), T3 (5R)
    - Return `ActiveSetup` with `setup_type=SetupType.MOMENTUM_BREAKOUT`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1_

  - [ ]* 4.2 Write property test for Momentum Breakout Detection (Property 4)
    - **Property 4: Momentum Breakout Detection Conditions**
    - Use Hypothesis to generate random 1H candle sequences
    - Verify signal emitted iff all 3 conditions met (close > EMA20, 3 higher highs, volume > 2.5× MA20)
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 4.3 Write property test for Stop-Loss Clamping (Property 5)
    - **Property 5: Momentum Breakout Stop-Loss Clamping**
    - Use Hypothesis to generate random entry prices, ATR14 values, and swing lows
    - Verify final stop-loss distance is always within [0.8%, 2.5%] of entry
    - **Validates: Requirements 3.4, 3.5, 3.6, 3.7**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Relaxed Trend Filter for Momentum Entries
  - [x] 6.1 Modify TrendFilter to support setup-type-specific evaluation
    - Add `evaluate_for_momentum(candles_1h: List[OHLCV]) -> TrendResult` method that only checks close > EMA20 on 1H
    - Modify `evaluate()` to accept optional `setup_type` parameter
    - When `setup_type == MOMENTUM_BREAKOUT`: delegate to `evaluate_for_momentum()`
    - When `setup_type` is COMPRESSION_BREAKOUT or PULLBACK_CONTINUATION: require all 3 existing 4H conditions
    - Reduce `MIN_CANDLES` from 200 to 50 for COMPRESSION_BREAKOUT and PULLBACK_CONTINUATION evaluations
    - If fewer than 50 candles available for non-momentum setups: reject with insufficient data status
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 6.2 Write property test for Trend Filter Routing (Property 6)
    - **Property 6: Trend Filter Setup-Type Routing**
    - Use Hypothesis to generate random candle data and setup types
    - Verify MOMENTUM_BREAKOUT only checks 1H close > EMA20
    - Verify COMPRESSION_BREAKOUT/PULLBACK_CONTINUATION require all 3 4H conditions with min 50 candles
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 7. Implement Per-Coin ATR Volatility Gate
  - [x] 7.1 Create `filters/volatility_gate.py` with VolatilityGate class
    - Implement `evaluate(atr14: float, current_price: float) -> Tuple[bool, float]`
    - Calculate ratio as (ATR14 / current_price) × 100
    - Return (True, ratio) if 1.5% ≤ ratio ≤ 8.0%
    - Return (False, ratio) if ratio < 1.5% or ratio > 8.0%
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.2 Integrate VolatilityGate into MomentumScanner `_handle_1h_event()`
    - Call VolatilityGate.evaluate() before trend filter evaluation
    - On rejection: log to JournalStore with symbol, ATR14, price, and ratio
    - Skip coin for this cycle if rejected
    - _Requirements: 5.4, 5.5_

  - [ ]* 7.3 Write property test for Volatility Gate Threshold (Property 7)
    - **Property 7: Volatility Gate Threshold**
    - Use Hypothesis to generate random ATR14 and price pairs
    - Verify gate passes iff 1.5% ≤ (ATR14/price × 100) ≤ 8.0%
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 8. Implement Trailing Stop Monitoring
  - [x] 8.1 Create `monitors/trailing_stop_monitor.py` with TrailingStopMonitor class
    - Implement `start_monitoring(signal: SetupSignal, signal_id: str)` to begin tracking a position
    - Implement `async on_15m_candle(symbol: str, candle: OHLCV)` with trailing logic:
      - When price reaches T1: move stop to entry (breakeven)
      - When price reaches T2: begin trailing at 1% below highest close since T2
      - Update trailing stop on each 15m close (never decrease)
    - When trailing stop hit (close < trailing stop): record exit price and calculate actual RR
    - When T3 reached: record exit as win with actual RR
    - Log warning if no data for 30 minutes, continue on next candle
    - Send Telegram message via AlertManager when stop level changes
    - Update JournalStore with exit price, actual RR, and duration
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 8.5_

  - [ ]* 8.2 Write property test for Trailing Stop at T1 (Property 8)
    - **Property 8: Trailing Stop at T1 Moves to Breakeven**
    - Use Hypothesis to generate random price sequences reaching T1
    - Verify stop moves to entry price when T1 is hit
    - **Validates: Requirements 6.2**

  - [ ]* 8.3 Write property test for Trailing Stop After T2 (Property 9)
    - **Property 9: Trailing Stop After T2 Tracks Highest Price**
    - Use Hypothesis to generate random price sequences after T2
    - Verify trailing stop = 0.99 × highest close since T2, never decreases
    - **Validates: Requirements 6.3, 6.4**

  - [ ]* 8.4 Write property test for Exit RR Calculation (Property 10)
    - **Property 10: Exit Risk-Reward Calculation**
    - Use Hypothesis to generate random exit scenarios
    - Verify actual RR = (exit_price − entry_price) / (entry_price − original_stop_loss)
    - **Validates: Requirements 6.6, 8.5**

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Periodic Status Messages
  - [x] 10.1 Create `monitors/status_reporter.py` with StatusReporter class
    - Implement `async send_startup_message(symbol_count: int)` sending "🟢 Scanner started" with symbol count
    - Implement `async send_daily_summary()` at 00:00 UTC with: total signals today, win rate %, best symbol
    - Implement `async check_idle_status(last_signal_time: Optional[datetime])` sending "✅ Scanner active. No setups found." with BTC regime status if no signals for 4+ hours
    - Rate limit: max one "no setups" message per 4-hour window
    - Retry Telegram delivery up to 2 times with 5-second intervals on failure
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 10.2 Write property test for Status Message Rate Limiting (Property 11)
    - **Property 11: Status Message Rate Limiting**
    - Use Hypothesis to generate random sequences of idle checks within 4-hour windows
    - Verify at most one "no setups" message emitted per window
    - **Validates: Requirements 7.4**

- [x] 11. Implement T3 Target and Update Alert Formatting
  - [x] 11.1 Update Setup_Detector to calculate T3 (5R) for all setup types
    - In `detect_compression_breakout()`: add `target_3 = entry_price + 5 * risk`
    - In `detect_pullback_continuation()`: add `target_3 = entry_price + 5 * risk`
    - In `detect_momentum_breakout()`: add `target_3 = entry_price + 5 * risk` (already done in 4.1)
    - _Requirements: 8.1_

  - [x] 11.2 Update Alert_Manager `_format_telegram_message()` to include T3 and position sizing
    - Add T3 value to the Entry/Exit section of the Telegram message
    - Add position sizing recommendation: "Take 40% at T1, 40% at T2, let 20% run to T3"
    - _Requirements: 8.2, 8.3_

  - [x] 11.3 Update JournalStore to persist T3 value alongside T1 and T2
    - Modify signal logging to include target_3 field
    - _Requirements: 8.4_

  - [ ]* 11.4 Write property test for T3 Calculation (Property 12)
    - **Property 12: T3 Calculation**
    - Use Hypothesis to generate random entry prices and stop-loss values
    - Verify T3 = entry + 5 × (entry − stop_loss)
    - **Validates: Requirements 8.1**

  - [ ]* 11.5 Write property test for T3 in Signal Outputs (Property 13)
    - **Property 13: T3 Included in Signal Outputs**
    - Use Hypothesis to generate random signal data
    - Verify T3 present in formatted Telegram message and journal record
    - **Validates: Requirements 8.2, 8.4**

- [x] 12. Implement Scoring Engine Market Alignment Update
  - [x] 12.1 Modify Scoring_Engine to use proportional market_alignment scoring
    - Update `_handle_1h_event()` in MomentumScanner to pass `regime_filter.get_alignment_score()` as market_alignment input instead of binary 0/100
    - When all 5 conditions bullish: market_alignment = 100
    - When N < 5 conditions bullish: market_alignment = N × 20
    - _Requirements: 1.4, 1.5, 1.6_

- [x] 13. Integrate new components into MomentumScanner orchestrator
  - [x] 13.1 Wire VolatilityGate, TrailingStopMonitor, and StatusReporter into MomentumScanner
    - Initialize VolatilityGate, TrailingStopMonitor, StatusReporter in `__init__()`
    - Call `status_reporter.send_startup_message()` in `start()`
    - Route 15m candle events to `trailing_stop_monitor.on_15m_candle()` in `_handle_15m_event()`
    - Call `trailing_stop_monitor.start_monitoring()` when a signal is emitted
    - Schedule `status_reporter.check_idle_status()` every 30 minutes
    - Schedule `status_reporter.send_daily_summary()` at 00:00 UTC
    - Update `_handle_1h_event()` to call VolatilityGate before trend filter
    - Update `_handle_1h_event()` to pass setup_type to trend filter
    - Update `_handle_1h_event()` to try `detect_momentum_breakout()` as third detection option
    - _Requirements: 5.4, 6.1, 7.1, 7.2, 7.3, 3.1, 4.1_

- [x] 14. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Railway Deployment Configuration
  - [x] 15.1 Create Railway deployment files (Procfile, railway.toml, nixpacks.toml, .dockerignore)
    - Create `Procfile` with: `worker: python main_momentum.py`
    - Create `railway.toml` with build and deploy configuration for worker process
    - Create `nixpacks.toml` specifying Python provider
    - Create `.dockerignore` excluding: data/, logs/, .env, __pycache__/, .git/, venv/, *.db
    - _Requirements: 9.1, 9.2, 9.3, 9.7_

  - [x] 15.2 Implement health check endpoint in `health/health_server.py`
    - Create `HealthCheckServer` class with aiohttp
    - Start HTTP server only when `PORT` env var is set
    - Respond to any request with HTTP 200 and JSON body: `{"status": "healthy", "uptime_seconds": ..., "monitored_symbols": ..., "active_positions": ...}`
    - Ensure response within 1 second
    - Integrate into MomentumScanner: start in `start()`, stop in `stop()`
    - _Requirements: 9.5, 9.9_

  - [x] 15.3 Update requirements.txt and ensure SIGTERM graceful shutdown
    - Add `ccxt>=4.0.0` to requirements.txt for Binance REST API
    - Add `hypothesis>=6.0.0` to requirements.txt for property tests
    - Verify SIGTERM handler completes shutdown within 10 seconds: save state, close WebSockets, stop monitors, stop health server
    - Update shutdown sequence to include new components (TrailingStopMonitor state, UniverseManager timer cancellation)
    - _Requirements: 9.6, 9.8_

  - [ ]* 15.4 Write unit tests for Railway configuration and health check
    - Test Procfile content declares worker process
    - Test health check returns valid JSON with required fields
    - Test health check responds within 1 second
    - Test graceful shutdown completes within 10 seconds
    - _Requirements: 9.1, 9.5, 9.6, 9.9_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Python with Hypothesis for property-based testing
- All new components follow the existing event-driven architecture pattern
- Railway deployment is conditional: health check only starts when PORT env var is set

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1", "7.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "4.1", "6.1", "7.3"] },
    { "id": 3, "tasks": ["3.3", "4.2", "4.3", "6.2", "7.2"] },
    { "id": 4, "tasks": ["8.1", "10.1", "11.1", "12.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4", "10.2", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 6, "tasks": ["13.1"] },
    { "id": 7, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 8, "tasks": ["15.4"] }
  ]
}
```
