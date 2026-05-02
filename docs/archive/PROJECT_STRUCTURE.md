# 📘 Crypto Scanner - Complete Project Structure & Architecture

## Table of Contents
1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Core Architecture](#core-architecture)
4. [Data Flow](#data-flow)
5. [Component Deep Dive](#component-deep-dive)
6. [Feature Implementation Map](#feature-implementation-map)
7. [Integration Points](#integration-points)
8. [Development Guide](#development-guide)

---

## Project Overview

**Project Name:** Crypto Scanner  
**Purpose:** Automated cryptocurrency trading signal scanner with AI-powered market sentiment analysis, intelligent signal validation, and market trend monitoring.  
**Tech Stack:** Python, AsyncIO, LLM (OpenAI/Gemini), Telegram Bot, Discord Webhooks, Railway deployment

**Core Capabilities:**
- Scan multiple cryptocurrencies for trading signals
- Analyze market sentiment and conditions
- Generate trading alerts (LONG/SHORT)
- Validate signals with AI agent
- Monitor market trend phases (BULLISH/BEARISH)
- Send alerts via Telegram, Discord, Email
- Track signal accuracy and performance
- Self-adapt based on learning

---

## Directory Structure

```
crypto_scanner/
│
├── 📄 main.py                          # Entry point, launches scanner
├── 📄 scanner.py                       # Main orchestrator, runs the scan
├── 📄 config.yaml                      # Configuration file (API keys, thresholds)
├── 📄 requirements.txt                 # Python dependencies
├── 📄 Procfile                         # Railway deployment config
│
├── 📁 ai/                              # AI & ML Components
│   ├── __init__.py                     # Exports
│   ├── market_sentiment_analyzer.py    # AI sentiment analysis
│   └── signal_validation_agent.py      # 🤖 AI agent for signal validation
│
├── 📁 engines/                         # Core Signal & Market Engines
│   ├── __init__.py                     # Exports
│   ├── market_sentiment_engine.py      # Market sentiment calculation
│   ├── trend_alert_engine.py           # Market trend phase alerts
│   ├── coin_filter_engine.py           # Coin filtering & ranking
│   ├── position_sizer.py               # Position sizing logic
│   ├── risk_management_engine.py       # Risk management rules
│   ├── confluence_engine.py            # Multi-timeframe analysis
│   ├── optimization_engine.py          # Signal optimization
│   └── market_regime_engine.py         # Market regime detection
│
├── 📁 strategies/                      # Trading Signal Strategies
│   ├── __init__.py                     # Exports
│   ├── mtf_engine.py                   # Multi-timeframe strategy
│   └── prd_signal_engine.py            # PRD (Price-Reversal-Direction) strategy
│
├── 📁 alerts/                          # Alert & Notification System
│   ├── __init__.py                     # Exports
│   ├── alert_manager.py                # Alert dispatcher & formatter
│   ├── signal_publisher.py             # Signal publishing logic
│   └── telegram_bot.py                 # Telegram bot integration
│
├── 📁 learning/                        # Learning & Self-Adaptation
│   ├── __init__.py                     # Exports
│   ├── accuracy_scorer.py              # Scores signal accuracy
│   ├── learning_engine.py              # Learns from results
│   ├── signal_tracker.py               # Tracks signal performance
│   ├── trade_journal.py                # Maintains trade journal
│   ├── resolution_checker.py           # Checks signal resolution
│   ├── self_adaptation.py              # Adapts parameters
│   └── notifier.py                     # Notifies on updates
│
├── 📁 reasoning/                       # Advanced Reasoning
│   ├── __init__.py                     # Exports
│   └── hybrid_reasoner.py              # Combines AI + rule-based logic
│
├── 📁 collectors/                      # Data Collection (Future)
│   └── __init__.py                     # Placeholder
│
├── 📁 filters/                         # Signal Filters
│   └── __init__.py                     # Placeholder
│
├── 📁 indicators/                      # Technical Indicators
│   └── __init__.py                     # Placeholder
│
├── 📁 models/                          # Data Models
│   └── __init__.py                     # Placeholder
│
├── 📁 config/                          # Configuration Management
│   └── __init__.py                     # Configuration utilities
│
├── 📁 memory/                          # Memory & State
│   └── __init__.py                     # Memory utilities
│
├── 📁 storage/                         # Data Storage
│   └── __init__.py                     # Storage utilities
│
├── 📁 src/                             # Source modules
│   ├── __init__.py                     # Exports
│   └── scheduler/                      # Scheduler system
│       ├── __init__.py
│       └── scanner_scheduler.py        # Cron-like scheduling
│
├── 📁 data/                            # Data storage
│   └── learning_history.json           # Learning history data
│
├── 📁 memory/                          # Persistent memory
│   ├── __init__.py
│   └── (market states, sentiment history)
│
├── 📁 logs/                            # Application logs
│
├── 📁 docs/                            # Documentation
│   ├── ISSUES.md                       # Known issues
│   └── PRD_REASONING_LEARNING.md       # PRD reasoning documentation
│
└── 📄 README.md                        # Project readme

```

---

## Core Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CRYPTO SCANNER SYSTEM                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌──────────────┐    ┌──────────────┐
            │   main.py    │    │   config.yaml│
            │  (Entry)     │    │  (Settings)  │
            └──────┬───────┘    └──────┬───────┘
                   │                   │
                   └─────────┬─────────┘
                             ▼
                      ┌─────────────────┐
                      │  scanner.py     │
                      │  (Orchestrator) │
                      └────────┬────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
   ┌─────────────┐      ┌──────────────┐     ┌────────────────┐
   │ Data Input  │      │ Core Engines │     │ AI Systems     │
   ├─────────────┤      ├──────────────┤     ├────────────────┤
   │• Coin List  │      │• Sentiment   │     │• Sentiment AI  │
   │• Market API │      │• Trend Alert │     │• Agent Validation
   │• Price Data │      │• Strategies  │     │• Reasoning     │
   └─────────────┘      │• Risk Mgmt   │     └────────────────┘
                        │• Position    │
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
            ┌──────────────────┐   ┌────────────────┐
            │  Signal Filter   │   │  Learning Sys  │
            │  Confidence      │   │  Accuracy Score│
            │  Ranking         │   │  Self-Adapt    │
            └────────┬─────────┘   │  Trade Journal │
                     │             └────────┬───────┘
                     │                      │
                     └──────────┬───────────┘
                                ▼
                      ┌──────────────────────┐
                      │   Alert Manager      │
                      ├──────────────────────┤
                      │ • Telegram           │
                      │ • Discord            │
                      │ • Email              │
                      │ • Signal Publisher   │
                      └──────────────────────┘
```

---

## Data Flow

### Complete Signal Generation & Validation Flow

```
1. SCAN INITIATION
   └─ scheduler.py triggers scanner.py
   └─ main.py calls scanner.run_scan()
   └─ Load config, establish API connections

2. DATA COLLECTION
   ├─ Fetch top cryptocurrencies (by market cap)
   ├─ Get OHLCV data (1h, 4h, 1d timeframes)
   ├─ Retrieve current price & market data
   └─ Calculate technical indicators

3. MARKET ANALYSIS
   ├─ market_sentiment_engine.py
   │  ├─ Analyze Bitcoin trend (leading indicator)
   │  ├─ Calculate market breadth (% gainers vs losers)
   │  ├─ Measure market strength (0-100 score)
   │  ├─ Check altcoin performance
   │  ├─ Monitor BTC dominance
   │  ├─ Assess volatility levels
   │  └─ Output: MarketSentimentScore (VERY_BEARISH to VERY_BULLISH)
   │
   └─ ai/market_sentiment_analyzer.py (AI Deep Analysis)
      ├─ Call LLM provider with sentiment metrics
      ├─ Get AI interpretation & risk assessment
      └─ Store for decision making

4. TREND ALERT CHECK
   └─ engines/trend_alert_engine.py
      ├─ Compare current sentiment with previous
      ├─ Detect phase transitions:
      │  ├─ Entering VERY_BULLISH (great for longs!)
      │  ├─ Entering BULLISH
      │  ├─ Entering BEARISH (good for shorts)
      │  └─ Entering VERY_BEARISH (caution!)
      ├─ Detect momentum changes
      └─ SEND TREND ALERTS → alert_manager → Telegram/Discord

5. SIGNAL GENERATION (Per Coin)
   ├─ coin_filter_engine.py
   │  ├─ Filter coins by market cap, volume
   │  └─ Rank coins by momentum
   │
   ├─ strategies/mtf_engine.py
   │  ├─ Multi-timeframe analysis (1h, 4h, 1d)
   │  ├─ Check trend alignment
   │  ├─ Identify support/resistance
   │  ├─ Spot breakouts/breakdowns
   │  └─ Generate LONG/SHORT signals
   │
   └─ strategies/prd_signal_engine.py
      ├─ Price level analysis
      ├─ Reversal detection
      ├─ Direction confirmation
      └─ Generate signals with confidence

6. SIGNAL ENRICHMENT
   ├─ confluence_engine.py
   │  └─ Check multi-timeframe confluence
   │
   ├─ position_sizer.py
   │  └─ Calculate position sizes
   │
   ├─ risk_management_engine.py
   │  ├─ Set appropriate stop losses
   │  ├─ Calculate risk/reward
   │  └─ Validate risk parameters
   │
   └─ optimization_engine.py
      └─ Optimize entry points

7. 🤖 AI AGENT VALIDATION (NEW)
   └─ ai/signal_validation_agent.py
      ├─ Rule-Based Checks (8-point framework):
      │  ├─ Market alignment (is direction favorable?)
      │  ├─ Risk/reward validation (1:1.5+?)
      │  ├─ Entry zone tightness (<2%?)
      │  ├─ Stop loss distance (1-5%?)
      │  ├─ Confidence score (6+/10?)
      │  ├─ Coin market cap (>$10M?)
      │  ├─ Volume confirmation
      │  └─ Strategy appropriateness
      │
      ├─ AI Analysis (LLM):
      │  ├─ Call AI provider
      │  ├─ Get deeper market insights
      │  └─ Get override decision
      │
      ├─ Combine Results:
      │  ├─ Merge rule-based + AI scores
      │  ├─ Make final decision:
      │  │  ├─ APPROVE (70+) → Send alert + +1.0 confidence boost
      │  │  ├─ HOLD (40-70) → Send alert + 0.0 adjustment
      │  │  └─ REJECT (<40) → Block signal - 2.0 confidence
      │  └─ Log decision with reasoning
      │
      └─ Output: SignalValidationResult

8. LEARNING SYSTEM (Tracks Performance)
   ├─ signal_tracker.py
   │  └─ Tracks each signal sent
   │
   ├─ resolution_checker.py
   │  └─ Checks if signal resolved (hit target/stop)
   │
   ├─ accuracy_scorer.py
   │  ├─ Calculates accuracy per strategy
   │  ├─ Calculates accuracy per time frame
   │  └─ Stores in learning_history.json
   │
   ├─ learning_engine.py
   │  └─ Analyzes patterns in successful signals
   │
   ├─ self_adaptation.py
   │  ├─ Adjusts thresholds based on performance
   │  ├─ Updates strategy parameters
   │  └─ Improves over time
   │
   └─ trade_journal.py
      └─ Maintains detailed trade journal

9. ALERT DISPATCH
   └─ alerts/alert_manager.py
      ├─ Format signal alerts with:
      │  ├─ Entry, stop, targets
      │  ├─ Risk/reward ratio
      │  ├─ Confidence score (AI-adjusted)
      │  ├─ AI agent decision & reasoning
      │  ├─ Market sentiment context
      │  └─ Setup quality score
      │
      ├─ Send to Telegram
      │  ├─ Via telegram_bot.py
      │  └─ High-priority alerts highlighted
      │
      ├─ Send to Discord
      │  ├─ Embedded rich formatting
      │  └─ Color-coded by signal strength
      │
      └─ Send via signal_publisher.py
         └─ Other channels

10. AUDIT & LOGGING
    ├─ Log all decisions (AI agent, strategy, alerts sent)
    ├─ Store in decision logs
    ├─ Track performance metrics
    └─ Maintain history for analysis
```

---

## Component Deep Dive

### 1. Entry Point: `main.py`

**Purpose:** Application entry point

**Flow:**
```python
main.py
├─ Load config.yaml
├─ Initialize logging
├─ Create Scanner instance
└─ Start scheduler (if scheduled mode)
   └─ Call scanner.run_scan() periodically
```

**Key Functions:**
- Initialization of all systems
- Error handling for crashes
- Graceful shutdown

---

### 2. Orchestrator: `scanner.py`

**Purpose:** Main orchestrator that runs the complete scan

**Key Methods:**
```
run_scan():
├─ initialize_engines()           # Set up all engines
├─ get_market_data()              # Fetch coin list & market data
├─ analyze_market_sentiment()     # Step 1: Market analysis
├─ check_trend_alerts()           # Step 2: Check for trend entries
├─ process_coins():
│  ├─ For each coin:
│  │  ├─ fetch_coin_data()
│  │  ├─ generate_signals()       # Strategy signals
│  │  ├─ rank_signals()           # By confidence
│  │  └─ apply_filters()          # Risk management
│  │
│  └─ collect_top_signals()       # Top N signals
│
├─ validate_signals_with_agent()  # Step 3: AI Agent validation
├─ apply_market_filter()          # Step 4: Filter by sentiment
├─ send_alerts()                  # Step 5: Dispatch alerts
├─ check_signal_resolution()      # Step 6: Learning system
├─ update_accuracy()              # Update stats
└─ self_adapt_parameters()        # Self-learning
```

**State Variables:**
```python
self.sentiment_engine            # Market sentiment
self.ai_analyzer                 # AI sentiment
self.trend_alert_engine          # Trend alerts
self.signal_validation_agent     # AI agent
self.learning_engine             # Learning system
self.accuracy_tracker            # Accuracy scores
```

---

### 3. Market Sentiment: `engines/market_sentiment_engine.py`

**Purpose:** Analyze overall market conditions

**How It Works:**
```
Input: Market data (BTC trend, gainers%, market cap, volume)
│
├─ Calculate 7 metrics:
│  ├─ BTC Trend Score (BTC_MA_50 vs BTC_MA_200)
│  ├─ Market Breadth (% gainers vs losers)
│  ├─ Market Strength (volatility-adjusted strength)
│  ├─ Altcoin Performance (alts vs BTC)
│  ├─ BTC Dominance (BTC market cap %)
│  ├─ Volatility Assessment
│  └─ Volume Pattern (increasing/decreasing)
│
├─ Weight metrics:
│  BTC Trend: 25%
│  Breadth: 25%
│  Strength: 20%
│  Alts: 15%
│  Dominance: 10%
│  Other: 5%
│
└─ Output: MarketSentimentScore
   ├─ Sentiment: VERY_BEARISH (-100 to 100)
   ├─ Score: 0-100
   ├─ Individual metrics
   └─ Favorable for: LONG/SHORT/NEUTRAL
```

**Key Classes:**
- `MarketSentiment` - Enum (5 levels)
- `MarketSentimentScore` - Dataclass with all metrics

---

### 4. AI Sentiment Analyzer: `ai/market_sentiment_analyzer.py`

**Purpose:** Deep AI analysis of market conditions

**Flow:**
```
Input: MarketSentimentScore
│
├─ Call LLM (OpenAI/Gemini):
│  ├─ Provide market metrics
│  ├─ Get market interpretation
│  ├─ Get risk assessment
│  └─ Get trading recommendations
│
├─ Parse AI response:
│  ├─ Risk level: LOW/MEDIUM/HIGH/CRITICAL
│  ├─ Recommendation: VERY_BULLISH → VERY_BEARISH
│  └─ Explanation
│
├─ Monitor sentiment shifts:
│  ├─ Compare with previous sentiment
│  ├─ If change > 15 points → Alert
│  └─ Track shift history
│
└─ Output: Sentiment + Risk + Recommendations
```

---

### 5. Trend Alert Engine: `engines/trend_alert_engine.py`

**Purpose:** Alert on market phase entries/exits

**What It Detects:**
```
Sentiment History:        Detected Alert:
NEUTRAL → BULLISH    →    ENTERING_BULLISH
BULLISH → VERY_BULLISH → ENTERING_VERY_BULLISH
BULLISH → NEUTRAL    →    EXITING_BULLISH
BEARISH → VERY_BEARISH → ENTERING_VERY_BEARISH

Also Detects:
├─ Momentum changes (same phase, stronger)
├─ Quick phase transitions (>15 point jumps)
└─ Multi-hour trend confirmation
```

**Alerts Sent:**
```
🚀 ENTERING_VERY_BULLISH
   Score: 35 → 82 | Perfect for LONG trades!

📈 ENTERING_BULLISH
   Score: 45 → 65 | Good conditions for longs

📉 ENTERING_BEARISH
   Score: 55 → 30 | SHORT opportunities emerge

🔴 ENTERING_VERY_BEARISH
   Score: 40 → 15 | Caution! High risk environment
```

---

### 6. Coin Filter Engine: `engines/coin_filter_engine.py`

**Purpose:** Filter and rank cryptocurrencies

**Logic:**
```
Input: All cryptocurrencies
│
├─ Filter by market cap:
│  ├─ Min: >$10M (liquid)
│  ├─ Max: <$1T (manageable)
│  └─ Exclude stablecoins
│
├─ Filter by volume:
│  ├─ Daily volume > $1M USD
│  ├─ Volume ratio > 1.5x average
│  └─ Exclude low liquidity
│
├─ Calculate ranking scores:
│  ├─ Momentum score
│  ├─ Trend strength
│  ├─ Volume increase
│  └─ Support zone strength
│
├─ Rank top candidates:
│  ├─ Return top 20-50 coins
│  └─ Sort by composite score
│
└─ Output: List[Coin] ordered by quality
```

---

### 7. Multi-Timeframe Strategy: `strategies/mtf_engine.py`

**Purpose:** Generate signals using multiple timeframes

**Timeframes Used:**
- 1H (short-term confirmation)
- 4H (medium-term trend)
- 1D (long-term direction)

**Signal Generation:**
```
For each coin:

1. Analyze 1D (Daily - Direction)
   ├─ Is there an established trend?
   ├─ Are we above/below key moving averages?
   └─ Direction: UP / DOWN / NEUTRAL

2. Analyze 4H (4-Hour - Entry Setup)
   ├─ Identify pullback zones
   ├─ Find breakout levels
   ├─ Spot reversal patterns
   └─ Entry zones: Entry_Low - Entry_High

3. Analyze 1H (1-Hour - Confirmation)
   ├─ Final confirmation
   ├─ Volume analysis
   ├─ Momentum indicators
   └─ Confluence check

4. Generate Signal:
   ├─ Type: LONG / SHORT / NONE
   ├─ Entry zone (1H confirms)
   ├─ Stop loss (below support)
   ├─ Targets (1:1, 1:2, 1:3)
   ├─ Risk/Reward ratio
   └─ Confidence score (0-10)
```

**Example Signal:**
```
{
  "symbol": "BTC",
  "type": "LONG",
  "entry_low": 45000,
  "entry_high": 45500,
  "stop_loss": 44500,
  "target_1": 46000,
  "target_2": 47000,
  "target_3": 48000,
  "risk_reward": 1:2.5,
  "confidence": 8.2/10,
  "strategy": "mtf_breakout"
}
```

---

### 8. PRD Signal Engine: `strategies/prd_signal_engine.py`

**Purpose:** Price-Reversal-Direction signal strategy

**Framework:**
```
PRD = Price (strong level) + Reversal (pattern) + Direction (confirmed)

1. PRICE ANALYSIS
   ├─ Identify key price levels (support/resistance)
   ├─ Find strong confluence zones
   ├─ Measure price proximity to levels
   └─ Score: 0-10 based on level strength

2. REVERSAL DETECTION
   ├─ Pattern recognition (head/shoulder, double bottom, etc)
   ├─ Candlestick reversal patterns
   ├─ Volume reversal confirmation
   └─ Score: 0-10 based on pattern clarity

3. DIRECTION CONFIRMATION
   ├─ Multiple indicator alignment
   ├─ Moving average cross confirmation
   ├─ Momentum reversal
   └─ Score: 0-10 based on direction strength

4. COMBINED SIGNAL
   Total Score = (Price * 0.33) + (Reversal * 0.33) + (Direction * 0.34)
   
   If Total >= 7.0 → Generate Signal
   Else → Skip or Hold
```

---

### 9. 🤖 AI Signal Validation Agent: `ai/signal_validation_agent.py`

**Purpose:** Intelligent validation of every signal

**Validation Framework (8 Points):**

```
┌─────────────────────────────────────────┐
│  AI SIGNAL VALIDATION AGENT             │
└─────────────────────────────────────────┘

1. MARKET ALIGNMENT (20 points)
   ├─ Check: Is signal direction favorable?
   ├─ LONG in BULLISH market = ✓ (20 pts)
   ├─ LONG in BEARISH market = ✗ (0 pts)
   └─ Score: 0-20

2. RISK/REWARD RATIO (15 points)
   ├─ Check: Ratio >= 1:3.0 = ✓ (15 pts)
   ├─ Check: Ratio >= 1:2.0 = ✓ (10 pts)
   ├─ Check: Ratio >= 1:1.5 = ✓ (5 pts)
   └─ Score: 0-15

3. ENTRY ZONE TIGHTNESS (10 points)
   ├─ Check: Width < 2% = ✓ (10 pts)
   ├─ Check: Width 2-3% = ✓ (6 pts)
   ├─ Check: Width 3-5% = ✓ (3 pts)
   └─ Score: 0-10

4. STOP LOSS DISTANCE (10 points)
   ├─ Check: 1-3% from entry = ✓ (10 pts)
   ├─ Check: 3-5% from entry = ✓ (6 pts)
   ├─ Check: >5% from entry = ✗ (2 pts)
   └─ Score: 0-10

5. CONFIDENCE SCORE (10 points)
   ├─ Check: >= 8.0/10 = ✓ (10 pts)
   ├─ Check: >= 6.0/10 = ✓ (6 pts)
   ├─ Check: < 6.0/10 = ✗ (2 pts)
   └─ Score: 0-10

6. COIN CHARACTERISTICS (10 points)
   ├─ Market Cap > $100M = ✓ (10 pts)
   ├─ Market Cap $10M-$100M = ✓ (6 pts)
   ├─ Market Cap < $10M = ✗ (2 pts)
   └─ Score: 0-10

7. VOLUME CONFIRMATION (10 points)
   ├─ Check: Volume > 1.5x average = ✓
   ├─ Check: Volume increasing = ✓
   └─ Score: 0-10

8. STRATEGY APPROPRIATENESS (5 points)
   ├─ Check: Established strategy type = ✓
   ├─ Check: Multiple indicators align = ✓
   └─ Score: 0-5

─────────────────────────────────────────
TOTAL SCORE: 0-100 (Sum of all 8 checks)
```

**Decision Logic:**
```
Rule-Based Score + AI Analysis = Decision

Score >= 70 AND AI Agrees
  → ✅ APPROVE (+1.0 confidence boost)
  
40 <= Score < 70 OR AI Suggests Caution
  → ⏸️ HOLD (0.0 adjustment)
  
Score < 40 OR AI Rejects
  → ❌ REJECT (-2.0 confidence reduction)
```

**AI Analysis:**
```
LLM Receives:
├─ Rule-based score breakdown
├─ Signal details (entry, stop, target)
├─ Market sentiment context
├─ Coin characteristics
└─ Recent market history

LLM Returns:
├─ Agrees/Disagrees with rule score
├─ Override recommendation (if any)
├─ Risk assessment
└─ Detailed reasoning
```

---

### 10. Learning System: `learning/`

**Purpose:** Track signal accuracy and self-adapt

**Components:**

#### `signal_tracker.py`
- Tracks every signal sent
- Records: Symbol, entry, stop, targets, time sent
- Stores in memory for resolution checking

#### `resolution_checker.py`
- Checks if signal resolved (hit target or stop)
- Marks: WIN / LOSS / PARTIAL
- Calculates P&L

#### `accuracy_scorer.py`
- Calculates per-strategy accuracy:
  ```
  MTF Strategy: 65% accuracy (1W data)
  PRD Strategy: 72% accuracy (1W data)
  Overall: 68% accuracy
  ```
- Calculates per-timeframe accuracy
- Stores in `data/learning_history.json`

#### `learning_engine.py`
- Analyzes patterns in successful signals:
  ```
  ✓ Successful signals avg confidence: 7.8/10
  ✓ Successful signals avg R:R: 1:2.3
  ✗ Failed signals avg confidence: 5.2/10
  ```
- Identifies what works best

#### `self_adaptation.py`
- Adjusts parameters based on learning:
  ```
  Performance: 68%
  Confidence Threshold: 7.0 → 6.5 (increase signals)
  Risk/Reward Min: 1:1.5 → 1:2.0 (higher quality)
  ```

#### `trade_journal.py`
- Detailed trade log:
  ```
  Signal: BTC LONG 1h ago
  Entry Executed: 45,250
  Current Price: 45,800
  Status: In Profit (+550, +1.2%)
  P&L: +$1,100 (on $100k position)
  ```

---

### 11. Alert System: `alerts/`

**Flow:**
```
Signal Ready
    ↓
alert_manager.py
├─ Format signal data
├─ Add AI agent decision
├─ Add market context
├─ Add confidence/quality scores
    ↓
Dispatch to channels:
├─ telegram_bot.py → Telegram
│  ├─ Text formatting
│  └─ Keyboard with actions
│
├─ Discord webhook → Discord
│  ├─ Embedded rich formatting
│  ├─ Color by signal strength
│  └─ Reactions for interaction
│
└─ signal_publisher.py → Other channels
   ├─ Email
   └─ Custom webhooks
```

**Alert Content:**
```
🟢 LONG - Bitcoin
─────────────────────────
Symbol: BTC
Strategy: MTF Breakout
Timeframe: 4H

Entry Zone: $45,000 - $45,500
Stop Loss: $44,500
Target 1: $46,000
Target 2: $47,000

Risk/Reward: 1:2.2
Confidence: 8.2/10

Market Sentiment: VERY_BULLISH (82/100)
Gainers: 78% | Market Strength: 78/100

🤖 AI Agent Review:
   Setup Quality: 78/100
   Market Alignment: 95/100
   Decision: ✅ APPROVE (+1.0 boost)
   
Risk Level: MEDIUM
Position Size: 2-3% of portfolio
```

---

## Feature Implementation Map

### Feature: Trading Signal Generation

**Which code generates it:**
```
1. Data Collection
   └─ scanner.py: get_market_data()

2. Market Analysis
   └─ engines/market_sentiment_engine.py: analyze_market_sentiment()

3. Signal Strategy 1 (Multi-Timeframe)
   └─ strategies/mtf_engine.py: generate_mtf_signals()

4. Signal Strategy 2 (PRD)
   └─ strategies/prd_signal_engine.py: generate_prd_signals()

5. Confluence Check
   └─ engines/confluence_engine.py: check_confluence()

6. Position Sizing
   └─ engines/position_sizer.py: calculate_position_size()

7. Risk Management
   └─ engines/risk_management_engine.py: validate_risk()

Output: Signal object with all details
```

---

### Feature: AI Market Sentiment Analysis

**Which code implements it:**
```
1. Basic Sentiment Calculation
   └─ engines/market_sentiment_engine.py: analyze_market_sentiment()
   
2. AI Analysis Layer
   └─ ai/market_sentiment_analyzer.py: analyze_sentiment_with_ai()
   
3. Sentiment Monitoring
   └─ ai/market_sentiment_analyzer.py: MarketSentimentMonitor
   
4. Trend Detection
   └─ engines/trend_alert_engine.py: check_trend_alerts()

Output: MarketSentimentScore + Trend alerts
```

---

### Feature: 🤖 AI Agent Signal Validation

**Which code implements it:**
```
1. Validation Agent
   └─ ai/signal_validation_agent.py: validate_signal()

2. Rule-Based Checks
   └─ ai/signal_validation_agent.py: _perform_rule_based_checks()

3. AI Analysis
   └─ ai/signal_validation_agent.py: _get_ai_validation()

4. Combine & Decide
   └─ ai/signal_validation_agent.py: _combine_validation_results()

5. Integrate into Scanner
   └─ scanner.py: validate_signals_with_agent()

Output: SignalValidationResult (APPROVE/REJECT/HOLD)
```

---

### Feature: Market Trend Alerts

**Which code implements it:**
```
1. Trend Detection
   └─ engines/trend_alert_engine.py: check_trend_alerts()

2. Alert Generation
   └─ engines/trend_alert_engine.py: _check_phase_changes()

3. Alert Dispatch
   └─ alerts/alert_manager.py: send_trend_alerts()

4. Channel-Specific Formatting
   └─ alerts/alert_manager.py: _send_discord_trend_alert()

Output: Alerts sent to Telegram, Discord, Email
```

---

### Feature: Signal Accuracy Tracking

**Which code implements it:**
```
1. Track Sent Signals
   └─ learning/signal_tracker.py: track_signal()

2. Check Resolution
   └─ learning/resolution_checker.py: check_resolution()

3. Score Accuracy
   └─ learning/accuracy_scorer.py: score_signal()

4. Store History
   └─ learning/accuracy_scorer.py: save_to_history()

Output: data/learning_history.json with stats
```

---

### Feature: Self-Adaptation

**Which code implements it:**
```
1. Analyze Learning History
   └─ learning/learning_engine.py: learn_from_history()

2. Identify Patterns
   └─ learning/learning_engine.py: identify_success_patterns()

3. Propose Adaptations
   └─ learning/self_adaptation.py: propose_adaptations()

4. Apply Changes
   └─ learning/self_adaptation.py: apply_parameter_updates()

5. Validate & Store
   └─ scanner.py: self_adapt_parameters()

Output: Updated config parameters
```

---

## Integration Points

### How Components Connect

```
scanner.py (Main Orchestrator)
    │
    ├─→ engines/market_sentiment_engine.py
    │   └─→ ai/market_sentiment_analyzer.py
    │       └─→ engines/trend_alert_engine.py
    │           └─→ alerts/alert_manager.py
    │
    ├─→ engines/coin_filter_engine.py
    │
    ├─→ strategies/mtf_engine.py
    │
    ├─→ strategies/prd_signal_engine.py
    │
    ├─→ engines/confluence_engine.py
    │
    ├─→ engines/position_sizer.py
    │
    ├─→ engines/risk_management_engine.py
    │
    ├─→ 🤖 ai/signal_validation_agent.py
    │   └─→ alerts/alert_manager.py
    │
    ├─→ learning/signal_tracker.py
    │
    ├─→ learning/resolution_checker.py
    │
    ├─→ learning/accuracy_scorer.py
    │
    ├─→ learning/learning_engine.py
    │
    ├─→ learning/self_adaptation.py
    │
    └─→ alerts/alert_manager.py
        ├─→ alerts/telegram_bot.py
        ├─→ alerts/signal_publisher.py
        └─→ Discord/Email endpoints
```

---

## Development Guide

### For New Developers

#### Understanding the Flow (Step-by-Step)

1. **Read These Files First:**
   ```
   1. main.py - Understand entry point
   2. scanner.py - Understand main flow
   3. engines/market_sentiment_engine.py - Understand sentiment
   4. config.yaml - Understand configuration
   ```

2. **Understand Core Loop:**
   ```python
   # In scanner.py
   while True:
       # 1. Get market data
       market_data = await self.get_market_data()
       
       # 2. Analyze market sentiment
       self.current_market_sentiment = await self.analyze_market_sentiment()
       
       # 3. Check trend alerts
       trend_alerts = self.trend_alert_engine.check_trend_alerts(...)
       
       # 4. Generate signals
       signals = await self.process_coins(...)
       
       # 5. Validate with AI agent
       validated_signals = await self.validate_signals_with_agent(...)
       
       # 6. Send alerts
       await self.send_alerts(validated_signals)
       
       # 7. Update learning
       await self.check_signal_resolution()
   ```

3. **Add New Signal Strategy:**
   ```
   a. Create file: strategies/my_strategy.py
   b. Create class: MySignalStrategy
   c. Implement: generate_signals() method
   d. Call from scanner.py in process_coins()
   e. Test with sample data
   ```

4. **Add New Filter:**
   ```
   a. Create filter logic in existing engine or new file
   b. Add filter call in scanner.py during signal processing
   c. Update filter parameters in config.yaml
   d. Test and validate
   ```

5. **Modify AI Agent Validation:**
   ```
   a. Edit: ai/signal_validation_agent.py
   b. Update: _perform_rule_based_checks() for new checks
   c. Modify: Scoring in _combine_validation_results()
   d. Test with sample signals
   ```

#### Key Configuration Points

**config.yaml:**
```yaml
# Market Analysis
market_analysis:
  min_market_cap: 10000000
  min_volume: 1000000

# Signals
signals:
  min_confidence: 6.0
  min_risk_reward: 1.5

# Filters
filters:
  use_market_sentiment_filter: true
  sentiment_long_threshold: "BULLISH"
  sentiment_short_threshold: "BEARISH"

# AI
ai:
  enabled: true
  ai_provider: "openai"  # or "gemini"
  
# Alerts
alerts:
  telegram_enabled: true
  discord_enabled: true
```

#### Testing Components

```python
# Test Market Sentiment
from engines.market_sentiment_engine import MarketSentimentEngine
engine = MarketSentimentEngine()
sentiment = engine.analyze_market_sentiment(market_data)

# Test Signal Generation
from strategies.mtf_engine import MTFEngine
mtf = MTFEngine()
signals = mtf.generate_mtf_signals(coin_data)

# Test AI Validation
from ai.signal_validation_agent import AISignalValidationAgent
agent = AISignalValidationAgent()
result = await agent.validate_signal(signal, coin, sentiment)

# Test Trend Alerts
from engines.trend_alert_engine import MarketTrendAlertEngine
trend_engine = MarketTrendAlertEngine()
alerts = trend_engine.check_trend_alerts(old_sentiment, new_sentiment)
```

---

### Common Development Tasks

#### Task 1: Add New Signal Strategy

```
Steps:
1. Create: strategies/new_strategy.py
2. Define strategy logic
3. Implement: generate_signals(coin_data) → List[Signal]
4. Import in scanner.py
5. Call in scanner.py process_coins()
6. Update config.yaml with strategy parameters
7. Test with sample data
8. Deploy
```

#### Task 2: Modify AI Agent Validation

```
Steps:
1. Edit: ai/signal_validation_agent.py
2. Modify _perform_rule_based_checks() to add new check
3. Adjust scoring logic
4. Test with various signals
5. Verify approval rate doesn't change drastically
6. Deploy
```

#### Task 3: Add New Alert Channel

```
Steps:
1. Create channel handler in: alerts/
2. Implement send_alert() method
3. Add to AlertManager.send_all_alerts()
4. Update config.yaml
5. Test alert delivery
6. Deploy
```

#### Task 4: Improve Learning System

```
Steps:
1. Analyze data in: data/learning_history.json
2. Identify patterns in: learning/learning_engine.py
3. Add new adaptation rules in: learning/self_adaptation.py
4. Test parameter adjustments
5. Measure impact on accuracy
6. Deploy
```

---

### Debugging Guide

#### Check Market Sentiment
```python
# In scanner or test script
sentiment = scanner.current_market_sentiment
print(f"Sentiment: {sentiment.sentiment}")
print(f"Score: {sentiment.score}")
print(f"BTC Trend: {sentiment.btc_trend_score}")
print(f"Gainers: {sentiment.gainers_percentage}%")
```

#### Check Signal Generation
```python
# Monitor which signals are generated
signals = await scanner.process_coins(coins)
for signal in signals:
    print(f"{signal.symbol}: {signal.type} @ {signal.entry_low}")
    print(f"  Confidence: {signal.confidence_score}")
    print(f"  Strategy: {signal.strategy}")
```

#### Check AI Agent Decisions
```python
# Monitor agent validation
agent = scanner.signal_validation_agent
decisions = agent.get_decision_log(10)
for d in decisions:
    print(f"{d.symbol}: {d.decision.value}")
    print(f"  Setup Quality: {d.setup_quality_score}")
    print(f"  Reasoning: {d.reasoning}")
```

#### Check Alerts Sent
```python
# Check alert manager logs
import logging
logger = logging.getLogger("alert_manager")
logger.setLevel(logging.DEBUG)

# All alerts will be logged with details
```

---

### Performance Optimization

#### Query Optimization
- Cache market data between scans
- Batch API calls
- Use timeouts for API requests

#### Async Improvements
- Parallelize coin analysis
- Use asyncio.gather() for multiple calls
- Connection pooling for API requests

#### Memory Management
- Clear old signal history periodically
- Limit learning history to last 30 days
- Archive old logs

---

## Configuration Reference

**key parameters and what they do:**

```yaml
# Market Sentiment Configuration
market_sentiment:
  btc_weight: 0.25              # How much BTC trend matters
  breadth_weight: 0.25          # How much gainers% matters
  strength_weight: 0.20
  alts_weight: 0.15
  dominance_weight: 0.10
  
  # Sentiment thresholds
  very_bullish_threshold: 75    # Score >= 75 = VERY_BULLISH
  bullish_threshold: 60
  bearish_threshold: 40
  very_bearish_threshold: 25

# Signal Configuration
signals:
  min_confidence: 6.0           # Skip signals below this
  min_risk_reward: 1.5          # R:R must be at least 1:1.5
  max_entry_width: 0.05         # Entry zone max 5%
  top_signals_count: 5          # Return top 5 signals

# AI Agent Configuration
ai_validation:
  market_alignment_weight: 0.20
  risk_reward_weight: 0.15
  entry_zone_weight: 0.10
  stop_loss_weight: 0.10
  confidence_weight: 0.10
  market_cap_weight: 0.10
  volume_weight: 0.10
  
  approval_threshold: 70        # Score >= 70 = APPROVE
  hold_threshold: 40            # 40-70 = HOLD, <40 = REJECT

# Learning Configuration
learning:
  history_retention_days: 30    # Keep 30 days of history
  accuracy_calculation_window: 7  # Calculate accuracy on last 7 days
  adaptation_check_interval: 24  # Check for adaptation every 24h

# Alert Configuration
alerts:
  telegram_enabled: true
  discord_enabled: true
  email_enabled: false
  min_signal_confidence_to_alert: 6.0  # Only alert high-confidence
  send_trend_alerts: true       # Send market trend alerts
  trend_alert_min_change: 15    # Alert if score changes >15 points
```

---

## Summary for New Developers

### What This System Does

1. **Scans the market** for promising cryptocurrencies
2. **Generates trading signals** using multiple strategies
3. **Analyzes market sentiment** using AI
4. **Validates signals** with an intelligent AI agent
5. **Monitors market trends** and sends phase alerts
6. **Tracks accuracy** and learns over time
7. **Sends alerts** via Telegram, Discord, etc.

### The Most Important Files

```
1. scanner.py           - Main orchestrator (READ THIS FIRST)
2. config.yaml          - Configuration
3. engines/market_sentiment_engine.py - Market analysis
4. strategies/mtf_engine.py - Signal generation
5. ai/signal_validation_agent.py - AI validation
6. alerts/alert_manager.py - Alert dispatch
7. learning/ folder - Accuracy tracking & adaptation
```

### How to Add Features

```
1. Understand the flow in scanner.py
2. Write your code in appropriate module
3. Update scanner.py to call it
4. Add config parameters
5. Test with sample data
6. Deploy
```

### Key Concepts

- **Market Sentiment** - Overall market conditions (bullish/bearish)
- **Signals** - Trading opportunities (entry, stop, target)
- **AI Validation** - AI reviews signals and approves/rejects
- **Trend Alerts** - Notifications when market enters new phases
- **Learning System** - Tracks accuracy and adapts parameters

---

**This document provides a complete roadmap for understanding and developing the Crypto Scanner system!** 🚀
