# Crypto UI Adaptation - Complete Summary

## Overview

The NSE Trend Scanner web UI has been fully ported to the Crypto Scanner project and adapted for 24/7 cryptocurrency markets. All stock-market-specific references (NSE, India timezone, market hours, currency) have been removed or replaced.

---

## Files Copied from NSE Trend Agent

- **`templates/`** - All 5 HTML pages (dashboard, trades, performance, analysis, settings)
- **`static/`** - CSS and JavaScript files with Chart.js visualizations

These files were copied verbatim from `/Users/ravikiran/Documents/nse-trend-agent/` without modification to the core UI structure.

---

## Changes Made for Crypto

### 1. Market Scheduler (`src/market_scheduler.py`)
**Before:** NSE-specific schedule (09:15-15:30 IST, Mon-Fri, holidays)
**After:** 24/7 operation, no timezone restrictions

- Removed all NSE market hour constants
- Removed holiday list and `_is_nse_holiday()` method
- Removed `_is_market_working_day()` weekday/weekend checks
- Simplified `get_market_status()` → always returns `"OPEN"`
- Simplified `is_market_open()` and `is_market_hours()` → always `True`
- Removed `get_time_until_market_open/close()` NSE-specific calculations
- Scheduler now uses UTC timezone by default
- Cron triggers run every day of week (no weekend skip)

### 2. Flask API (`src/api.py`)
**Before:** Used IST timezone, hardcoded 09:15/15:30, calculated next market open
**After:** UTC timestamps, no market open/close times

- Removed `pytz` import
- Changed all `datetime.now(pytz.timezone("Asia/Kolkata"))` → `datetime.utcnow()`
- Removed `calculate_next_market_open()` function entirely
- Simplified `/api/market-status` endpoint:
  - No longer returns `market_open`, `market_close`, `time_to_close`
  - Returns `market_type: "crypto"`, `timezone: "UTC"`, `message: "Crypto markets operate 24/7"`
- All timestamps now in UTC ISO format

### 3. Dashboard UI

#### `templates/dashboard.html`
- Changed **"Market Hours: 09:15 - 15:30"** → **"Market Type: 24/7 Crypto"**
- Changed **"Time to Close"** → **"Last Scan"**
- All currency symbols `₹` → `$`

#### `static/js/dashboard.js`
- `updateCurrentTime()`: Changed from IST to UTC
  ```js
  // Before: Asia/Kolkata timezone
  // After: UTC
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { timeZone: 'UTC' });
  ```
- Removed `updateMarketStatus()` function (no longer needed)
- Removed fetching `/api/market-status` in `loadDashboardData()`
- Changed all P&L displays from `₹` to `$`
- Removed market status badge color logic (now always shows OPEN)

### 4. Analysis Page

#### `templates/analysis.html`
- **"NIFTY Trend"** → **"BTC Trend"**
- **"Top Performing Stocks"** → **"Top Performing Coins"**

#### `static/js/analysis.js`
- Updated to read `data.btc_trend` instead of `data.nifty_trend`
- Fallback remains for compatibility: `data.btc_trend || data.nifty_trend`

#### `src/api.py` - `/api/analysis/market-sentiment` endpoint
Returned JSON changed from:
```json
{
  "nifty_trend": "BULLISH",
  "sector_leaders": [{"sector": "IT", ...}, {"sector": "FINANCE", ...}, ...]
}
```
To:
```json
{
  "btc_trend": "BULLISH",
  "sector_leaders": [{"sector": "Layer 1", ...}, {"sector": "DeFi", ...}, ...]
}
```

### 5. Settings Page

#### `templates/settings.html`
- Removed **"Skip Scans on Weekends"** checkbox (crypto runs 24/7)

#### `static/js/settings.js`
- Removed `skip_weekends` from saved settings payload
- `saveGeneralSettings()` no longer includes that field

#### `static/js/settings.js` (filename)
- Changed download filename from `nse-scanner-settings.json` → `crypto-scanner-settings.json`

### 6. Currency Changes
All occurrences of Indian Rupee (₹) replaced with US Dollar ($) in:
- `templates/*.html`
- `static/js/*.js`
- `static/css/*.css` (none found there)

### 7. Legacy NSE Files Marked as Deprecated

These files remain in the repo but are **NOT USED** by the crypto scanner. They were copied from NSE project and are kept only for reference:

- `src/data_fetcher.py` - Added header: "LEGACY DATA FETCHER - NSE Stock Market (Deprecated)"
- `src/history_manager.py` - Marked as legacy
- `src/performance_tracker.py` - Marked as legacy
- `src/signal_tracker.py` - Marked as legacy

**Note:** The crypto scanner uses:
- `src/crypto_data_fetcher.py` for price data (CoinGecko/Binance)
- `learning.trade_journal.TradeJournal` for journaling
- `storage.performance_tracker.PerformanceTracker` for performance
- `learning.signal_tracker.SignalTracker` for signal tracking

---

## Verification Results

All endpoints tested and confirmed working:

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/` | 200 | Dashboard loads |
| `/api/dashboard` | 200 | Returns UTC timestamp, market_status: "OPEN" |
| `/api/market-status` | 200 | Returns crypto-specific fields |
| `/api/trades/open` | 200 | Empty array (no trades yet) |
| `/api/trades/history` | 200 | Empty array |
| `/api/performance/summary` | 200 | Stats OK |
| `/api/signals/top5` | 200 | Returns top 5 signals from DB |
| `/api/analysis/market-sentiment` | 200 | Returns `btc_trend`, crypto sectors |
| `/api/scanner/status` | 200 | Scanner state |
| `/trades` | 200 | Page loads |
| `/performance` | 200 | Page loads |
| `/analysis` | 200 | Page loads, shows "BTC Trend" |
| `/settings` | 200 | Page loads, no weekend option |

All static assets (CSS, JS) served correctly with 200 responses.

---

## How to Run the Web UI

### Quick Start

```bash
cd /Users/ravikiran/Documents/crypto_scanner

# Option 1: Using launcher script
./run_ui.sh ui

# Option 2: Direct Python
python3 start_ui.py
```

The UI will be available at: **http://localhost:5002**

### Running the Scanner

The scanner runs separately. In another terminal:

```bash
# Single scan with alerts
python3 main.py scan --alerts

# Continuous scanning (every 15 min by default)
python3 main.py continuous

# With scheduler (runs continuously, 24/7)
python3 main.py --schedule
```

### Integrating Scanner + UI in One Process

To mimic NSE's integrated run (both scanner and UI together), modify `main.py` to initialize the Flask API in a background thread, as shown in the NSE project's `src/main.py` (lines 3346-3353). A skeleton already exists in the `run_scheduled()` function.

Alternatively, use two terminals:
- Terminal 1: `./run_ui.sh ui` (Web UI)
- Terminal 2: `python3 main.py --schedule` (Scanner)

---

## Configuration

### Port
Default: **5002**
Change via environment variable:
```bash
PORT=8080 ./run_ui.sh ui
```

### Virtual Environment
The launcher script auto-activates `.venv/`. Required packages are in `requirements.txt`:
- Flask >= 2.3.0
- Flask-CORS >= 4.0.0
- All other crypto scanner dependencies

---

## Data Flow

```
Browser (HTML/JS/Chart.js)
    ↓ HTTP requests
Flask API (src/api.py)
    ↓ Queries
SQLite DB (data/performance.db) + JSON (data/trade_journal.json) + Live Prices (CoinGecko)
    ↓ JSON response
Browser updates UI
```

---

## Key Differences from NSE Version

| Feature | NSE Trend Agent | Crypto Scanner AI |
|---------|-----------------|-------------------|
| Market Hours | 09:15-15:30 IST, Mon-Fri | **24/7, every day** |
| Timezone | Asia/Kolkata (IST) | **UTC** |
| Currency | Indian Rupee (₹) | **US Dollar ($)** |
| Weekend Scans | Skipped | **Enabled** |
| Market Holidays | NSE holiday calendar | **None** |
| Trend Indicator | NIFTY Index | **BTC Trend** |
| Sectors | IT, Finance, Pharma | **Layer 1, DeFi, Gaming** |
| Scanner Stop/Start | Manual or scheduled | **Continuous 24/7** |
| Price Source | Yahoo Finance (NSE) | **CoinGecko/Binance** |

---

## Files Modified or Created

### Created (New Files)
- `run_ui.sh` - Launcher script (bash)
- `start_ui.py` - Minimal Flask startup
- `src/crypto_data_fetcher.py` - Crypto price fetcher (CoinGecko)
- `src/market_scheduler.py` - New 24/7 scheduler (replaced NSE logic)
- `UI_RUN_GUIDE.md` - Documentation

### Modified (Key Changes)
- `templates/` - All 5 HTML pages (branding, currency, market hours)
- `static/js/dashboard.js` - UTC time, $ currency, removed market-close logic
- `static/js/analysis.js` - BTC trend instead of NIFTY
- `static/js/settings.js` - Removed weekend skip, changed filename
- `src/api.py` - UTC timestamps, simplified market-status, removed NSE functions
- `learning/trade_journal.py` - Added `get_all_trades()` method for API
- `src/market_scheduler.py` - Complete rewrite for 24/7

### Copied Unchanged (from NSE Agent)
- All template HTML files
- All static CSS/JS files (except modifications noted above)
- NSE-specific files kept as legacy but not used

---

## Testing Checklist

- [x] UI loads at http://localhost:5002
- [x] Dashboard shows correct metrics
- [x] Market status shows "OPEN" and "24/7 Crypto"
- [x] Current time displays in UTC
- [x] All API endpoints return JSON (200 OK)
- [x] All pages render (Dashboard, Trades, Performance, Analysis, Settings)
- [x] No `₹` symbols remain in UI
- [x] No "NSE", "NIFTY", or "India" references in UI text
- [x] No "09:15" or "15:30" market times displayed
- [x] Weekend skip option removed from Settings
- [x] Top5 signals endpoint returns data
- [x] Analysis page shows "BTC Trend" and crypto sectors

---

## Known Limitations / TODO

1. **`/api/trades/open` requires live prices** - The endpoint calls `data_fetcher.get_current_price()`. The `CryptoDataFetcher` implementation currently fetches from CoinGecko's simple/price endpoint, which may have rate limits. Production use should implement proper caching.

2. **Top5 signals source** - Currently reads from the `signals` table in SQLite (which contains historical NSE test data). Should be wired to live scanner signals as they're generated.

3. **Scanner integration** - To run both scanner and UI in one process, modify `main.py` to initialize the Flask API background thread (see NSE's `src/main.py` lines 3334-3353 for reference).

4. **Analysis page data** - `market-sentiment` endpoint still returns placeholder data (BTC trend, static sector strengths). Should integrate with actual market sentiment analyzer.

5. **Settings persistence** - The `/api/settings` endpoints exist but the backend config system needs to be wired to read/write actual config files.

6. **Time handling in database** - Some timestamps stored from previous NSE runs may be in IST. Consider cleaning `data/performance.db` for fresh start.

---

## Conclusion

The UI is now fully adapted for a 24/7 cryptocurrency trading scanner. All references to Indian stock market hours, timezone, and currency have been removed. The system runs on UTC and displays USD.

**Access the dashboard:** http://localhost:5002

For questions or issues, refer to `UI_RUN_GUIDE.md`.
