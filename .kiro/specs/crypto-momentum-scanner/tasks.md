# Implementation Plan: Crypto Momentum Scanner

## Overview

Transform the existing polling-based REST crypto scanner into a websocket-streaming, event-driven momentum scanning engine. Implementation proceeds bottom-up: data models and configuration first, then streaming infrastructure, processing pipeline components, scoring/alerting, and finally the orchestrator that wires everything together.

## Tasks

- [x] 1. Set up data models, configuration, and project structure
  - [x] 1.1 Create data models module (`streaming/models.py`)
    - Define all enums: `TrendStatus`, `SetupType`, `SetupState`, `SignalOutcomeType`
    - Define all dataclasses: `WebSocketConfig`, `CandleCloseEvent`, `ConnectionFailureEvent`, `ActiveSetup`, `PendingTrigger`, `RelativeStrength`, `OIFundingData`, `BreakoutQualityScore`, `CoinState`, `CompressionZone`, `SetupSignal`, `ScoreInputs`, `ScoredSetup`, `JournalEntry`, `AlertCacheEntry`
    - Ensure all fields have proper type annotations and defaults
    - _Requirements: 2.2, 6.1, 7.1, 8.1, 9.1, 11.1, 12.1, 17.1_

  - [x] 1.2 Create configuration extension (`config/websocket_config.py`)
    - Implement `WebSocketStreamConfig` dataclass with env-var-driven defaults
    - Add fields for all exchange URLs, enable flags, reconnect settings, max coins, alert cooldown, journal retention
    - Integrate with existing `config/__init__.py`
    - _Requirements: 1.1, 1.2, 1.3, 15.2, 17.7, 20.4_

  - [x] 1.3 Create directory structure for new modules
    - Create directories: `streaming/`, `detectors/`, `scoring/`, `storage/`, `core/`
    - Add `__init__.py` files to each new package
    - _Requirements: N/A (infrastructure)_

- [x] 2. Implement WebSocket streaming layer
  - [x] 2.1 Implement `ExchangeConnection` class (`streaming/websocket_manager.py`)
    - Implement `connect()` with 10-second timeout
    - Implement `disconnect()` for graceful shutdown
    - Implement `_reconnect_with_backoff()` with exponential backoff (initial 1s, max 5 attempts)
    - Handle connection drop detection and automatic reconnection
    - _Requirements: 1.1, 1.5, 1.8, 1.9, 20.3_

  - [x] 2.2 Implement `WebSocketManager` class (`streaming/websocket_manager.py`)
    - Implement `start()` to establish connections to all configured exchanges
    - Implement `stop()` for graceful shutdown of all connections
    - Implement `_subscribe_streams()` to subscribe to kline streams for 4H/1H/15m timeframes
    - Implement `_handle_message()` to parse raw messages, validate (discard zero volume/malformed), and emit to event bus
    - Implement `_validate_message()` for message integrity checks
    - Support Binance (primary), Bybit, and OKX message formats
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 20.3, 20.6_

  - [ ]* 2.3 Write unit tests for WebSocket streaming layer
    - Test connection establishment and timeout handling
    - Test reconnection with exponential backoff
    - Test message validation (zero volume, malformed fields)
    - Test multi-exchange subscription
    - _Requirements: 1.1, 1.4, 1.5, 1.8, 1.9_

- [x] 3. Implement Event Bus
  - [x] 3.1 Implement `EventBus` class (`streaming/event_bus.py`)
    - Implement async queue with configurable max size (default 10000)
    - Implement `emit()` with per-coin+timeframe latest-event semantics (replace stale events)
    - Implement `consume()` as async iterator yielding most-recent-per-coin events
    - Implement `get_queue_depth()` for monitoring
    - Handle backpressure when queue is full
    - _Requirements: 2.1, 2.4, 2.7, 20.7_

  - [ ]* 3.2 Write unit tests for EventBus
    - Test stale event discard logic
    - Test backpressure handling
    - Test concurrent emit/consume
    - _Requirements: 2.1, 2.7_

- [x] 4. Implement StateManager
  - [x] 4.1 Implement `StateManager` class (`core/state_manager.py`)
    - Implement `get_state()` and `update_candle()` for per-coin state tracking
    - Implement `set_trend_status()`, `add_active_setup()`, `expire_setup()`
    - Implement `save_state()` for crash recovery persistence (JSON file)
    - Implement `restore_state()` for startup state restoration
    - Implement `get_all_states()` for bulk access
    - Support up to 300 concurrent coin states with rolling candle buffers
    - _Requirements: 2.2, 2.5, 20.4, 20.5_

  - [ ]* 4.2 Write unit tests for StateManager
    - Test state persistence and restoration
    - Test candle buffer management
    - Test setup lifecycle (add, expire, invalidate)
    - _Requirements: 2.2, 20.5_

- [x] 5. Checkpoint - Core infrastructure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Market Regime Filter
  - [x] 6.1 Implement `MarketRegimeFilter` class (`filters/market_regime_filter.py`)
    - Implement `evaluate()` computing all 5 BTC conditions: trend (price > EMA200), momentum (EMA20 > EMA50), direction (EMA200 rising over 5 candles), volatility (ATR% 1.0-3.0%), breadth (>50% coins positive 24h)
    - Implement `should_allow_longs()` returning True only when all 5 conditions are bullish
    - Handle insufficient data case (<200 candles → indeterminate)
    - Use existing `IndicatorEngine` for EMA/ATR calculations
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 6.2 Write unit tests for MarketRegimeFilter
    - Test each of the 5 conditions individually
    - Test composite gate logic (all bullish vs any not bullish)
    - Test insufficient data handling
    - _Requirements: 3.1, 3.7, 3.8, 3.9_

- [x] 7. Implement Trend Filter
  - [x] 7.1 Implement `TrendFilter` class (`filters/trend_filter.py`)
    - Implement `evaluate()` checking 3 conditions: price above EMA200, EMA20 above EMA50, EMA200 rising over 5 candles
    - Return `TrendResult` with pass/fail and individual condition status
    - Handle insufficient data (<200 4H candles → reject)
    - Use existing `IndicatorEngine` for EMA calculations
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 7.2 Write unit tests for TrendFilter
    - Test each trend condition individually
    - Test composite pass/fail logic
    - Test insufficient data rejection
    - _Requirements: 4.1, 4.4, 4.5, 4.7_

- [x] 8. Implement Relative Strength Engine
  - [x] 8.1 Implement `RelativeStrengthEngine` class (`engines/relative_strength_engine.py`)
    - Implement `calculate()` for rolling 4H and 24H relative performance vs BTC
    - Implement momentum acceleration (current 4H RS - previous 4H RS)
    - Implement `rank_all()` for percentile normalization (0-100 scale)
    - Implement `get_stale_status()` for BTC data staleness detection (>60s)
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6_

  - [ ]* 8.2 Write unit tests for RelativeStrengthEngine
    - Test RS calculation against known values
    - Test percentile ranking
    - Test stale data handling
    - _Requirements: 5.1, 5.5, 5.6_

- [x] 9. Implement Setup Detector
  - [x] 9.1 Implement Compression Breakout detection (`detectors/setup_detector.py`)
    - Implement `detect_compression_breakout()`: identify compression zones (3-8 candles with ATR < 75% of ATR14), monitor for decreasing sell pressure, detect breakout (close above zone high, volume > 1.5x MA30, close in upper 33%)
    - Set entry at breakout candle high, stop-loss at lower of zone low or entry - 1.2*ATR14
    - Implement zone expiry after 12 candles
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 9.2 Implement Pullback Continuation detection (`detectors/setup_detector.py`)
    - Implement `detect_pullback_continuation()`: monitor pullbacks to EMA20/EMA50 (within 0.5%), detect bullish reclaim candle (close above EMA, upper 50% range, volume > 1.5x MA30)
    - Set entry at trigger candle high, stop-loss at lower of trigger candle low or entry - 1.2*ATR14
    - Implement invalidation when price closes below EMA by >1.0%
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 9.3 Implement 15m entry trigger confirmation (`detectors/setup_detector.py`)
    - Implement `check_15m_trigger()`: confirm when 15m candle closes above entry with volume > 1.5x MA30
    - Implement 4-candle (1 hour) expiry window
    - Implement rejection for insufficient volume triggers
    - Implement cancellation when 1H setup is invalidated during confirmation window
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 9.4 Implement setup expiry and lifecycle management (`detectors/setup_detector.py`)
    - Implement `expire_stale_setups()` for time-based expiry
    - Log all expirations and cancellations to journal
    - _Requirements: 6.7, 8.3, 8.5_

  - [ ]* 9.5 Write unit tests for SetupDetector
    - Test compression zone identification with various candle sequences
    - Test breakout validation (volume, close position, zone breach)
    - Test pullback detection and invalidation
    - Test 15m trigger confirmation and expiry
    - _Requirements: 6.1, 6.3, 6.4, 7.2, 7.3, 8.2, 8.3_

- [x] 10. Checkpoint - Detection pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Scoring Engine
  - [x] 11.1 Implement composite scoring (`scoring/scoring_engine.py`)
    - Implement `score()` with fixed weights: RS 30%, RVOL 25%, breakout quality 20%, trend quality 15%, market alignment 10%
    - Implement min-max normalization of all inputs to 0-100 scale
    - Round composite score to 2 decimal places
    - _Requirements: 12.1, 12.2, 12.6_

  - [x] 11.2 Implement breakout quality scoring (`scoring/scoring_engine.py`)
    - Implement `score_breakout_quality()` with 5 sub-scores (body ratio, close position, range expansion, momentum acceleration, RVOL), each 0-20 points
    - Handle zero-range candle edge case (score = 0)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [x] 11.3 Implement relative volume normalization (`scoring/scoring_engine.py`)
    - Implement `normalize_rvol()`: RVOL 1.0→0, 3.0→100, linear interpolation
    - Handle insufficient volume history (<30 periods → exclude)
    - Handle zero/missing volume (RVOL = 0, invalid)
    - _Requirements: 14.1, 14.2, 14.3, 14.5, 14.6_

  - [x] 11.4 Implement OI/funding adjustments and ranking (`scoring/scoring_engine.py`)
    - Implement `apply_oi_adjustments()`: -20% for extreme funding, -15% for declining OI with rising price
    - Implement `rank_setups()`: descending by composite score, tie-break by relative_volume
    - Return top 5 setups
    - Handle unavailable OI/funding data gracefully
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.3, 12.4, 12.5_

  - [x] 11.5 Implement ATR-based risk management in scoring context (`scoring/scoring_engine.py`)
    - Calculate stop-loss as wider of structure stop and entry - 1.2*ATR14
    - Calculate Target1 (1R) and Target2 (2R)
    - Reject setups with RR < 2.0
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.5_

  - [ ]* 11.6 Write unit tests for ScoringEngine
    - Test composite score calculation with known inputs
    - Test breakout quality sub-scores at each threshold
    - Test RVOL normalization edge cases
    - Test OI adjustments and ranking
    - Test RR rejection threshold
    - _Requirements: 12.1, 13.1, 14.3, 11.3, 9.5_

- [x] 12. Implement Alert Manager
  - [x] 12.1 Implement `MomentumAlertManager` class (`alerts/momentum_alert_manager.py`)
    - Implement `should_send()` with cooldown check (default 4h, configurable 1-48h)
    - Implement volume-override logic (send if current RVOL exceeds previous by 50+ percentage points)
    - Implement score threshold override (send when score crosses threshold regardless of cooldown)
    - Implement cache invalidation on stop-loss breach or trend score < 40
    - Maintain state cache keyed by symbol+setup_type, max 500 entries
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

  - [x] 12.2 Implement Telegram alert formatting and delivery (`alerts/momentum_alert_manager.py`)
    - Implement `_format_telegram_message()` with labeled sections: Signal, Entry/Exit, Market Context, Scoring
    - Include: symbol, setup type, entry, stop-loss, risk%, Target1, Target2, RS, RVOL, OI change, funding rate, trend score, composite score, UTC timestamp (ISO-8601)
    - Add directional emoji (🟢 LONG)
    - Enforce 4096 char limit
    - Display "N/A" for unavailable fields
    - Include 50% exit recommendation at Target1, EMA20 trailing stop for remainder
    - _Requirements: 16.1, 16.2, 16.3, 16.5, 16.7, 16.8, 10.3, 10.4_

  - [x] 12.3 Implement retry logic for Telegram delivery (`alerts/momentum_alert_manager.py`)
    - Implement `_send_with_retry()`: 2 retries, 5-second intervals, 10-second timeout
    - Log failure if all attempts fail
    - _Requirements: 16.6_

  - [ ]* 12.4 Write unit tests for MomentumAlertManager
    - Test cooldown enforcement
    - Test volume-override bypass
    - Test cache invalidation
    - Test message formatting and character limit
    - Test retry logic
    - _Requirements: 15.1, 15.2, 15.3, 15.5, 16.5, 16.6, 16.8_

- [x] 13. Implement Journal Store
  - [x] 13.1 Implement `JournalStore` class (`storage/journal_store.py`)
    - Implement `log_signal()` persisting all required fields (symbol, setup type, entry, stop, score, RS, RVOL, OI, funding, EMAs, ATR, BTC regime, timestamp)
    - Implement `log_rejection()` with reason, stage, indicator values, timestamp
    - Implement `record_outcome()` with outcome type, actual RR, time to outcome, exit price
    - Implement `check_outcome()` monitoring price vs stop-loss and Target1 (win/loss/expiry after 7 days)
    - Use JSON file persistence in `data/journal/` directory
    - Enforce 90-day retention
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.7_

  - [x] 13.2 Implement analytics generation (`storage/journal_store.py`)
    - Implement `generate_daily_analytics()`: win rate, avg RR, best setup type, best BTC regime, best hour (UTC)
    - Handle zero-signal days (report zeros)
    - Implement `get_rolling_stats()`: 30-day rolling performance by setup type
    - Mark setup types with <5 trades as insufficient data
    - Store analytics reports with 90-day retention
    - _Requirements: 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

  - [ ]* 13.3 Write unit tests for JournalStore
    - Test signal logging and retrieval
    - Test outcome determination logic
    - Test analytics calculation
    - Test retention enforcement
    - _Requirements: 17.1, 17.3, 17.5, 18.1_

- [x] 14. Checkpoint - Scoring, alerting, and journaling
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Implement MomentumScanner orchestrator
  - [x] 15.1 Implement `MomentumScanner` class (`core/momentum_scanner.py`)
    - Implement `start()`: initialize all components, establish WS connections, restore state, begin event processing
    - Implement `stop()`: graceful shutdown (save state, close connections)
    - Implement `_process_event()`: route candle events through the full pipeline (regime filter → trend filter → setup detection → scoring → alerting)
    - Handle BTC events specially (update regime filter)
    - Handle 4H events (update trend filter)
    - Handle 1H events (setup detection)
    - Handle 15m events (trigger confirmation)
    - _Requirements: 2.1, 2.3, 2.5, 2.6, 20.1, 20.2, 20.5_

  - [x] 15.2 Implement ranking and alert emission (`core/momentum_scanner.py`)
    - Implement `_update_rankings()`: re-rank all active setups after each scoring update
    - Implement `_emit_alerts()`: send alerts for top-5 setups that pass dedup/cooldown
    - Ensure pipeline completes within 500ms target
    - Support 50 concurrent coin updates via async processing
    - _Requirements: 2.3, 12.5, 20.1, 20.4_

  - [x] 15.3 Implement failover and error handling (`core/momentum_scanner.py`)
    - Handle exchange failover (primary → secondary within 10s)
    - Queue events during failover (no discard)
    - Handle per-coin processing errors (log, skip, continue)
    - Send Telegram alert on total exchange failure
    - _Requirements: 2.6, 20.3, 20.6, 20.7_

  - [x] 15.4 Implement AI boundary enforcement (`core/momentum_scanner.py`)
    - Ensure no AI/LLM calls in filter-detect-score pipeline
    - Add optional AI integration points for: EOD summary, journal commentary, analytics narrative, message formatting only
    - Ensure deterministic output given identical input regardless of AI enable/disable state
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6_

  - [ ]* 15.5 Write integration tests for MomentumScanner
    - Test full pipeline with mock websocket data
    - Test event routing by timeframe
    - Test failover behavior
    - Test deterministic output (same input → same output)
    - _Requirements: 2.1, 19.6, 20.1, 20.3_

- [x] 16. Update entry point and environment configuration
  - [x] 16.1 Create new entry point (`main_momentum.py`)
    - Wire `MomentumScanner` with configuration
    - Add graceful shutdown signal handling (SIGINT, SIGTERM)
    - Add startup logging with configuration summary
    - _Requirements: 20.5_

  - [x] 16.2 Update environment configuration
    - Update `.env.example` with all new environment variables (WS URLs, enable flags, reconnect settings, cooldown, retention)
    - Update `config.yaml` with momentum scanner section
    - _Requirements: 1.1, 15.2, 17.7_

- [x] 17. Final checkpoint - Full system integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The existing `IndicatorEngine` is reused for all EMA/RSI/ATR/BB calculations — no reimplementation needed
- JSON file persistence is used for journal and state (consistent with existing project patterns)
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end pipeline behavior

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2"] },
    { "id": 3, "tasks": ["2.3", "6.1", "7.1", "8.1"] },
    { "id": 4, "tasks": ["6.2", "7.2", "8.2", "9.1"] },
    { "id": 5, "tasks": ["9.2", "9.3", "11.1"] },
    { "id": 6, "tasks": ["9.4", "9.5", "11.2", "11.3"] },
    { "id": 7, "tasks": ["11.4", "11.5", "12.1", "13.1"] },
    { "id": 8, "tasks": ["11.6", "12.2", "12.3", "13.2"] },
    { "id": 9, "tasks": ["12.4", "13.3"] },
    { "id": 10, "tasks": ["15.1"] },
    { "id": 11, "tasks": ["15.2", "15.3", "15.4"] },
    { "id": 12, "tasks": ["15.5", "16.1", "16.2"] }
  ]
}
```
