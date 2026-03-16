# Crypto Momentum & Reversal AI Scanner

An AI-driven crypto market scanner that continuously analyzes the **top 500 cryptocurrencies** and identifies high-probability trading setups based on trend structure, volume confirmation, and volatility expansion.

## Features

### 🔍 Multi-Strategy Scanning

- **Trend Continuation (Momentum)** - EMA alignment with pullback entries
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

### 🔔 Alert System

- Telegram Bot notifications
- Discord Webhooks
- Email alerts
- TradingView alert syntax

### 📈 Performance Tracking

- SQLite database for signal history
- Win rate and P&L tracking
- CSV export capability

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

Edit `.env` and add your API keys:

```env
# API Keys
COINGECKO_API_KEY=your_key_here

# Alert Settings
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DISCORD_WEBHOOK_URL=your_webhook_url
```

### 3. Run Scanner

```bash
# Single scan
python main.py scan --display --alerts

# Continuous scanning
python main.py continuous

# Continuous scanning with alerts
python main.py continuous --alerts

# View statistics
python main.py stats

# Test alerts
python main.py test
```

## Project Structure

```
crypto_scanner/
├── config/           # Configuration management
├── models/           # Data models and enums
├── collectors/      # Market data collection (CoinGecko, Binance)
├── indicators/     # Technical indicators (EMA, RSI, ATR, Bollinger)
├── strategies/      # Trading strategy engines
├── scorer/          # AI signal scoring
├── filters/        # Bitcoin market filter
├── alerts/         # Alert notifications
├── dashboard/      # Display dashboard
├── storage/        # Performance tracking
├── scanner.py      # Main orchestrator
├── main.py         # CLI interface
└── requirements.txt
```

## Configuration

### Scanner Settings

| Setting                   | Default | Description           |
| ------------------------- | ------- | --------------------- |
| `SCAN_INTERVAL_MINUTES`   | 5       | Scan frequency        |
| `MAX_COINS_TO_SCAN`       | 500     | Max coins to analyze  |
| `MIN_MARKET_CAP_MILLIONS` | $50M    | Min market cap filter |
| `MIN_VOLUME_24H_MILLIONS` | $5M     | Min 24h volume        |
| `MIN_SIGNAL_SCORE`        | 7.0     | Min confidence score  |

### Strategy Parameters

| Indicator     | Period | Description           |
| ------------- | ------ | --------------------- |
| EMA Short     | 20     | Fast moving average   |
| EMA Medium    | 50     | Medium moving average |
| EMA Long      | 100    | Slow moving average   |
| EMA Very Long | 200    | Trend confirmation    |
| RSI           | 14     | Momentum oscillator   |
| ATR           | 14     | Volatility measure    |
| Bollinger     | 20     | Range compression     |

## Supported Timeframes

- Daily (`daily`)
- 4 Hours (`4h`)
- 1 Hour (`1h`)
- 15 Minutes (`15m`)

## Strategy Details

### 1. Trend Continuation (Long)

**Conditions:**

- Price > EMA20 > EMA50 > EMA100 > EMA200
- Volume > Volume MA(30)
- RSI between 55-70
- Pullback to EMA20/EMA50

**Entry:** Break above previous candle high  
**Stop:** Below EMA50  
**Target:** 2R risk reward

### 2. Bearish Trend Short

**Conditions:**

- Price < EMA20 < EMA50 < EMA100 < EMA200
- Bounce to EMA20/EMA50

**Entry:** Break below previous candle low  
**Stop:** Above EMA50  
**Target:** 2R-3R

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

## API Rate Limits

- **CoinGecko Free:** 10-30 calls/minute
- **Binance:** 1200 calls/minute
- Cache data locally to reduce API calls

## Database

Signals and trades are stored in `data/performance.db` (SQLite).

### Export Signals

```bash
python main.py stats --export signals.csv
```

## Future Enhancements

- Machine learning signal scoring
- Whale wallet tracking
- Funding rate analysis
- Order book imbalance
- Sentiment analysis
- Paper trading integration

## Disclaimer

This scanner is for educational purposes. Always do your own research before making trading decisions. Cryptocurrency trading involves substantial risk.

## License

MIT License
