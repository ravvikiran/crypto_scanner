
---

## 🔴 CRITICAL ISSUES

### 1. SHORT Setups Always Rejected by Scoring Engine (BUG)
**File:** `/Users/ravikiran/Documents/crypto_scanner/scoring/scoring_engine.py`, called from `momentum_scanner.py:1021-1025`

`calculate_risk_levels()` computes `risk = entry_price - stop_loss`. For SHORT setups, `stop_loss > entry_price`, making `risk` negative, so the function always returns `None`. **No SHORT setup can ever pass scoring.**

In `momentum_scanner.py`:
```python
atr14=setup.entry_price - setup.stop_loss,  # Negative for SHORT setups!
```

**Fix:** `calculate_risk_levels` needs to use `abs(entry_price - stop_loss)` or the caller needs to handle the direction-aware risk calculation differently. The function should receive `risk` as a positive value regardless of direction.

### 2. Active Setup Direction Not Persisted in State (BUG)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/state_manager.py`, `_serialize_active_setup()` / `_deserialize_active_setup()`

The `direction` field (`SignalDirection.SHORT` or `SignalDirection.LONG`) is **never serialized or deserialized**. On crash recovery, all deserialized setups default to `LONG` (via `__post_init__`). A SHORT setup that was persisted would be incorrectly restored as LONG.

**Fix:** Add `direction` to `_serialize_active_setup` and `_deserialize_active_setup`.

### 3. Hardcoded Real Telegram Bot Token (SECURITY)
**File:** `/Users/ravikiran/Documents/crypto_scanner/.env`, line 22
```
TELEGRAM_BOT_TOKEN=8368160728:AAH-boeIBXWOLj9MNpYnNut9DhFSoaz-LLE
```
A real, active bot token is committed to the repository. If the repo is shared or public, this token should be considered compromised. The `.env` file is in `.gitignore` but was found in the working directory.

**Fix:** Rotate this token immediately. Never commit real credentials.

### 4. Per-Coin Race Condition in Event Processing (CONCURRENCY BUG)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`, line 394

`asyncio.create_task(self._process_event_bounded(event))` processes events concurrently. Multiple events for the **same coin** (e.g., 4H + 1H + 15m) can be processed simultaneously. The semaphore (`max_concurrent_coin_updates`) is global, not per-coin. This means:
- A coin's `CoinState` could be read and written concurrently
- `active_setup` could be set while another coroutine is reading it
- `pending_trigger` expiration could race with setup detection

**Fix:** Add per-coin asyncio locks (e.g., `self._coin_locks: Dict[str, asyncio.Lock]`) and acquire the lock for a coin before processing any event for it.

---

## 🟠 HIGH-SEVERITY ISSUES

### 5. Unbounded Growth of `_active_scored_setups` (MEMORY LEAK)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`, line 176

`self._active_scored_setups` is appended to on every new scored setup but never pruned for resolved/expired setups. Over time this list grows without bound.

**Fix:** Periodically prune `_active_scored_setups` to remove setups that are no longer active (e.g., expired, triggered, or resolved).

### 6. `_active_scored_setups` / `_ranked_top5` State Not Persisted (STATE LOSS)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`

The `_active_scored_setups` and `_ranked_top5` lists are maintained in memory but never persisted. On restart, all ranked setups are lost, even if they were valid. Only `CoinState` (via `StateManager`) is persisted.

**Fix:** Serialize these lists in `StateManager.save_state()` and restore them on startup.

### 7. State for Removed Coins Never Cleaned Up (MEMORY LEAK)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/state_manager.py`

When the universe refreshes and coins are removed, `StateManager._states` retains their `CoinState` objects indefinitely. Over months of operation with a dynamic universe, the state dict accumulates stale entries.

**Fix:** Add a cleanup method to `StateManager` that removes states for symbols no longer in the active universe. Call it after `_refresh_universe` removes symbols.

### 8. Duplicate Expensive Computation (PERFORMANCE)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`

ATR14 is calculated independently in two places for the same candle data:
- `_handle_1h_event()` (line 690-699) for the volatility gate
- `_score_setup()` (line 969-979) for breakout quality scoring

Both create a pandas DataFrame from the same 1H candles and compute ATR14 identically.

**Fix:** Compute ATR14 once in `_handle_1h_event` and pass it through to `_score_setup`, or cache it on the `CoinState`.

### 9. Same: Duplicate EMA Calculations (PERFORMANCE)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`, `/Users/ravikiran/Documents/crypto_scanner/filters/trend_filter.py`, `/Users/ravikiran/Documents/crypto_scanner/indicators/__init__.py`

EMA calculations are implemented independently in `TrendFilter` (using pandas EWM directly) and `IndicatorEngine` (also using pandas EWM). Both use `adjust=False` and the same formula, but they're separate code paths.

**Fix:** Consolidate into a single `IndicatorEngine` call.

---

## 🟡 MEDIUM-SEVERITY ISSUES

### 10. Mixed Logging Frameworks (CODE SMELL)
**Files:** `market_regime_filter.py`, `trend_filter.py`, `volatility_gate.py` use `loguru`. All other files use standard `logging`.

Having two logging frameworks is confusing, can produce duplicate output, and makes centralized log management harder.

**Fix:** Standardize on one framework. The standard `logging` module is already configured in `main_momentum.py`.

### 11. Missing `__init__.py` in `tests/` Directory
**File:** `/Users/ravikiran/Documents/crypto_scanner/tests/__init__.py` exists but is empty. Individual test files need `sys.path.insert` hacks.

**Fix:** Configure pytest properly with `pyproject.toml` or `setup.cfg` to handle imports, or use a conftest.py.

### 12. `config.yaml` Contains Unused Fields
**File:** `/Users/ravikiran/Documents/crypto_scanner/config.yaml`, line 20

`min_top_coins: 100` is defined but never read by any code. `scanner.scan_interval_minutes`, `scanner.max_coins_to_scan`, `scanner.min_market_cap_millions`, and other `scanner.*` fields are also never used — the actual scanner reads from `WebSocketStreamConfig` which uses env vars with different names.

**Fix:** Remove unused fields or wire them up properly.

### 13. Python Version Mismatch
**File:** `nixpacks.toml` specifies `PYTHON_VERSION = "3.11"` but the `.venv` directory shows Python 3.9 paths.

**Fix:** Align the Python version between development and deployment.

### 14. `asyncio` Listed in `requirements.txt`
**File:** `/Users/ravikiran/Documents/crypto_scanner/requirements.txt`, line 7

`asyncio` is part of the Python standard library since Python 3.4. Including it as a dependency is unnecessary and could cause issues.

**Fix:** Remove `asyncio>=3.4.3` from requirements.txt.

### 15. Redundant Scheduling Libraries
**File:** `/Users/ravikiran/Documents/crypto_scanner/requirements.txt`

Both `apscheduler>=3.10.4` and `schedule>=1.2.0` are listed. Neither appears to be imported or used in the actual code — the scanner uses `asyncio.sleep()` for scheduling.

**Fix:** Remove unused dependencies.

### 16. Private Attribute Access in StatusReporter
**File:** `/Users/ravikiran/Documents/crypto_scanner/monitors/status_reporter.py`, line 183

`self._regime_filter._btc_candles_1h` accesses a private attribute of `MarketRegimeFilter`. This couples the two classes and could break if the internal structure changes.

**Fix:** Add a public method to `MarketRegimeFilter` that returns the data `StatusReporter` needs.

### 17. `_handle_1h_event` Method Too Long (CODE SMELL)
**File:** `/Users/ravikiran/Documents/crypto_scanner/core/momentum_scanner.py`, lines 662-909

This method is ~250 lines and handles regime check, volatility gate, setup detection, scoring, and alert emission. It should be decomposed into smaller methods.

### 18. Imports Inside Functions (PERFORMANCE/STYLE)
**File:** `momentum_scanner.py` imports `pandas` inside `_handle_1h_event` (line 690) and `_score_setup` (line 969). `websocket_manager.py` imports `json` inside `_listen_loop` (line 296).

While Python caches module imports so the performance hit is minimal after the first call, it's cleaner to import at the top level.

### 19. `EventBus.consume()` Has 1-Second Delay on Shutdown
**File:** `/Users/ravikiran/Documents/crypto_scanner/streaming/event_bus.py`, line 109

The `asyncio.wait_for(self._queue.get(), timeout=1.0)` means after `stop()` is called, the consume loop takes up to 1 second to notice and exit. This is fine for normal operation but adds latency to shutdown.

---

## 🔵 LOW-SEVERITY / SUGGESTIONS

### 20. No Integration Tests
The test suite has thorough unit tests but no end-to-end integration test that exercises the full pipeline (WebSocket → EventBus → Filter → Detect → Score → Alert).

### 21. `setup_detector.py` Zone Expiry Side Effect
The `detect_compression_breakout` function mutates the `existing_zone.expired` flag as a side effect (line 171). This is unexpected — callers may not expect their `CompressionZone` object to be modified.

### 22. No Hypothesis-Based Tests Despite Dependency
`hypothesis>=6.0.0` is in requirements.txt but there are no property-based tests. Either add hypothesis tests or remove the dependency.

### 23. `UniverseManager.close()` Is a No-Op
`/Users/ravikiran/Documents/crypto_scanner/universe/universe_manager.py`, line 299 — the `close()` method does nothing. This is fine since sessions are per-request, but it could mislead callers into thinking cleanup happens.

### 24. `config.yaml` vs `.env` Name Mismatch for Cooldown
`config.yaml` uses `alert_cooldown_hours: 4.0` while `.env` env var is `WS_ALERT_COOLDOWN_HOURS=4.0`. The scanner code reads from env vars, so the `config.yaml` value is ignored. This is confusing.

### 25. Missing `direction` in `SetupSignal` Serialization (Minor)
`/Users/ravikiran/Documents/crypto_scanner/streaming/models.py` — `SetupSignal` has a `direction` field but `_score_setup` in momentum_scanner.py creates `SetupSignal` without explicitly setting direction (line 1041-1053), so it always defaults to `SignalDirection.LONG` via `__post_init__`. This means the `direction` in `SetupSignal` is effectively unused since the actual direction comes from the `ActiveSetup` that contains it.

### 26. Breakeven Exits Classified as Wins
`/Users/ravikiran/Documents/crypto_scanner/monitors/trailing_stop_monitor.py`, line 352 — `actual_rr >= 0` classifies breakeven exits (RR=0) as WIN. Consider using `actual_rr > 0` for WIN and a separate classification for breakeven.

---

## Summary by Category

| Category | Count |
|----------|-------|
| 🔴 Critical Bugs | 4 |
| 🟠 High (Leaks/Perf/Crash Risk) | 5 |
| 🟡 Medium (Design/Style/Reliability) | 9 |
| 🔵 Low/Improvements | 8 |
| **Total** | **26** |