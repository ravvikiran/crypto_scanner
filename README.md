# Crypto Momentum & Reversal AI Scanner

An AI-driven crypto market scanner that continuously analyzes the **top 500 cryptocurrencies** and identifies high-probability trading setups based on trend structure, volume confirmation, and volatility expansion. Now with **real AI/LLM integration** for intelligent signal analysis and generation.

## Features

### 🔍 Multi-Strategy Scanning

- **Trend Continuation (Long)** - EMA alignment with pullback entries
- **Bearish Trend Short** - Short setups in downtrends
- **Liquidity Sweep Reversal** - Detects fake breakouts
- **Volatility Breakout** - Captures explosive moves from compression

### 🧠 AI/LLM Integration

The scanner now uses AI to enhance trading signals:

- **AI Signal Analysis** - Each signal is analyzed by an LLM to:
  - Validate the trading setup
  - Provide enhanced reasoning and market context
  - Assess risk factors
  - Generate actionable recommendations
  - Identify key support/resistance levels

- **AI Signal Generation** - The AI can also generate its own signals by:
  - Analyzing market data independently
  - Identifying patterns the rule-based system might miss
  - Providing independent confirmation of setups

- **Multiple AI Providers Supported**:
  - OpenAI (GPT-4, GPT-4o-mini)
  - Anthropic (Claude 3)
  - Groq (Fast free inference)
  - Ollama (Local LLM)

- **Smart Caching** - Reduces API calls by caching analysis results

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

### AI/LLM Settings

| Setting | Default | Description |
| ------------------------- | ------- | --------------------- |
| `AI_PROVIDER` | openai | AI provider: openai, anthropic, groq, ollama |
| `OPENAI_API_KEY` | - | Your OpenAI API key |
| `ANTHROPIC_API_KEY` | - | Your Anthropic API key |
| `GROQ_API_KEY` | - | Your Groq API key (free) |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama local server URL |
| `ENABLE_AI_ANALYSIS` | true | Enable/disable AI analysis |
| `MAX_AI_CALLS_PER_SCAN` | 10 | Max AI analyses per scan |
| `CACHE_AI_ANALYSIS` | true | Cache results to reduce API calls |

## Setting Up AI Providers

### Option 1: Groq (Recommended - Free & Fast)

1. Get a free API key at https://console.groq.com/
2. Add to `.env`:
   ```
   AI_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key
   ```

### Option 2: OpenAI

1. Get an API key at https://platform.openai.com/
2. Add to `.env`:
   ```
   AI_PROVIDER=openai
   OPENAI_API_KEY=your_openai_api_key
   ```

### Option 3: Anthropic Claude

1. Get an API key at https://www.anthropic.com/
2. Add to `.env`:
   ```
   AI_PROVIDER=anthropic
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

### Option 4: Ollama (Local - No API Costs)

1. Install Ollama from https://ollama.ai
2. Run: `ollama pull llama3`
3. Add to `.env`:
   ```
   AI_PROVIDER=ollama
   OLLAMA_MODEL=llama3
   ```

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

### Standard Signal (Rule-based)
```
BNB SHORT (4h)
Strategy: Bearish Trend Short
Entry: $671.62 - $673.64
Stop Loss: $687.11
Targets: T1=$631.20, T2=$617.72
Risk/Reward: 1:3.0
Confidence: 8.5/10
```

### AI-Enhanced Signal
```
1. ETH LONG 🧠
   Strategy: Trend Continuation
   Timeframe: 4h
   Entry: $3245.00 - $3250.00
   Stop Loss: $3185.00
   Targets: T1=$3380.00, T2=$3450.00
   Risk/Reward: 1:3.5
   Confidence: 9.2/10
   🧠 AI Enhanced: Yes (AI conf: 9.5/10)
   Reason: Trend pullback to EMA20/EMA50. RSI momentum at 62.1.

   🧠 AI Analysis: Strong bullish setup with clear EMA alignment...
   📊 Market Context: BTC showing bullish momentum...
   ⚠️ Risk Assessment: Low risk - good risk/reward...
   🎯 Recommendation: STRONG BUY
```

## Database

Signals and trades are stored in `data/performance.db` (SQLite).

## Disclaimer

This scanner is for educational purposes. Always do your own research before making trading decisions. Cryptocurrency trading involves substantial risk.

## Version History

### v1.1.0 - AI Integration (Current)
- Added AI/LLM integration for intelligent signal analysis
- Support for multiple AI providers (OpenAI, Anthropic, Groq, Ollama)
- AI signal enhancement with market context and risk assessment
- AI-powered signal generation capability
- Smart caching to reduce API costs

### v1.0.0 - Initial Release
- Multi-strategy scanning
- Rule-based confidence scoring
- Bitcoin market filter
- Alert system

## License

MIT License
