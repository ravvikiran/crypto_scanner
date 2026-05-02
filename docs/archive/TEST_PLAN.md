# Crypto Scanner Enhancement - Test & Verification Plan

## Test Environment Setup
```bash
# 1. Install dependencies (including Flask)
pip install -r requirements.txt

# 2. Configure Telegram (optional for alert testing)
# Edit config.yaml or set environment variables:
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# 3. Run database migrations (auto-created)
# No action needed; tables created on first run.
```

---

## 1. Top5 Selection Test

**Goal:** Verify scanner sends at most 5 signals per scan cycle.

**Steps:**
```bash
# Run a single scan
python main.py scan --alerts
```

**Expected:**
- Log shows: `Top 5 signals selected` or fewer
- If more than 5 qualifying signals, only 5 are processed
- Alert count matches number of final signals (≤5)

**Pass Criteria:** ✅ Number of alerts sent ≤ 5

---

## 2. Signal Update Detection Test

**Goal:** Verify that a recurring signal in Top5 triggers UPDATE, not NEW.

**Steps:**
1. Run first scan: `python main.py scan --alerts`
   - Note one symbol (e.g., BTC) appears as NEW
2. Without that signal resolving, run another scan within same day
3. Observe alert for that same symbol

**Expected:**
- Second alert says `🔄 SIGNAL UPDATE` with previous date
- Message includes progress P&L, current rank/score

**Pass Criteria:** ✅ Same symbol shows UPDATE not NEW

---

## 3. Stop Loss & Target Validation Test

**Goal:** All signals must pass SL/target validation before sending.

**Steps:**
- Scan with debug logging: `python main.py scan`
- Check logs for `Signal {symbol} rejected:` messages
- Alternatively, deliberately create invalid signals via test (harder)

**Expected:**
- Any signal with invalid SL (e.g., on wrong side) is rejected
- Any signal with T1 R:R < 1.5 rejected
- Logs show validation errors

**Pass Criteria:** ✅ No invalid signals pass through

---

## 4. Trade Journal Recording Test

**Goal:** Every NEW and UPDATE signal is recorded in JSON journal.

**Steps:**
```bash
# After a scan, check data directory
cat data/trade_journal.json | jq '.journal_trades'  # if jq installed
# or open file
```

**Expected:**
- New signals appear in `journal_trades` array
- Fields: symbol, direction, entry, stop_loss, targets, strategy, outcome=OPEN

**Pass Criteria:** ✅ Journal file updated with new trades

---

## 5. Learning & Optimization Test

**Goal:** After 20+ closed trades, strategy weights adjust automatically.

**Steps:**
1. Manually journal at least 20 closed trades with varied outcomes:
```bash
python main.py trade journal BTC LONG 50000 1 --sl 48000 --t1 55000 --t2 60000 --strategy TREND
# then later close them:
python main.py trade exit --trade-id XXX --exit_price 52000 TARGET_1_HIT
```
2. Run learning adaptation:
```bash
python main.py learning adapt
```
3. Check weights:
```bash
python main.py learning show
```

**Expected:**
- Weights for winning strategies increase
- Weights for losing strategies decrease
- Insights generated (if learning threshold met)

**Pass Criteria:** ✅ Weights change after sufficient data

---

## 6. Web UI Dashboard Test

**Goal:** All pages load with live data, top5 displayed correctly.

**Steps:**
```bash
# Start API server
python src/api.py
```
In browser:
- Open http://localhost:5000/dashboard
- Verify:
  - Summary stats (signals, win rate, etc.) populated
  - Top 5 signals cards displayed with rank, symbol, score, entry/SL/targets
  - Recent signals table populated
  - Market sentiment section
- Click through:
  - /trades → Open Trades tab + History tab
  - /performance → Stats, P&L chart, strategy table
  - /analysis → Insights list, strategy weights, performance analytics
  - /settings → Config form loads current values

**Expected:** All pages render without blank or error states.

**Pass Criteria:** ✅ All 5 pages load and show data

---

## 7. API Endpoint Verification

**Goal:** All REST endpoints return valid JSON.

**Commands:**
```bash
curl -s http://localhost:5000/api/dashboard | jq .
curl -s http://localhost:5000/api/signals/top5 | jq .
curl -s http://localhost:5000/api/trades/open | jq .
curl -s http://localhost:5000/api/trades/history | jq .
curl -s http://localhost:5000/api/performance/summary | jq .
curl -s http://localhost:5000/api/performance/by-strategy | jq .
curl -s http://localhost:5000/api/performance/pnl-curve?days=30 | jq .
curl -s http://localhost:5000/api/learning/insights | jq .
curl -s http://localhost:5000/api/scanner/status | jq .
```

**Expected:** All return `{"success": true, ...}` structure.

**Pass Criteria:** ✅ No 500 errors, JSON well-formed

---

## 8. Continuous Scanner Test

**Goal:** Scanner runs scheduled and sends alerts continually.

**Steps:**
```bash
python main.py --schedule
# Watch logs for repeated scans every 15 min (or configured)
```

**Expected:**
- Scanning continues without crashes
- Top5 selection respected each cycle
- Learning check runs periodically (log entry)

**Pass Criteria:** ✅ Runs for >1 hour without fatal errors

---

## Known Limitations & Notes

- `SignalMemory._fetch_current_price` stub: uses stored price, not live.
- PRD signals rely on existing scoring; enhanced scorer uses snapshot attached at creation.
- MTF signals snapshot uses coin state which may represent last TF; acceptable for demo.
- Duplicate Telegram avoided; other channels may get duplicate messages in scheduled mode (commented out).

---

## Success Checklist

- Top5 max signals per scan
- UPDATE vs NEW detection working
- All signals pass validation (SL %, R:R)
- Journal records every signal
- Strategy weights adapt after 20+ trades
- Dashboard renders with live data
- All API endpoints respond correctly
- Continuous scan stable

If all ✅ met, implementation complete.
