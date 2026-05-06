# Crypto Scanner - Bug Fixes & Improvements Summary

## Date: 2026-05-06

---

## Critical Fixes

### 1. Database Connection Leaks → Converted to JSON (storage/__init__.py)
**Problem:** `PerformanceTracker` used SQLite (`performance.db`) with connection leaks. You want JSON-only persistence.

**Fix:** 
- Completely rewrote `PerformanceTracker` to use JSON files instead of SQLite
- Data stored in `data/signals.json`, `data/trades.json`, `data/scans.json`, `data/signal_outcomes.json`
- Atomic writes (write to `.tmp` then rename) to prevent corruption
- In-memory caching with periodic saves
- Auto-limits scans to last 500 entries to prevent unbounded growth
- Removed all `sqlite3` imports

### 2. HTTP Session Leak (collectors/crypto_data_fetcher.py)
**Problem:** `requests.Session()` was created but never closed, holding TCP connections indefinitely.

**Fix:**
- Added `close()` method to explicitly close the session
- Added `__del__` destructor for garbage collection cleanup
- Added context manager support (`__enter__`/`__exit__`)
- Added retry logic with exponential backoff for rate limits and timeouts
- Increased timeout from 5s to 10s for reliability

### 3. Missing Attribute Initializations (scanner.py)
**Problem:** `self.ai_sentiment_analyzer`, `self.sentiment_monitor`, `self.signal_validation_agent`, `self.prd_engine` were used but never initialized in `__init__()`, causing `AttributeError` at runtime.

**Fix:**
- Added initialization of `AIMarketSentimentAnalyzer`, `MarketSentimentMonitor`, `AISignalValidationAgent`, and `PRDSignalEngine` in `__init__()`
- Fixed `self.trend_alert_engine` → `self.market_trend_alert_engine` (correct attribute name)
- Fixed `self.risk_engine` → `self.risk_management_engine` (correct attribute name)

### 4. Undefined Variable in Learning Check (scanner.py)
**Problem:** `run_learning_check()` referenced `coins` variable which was not in scope (it's local to `run_scan()`).

**Fix:**
- Changed to use `self._coins_cache` which is populated during each scan
- Added `self._coins_cache` population in `run_scan()` after fetching coins
- Fixed indentation error in the nested if-block

---

## Major Fixes

### 5. Duplicate Function Definitions + SQLite Removal (infrastructure/api.py)
**Problem:** `is_crypto_symbol()` and `get_crypto_quote_from_coingecko()` were defined twice. The `/api/signals/top5` endpoint used direct SQLite queries.

**Fix:** 
- Removed duplicate function definitions
- Rewrote `/api/signals/top5` to use JSON-based `PerformanceTracker.get_top_signals()` instead of SQLite
- Removed `sqlite3` import entirely

### 6. Optimization Engine SQLite → JSON (engines/optimization_engine.py)
**Problem:** `TradeJournal` class in optimization engine used SQLite (`trade_journal.db`).

**Fix:**
- Rewrote to use JSON file (`data/optimization_journal.json`)
- Atomic writes for crash safety
- Auto-limits to last 1000 trades
- Removed `sqlite3` import

### 7. Signal Memory Unbounded Growth (alerts/signal_memory.py)
**Problem:** `all_signals` list grew indefinitely without cleanup, causing memory exhaustion over time.

**Fix:** Added automatic `cleanup_old_signals(days=30)` call during initialization to prune old entries.

### 8. Signal Publisher Creating New SignalMemory Per Call (alerts/signal_publisher.py)
**Problem:** `publish_signal()` created a new `SignalMemory()` instance on every call, wasting resources and losing state.

**Fix:** 
- Moved `SignalMemory` to instance-level (`self.signal_memory`) in `__init__()`
- Removed per-call instantiation

---

## Reliability Improvements

### 9. Graceful Shutdown (main.py)
**Problem:** No proper cleanup on Ctrl+C - scheduler, Telegram bot, and data fetcher were not stopped.

**Fix:**
- Added cleanup of Telegram bot on shutdown
- Added cleanup of data fetcher session on shutdown
- Added proper logging of shutdown completion

### 10. Telegram Bot Reconnection (alerts/telegram_bot.py)
**Problem:** If `infinity_polling()` threw an exception, the bot thread died permanently with no recovery.

**Fix:**
- Added retry logic with max 3 attempts and exponential backoff
- Bot now recovers from transient network errors
- Properly sets `_running = False` when all retries exhausted

### 11. Flask API Thread Error Handling (main.py)
**Problem:** If Flask failed to start, the error was silently swallowed in the daemon thread.

**Fix:** Added try/except in the `run_api()` thread function with proper error logging.

### 12. Scan Job Error Handling (main.py)
**Problem:** If `run_scan()` raised an exception, the event loop cleanup could also fail, masking the original error.

**Fix:**
- Added try/except around the scan execution with traceback logging
- Added try/except around the event loop cleanup in the finally block
- Added `break` when daily limit is reached (no point continuing the loop)

### 13. Scheduler Thread Safety (infrastructure/scanner_scheduler.py)
**Problem:** `add_job()` could be called from multiple threads without synchronization, causing race conditions.

**Fix:**
- Added `threading.Lock` for job operations
- `add_job()` now acquires the lock before modifying scheduler state
- `stop()` now uses `wait=False` and catches exceptions for robustness

### 14. Atomic File Writes (learning/trade_journal.py)
**Problem:** `_save_state()` wrote directly to the storage file, risking corruption if the process was killed mid-write.

**Fix:** Implemented atomic write pattern - writes to `.tmp` file first, then renames (which is atomic on most filesystems).

---

## Configuration Improvements

### 15. Configuration Validation (config/__init__.py)
**Problem:** No validation that required environment variables were set, leading to silent failures.

**Fix:** Added `_validate_config()` that logs warnings for:
- Missing Telegram bot token or chat ID
- Missing AI API key for the selected provider
- Out-of-range numeric values (min_signal_score, max_daily_signals)

---

## Files Modified

| File | Changes |
|------|---------|
| `storage/__init__.py` | Rewrote from SQLite to JSON-based persistence |
| `collectors/crypto_data_fetcher.py` | Added session cleanup, retry logic, context manager |
| `scanner.py` | Fixed 5 missing attribute inits, fixed variable scope, fixed indentation |
| `infrastructure/api.py` | Removed duplicate functions, removed SQLite, uses JSON tracker |
| `engines/optimization_engine.py` | Rewrote from SQLite to JSON-based persistence |
| `infrastructure/scanner_scheduler.py` | Added thread safety lock, robust shutdown |
| `main.py` | Added graceful shutdown, error handling in threads |
| `alerts/telegram_bot.py` | Added reconnection with retry logic |
| `alerts/signal_memory.py` | Added auto-cleanup on init |
| `alerts/signal_publisher.py` | Fixed per-call SignalMemory instantiation |
| `config/__init__.py` | Added configuration validation |
| `learning/trade_journal.py` | Added atomic file writes |
