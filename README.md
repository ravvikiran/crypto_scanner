# Crypto Momentum & Reversal AI Scanner

An AI-driven crypto market scanner that continuously analyzes the **top 500 cryptocurrencies** and identifies high-probability trading setups based on trend structure, volume confirmation, and volatility expansion.

## Features

### 🔍 Multi-Strategy Scanning

- **Trend Continuation (Long)** - EMA alignment with pullback entries
- **Bearish Trend Short** - Short setups in downtrends
- **Liquidity Sweep Reversal** - Detects fake breakouts
- **Volatility Breakout** - Captures explosive moves from compression

### 🧠 AI Signal Scoring

- Confidence scoring (0-10) based on:
  - Trend alignment (+3)
  - Volume confirmation (+2)
  - BTC alignment (+2)
  - Volatility expansion (+2)
  - Liquidity sweep (+1)

### 📊 Bitcoin Market Filter

- Filters signals based on Bitcoin's trend
- Avoids trading against the market leader
- LONG signals when BTC is Bullish
- SHORT signals when BTC is Bearish

### 🎯 Quality Filters

- Minimum 3:1 Risk/Reward ratio
- Excludes stablecoins (USDT, USDC, DAI, etc.)
- Price range filter ($1 - $10,000)

### 🔔 Alert System

- Telegram Bot notifications
- Discord Webhooks
- Email alerts

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

Edit `.env` and add your Telegram credentials:

```env
# Telegram Alerts (Required for notifications)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_numeric_chat_id
```

**To get Telegram Chat ID:**
1. Search for @BotFather on Telegram and create a bot
2. Search for @userinfobot to get your numeric chat ID

### 3. Run Scanner

```bash
# Single scan
python main.py scan

# Single scan with Telegram alerts
python main.py scan --alerts

# Continuous scanning (every 5 minutes)
python main.py continuous

# Continuous scanning with Telegram alerts
python main.py continuous --alerts

# View statistics
python main.py stats

# Test alert configuration
python main.py test
```

## Configuration

### Scanner Settings

| Setting | Default | Description |
| ------------------------- | ------- | --------------------- |
| `SCAN_INTERVAL_MINUTES` | 5 | Scan frequency (minutes) |
| `MAX_COINS_TO_SCAN` | 500 | Max coins to analyze |
| `MIN_MARKET_CAP_MILLIONS` | $10M | Min market cap filter |
| `MIN_VOLUME_24H_MILLIONS` | $1M | Min 24h volume |
| `MIN_SIGNAL_SCORE` | 7.0 | Min confidence score |
| `TIMEFRAMES` | 4h,daily | Timeframes to scan |

Edit these in `.env` file.

## Supported Timeframes

- 4 Hours (`4h`)
- Daily (`daily`)

## Strategy Details

### 1. Trend Continuation (Long)

**Conditions:**

- Price > EMA20 > EMA50 > EMA100 > EMA200
- Volume > Volume MA(30)
- RSI between 55-70
- Pullback to EMA20/EMA50

**Entry:** Slightly above current price  
**Stop:** Below entry (2%)  
**Target:** 3R-4R risk reward

### 2. Bearish Trend Short

**Conditions:**

- Price < EMA20 < EMA50 < EMA100 < EMA200
- Bounce to EMA20/EMA50

**Entry:** Slightly below current price  
**Stop:** Above entry (2%)  
**Target:** 3R-4R risk reward

### 3. Liquidity Sweep Reversal

**Conditions:**

- Price breaks previous high/low
- Volume spike
- Candle closes below/above breakout level

**Signal:** Reversal opportunity after liquidity grab

### 4. Volatility Breakout

**Conditions:**

- ATR lowest in 20 periods
- Bollinger Band squeeze
- Range contraction

**Entry:** Breakout above/below range  
**Stop:** Middle of range  
**Target:** Measured move

## Signal Output Example

```
BNB SHORT (4h)
Strategy: Bearish Trend Short
Entry: $671.62 - $673.64
Stop Loss: $687.11
Targets: T1=$631.20, T2=$617.72
Risk/Reward: 1:3.0
Confidence: 10.0/10
```

## Database

Signals and trades are stored in `data/performance.db` (SQLite).

## Disclaimer

This scanner is for educational purposes. Always do your own research before making trading decisions. Cryptocurrency trading involves substantial risk.

## License

MIT License
