# Crypto Scanner - Known Issues & Leaks

## Summary
This document outlines issues, bugs, and potential improvements for the crypto scanner project.

---

## 1. PRD Signal Engine Issues

### 1.1 PRD Signals Not Generating in Bearish Market
**Status:** Resolved ✅

When BTC is in a bearish trend, the PRD engine now generates breakout/pullback signals:
- Added bearish breakout (SHORT) - price breaks below support + bearish candle
- Added bearish pullback (SHORT) - price retraces to EMA + RSI 45-60 + bearish candle
- Modified scan_all_prd_signals to allow bearish signals when price < EMA 200
- AI has final say on all signals (approve/reject/modify)

**AI Dependency:** AI analyzes and makes final decision on all PRD signals.

---

### 1.2 PRD Parameters Not Using Config Values
**Status:** Resolved ✅

In `strategies/prd_signal_engine.py`, the PRD engine now uses config values:
```python
# Current (using config):
self.breakout_volume_multiplier = getattr(self.strategy, 'breakout_volume_multiplier', 1.5)
self.pullback_rsi_low = getattr(self.strategy, 'pullback_rsi_low', 40)
self.pullback_rsi_high = getattr(self.strategy, 'pullback_rsi_high', 55)
self.min_risk_reward = getattr(self.strategy, 'min_risk_reward', 2.0)
```

Uses `StrategyConfig` values with env variable support:
- `BREAKOUT_VOLUME_MULTIPLIER` (default: 1.5)
- `PULLBACK_RSI_LOW` (default: 40)
- `PULLBACK_RSI_HIGH` (default: 55)
- `MIN_RISK_REWARD` (default: 2.0)

---

## 2. Signal Publisher Feature (New)

### 2.1 Signal Publishing on Startup/Deployment
**Status:** Implemented ✅

When application starts or is deployed:
- Scanner runs immediately and scans all coins/charts
- If any signals meet confidence threshold, they are sent to Telegram
- Daily limit: maximum 3 signals (long + short combined)
- Published signals are automatically journaled to TradeJournal
- SL/TP monitoring runs every 15 minutes
- Immediate alerts when SL or TP is hit

**Configuration:**
```yaml
scheduler:
  run_mode: "continuous"  # or "scheduled"
  continuous_interval_minutes: 15

alerts:
  max_daily_signals: 3
```

**Files Modified:**
- `alerts/signal_publisher.py` - New signal publisher module
- `config/__init__.py` - Added max_daily_signals config
- `src/scheduler/scanner_scheduler.py` - Added continuous mode + monitoring
- `main.py` - Integrated signal publisher with scan jobs
- `config.yaml` - Added new config options

---

## 3. AI Dependency

### 1.3 AI Has Final Say on All Signals
**Status:** Working as Expected ✅

All PRD-generated signals go through AI analysis:
1. PRD rules generate candidate signals
2. AI analyzes each signal (APPROVE/REJECT/MODIFY)
3. AI can adjust entry, stop loss, targets, or direction
4. Final signals are AI-approved only

Signal flow:
```
PRD Rules → Candidates → AI Analysis → AI Decision → Final Signals
```

---

## 4. Type Checking Warnings

### 2.1 LSP/Type Checker Errors
**Status:** Non-blocking - Low Priority

The LSP shows type warnings for:
- Import resolution (loguru, telebot) - IDE issue, not runtime
- Pandas type hints - false positives
- None handling in calculations

**Impact:** None - these are static analysis warnings only.

**Recommendation:** Add type stubs or ignore comments if desired.

---

## 5. Configuration Issues

### 3.1 Duplicate Configuration Definition
**Status:** Resolved ✅

PRD parameters are consolidated in `StrategyConfig`:
- `StrategyConfig.prd_min_confidence` - now used for threshold
- PRD params in `StrategyConfig`: breakout_volume_multiplier, pullback_rsi_low, pullback_rsi_high, min_risk_reward

The `ScannerConfig.prd_min_confidence` is still used as fallback (70.0).

---

### 3.2 Env Variable Parsing for Booleans
**Status:** Bug - Low Priority

In `ScannerConfig`:
```python
enable_prd_strategy: bool = os.getenv("ENABLE_PRD_STRATEGY", "true").lower() == "true"
```
This works, but the YAML config uses `true` (lowercase) which may not match.

---

## 6. Alert System Issues

### 4.1 AI Confidence Score vs Standard Score
**Status:** Design Issue - Medium Priority

The alert system checks two different confidence scores:
- `confidence_score` (0-10 scale)
- `ai_confidence_score` (0-100 scale)

This creates confusion in threshold logic:
```python
qualified_signals = [s for s in signals if s.confidence_score >= threshold_10 or s.ai_confidence_score >= threshold]
```

**Recommendation:** Standardize to one scoring system.

---

### 4.2 Duplicate Alert Detection
**Status:** Working as Expected

The `SignalDuplicateChecker` uses signal `id` (timestamp-based) for cooldown, not symbol. This means:
- Same symbol can get alerts multiple times if signal IDs differ
- Current 24-hour cooldown applies per signal, not per symbol

**Current behavior:** Acceptable - each signal gets unique ID.

---

## 7. Runtime Observations

### 5.1 Ollama Connection Error
**Status:** Expected (when not running)

When Ollama is not running:
```
AI Analysis: Error: Cannot connect to host localhost:11434
```

The system gracefully falls back to rule-based mode.

---

### 5.2 Performance
- Scan time: ~30 seconds for 100 coins
- MTF data fetching: ~4 seconds
- Signal processing: ~1 second

**Status:** Acceptable

---

## 8. Missing Functionality

### 6.1 Missing Data Directory Creation
**Status:** Bug - Low Priority

The `data/` directory may not be created automatically on first run, causing SQLite errors.

**Current:** Works because `storage/__init__.py` creates it.

---

### 6.2 No Test Coverage
**Status:** Improvement - Low Priority

No unit tests exist for:
- PRD signal engine
- Indicator calculations
- Strategy engines

---

## 9. Recommended Fixes

### Priority 1 (High Impact)
1. ~~Fix PRD config values usage in PRDSignalEngine~~ - **Resolved ✅**
2. ~~Consolidate duplicate confidence threshold configs~~ - **Resolved ✅**

### Priority 2 (Medium Impact)
3. Standardize confidence scoring between PRD and existing strategies
4. Add proper error handling for API failures

### Priority 3 (Low Impact)
5. Add type hints/stubs for cleaner type checking
6. Add basic unit tests
7. Document the two confidence score systems

---

## 10. Files Modified

| File | Changes |
|------|---------|
| `strategies/prd_signal_engine.py` | Hardcoded PRD params |
| `config/__init__.py` | Duplicate config + max_daily_signals |
| `models/__init__.py` | Added PRD fields |
| `alerts/__init__.py` | Confidence logic |
| `scanner.py` | PRD integration |
| `alerts/signal_publisher.py` | **NEW** - Signal publisher module |
| `src/scheduler/scanner_scheduler.py` | Continuous mode + SL/TP monitoring |
| `main.py` | Signal publisher integration |
| `config.yaml` | Scheduler run_mode + max_daily_signals |

---

*Document generated: 2026-04-15*
*Scanner version: 2.2.1*