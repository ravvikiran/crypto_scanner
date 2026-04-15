# Crypto Scanner - Developer Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Trading Strategies](#trading-strategies)
4. [Risk Management](#risk-management)
5. [AI Integration](#ai-integration)
6. [Learning System](#learning-system)
7. [Running the Scanner](#running-the-scanner)
8. [Configuration](#configuration)

---

## Overview

**Crypto Scanner** is an AI-powered crypto trading signal scanner that:
- Continuously scans top 100-300 cryptocurrencies 24x7
- Runs every 15 minutes in continuous mode
- Sends top 3 signals to Telegram with entry, SL, and targets
- Monitors open positions for SL/TP hits
- Self-improves based on trade outcomes

---

## Architecture

### Project Structure

```
crypto_scanner/
├── main.py                 # CLI entry point
├── scanner.py              # Main scanner orchestration
├── config.yaml             # Configuration file
├── Procfile                 # Railway deployment
│
├── strategies/             # Trading strategy engines
│   ├── prd_signal_engine.py    # PRD breakout/pullback signals
│   ├── mtf_engine.py          # Multi-timeframe signals
│   └── __init__.py            # Trend continuation
│
├── engines/                # Core analysis engines
│   ├── coin_filter_engine.py   # Filter coins by volume/mcap
│   ├── confluence_engine.py  # Multi-signal scoring
│   ├── risk_management_engine.py
│   ├── position_sizer.py
│   └── market_regime_engine.py
│
├── ai/                     # AI analysis & enhancement
│   └── __init__.py           # AI signal enhancer
│
├── alerts/                 # Alert & notification system
│   ├── __init__.py          # AlertManager
│   ├── signal_publisher.py  # Publishes signals, monitors SL/TP
│   └── telegram_bot.py      # Telegram integration
│
├── learning/               # Self-improvement system
│   ├── trade_journal.py    # Tracks all trades
│   ├── signal_tracker.py   # Tracks active signals
│   ├── self_adaptation.py  # Adapts strategy weights
│   └── accuracy_scorer.py  # Scores predictions
│
├── collectors/             # Data collection
│   └── __init__.py         # MarketDataCollector
│
├── strategies/            # Technical indicators
│   └── __init__.py        # EMA, RSI, ATR, Bollinger
│
└── models/                # Data models
    └── __init__.py        # CoinData, TradingSignal, etc.
```

### Flow

```
Scheduler (15 min interval)
    ↓
CryptoScanner.run_scan()
    ↓
1. Collect market data (coins, candles)
2. Run PRD Engine (breakout/pullback)
3. Run MTF Engine (multi-timeframe)
4. Apply filters (BTC correlation, volume)
5. Score & rank signals
6. Apply AI enhancements (optional)
7. Keep top 3 signals
    ↓
SignalPublisher
    - Send Telegram alert
    - Journal trade
    - Monitor for SL/TP
```

---

## Trading Strategies

### 1. PRD Signal Engine (`strategies/prd_signal_engine.py`)

#### Breakout Signal (LONG)
- **Entry**: Current price + 0.1% to +0.5%
- **Stop Loss**: Recent swing low × 0.985 (or 2% below)
- **Target 1**: 1st swing high above entry
- **Target 2**: 2nd swing high above entry
- **Conditions**:
  - Price breaks resistance
  - Volume ≥ 1.5x average
  - Bullish close above resistance
  - Trend: EMA50 > EMA200

#### Breakout Signal (SHORT)
- **Entry**: Current price - 0.1% to -0.5%
- **Stop Loss**: Recent swing high × 1.015 (or 2% above)
- **Target 1**: 1st swing low below entry
- **Target 2**: 2nd swing low below entry

#### Pullback Signal (LONG)
- **Entry**: Price at EMA20/EMA50 zone
- **RSI**: 40-55 (oversold recovery)
- **Stop Loss**: Recent swing low × 0.985

#### Pullback Signal (SHORT)
- **Entry**: Price at EMA20/EMA50 zone  
- **RSI**: 45-60

### 2. Multi-Timeframe Engine (`strategies/mtf_engine.py`)

- **Daily**: Trend direction (EMA200 alignment)
- **1H**: Market structure (Higher Highs/Lower Lows)
- **15m**: Entry timing (breakout confirmation)
- All timeframes must align

### 3. Trend Continuation Engine (`strategies/__init__.py`)

- **Bullish**: EMA20 > EMA50 > EMA100 > EMA200
- **Bearish**: EMA20 < EMA50 < EMA100 < EMA200
- **Entry**: Price retraces to EMA with volume contraction

---

## Risk Management

### Stop Loss Rules
- Always use recent swing low/high from price data
- Buffer: 1.5% below/above swing level
- Fallback: 2% from entry if no swing detected

### Target Calculation
- **Primary**: Actual swing levels from chart (T1, T2)
- **Fallback**: 2R/3R if not enough swing levels

### Position Sizing (`engines/position_sizer.py`)
- Max 2% risk per trade
- Risk/Reward minimum: 1:2
- Daily loss cap: 3%

### Filters (`engines/`)
- **Volume Filter**: Min $1M 24h volume
- **Market Cap Filter**: Min $10M market cap
- **BTC Filter**: Align with BTC trend
- **Confluence Filter**: Min 6/10 score

---

## AI Integration

### Role of AI (`ai/__init__.py`)

AI is **optional enhancement** - not required for signals:

1. **Signal Validation**
   - AI reviews each signal
   - Can APPROVE, REJECT, or MODIFY
   - Considers market regime, volume, structure

2. **Confidence Scoring**
   - Scores 0-100 based on:
     - Trend strength
     - Volume confirmation
     - Market structure quality
     - Volatility
     - Price level

3. **Entry Adjustment**
   - Can adjust entry zone
   - Can adjust stop loss
   - Provides reasoning

### Supported AI Providers
- OpenAI (GPT-4, GPT-4o-mini)
- Anthropic (Claude 3 Haiku)
- Groq (Fast free inference)
- Google Gemini
- Ollama (Local LLM)

### Without AI
The scanner works fully without AI using rule-based scoring:
- Confidence = f(trend, volume, structure, risk_reward)
- Min score: 7.0/10

---

## Learning System

### How It Works

1. **Trade Journal** (`learning/trade_journal.py`)
   - Records every published signal
   - Entry price, SL, targets, direction
   - Updates outcome when closed

2. **Signal Tracker** (`learning/signal_tracker.py`)
   - Tracks active signals
   - Monitors for SL/TP hits

3. **Self-Adaptation** (`learning/self_adaptation.py`)
   - Analyzes outcomes
   - Adjusts strategy weights
   - Timeframe weights
   - Direction bias

### Adaptation Process
```
After 5+ resolved trades:
    → Analyze win rate by strategy
    → Analyze win rate by timeframe  
    → Adjust weights toward better performers
    → Log recommendations
```

### Metrics Tracked
- Total signals generated
- Long vs Short breakdown
- Win rate by strategy
- Win rate by timeframe
- Average risk/reward achieved

---

## Running the Scanner

### Local Development

```bash
# Single scan
python main.py scan --alerts

# Continuous (15 min interval)
python main.py continuous

# With scheduler (24x7)
python main.py --schedule

# Test alerts
python main.py test

# Show stats
python main.py stats
```

### Railway Deployment

The `Procfile` handles deployment:
```
worker: python main.py --schedule
```

This runs:
- Continuous scanning every 15 minutes
- Signal publishing to Telegram
- SL/TP monitoring

---

## Configuration

### `config.yaml` Key Settings

```yaml
scheduler:
  timezone: "Asia/Kolkata"
  run_mode: "continuous"
  continuous_interval_minutes: 15
  run_days: [0,1,2,3,4,5,6]  # All days

scanner:
  min_signal_score: 7.0
  top_coins_by_market_cap: 300
  max_trades_per_day: 5
  daily_loss_cap: 0.03

strategy:
  breakout_volume_multiplier: 1.5
  pullback_rsi_low: 40
  pullback_rsi_high: 55
  min_risk_reward: 2.0
  max_risk_per_trade: 0.02

alerts:
  max_daily_signals: 3
  confidence_threshold: 70
```

### Telegram Setup

Set environment variables:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_CHANNEL_CHAT_ID=your_channel_id
```

---

## Signal Output Format

When a signal is found, Telegram receives:

```
📈 BREAKOUT SIGNAL (LONG)

🔔 BTC/USDT
Entry Zone: $67,250 - $67,500
Stop Loss: $66,200
Target 1: $68,500
Target 2: $69,800
Risk/Reward: 1:2.5
Confidence: 8.5/10
Timeframe: 4h
```

---

## Troubleshooting

### No signals?
- Check market hours (24x7 for crypto)
- Verify API keys in config
- Check Telegram credentials
- Try: `python main.py test`

### Signals but no alerts?
- Ensure `max_daily_signals` not reached
- Check daily limit reset at midnight IST

### Wrong targets?
- Targets now use actual swing levels from chart
- Fallback to 2R/3R if insufficient levels

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `scanner.py` | Main orchestration |
| `main.py` | CLI entry point |
| `strategies/prd_signal_engine.py` | Breakout/pullback |
| `strategies/mtf_engine.py` | Multi-timeframe |
| `engines/confluence_engine.py` | Signal scoring |
| `ai/__init__.py` | AI enhancement |
| `alerts/signal_publisher.py` | Telegram + monitoring |
| `learning/trade_journal.py` | Trade tracking |
| `learning/self_adaptation.py` | Self-improvement |

---

For issues or questions, check the logs in `logs/scanner.log`.