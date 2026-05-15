# Crypto Scanner - Known Issues & Status

## Summary

This document tracks the current state of issues, resolved items, and remaining gaps
for the crypto momentum scanner (WebSocket-based event-driven architecture).

**Architecture:** Event-driven pipeline using WebSocket streaming (Bybit/Binance/OKX)
with real-time candle close processing across 4H, 1H, and 15m timeframes.

**Entry point:** `main_momentum.py` → `core/momentum_scanner.py`

---

## 1. Signal Detection & Technical Patterns

### 1.1 Setup Types Implemented ✅

The scanner detects 3 setup types on the 1H timeframe with 15m confirmation:

| Setup Type | Direction | Detection Logic |
|---|---|---|
| Compression Breakout | LONG | 3-8 candles with range < 75% ATR14, breakout with volume > 1.5x MA30, close in upper 33% |
| Pullback Continuation | LONG | Price pulls back to EMA20/EMA50 (within 0.5%), bullish reclaim candle, volume > 1.5x MA30 |
| Momentum Breakout | LONG | Close > EMA20, 3 consecutive higher highs, volume > 2.5x MA20 |
| Momentum Breakdown | SHORT | Close < EMA20, 3 consecutive lower lows, volume > 2.5x MA20 |

**Status:** All 4 patterns are implemented in `detectors/setup_detector.py`.

### 1.2 SHORT Signals Working ✅

SHORT signals (momentum breakdown) are detected even when the market regime
doesn't allow longs. The trend filter correctly rejects shorts when the trend
is bullish (good for longs = bad for shorts).

### 1.3 15m Entry Confirmation ✅

All setups require 15m candle confirmation within a 4-candle window (1 hour):
- Price must close above entry price
- Volume must exceed 1.5x the 15m 30-period volume MA
- Setup is cancelled if parent 1H setup is invalidated

---

## 2. Scoring System

### 2.1 Deterministic Composite Scoring ✅

Fixed-weight formula (no AI involvement):
- Relative Strength vs BTC: 30%
- Relative Volume: 25%
- Breakout Quality: 20%
- Trend Quality: 15%
- Market Alignment: 10%

Score range: 0-100. OI/funding adjustments applied multiplicatively.

### 2.2 AI is Post-Pipeline Only ✅

AI integration is strictly post-pipeline (EOD summaries, journal commentary,
analytics narrative). The core pipeline (filter → detect → score → alert) is
fully deterministic and never calls AI. This is by design (Requirement 19.6).

**Note:** AI provider stubs exist but no provider is wired up yet. This is
acceptable — the scanner operates fully without AI.

---

## 3. Alert System

### 3.1 Telegram Alert Delivery ✅ (Fixed)

**Previous Issue:** The `_try_emit_alert` and `_emit_alerts` methods logged signals
to the journal and marked them as sent in the dedup cache, but never actually
sent a Telegram message.

**Fix Applied:** Added `_send_telegram_alert()` method that:
1. Formats the message using `MomentumAlertManager._format_telegram_message()`
2. Sends via `_send_with_retry()` (3 attempts, 5s intervals, 10s HTTP timeout)
3. Both `_try_emit_alert` and `_emit_alerts` now call this method

**Configuration Required:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3.2 Alert Deduplication ✅

- Cache keyed by symbol + setup_type (LRU, max 500 entries)
- Configurable cooldown: 4 hours default (range 1-48h)
- Volume override: sends if RVOL exceeds previous by 50+ percentage points
- Score threshold override: sends when score crosses 80.0
- Cache invalidation on stop-loss breach or trend score < 40

### 3.3 Trailing Stop Notifications ✅

The `TrailingStopMonitor` sends Telegram messages for:
- Stop level changes (breakeven move, trailing updates)
- Position exits (T3 reached or trailing stop hit)

### 3.4 Status Reporter ✅

- Startup message with symbol count
- Daily summary at 00:00 UTC (signals, win rate, best symbol)
- Idle status if no signals for 4+ hours (rate-limited)

---

## 4. Market Condition Filters

### 4.1 Market Regime Filter (BTC-based) ✅

**Hard gate:** Only blocks LONG signals when BTC is actively crashing
(>3% decline over 4 consecutive 1H candles). Allows signals during
sideways and mildly bearish markets.

**Soft scoring (market_alignment):** 5 conditions evaluated on BTC 4H data,
each worth 20 points (0-100 total):
1. Trend: BTC price > EMA200
2. Momentum: EMA20 > EMA50
3. Direction: EMA200 rising over last 5 candles
4. Volatility: ATR(14)/price between 1.0%-3.0%
5. Breadth: >50% of tracked coins with positive 24h change

### 4.2 Trend Filter (Per-Coin) ✅

Setup-type-specific evaluation:
- **Compression/Pullback (4H):** Price > EMA200, EMA20 > EMA50, EMA200 rising (all 3 required, min 50 candles)
- **Momentum Breakout (1H):** Only requires close > EMA20 (min 20 candles)

### 4.3 Volatility Gate ✅

ATR14/price ratio must be between 1.5% and 8.0%:
- Below 1.5%: "dead coin" — insufficient movement
- Above 8.0%: "pump/dump coin" — excessive risk

### 4.4 Risk-Reward Validation ✅

All setups must have RR >= 2.0 (enforced in scoring engine).
Stop-loss uses the wider (safer) of structure stop and ATR-based stop.

---

## 5. Data & Connectivity

### 5.1 WebSocket Multi-Exchange Support ✅

- Primary: Bybit (default enabled)
- Secondary: Binance
- Tertiary: OKX
- Auto-reconnection with exponential backoff (max 5 attempts)
- Connection drop detection via message timeout
- Exchange failover on total failure

### 5.2 Dynamic Universe Management ✅

- Fetches top 200 USDT linear pairs from Bybit by 24h volume
- Filters by minimum volume ($10M) and minimum price ($0.10)
- BTCUSDT always included
- Refreshes every 60 minutes
- Falls back to hardcoded list if API fails

### 5.3 Data Validation ✅

All incoming candle data is validated:
- Volume must be positive (zero volume discarded)
- OHLC values must be positive
- High >= Low, High >= Open/Close, Low <= Open/Close
- Only confirmed/closed candles are processed

---

## 6. Persistence & Recovery

### 6.1 State Persistence ✅

- Per-coin state saved to `data/state/scanner_state.json`
- Includes candle buffers, trend status, active setups, pending triggers
- Atomic write (temp file + rename)
- Restored on startup for crash recovery

### 6.2 Journal Store ✅

- Daily JSON files: `data/journal/signals_YYYY-MM-DD.json`
- Logs all signals with full context (entry, stop, score, indicators)
- Logs all rejections with reason and stage
- 90-day retention with automatic cleanup
- Outcome recording (win/loss/expiry)

### 6.3 Direction-Aware Outcome Tracking ✅ (Fixed)

**Previous Issue:** `JournalStore.check_outcome()` only handled LONG direction
(price <= stop = loss, price >= target = win).

**Fix Applied:** Added `direction` parameter to `check_outcome()` and
`JournalEntry` model. SHORT signals now correctly detect:
- Loss when price >= stop_loss (price going up against short)
- Win when price <= target_1 (price going down as expected)

---

## 7. Configuration

### 7.1 Config Architecture ✅

Two config systems coexist:
- `config/__init__.py` — Dataclass-based config with env var support (used by older code paths)
- `config/websocket_config.py` — `WebSocketStreamConfig` dataclass (used by the momentum scanner)
- `config.yaml` — YAML config file (loaded by `main_momentum.py` for symbols only)

### 7.2 StrategyConfig PRD Parameters — Unused ⚠️

**Status:** Low Priority

`StrategyConfig` defines PRD parameters (`breakout_volume_multiplier`, `pullback_rsi_low`,
`pullback_rsi_high`, `min_risk_reward`) but these are NOT consumed by the current
momentum scanner pipeline. The setup detector uses hardcoded values:
- Volume multiplier: 1.5x (compression/pullback) or 2.5x (momentum)
- RSI: Not used in current detection logic
- Min RR: 2.0 (enforced in scoring engine)

**Impact:** None — the current values are correct. The `StrategyConfig` exists
for potential future use or alternative scan modes.

### 7.3 LearningConfig Exists but No Learning Module ⚠️

**Status:** Low Priority (PRD Phase 2-4 not implemented)

`LearningConfig` is defined in `config/__init__.py` and `config.yaml` has a
`learning:` section, but no `learning/` module exists. The `data/learning_history.json`
file exists for future use.

The PRD's Hybrid Reasoning + Learning System (signal tracker, accuracy scorer,
learning engine, hybrid reasoner) was never built. The current system relies on:
- Journal Store for signal/outcome persistence
- Trailing Stop Monitor for real-time position tracking
- Rolling stats in JournalStore for performance analytics

---

## 8. Remaining Gaps & Improvements

### 8.1 No RSI Validation in Setup Detection — Medium Priority

The PRD specifies RSI 40-55 for pullback signals, but the current
`detect_pullback_continuation()` does not check RSI. It relies on:
- EMA proximity (within 0.5%)
- Bullish reclaim candle (close above EMA, upper 50% of range)
- Volume confirmation (> 1.5x MA30)

**Recommendation:** Add RSI check to pullback detection for additional
confluence. The `IndicatorEngine.calculate_rsi()` method already exists.

### 8.2 No OI/Funding Data Integration — Low Priority

The scoring engine supports OI/funding adjustments (-20% overcrowded,
-15% weak OI), but `OIFundingData(data_available=False)` is always passed.
No exchange API integration fetches this data.

**Impact:** Scores are slightly optimistic (no penalty applied). Not critical
for signal quality since the other 5 scoring components are active.

### 8.3 AI Provider Not Wired Up — Low Priority

AI stubs exist for:
- EOD summary generation
- Journal commentary
- Analytics narrative formatting

No provider is configured. The scanner works fully without AI.

### 8.4 Max Daily Signals Limit Not Enforced — Medium Priority

`AlertConfig.max_daily_signals` (default 5) is defined but not checked
in the alert emission pipeline. The dedup cooldown (4h) provides natural
rate limiting, but a hard daily cap is not enforced.

**Recommendation:** Add a daily signal counter to `MomentumAlertManager`
that resets at 00:00 UTC.

---

## 9. Deployment

### 9.1 Railway Deployment ✅

- `Procfile`: `web: python main_momentum.py`
- Health check server starts when `PORT` env var is set
- Graceful shutdown within 10 seconds on SIGTERM
- State persisted before shutdown

### 9.2 Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes (for alerts) | Telegram bot API token |
| `TELEGRAM_CHAT_ID` | Yes (for alerts) | Telegram chat/channel ID |
| `WS_ENABLE_BYBIT` | No (default: true) | Enable Bybit WebSocket |
| `WS_ENABLE_BINANCE` | No (default: false) | Enable Binance WebSocket |
| `PORT` | No | Health check server port (set by Railway) |

---

## 10. Test Coverage ✅

17 test files covering:
- Setup detection (compression, pullback, momentum breakout)
- Scoring engine (breakout quality)
- Alert manager (dedup, cooldown)
- Trend filter (setup routing)
- Market regime filter
- Volatility gate
- Trailing stop monitor
- Relative strength engine
- Universe integration
- Failover/error handling
- Journal analytics

---

*Document updated: 2026-05-15*
*Scanner architecture: WebSocket event-driven (v3.0)*
*Entry point: main_momentum.py*
