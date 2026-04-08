# Crypto Momentum & Reversal AI Scanner (Enhanced)

An **AI-first** self-improving crypto market scanner that adapts to market conditions and learns from trading performance. Continuously analyzes the **top 150 cryptocurrencies** and identifies high-probability trading setups.

## What's New in v2.0 (Enhanced Version)

### 🚀 AI-First Architecture

- **AI as Primary Decision Maker** - Signals generated and validated by AI
- **Rule-based Logic as Fallback** - Used when AI is unavailable
- **Journal-Aware Decisions** - AI references trade history before making decisions
- **APPROVE/REJECT/MODIFY** - AI decides whether to execute, reject, or modify signals

### 📊 New Engine Modules

- **Market Regime Engine** - Detects TRENDING, RANGING, HIGH_VOL, LOW_VOL
- **Coin Filter Engine** - Filters top 150 by volume/momentum/strength vs BTC
- **Confluence Engine** - Multi-signal scoring (0-10) with 6 factors
- **Position Sizer** - Dynamic position sizing based on confidence
- **Optimization Engine** - Auto-optimizes strategies based on win rate
- **Trade Journal** - Tracks all trades for continuous learning

## Features

### 🔍 Multi-Strategy Scanning

- **Trend Continuation (Long)** - EMA alignment with pullback entries
- **Bearish Trend Short** - Short setups in downtrends
- **Liquidity Sweep Reversal** - Detects fake breakouts
- **Volatility Breakout** - Captures explosive moves from compression
- **Multi-Timeframe Strategy** - Daily/1h/15m alignment

### 🧠 AI/LLM Integration (AI-First)

The scanner uses AI as the **primary decision maker**:

- **AI Signal Analysis** - Each signal is validated by AI
- **Journal-Aware** - References past trades before deciding
- **APPROVE/REJECT/MODIFY** - Explicit AI decisions
- **Fallback Mode** - Rule-based with 50% size reduction when AI fails

**Multiple AI Providers Supported**:

- OpenAI (GPT-4, GPT-4o-mini)
- Anthropic (Claude 3 Haiku)
- Groq (Fast free inference)
- Google Gemini
- Ollama (Local LLM)

### 📈 Adaptive Trading System

- **Market Regime Detection** - Adjusts strategy based on conditions
- **ATR-Based Stop Loss** - Dynamic stops instead of fixed 2%
- **Adaptive RSI** - Different bounds per regime (Trending: 60-75, Ranging: 40-60)
- **Confluence Scoring** - 8+ high, 6-8 medium, <6 reject
- **Auto-Optimization** - Disables weak strategies, boosts strong ones

### 📊 Trade Journal & Learning

- **Auto-logs** every signal with full trade data
- **Tracks outcomes** - Win/Loss, RR achieved, market regime
- **Performance metrics** - Win rate, avg RR, max drawdown
- **Auto-optimization** - Win rate <40% → reduce weight, >60% → boost

## Quick Start

### 1. Install Dependencies

```bash
cd crypto_scanner
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```env
# Telegram Alerts (Required for notifications)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_numeric_chat_id
```

### 3. Run Scanner

```bash
# Single scan
python main.py scan

# Single scan with Telegram alerts
python main.py scan --alerts

# Continuous scanning
python main.py continuous

# View statistics
python main.py stats

# Test alert configuration
python main.py test
```

### ⏰ Scheduled Scanner Mode

```bash
# Run with scheduler (daily at 3 PM IST Mon-Fri)
python main.py --schedule
```

## Configuration

### Scanner Settings

| Setting                 | Default  | Description              |
| ----------------------- | -------- | ------------------------ |
| `SCAN_INTERVAL_MINUTES` | 5        | Scan frequency (minutes) |
| `MAX_COINS_TO_SCAN`     | 500      | Max coins to analyze     |
| `MIN_SIGNAL_SCORE`      | 7.0      | Min confidence score     |
| `TIMEFRAMES`            | 4h,daily | Timeframes to scan       |

### AI/LLM Settings

| Setting               | Default | Description                |
| --------------------- | ------- | -------------------------- |
| `AI_PROVIDER`         | openai  | Primary AI provider        |
| `ENABLE_AI_ANALYSIS`  | true    | Enable AI analysis         |
| `AI_FALLBACK_ENABLED` | true    | Enable rule-based fallback |

### New Engine Settings

| Setting                | Default | Description              |
| ---------------------- | ------- | ------------------------ |
| `MIN_CONFLUENCE_SCORE` | 6.0     | Minimum confluence score |
| `MAX_POSITION_SIZE`    | 100%    | Base position size       |
| `OPTIMIZATION_ENABLED` | true    | Auto-optimize strategies |

## System Flow (Updated)

```
Scan → Filter Coins → Detect Regime → Generate Signals → Apply Confluence → AI Validate → Position Size → Execute → Log → Learn → Optimize
```

1. **Filter Coins** - Top 150 by volume/momentum/strength
2. **Detect Regime** - TRENDING/RANGING/HIGH_VOL/LOW_VOL
3. **Generate Signals** - Rule-based strategy engines
4. **Apply Confluence** - Score EMA, volume, RSI, BTC, timeframe
5. **AI Validate** - APPROVE/REJECT/MODIFY with journal awareness
6. **Position Size** - 9+→100%, 8+→70%, 7→50%, <6→skip
7. **Execute** - Send alerts
8. **Log** - Store in trade journal
9. **Learn** - Track outcomes and update metrics
10. **Optimize** - Adjust strategy weights based on performance

## Strategy Details

### Market Regime Adjustments

| Regime   | RSI Bounds | Favor Strategies                        | Min Confidence |
| -------- | ---------- | --------------------------------------- | -------------- |
| TRENDING | 55-75      | Trend Continuation, Volatility Breakout | 6.0            |
| RANGING  | 40-60      | Liquidity Sweep, Reversals              | 7.0            |
| HIGH_VOL | 45-70      | Volatility Breakout                     | 6.5            |
| LOW_VOL  | 30-70      | Avoid trades                            | 8.5            |

### Confluence Scoring (0-10)

- **EMA Alignment** (20%) - Strong EMA alignment = 10
- **Volume** (15%) - 2x volume = 10
- **RSI** (15%) - In optimal zone = 10
- **BTC Alignment** (25%) - Aligned with BTC trend = 10
- **Signal Quality** (15%) - High RR, trend aligned = 10
- **Timeframe Agreement** (10%) - Multi-TF alignment = 10

### Position Sizing

| Confidence | Position Size | Risk |
| ---------- | ------------- | ---- |
| 9+         | 100%          | 2%   |
| 8+         | 70%           | 1.4% |
| 7+         | 50%           | 1%   |
| <7         | Skip          | -    |

## Database

- **Signals**: `data/performance.db` (SQLite)
- **Trade Journal**: `data/trade_journal.db` (SQLite)

## Disclaimer

This scanner is for educational purposes. Always do your own research before making trading decisions. Cryptocurrency trading involves substantial risk.

## Version History

### v2.0.0 - Enhanced (Current)

- AI-first architecture with journal awareness
- Market Regime Engine (TRENDING/RANGING/HIGH_VOL/LOW_VOL)
- Confluence Scoring Engine (0-10)
- Position Sizing Engine
- Trade Journal System with auto-optimization
- Coin Filter Engine (top 150)
- Adaptive indicators (ATR stops, regime-aware RSI)

### v1.1.0 - AI Integration

- AI/LLM integration for signal analysis
- Multiple AI providers support
- Smart caching

### v1.0.0 - Initial Release

- Multi-strategy scanning
- Rule-based confidence scoring
- Bitcoin market filter
- Alert system

## License

MIT License
