# Crypto Momentum & Reversal AI Scanner (Enhanced)

An **AI-first** self-improving crypto market scanner that identifies high-probability trading opportunities based on **Trend Continuation**, **Breakouts**, and **Pullbacks**. Continuously scans the **top 100+ cryptocurrencies** across multiple timeframes.

## What's New in v2.1 (PRD Signal Engine)

### 🎯 PRD-Specific Features

- **Breakout Signals** - Resistance breakout + volume ≥1.5x + bullish close
- **Pullback Signals** - EMA 20/50 pullback + RSI 40-55 + bullish reversal
- **Trend Detection** - Price > EMA 50 > EMA 200 + Higher Highs/Higher Lows
- **Rejection Filters** - Excludes price below EMA 200, low volume, choppy markets
- **AI Confidence Score** - 0-100 scale based on trend/volume/structure/volatility
- **PRD Output Format** - Clear signals with entry, stop loss, target, and reasoning

### 📊 New Engine Modules

- **PRD Signal Engine** - Complete PRD signal logic implementation
- **Market Regime Engine** - Detects TRENDING, RANGING, HIGH_VOL, LOW_VOL
- **Coin Filter Engine** - Filters by volume/momentum/strength vs BTC
- **Confluence Engine** - Multi-signal scoring (0-10) with 6 factors

## Features

### 🔍 PRD Signal Types

- **Breakout** - Price breaks above resistance with volume confirmation
- **Pullback** - Healthy retracement to EMA with RSI 40-55 zone
- **Trend Continuation** - EMA aligned with momentum

### 📈 Risk Management

- Stop Loss: Below recent swing low or 1.5-2% below entry
- Max Risk per Trade: 1-2%
- Minimum Risk/Reward: 1:2

### 🧠 AI/LLM Integration

**Multiple AI Providers Supported**:
- OpenAI (GPT-4, GPT-4o-mini)
- Anthropic (Claude 3 Haiku)
- Groq (Fast free inference)
- Google Gemini
- Ollama (Local LLM)

### 📊 Trade Journal & Learning

- Auto-logs every signal with full trade data
- Tracks outcomes - Win/Loss, RR achieved, market regime
- Performance metrics - Win rate, avg RR
- Auto-optimization based on win rate

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

# AI Provider (optional - enables AI analysis)
OPENAI_API_KEY=your_key
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

| Setting | Default | Description |
|---------|---------|-------------|
| `SCAN_INTERVAL_MINUTES` | 5 | Scan frequency (minutes) |
| `MAX_COINS_TO_SCAN` | 500 | Max coins to analyze |
| `TOP_COINS_BY_MARKET_CAP` | 100 | Top N coins by market cap |
| `TIMEFRAMES` | 4h,daily | Timeframes to scan |

### PRD Engine Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ENABLE_PRD_STRATEGY` | true | Enable PRD signal detection |
| `PRD_TIMEFRAMES` | 4h,daily | PRD timeframes |
| `PRD_MIN_CONFIDENCE` | 70.0 | Min AI confidence (0-100) |
| `BREAKOUT_VOLUME_MULTIPLIER` | 1.5 | Volume required for breakout |
| `PULLBACK_RSI_LOW` | 40 | Pullback RSI lower bound |
| `PULLBACK_RSI_HIGH` | 55 | Pullback RSI upper bound |
| `MIN_RISK_REWARD` | 2.0 | Minimum R/R ratio |

### Alert Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ALERT_CONFIDENCE_THRESHOLD` | 70 | Send alerts above this confidence |
| `ALERT_COOLDOWN_HOURS` | 24 | Duplicate alert cooldown |

## Signal Output Format

```
🟢 LONG - Breakout

SOL/USDT

Entry: $145.00
Stop Loss: $138.00
Target: $165.00

Confidence Score: 82%

Reason:
Breakout on 4h | Resistance breakout at $143.50 | 
Volume spike (2.1x avg) | Strong bullish close | 
Market in uptrend (EMA aligned)
```

## System Flow

```
Scan → Filter Coins → Detect Regime → Generate PRD Signals → 
Apply Confluence → AI Validate → Filter by R/R → 
Position Size → Execute → Log → Learn
```

1. **Filter Coins** - Top 100+ by market cap and volume
2. **Detect Regime** - TRENDING/RANGING/HIGH_VOL/LOW_VOL
3. **Generate PRD Signals** - Breakout, Pullback, Trend Continuation
4. **Apply Confluence** - Score EMA, volume, RSI, BTC alignment
5. **AI Validate** - Optional AI enhancement
6. **Filter by R/R** - Reject signals with R/R < 2.0
7. **Execute** - Send alerts (confidence ≥70)

## PRD Signal Logic

### Trend Detection
- Price > EMA 50 > EMA 200
- Last 3 swing highs are increasing
- Last 3 swing lows are increasing

### Breakout Signal
- Price breaks above resistance (last 20-period high)
- Volume ≥ 1.5x average volume
- Candle closes above breakout level

### Pullback Signal
- Uptrend confirmed
- Price retraces to EMA 20 or EMA 50
- RSI between 40-55
- Bullish reversal candle appears

### Rejection (Don't Trade)
- Price below EMA 200
- Low volume environment
- Choppy sideways market

## Database

- **Signals**: `data/performance.db` (SQLite)
- **Trade Journal**: `data/trade_journal.db` (SQLite)

## Disclaimer

This scanner is for educational purposes. Always do your own research before making trading decisions. Cryptocurrency trading involves substantial risk.

## Version History

### v2.1.0 - PRD Signal Engine (Current)
- PRD signal logic (Breakout, Pullback, Trend)
- AI Confidence Scoring (0-100)
- Risk Management Layer
- PRD output format

### v2.0.0 - Enhanced
- AI-first architecture with journal awareness
- Market Regime Engine
- Confluence Scoring Engine

### v1.0.0 - Initial Release
- Multi-strategy scanning
- Rule-based confidence scoring

## License

MIT License