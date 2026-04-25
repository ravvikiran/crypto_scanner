# Crypto Scanner AI - Web UI Guide

## Overview

The Crypto Scanner AI includes a full-featured web dashboard ported from the NSE Trend Scanner. The UI provides real-time monitoring, trade tracking, performance analytics, and market insights.

## Quick Start

### Start the Web UI

```bash
./run_ui.sh ui
```

This starts the Flask API on port 5002 by default.

**Access the dashboard:** http://localhost:5002

### Start the Scanner (Terminal Mode)

```bash
./run_ui.sh scanner
```

Or use direct commands:

```bash
# Single scan
python3 main.py scan --alerts

# Continuous scanning
python3 main.py continuous

# With scheduler (24x7, every 15 min)
python3 main.py --schedule
```

## Architecture

### Components

1. **Flask API** (`src/api.py`) - REST endpoints serving JSON data
2. **Templates** (`templates/`) - HTML pages (dashboard, trades, performance, analysis, settings)
3. **Static Assets** (`static/`) - CSS and JavaScript (Chart.js visualizations)
4. **Data Layer**:
   - `PerformanceTracker` - SQLite database (`data/performance.db`) for signals/trades
   - `TradeJournal` - JSON file (`data/trade_journal.json`) for manual trades
   - `SignalMemory` - Tracks signals for update detection
5. **Crypto Data Fetcher** (`src/crypto_data_fetcher.py`) - Fetches live prices from CoinGecko

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Dashboard UI |
| `GET /api/dashboard` | Overview metrics (open trades, P&L, win rate) |
| `GET /api/trades/open` | Active trades with live prices |
| `GET /api/trades/history` | Closed trade history |
| `GET /api/performance/summary` | Performance statistics |
| `GET /api/performance/by-strategy` | Breakdown by strategy |
| `GET /api/performance/pnl-curve` | Cumulative P&L over time |
| `GET /api/signals/top5` | Current top 5 ranked signals |
| `GET /api/analysis/market-sentiment` | Market sentiment data |
| `GET /api/scanner/status` | Scanner state (running/stopped) |
| `POST /api/scanner/start` | Start scanner |
| `POST /api/scanner/stop` | Stop scanner |
| `GET /api/settings` | Current configuration |
| `POST /api/settings` | Update settings |

### Data Flow

```
Browser UI (HTML/JS)
    ↓ (HTTP GET/POST)
Flask API (src/api.py)
    ↓ (queries)
SQLite DB + JSON Files + Live Price API
    ↓ (returns JSON)
UI updates charts/tables
```

## Configuration

### Port

Default: 5002

Change via environment variable:
```bash
PORT=8080 ./run_ui.sh ui
```

### Virtual Environment

The project uses a virtual environment (`.venv/`). The `run_ui.sh` script auto-activates it. Dependencies:

- Flask >= 2.3.0
- Flask-CORS >= 4.0.0
- All other packages from `requirements.txt`

Install manually:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## File Locations

| Path | Purpose |
|------|---------|
| `templates/` | HTML pages (5 pages) |
| `static/css/` | Stylesheets |
| `static/js/` | JavaScript modules (one per page) |
| `src/api.py` | Flask backend |
| `data/performance.db` | SQLite database |
| `data/trade_journal.json` | Manual trades JSON |
| `data/memory/` | Signal memory storage |
| `logs/` | Application logs |

## Customization

### branding

Edit templates to change "Crypto Scanner AI" name:
- `templates/*.html` - Update `<title>` and navbar branding
- `static/js/*.js` - Update comments/page titles

### Data Sources

The API uses:
- `PerformanceTracker` for automated signals (from scanner)
- `TradeJournal` for manual trades
- `CryptoDataFetcher` for live prices (CoinGecko)

To connect to your own data source, modify:
- `src/crypto_data_fetcher.py` - Change `get_current_price()` implementation
- `src/api.py` - Adjust database queries if schema differs

## Troubleshooting

### Port Already in Use

```bash
# Kill process on port 5002
lsof -ti:5002 | xargs kill -9

# Or use a different port
PORT=8080 ./run_ui.sh ui
```

### Import Errors

Ensure you're in the project root and virtual env is active:
```bash
cd /Users/ravikiran/Documents/crypto_scanner
source .venv/bin/activate
```

### Missing Data

The UI shows empty states until the scanner has generated signals or trades have been journaled. Run a scan first:
```bash
python3 main.py scan --alerts
```

### Database Errors

Delete and reinitialize:
```bash
rm data/performance.db
python3 main.py scan
```

## Integration with Scanner

The NSE Trend Scanner runs scanner + UI together. To do the same for crypto:

Edit `main.py` to initialize the Flask API in a background thread (similar to NSE's `src/main.py` lines 3346-3353). The skeleton is already in `run_scheduled()` function.

Or simply run two terminals:
- Terminal 1: `./run_ui.sh ui` (Web UI)
- Terminal 2: `./run_ui.sh scanner` (Scanner)

## Next Steps

- [ ] Wire `/api/signals/top5` to real-time scanner signals (currently reads from DB)
- [ ] Add WebSocket support for live updates (instead of polling)
- [ ] Integrate scanner control (start/stop/pause) from UI
- [ ] Deploy to Railway/Render (see `Procfile`)

---

**UI successfully integrated from NSE Trend Scanner.** All pages, charts, and styling are intact.