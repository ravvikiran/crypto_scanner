# 🔄 Crypto Scanner - Complete Data Flow & Architecture

## Overview

This document provides detailed data flow diagrams and architectural views for understanding how data moves through the system.

---

## 1. High-Level System Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CRYPTO SCANNER SYSTEM                          │
│                                                                         │
│  INPUT SOURCES                    PROCESSING                OUTPUT      │
│  ──────────────                    ──────────                ────────   │
│                                                                         │
│  Market Data    ──→  ┌──────────────────────────────┐    Telegram  ──→│
│  (CoinGecko)         │   Market Sentiment Engine     │  (Alerts Sent) │
│                      ├──────────────────────────────┤               │
│  Price Data     ──→  │   AI Market Analyzer          │    Discord   ──→│
│  (1h, 4h, 1d)        ├──────────────────────────────┤  (Rich Embeds) │
│                      │   Trend Alert Engine          │               │
│  BTC Trend      ──→  └──┬───────────────────────────┘    Email     ──→│
│                         │                              (Notifications)│
│  Gainers/Losers ──→     ├─→ Coin Filter Engine                       │
│                         │                                             │
│  Volume Data    ──→     ├─→ MTF Strategy Engine                       │
│                         │   (Multi-Timeframe)                         │
│                         │                                             │
│  Market Cap     ──→     ├─→ PRD Strategy Engine                       │
│                         │   (Price-Reversal-Direction)                │
│                         │                                             │
│  Volatility     ──→     ├─→ Confluence Engine                         │
│                         │                                             │
│                         ├─→ Position Sizer                            │
│                         │                                             │
│                         ├─→ Risk Management Engine                    │
│                         │                                             │
│                         ├─→ 🤖 AI Signal Validation Agent             │
│                         │   (Intelligent Validation)                  │
│                         │                                             │
│                         ├─→ Learning System                           │
│                         │   (Accuracy Tracking)                       │
│                         │                                             │
│                         ├─→ Self-Adaptation Engine                    │
│                         │   (Parameter Tuning)                        │
│                         │                                             │
│                         └─→ Alert Manager                             │
│                             (Dispatch)                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Single Scan Cycle - Detailed Flow

```
╔════════════════════════════════════════════════════════════════════════╗
║                    SINGLE SCAN CYCLE - COMPLETE FLOW                  ║
╚════════════════════════════════════════════════════════════════════════╝

START
│
├─ [1] INITIALIZE
│  ├─ Load config.yaml
│  ├─ Initialize all engines
│  └─ Setup API connections
│
├─ [2] FETCH MARKET DATA
│  ├─ Get BTC price & trend
│  ├─ Get top 100-200 coins by market cap
│  ├─ Get OHLCV data (1h, 4h, 1d)
│  ├─ Calculate gainers/losers %
│  ├─ Fetch volume data
│  └─ Store in market_data object
│
├─ [3] ANALYZE MARKET SENTIMENT
│  ├─ Call: engines/market_sentiment_engine.py
│  │  ├─ Analyze BTC trend
│  │  ├─ Calculate market breadth
│  │  ├─ Measure market strength
│  │  ├─ Check altcoin performance
│  │  ├─ Monitor BTC dominance
│  │  ├─ Assess volatility
│  │  └─ Combine metrics → MarketSentimentScore
│  │      (0-100 score, VERY_BEARISH to VERY_BULLISH)
│  │
│  └─ Optional AI Analysis:
│     ├─ Call: ai/market_sentiment_analyzer.py
│     ├─ Send score to LLM
│     ├─ Get risk assessment
│     └─ Store AI insights
│
├─ [4] CHECK TREND ALERTS
│  ├─ Call: engines/trend_alert_engine.py
│  ├─ Compare current sentiment vs previous
│  ├─ Detect phase changes:
│  │  ├─ NEUTRAL → BULLISH = ENTERING_BULLISH alert
│  │  ├─ BULLISH → VERY_BULLISH = ENTERING_VERY_BULLISH alert
│  │  ├─ BULLISH → BEARISH = EXITING_BULLISH alert
│  │  └─ etc.
│  │
│  ├─ If alerts detected:
│  │  ├─ Generate TrendAlert objects
│  │  ├─ Call: alerts/alert_manager.py → send_trend_alerts()
│  │  ├─ Send to Telegram
│  │  ├─ Send to Discord
│  │  └─ Send to Email (optional)
│  │
│  └─ Update previous sentiment for next scan
│
├─ [5] FILTER & RANK COINS
│  ├─ Call: engines/coin_filter_engine.py
│  ├─ Filter:
│  │  ├─ Market cap > $10M (minimum liquidity)
│  │  ├─ Daily volume > $1M
│  │  ├─ Volume ratio > 1.5x average
│  │  ├─ Exclude stablecoins
│  │  └─ Get ~50 qualified coins
│  │
│  └─ Rank by composite score:
│     ├─ Momentum
│     ├─ Trend strength
│     ├─ Volume increase
│     └─ Return top 20-30 coins
│
├─ [6] FOR EACH QUALIFIED COIN - GENERATE SIGNALS
│  │
│  ├─ COIN LOOP: for coin in qualified_coins:
│  │
│  │  ├─ [6a] FETCH COIN DATA
│  │  │  ├─ Get OHLCV (1h, 4h, 1d)
│  │  │  ├─ Calculate indicators (MA, RSI, MACD, Bollinger, etc)
│  │  │  ├─ Identify support/resistance
│  │  │  ├─ Detect trends
│  │  │  └─ Store in coin_data object
│  │  │
│  │  ├─ [6b] GENERATE MTF SIGNALS (Multi-Timeframe)
│  │  │  ├─ Call: strategies/mtf_engine.py
│  │  │  ├─ Analyze 1D: Trend direction
│  │  │  ├─ Analyze 4H: Entry setup & zones
│  │  │  ├─ Analyze 1H: Confirmation
│  │  │  ├─ If all align → Generate Signal:
│  │  │  │  ├─ Type: LONG/SHORT/NONE
│  │  │  │  ├─ Entry zone (low, high)
│  │  │  │  ├─ Stop loss
│  │  │  │  ├─ Targets (T1, T2, T3)
│  │  │  │  ├─ Risk/Reward ratio
│  │  │  │  ├─ Confidence: 0-10
│  │  │  │  └─ Add to signals_list
│  │  │  │
│  │  │  └─ No alignment → Skip coin
│  │  │
│  │  ├─ [6c] GENERATE PRD SIGNALS (if enabled)
│  │  │  ├─ Call: strategies/prd_signal_engine.py
│  │  │  ├─ Similar flow to MTF
│  │  │  └─ Add to signals_list if valid
│  │  │
│  │  ├─ [6d] CONFLUENCE CHECK (Optional)
│  │  │  ├─ Call: engines/confluence_engine.py
│  │  │  ├─ Check multi-indicator alignment
│  │  │  ├─ Boost confidence if high
│  │  │  └─ Reduce if low
│  │  │
│  │  ├─ [6e] POSITION SIZING
│  │  │  ├─ Call: engines/position_sizer.py
│  │  │  ├─ Calculate: Position size = Risk / Stop distance
│  │  │  ├─ Risk: 2% of account (default)
│  │  │  └─ Store in signal
│  │  │
│  │  └─ [6f] RISK VALIDATION
│  │     ├─ Call: engines/risk_management_engine.py
│  │     ├─ Validate:
│  │     │  ├─ R:R >= 1:1.5 ✓ / ✗
│  │     │  ├─ Stop distance 1-5% ✓ / ✗
│  │     │  ├─ Entry width < 5% ✓ / ✗
│  │     │  └─ Position size valid ✓ / ✗
│  │     │
│  │     ├─ If fails validation → Mark for rejection
│  │     └─ If passes → Add to validated_signals
│  │
│  └─ END COIN LOOP
│
├─ [7] COLLECT TOP SIGNALS
│  ├─ Filter signals:
│  │  ├─ Remove failed risk validation
│  │  └─ Keep only passing signals
│  │
│  ├─ Rank by confidence & strategy type
│  └─ Select top N signals (e.g., top 10)
│
├─ [8] 🤖 AI AGENT VALIDATION (NEW!)
│  ├─ For each signal:
│  │  │
│  │  ├─ [8a] RULE-BASED CHECKS
│  │  │  ├─ Call: ai/signal_validation_agent.py
│  │  │  ├─ _perform_rule_based_checks():
│  │  │  │
│  │  │  ├─ Check 1: Market Alignment (20 pts)
│  │  │  │  └─ Is LONG in BULLISH? +20 pts
│  │  │  │
│  │  │  ├─ Check 2: Risk/Reward (15 pts)
│  │  │  │  └─ If 1:3.0 ratio? +15 pts
│  │  │  │
│  │  │  ├─ Check 3: Entry Zone (10 pts)
│  │  │  │  └─ If < 2% width? +10 pts
│  │  │  │
│  │  │  ├─ Check 4: Stop Loss (10 pts)
│  │  │  │  └─ If 1-3% from entry? +10 pts
│  │  │  │
│  │  │  ├─ Check 5: Confidence (10 pts)
│  │  │  │  └─ If >= 8.0/10? +10 pts
│  │  │  │
│  │  │  ├─ Check 6: Market Cap (10 pts)
│  │  │  │  └─ If > $100M? +10 pts
│  │  │  │
│  │  │  ├─ Check 7: Volume (10 pts)
│  │  │  │  └─ If > 1.5x average? +10 pts
│  │  │  │
│  │  │  └─ Check 8: Strategy Type (5 pts)
│  │  │     └─ If established strategy? +5 pts
│  │  │
│  │  ├─ Calculate: Rule-Based Score = Sum of all points
│  │  │             (0-100 scale)
│  │  │
│  │  ├─ [8b] AI ANALYSIS
│  │  │  ├─ Call: _get_ai_validation()
│  │  │  ├─ Send to LLM:
│  │  │  │  ├─ Rule-based score breakdown
│  │  │  │  ├─ Signal details
│  │  │  │  ├─ Market sentiment
│  │  │  │  └─ Coin characteristics
│  │  │  │
│  │  │  └─ LLM returns:
│  │  │     ├─ Agrees/disagrees with score
│  │  │     ├─ Override recommendation
│  │  │     └─ Risk assessment
│  │  │
│  │  ├─ [8c] COMBINE & DECIDE
│  │  │  ├─ Call: _combine_validation_results()
│  │  │  ├─ Merge rule + AI scores:
│  │  │  │  ├─ If Score >= 70 AND AI agrees:
│  │  │  │  │  ├─ Decision = APPROVE ✅
│  │  │  │  │  ├─ Confidence adjustment = +1.0
│  │  │  │  │  └─ Signal.confidence = orig + 1.0
│  │  │  │  │
│  │  │  │  ├─ Else if 40 <= Score < 70:
│  │  │  │  │  ├─ Decision = HOLD ⏸️
│  │  │  │  │  ├─ Confidence adjustment = 0.0
│  │  │  │  │  └─ Signal.confidence = orig + 0.0
│  │  │  │  │
│  │  │  │  └─ Else (Score < 40):
│  │  │  │     ├─ Decision = REJECT ❌
│  │  │  │     ├─ Confidence adjustment = -2.0
│  │  │  │     └─ Mark for removal
│  │  │
│  │  ├─ [8d] LOG DECISION
│  │  │  └─ Store in decision_log:
│  │  │     ├─ Signal ID
│  │  │     ├─ Decision & reasoning
│  │  │     ├─ All check results
│  │  │     ├─ Confidence adjustment
│  │  │     └─ Timestamp
│  │  │
│  │  └─ Return: SignalValidationResult
│  │
│  └─ Filter out REJECTED signals
│     Keep APPROVED & HOLD signals
│
├─ [9] APPLY MARKET SENTIMENT FILTER
│  ├─ For each signal:
│  │  ├─ If LONG & market is BEARISH → Remove
│  │  ├─ If SHORT & market is BULLISH → Remove
│  │  └─ Else → Keep
│  │
│  └─ Result: market_filtered_signals
│
├─ [10] SEND ALERTS
│  ├─ For each signal:
│  │  ├─ Call: alerts/alert_manager.py → send_signal_alerts()
│  │  │
│  │  ├─ Format alert:
│  │  │  ├─ Entry, stop, targets
│  │  │  ├─ Risk/reward
│  │  │  ├─ Confidence (AI-adjusted)
│  │  │  ├─ AI agent decision
│  │  │  ├─ Market sentiment context
│  │  │  ├─ Setup quality score
│  │  │  └─ Reasoning
│  │  │
│  │  ├─ Send to Telegram
│  │  │  └─ Via telegram_bot.py
│  │  │
│  │  ├─ Send to Discord
│  │  │  ├─ Rich embed format
│  │  │  ├─ Color-coded (green=strong, red=weak)
│  │  │  └─ Via webhook
│  │  │
│  │  └─ Send to Email (if enabled)
│  │
│  └─ Store in signal_tracker for resolution checking
│
├─ [11] LEARNING SYSTEM - TRACK PERFORMANCE
│  ├─ For recently sent signals:
│  │  │
│  │  ├─ [11a] CHECK RESOLUTION
│  │  │  ├─ Call: learning/resolution_checker.py
│  │  │  ├─ Get current price
│  │  │  ├─ Check:
│  │  │  │  ├─ Hit target 1? → Mark WIN
│  │  │  │  ├─ Hit target 2? → Mark WIN (more profit)
│  │  │  │  ├─ Hit stop loss? → Mark LOSS
│  │  │  │  └─ Still open? → Mark PENDING
│  │  │  │
│  │  │  └─ Calculate P&L
│  │  │
│  │  ├─ [11b] SCORE ACCURACY
│  │  │  ├─ Call: learning/accuracy_scorer.py
│  │  │  ├─ Score signal (WIN/LOSS/PARTIAL)
│  │  │  │
│  │  │  └─ Calculate:
│  │  │     ├─ Per-strategy accuracy %
│  │  │     ├─ Per-timeframe accuracy %
│  │  │     ├─ Win/loss ratio
│  │  │     ├─ Average R:R achieved
│  │  │     └─ Profit factor
│  │  │
│  │  └─ [11c] SAVE TO HISTORY
│  │     └─ Append to data/learning_history.json
│  │
│  └─ Returned: Updated accuracy stats
│
├─ [12] SELF-ADAPTATION
│  ├─ Call: learning/self_adaptation.py
│  ├─ Analyze stats:
│  │  ├─ If accuracy < 60% → Increase thresholds
│  │  ├─ If accuracy > 75% → Keep current
│  │  ├─ If avg R:R < 1:2 → Increase minimum R:R
│  │  └─ etc.
│  │
│  ├─ Propose parameter updates:
│  │  ├─ min_confidence: 6.0 → 6.5
│  │  ├─ min_risk_reward: 1.5 → 1.8
│  │  ├─ strategy_weights: {...updated...}
│  │  └─ other params
│  │
│  └─ Apply updates if above threshold
│     (Store in memory for next scan)
│
├─ [13] LOG & REPORT
│  ├─ Log scan statistics:
│  │  ├─ Coins scanned
│  │  ├─ Signals generated
│  │  ├─ Signals approved by AI
│  │  ├─ Signals sent
│  │  ├─ Market sentiment
│  │  └─ Scan duration
│  │
│  └─ Output console summary:
│     ```
│     Scan completed in 45.2s
│     Coins scanned: 200
│     Signals generated: 47
│     Signals approved (AI): 5
│     Signals sent: 5
│     Market: VERY_BULLISH (82/100)
│     Trend alerts: 1 (ENTERING_BULLISH)
│     ```
│
└─ END OF SCAN CYCLE

NEXT SCAN: Repeat after scheduler interval (e.g., 15 minutes)
```

---

## 3. Signal Validation Decision Tree

```
                    SIGNAL ARRIVES
                          │
                          ▼
        ┌─────────────────────────────────┐
        │   RULE-BASED CHECKS (8 POINTS)  │
        └─────────────┬───────────────────┘
                      │
        ┌─────────────┴──────────────┐
        ▼                            ▼
   Market Alignment           Risk/Reward Check
   LONG in BULLISH?          R:R >= 1:1.5?
   (+20 pts if YES)           (+15 pts if YES)
        │                            │
        ├─ Entry Zone Check         Entry Zone Width
        │  < 2% width?              < 2%?
        │  (+10 pts)                (+10 pts)
        │
        ├─ Stop Loss Distance
        │  1-5% from entry?
        │  (+10 pts)
        │
        ├─ Confidence Score
        │  >= 8.0/10?
        │  (+10 pts)
        │
        ├─ Market Cap
        │  > $100M?
        │  (+10 pts)
        │
        ├─ Volume Confirmation
        │  > 1.5x average?
        │  (+10 pts)
        │
        └─ Strategy Appropriateness
           Established strategy?
           (+5 pts)
                      │
                      ▼
        ┌──────────────────────────┐
        │  CALCULATE RULE SCORE    │
        │  Sum of all checks       │
        │  0-100 scale             │
        └──────────┬───────────────┘
                   │
                   ├─ Score >= 70? ──────────┐
                   │                          │
                   ├─ Score 40-70? ────┐     │
                   │                   │     │
                   └─ Score < 40?─┐    │     │
                                  │    │     │
                                  ▼    ▼     ▼
                              ┌─────────────────────┐
                              │  AI ANALYSIS (LLM)  │
                              └──────────┬──────────┘
                                         │
                         ┌───────────────┼───────────────┐
                         │               │               │
                      Agrees        Suggests         Rejects
                       with        Caution
                      Score
                         │               │               │
                         ▼               ▼               ▼
                    ┌──────────┐   ┌──────────┐   ┌──────────┐
                    │ APPROVE  │   │  HOLD    │   │ REJECT   │
                    │    ✅    │   │   ⏸️     │   │    ❌    │
                    └──────────┘   └──────────┘   └──────────┘
                         │               │               │
                    +1.0 Conf       0.0 Conf        -2.0 Conf
                    Send Alert      Send Alert       Block
                    High Priority   Lower Priority   Signal
                         │               │               │
                         └───────────────┴───────────────┘
                                    │
                                    ▼
                        FINAL CONFIDENCE SCORE
                        (Original ± Adjustment)
                                    │
                                    ▼
                        SEND ALERT WITH:
                        ├─ Decision status
                        ├─ Adjusted confidence
                        ├─ Setup quality score
                        ├─ Market alignment score
                        ├─ Reasoning/explanation
                        └─ AI recommendations
```

---

## 4. Market Sentiment Calculation Flow

```
MARKET DATA INPUT
├─ BTC Price & Indicators
├─ Market breadth (gainers % vs losers %)
├─ Total market cap
├─ Altcoin prices & performance
├─ BTC dominance %
├─ Volatility metrics
└─ Volume data
    │
    ▼
METRIC CALCULATION
│
├─ BTC Trend Score (0-100)
│  ├─ If BTC above MA200: +40
│  ├─ If BTC above MA50: +30
│  ├─ If MA50 above MA200: +30
│  └─ Total: 0-100
│
├─ Market Breadth (0-100)
│  ├─ % Gainers: Gainers / (Gainers + Losers) * 100
│  ├─ If >= 75%: 100/100
│  ├─ If <= 25%: 0/100
│  └─ Linear scale: (% Gainers - 25) / 50 * 100
│
├─ Market Strength (0-100)
│  ├─ Volatility-adjusted strength
│  ├─ Volume increase indicator
│  ├─ Momentum calculation
│  └─ Composite of multiple factors
│
├─ Altcoin Performance (0-100)
│  ├─ Compare altcoin avg price change vs BTC
│  ├─ If alts outperforming: Higher score
│  └─ Momentum & relative strength
│
├─ BTC Dominance (0-100)
│  ├─ BTC market cap / Total market cap * 100
│  ├─ If high dominance: = potential BEARISH (money in BTC, not alts)
│  ├─ If low dominance: = potential BULLISH (money flowing to alts)
│  └─ Inverted scale (lower dominance = higher score)
│
└─ Other Metrics (Volatility, Volume, etc.)
    │
    ▼
WEIGHTED COMBINATION
│
│ Total Score = (BTC_Score × 0.25)
│             + (Breadth × 0.25)
│             + (Strength × 0.20)
│             + (Alts × 0.15)
│             + (Dominance × 0.10)
│             + (Other × 0.05)
│
    │
    ▼
SENTIMENT CLASSIFICATION
│
├─ Score 75-100 → VERY_BULLISH 🚀
├─ Score 60-74  → BULLISH 📈
├─ Score 40-59  → NEUTRAL ➖
├─ Score 25-39  → BEARISH 📉
└─ Score 0-24   → VERY_BEARISH 🔴
    │
    ▼
OUTPUT: MarketSentimentScore
├─ sentiment: BULLISH
├─ score: 68.5
├─ favorable_for: "LONG"
├─ individual_metrics:
│  ├─ btc_trend: 75
│  ├─ breadth: 68
│  ├─ strength: 70
│  └─ etc.
└─ timestamp: 2026-04-18 10:30:00
```

---

## 5. Multi-Timeframe Signal Generation

```
COIN DATA INPUT (BTC)
├─ 1D OHLCV data
├─ 4H OHLCV data
├─ 1H OHLCV data
└─ Technical indicators for each TF
    │
    ▼ ANALYZE 1D (DIRECTION - Long-term)
    │
    ├─ Check: Is there an established trend?
    │  ├─ Price above MA200? (Very bullish)
    │  ├─ MA50 above MA200? (Trend established)
    │  ├─ Trend Strength: Calculate (RSI, MACD, slope)
    │  └─ Result: UPTREND / DOWNTREND / RANGING
    │
    ├─ Key Levels:
    │  ├─ Support zones
    │  ├─ Resistance zones
    │  └─ Breakout candidates
    │
    ├─ Direction Score: 0-100
    │  └─ How strong is the trend?
    │
    └─ Decision: USE LONG / USE SHORT / SKIP
        │
        ▼ IF DECIDED TO USE LONG:
        │
        ├─ ANALYZE 4H (ENTRY SETUP - Medium-term)
        │  │
        │  ├─ Find pullback zones in uptrend
        │  │  └─ Price pulled back to MA50/MA200
        │  │
        │  ├─ Find breakout levels
        │  │  └─ Price breaking above resistance
        │  │
        │  ├─ Identify entry zone
        │  │  ├─ Entry Low: Support level
        │  │  ├─ Entry High: Resistance level + 0.5-2%
        │  │  └─ Zone width: 1-3% (tight is better)
        │  │
        │  ├─ Set Stop Loss
        │  │  ├─ Just below entry zone support
        │  │  ├─ Typically 1-3% below entry
        │  │  └─ Distance: Stop = Entry_Low - (Entry_Low × 0.02-0.05)
        │  │
        │  ├─ Calculate Targets
        │  │  ├─ Target 1: Next resistance level
        │  │  ├─ Target 2: 2-3% above entry
        │  │  └─ Target 3: Major resistance or 5%+ above entry
        │  │
        │  ├─ Calculate Risk/Reward
        │  │  ├─ Risk = Entry - Stop_Loss
        │  │  ├─ Reward = Target - Entry
        │  │  ├─ R:R Ratio = Reward / Risk
        │  │  └─ Example: Risk=500, Reward=1500 → R:R = 1:3.0
        │  │
        │  ├─ Calculate Entry Confidence
        │  │  ├─ Volume at entry? High volume = +2 points
        │  │  ├─ Confluence of indicators? +2 points each
        │  │  ├─ Setup quality? +2-4 points
        │  │  └─ 4H Setup Confidence: 0-10
        │  │
        │  └─ Decision: GOOD ENTRY / POOR ENTRY
        │      │
        │      ▼ IF GOOD ENTRY:
        │      │
        │      └─ ANALYZE 1H (CONFIRMATION - Short-term)
        │         │
        │         ├─ Final confirmation needed
        │         ├─ Check volume spike
        │         ├─ Check momentum indicators
        │         ├─ Check for rejection at support
        │         │
        │         ├─ 1H Confirmation Confidence: 0-10
        │         │
        │         └─ Decision: READY TO SIGNAL / NOT READY
        │             │
        │             ▼ IF READY TO SIGNAL:
        │                │
        │                ├─ Signal Type: LONG
        │                ├─ Entry Zone: Entry_Low - Entry_High
        │                ├─ Stop Loss: Stop_Loss value
        │                ├─ Targets: Target_1, Target_2, Target_3
        │                ├─ Risk/Reward: 1:3.0
        │                ├─ Confidence: (1D + 4H + 1H)/3 → ~7-9/10
        │                ├─ Strategy: "mtf_breakout" or "mtf_pullback"
        │                └─ Timestamp: scan time
        │                    │
        │                    └─ ADD TO SIGNALS LIST
        │
        └─ IF POOR ENTRY OR NOT READY:
           └─ SKIP THIS COIN
```

---

## 6. Learning & Adaptation Cycle

```
DAY 1 SIGNALS SENT
│
├─ Signal 1: BTC LONG
│  ├─ Entry: $45,000
│  ├─ Stop: $44,500
│  ├─ Target: $46,000
│  └─ Confidence: 8.2/10
│
├─ Signal 2: ETH LONG
│  ├─ Entry: $2,850
│  ├─ Stop: $2,750
│  ├─ Target: $3,000
│  └─ Confidence: 7.5/10
│
└─ (+ 3 more signals)
    │
    ▼ TRACK IN SIGNAL TRACKER
    │
    └─ Stored: data/learning_history.json
        │
        ▼ 24 HOURS LATER - RESOLUTION CHECK
        │
        ├─ Signal 1 Status Check:
        │  ├─ Current BTC price: $46,200
        │  ├─ Hit target? YES → Resolution = WIN
        │  ├─ Entry executed? YES, at $45,150
        │  ├─ Exit price: $46,200
        │  ├─ P&L: +$1,050
        │  ├─ P&L %: +2.3%
        │  └─ Trade outcome: WIN ✅
        │
        ├─ Signal 2 Status Check:
        │  ├─ Current ETH price: $2,780
        │  ├─ Hit stop? YES → Resolution = LOSS
        │  ├─ Entry attempted but not filled
        │  ├─ Exit price: $2,780
        │  ├─ P&L: -$70 (if entered)
        │  ├─ P&L %: -2.4%
        │  └─ Trade outcome: LOSS ❌
        │
        └─ (Continue for all signals)
            │
            ▼ ACCURACY SCORING
            │
            ├─ Total signals: 5
            ├─ Winning signals: 3
            ├─ Losing signals: 2
            ├─ Win Rate: 60%
            │
            ├─ Per Strategy Analysis:
            │  ├─ MTF Strategy: 3 signals, 2 wins, 1 loss = 67%
            │  ├─ PRD Strategy: 2 signals, 1 win, 1 loss = 50%
            │  └─ Overall: 5 signals, 3 wins, 2 losses = 60%
            │
            ├─ R:R Analysis:
            │  ├─ Planned average R:R: 1:2.3
            │  ├─ Actual average R:R: 1:1.8 (lower due to loss)
            │  └─ Winning trades avg: 1:3.2
            │
            └─ Store: data/learning_history.json
                {
                  "date": "2026-04-18",
                  "signals": [...],
                  "accuracy": {
                    "mtf": 67%,
                    "prd": 50%,
                    "overall": 60%
                  },
                  "rr_achieved": 1:1.8
                }
                │
                ▼ LEARNING ANALYSIS
                │
                ├─ Analyze last 7 days of history:
                │  ├─ MTF Strategy: 67% average
                │  ├─ PRD Strategy: 50% average
                │  ├─ Average entry confidence: 7.3
                │  ├─ Successful signals avg confidence: 8.1
                │  ├─ Failed signals avg confidence: 6.2
                │  └─ Conclusion: Higher confidence → Better accuracy
                │
                ├─ Identify patterns:
                │  ├─ Better performance in BULLISH markets
                │  ├─ Worse performance in RANGING markets
                │  ├─ Best R:R in 4H timeframe
                │  └─ Entry zone width < 1.5% = higher accuracy
                │
                └─ Propose Adaptations:
                    │
                    ├─ Adaptation 1: INCREASE MINIMUM CONFIDENCE
                    │  ├─ Current: 6.0
                    │  ├─ Proposed: 6.5-7.0
                    │  ├─ Reason: Failed signals avg 6.2
                    │  └─ Expected impact: +5-10% accuracy
                    │
                    ├─ Adaptation 2: INCREASE MINIMUM R:R
                    │  ├─ Current: 1:1.5
                    │  ├─ Proposed: 1:2.0
                    │  ├─ Reason: Higher R:R = better outcomes
                    │  └─ Expected impact: +2-5% profitability
                    │
                    ├─ Adaptation 3: TIGHTEN ENTRY ZONES
                    │  ├─ Current max: 5%
                    │  ├─ Proposed: 2%
                    │  ├─ Reason: Tight zones = more accurate
                    │  └─ Expected impact: +3-8% accuracy
                    │
                    ├─ Adaptation 4: WEIGHT STRATEGIES
                    │  ├─ MTF: 70% (67% accuracy)
                    │  ├─ PRD: 30% (50% accuracy)
                    │  └─ Result: Focus on better strategy
                    │
                    └─ Adaptation 5: SKIP RANGING MARKETS
                       ├─ Only trade in BULLISH/BEARISH
                       ├─ Skip when sentiment is NEUTRAL
                       └─ Expected impact: +15% accuracy
                           │
                           ▼ APPLY ADAPTATIONS
                           │
                           └─ Update config/parameters in memory
                               (Applied in next scan cycle)
                                   │
                                   ▼ NEXT SCAN
                                   │
                                   └─ Uses updated parameters
                                      ├─ min_confidence: 7.0 (was 6.0)
                                      ├─ min_rr: 2.0 (was 1.5)
                                      ├─ max_entry_width: 2% (was 5%)
                                      └─ etc.
                                          │
                                          ▼ SYSTEM IMPROVES OVER TIME!
```

---

## 7. Alert Dispatch Flow

```
SIGNAL READY TO ALERT
│
├─ Signal object with:
│  ├─ Type: LONG/SHORT
│  ├─ Entry, stop, targets
│  ├─ Confidence (AI-adjusted)
│  ├─ Risk/reward
│  ├─ AI agent decision
│  ├─ Market sentiment
│  └─ Setup quality score
│
└─ ENTER ALERT MANAGER
    │
    ├─ alert_manager.py: send_signal_alerts()
    │
    ├─ [1] FORMAT ALERT
    │  │
    │  ├─ Build message text:
    │  │  ```
    │  │  🟢 LONG - Bitcoin
    │  │  Entry: $45,000-$45,500
    │  │  Stop: $44,500
    │  │  Targets: $46,000, $47,000
    │  │  Confidence: 9.2/10 (AI Boosted)
    │  │  R:R: 1:2.2
    │  │  Market: VERY_BULLISH (82/100)
    │  │  Agent: ✅ APPROVE
    │  │  Setup Quality: 78/100
    │  │  ```
    │  │
    │  └─ Add metadata:
    │     ├─ Signal ID
    │     ├─ Timestamp
    │     ├─ Strategy used
    │     └─ Trader ID (if multi-user)
    │
    ├─ [2] DISPATCH TO TELEGRAM
    │  │
    │  ├─ Call: telegram_bot.py
    │  │  │
    │  │  ├─ Format for Telegram:
    │  │  │  └─ Text message with emojis
    │  │  │
    │  │  ├─ Add keyboard (optional):
    │  │  │  ├─ "View on Chart"
    │  │  │  ├─ "Executed"
    │  │  │  └─ "Skip"
    │  │  │
    │  │  └─ Send via bot_token to chat_id
    │  │
    │  └─ Telegram notification sent ✓
    │
    ├─ [3] DISPATCH TO DISCORD
    │  │
    │  ├─ Format for Discord:
    │  │  │
    │  │  ├─ Create Rich Embed:
    │  │  │  ├─ Title: "🟢 LONG - Bitcoin"
    │  │  │  ├─ Color: Green (for LONG)
    │  │  │  ├─ Fields:
    │  │  │  │  ├─ Entry: "$45,000-$45,500"
    │  │  │  │  ├─ Stop: "$44,500"
    │  │  │  │  ├─ Target 1: "$46,000"
    │  │  │  │  ├─ Target 2: "$47,000"
    │  │  │  │  ├─ Risk/Reward: "1:2.2"
    │  │  │  │  ├─ Confidence: "9.2/10 🚀"
    │  │  │  │  ├─ Market Sentiment: "VERY_BULLISH 🚀"
    │  │  │  │  ├─ AI Decision: "✅ APPROVE"
    │  │  │  │  ├─ Setup Quality: "78/100"
    │  │  │  │  └─ Timestamp: "[Time]"
    │  │  │  │
    │  │  │  └─ Thumbnail: Chart image (if available)
    │  │  │
    │  │  └─ Add reactions: 🎯 📈 ⚡
    │  │
    │  ├─ Send via Discord webhook
    │  │
    │  └─ Discord notification sent ✓
    │
    ├─ [4] DISPATCH TO EMAIL (Optional)
    │  │
    │  ├─ Format for Email:
    │  │  ├─ Subject: "[SIGNAL] LONG Bitcoin - $45,000 Entry"
    │  │  ├─ Body: HTML formatted message
    │  │  ├─ Include all signal details
    │  │  ├─ Add chart (if available)
    │  │  └─ Add footer with disclaimer
    │  │
    │  └─ Send via SMTP
    │      └─ Email notification sent ✓
    │
    ├─ [5] ADDITIONAL DISPATCHES
    │  ├─ Slack (if configured)
    │  ├─ PushBullet (mobile)
    │  ├─ Custom Webhooks
    │  └─ Other integrations
    │
    └─ [6] LOG ALERT SENT
       │
       └─ Store in logs:
          ├─ Signal ID
          ├─ Channels sent to
          ├─ Timestamp
          ├─ Recipient count
          └─ Send status (success/failed)

ALL CHANNELS NOTIFIED ✓
```

---

## 8. Component Interaction Diagram

```
                          SCANNER.PY
                      (Main Orchestrator)
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
           Market        Signal        Learning
         Sentiment      Generation      System
           Engine           │
             │              │
    ┌────────┴────────┐     │
    │                 │     │
    ▼                 ▼     ▼
Sentiment      Trend Alert  MTF
Engine         Engine       Strategy
    │              │            │
    │              │            ├─→ Confluence
    │              │            ├─→ Position Sizer
    ▼              │            ├─→ Risk Mgmt
 AI Analyzer       │            └─→ Optimization
    │              │                 │
    │              │                 ▼
    │              │            PRD Strategy
    │              │                 │
    │              │                 ▼
    │              │         Coin Filter
    │              │              │
    │              │              ▼
    └──────┬───────┴──────────────────┘
           │
           ▼
    🤖 AI VALIDATION AGENT
           │
           ├─ Rule-Based Checks
           ├─ AI Analysis
           └─ Decision Logic
                │
                ▼
        ALERT MANAGER
           │
        ┌──┼──┬──────────┐
        │  │  │          │
        ▼  ▼  ▼          ▼
     Telegram Discord Email PushBullet
        │      │      │      │
        └──────┴──────┴──────┴─→ Users
```

---

## 9. Configuration & Parameter Flow

```
CONFIG.YAML
│
├─ Market Analysis Parameters
│  ├─ Market Sentiment Weights
│  ├─ Bullish/Bearish Thresholds
│  └─ Update Frequency
│
├─ Signal Parameters
│  ├─ Min Confidence: 6.0
│  ├─ Min R:R Ratio: 1.5
│  ├─ Max Entry Width: 5%
│  └─ Top Signals: 10
│
├─ Strategy Parameters
│  ├─ MTF Settings
│  │  ├─ Timeframes: [1h, 4h, 1d]
│  │  ├─ Confluence threshold
│  │  └─ Entry zone width
│  │
│  └─ PRD Settings
│     ├─ Price level strength
│     ├─ Reversal confirmation
│     └─ Direction confirmation
│
├─ AI Configuration
│  ├─ Provider: OpenAI/Gemini
│  ├─ Model: gpt-4/gemini-pro
│  ├─ Temperature: 0.3
│  └─ Max Tokens: 800
│
├─ AI Agent Settings
│  ├─ Approval Threshold: 70
│  ├─ Hold Threshold: 40
│  ├─ Check Weights
│  └─ Confidence Adjustments
│
├─ Alert Settings
│  ├─ Telegram Enabled
│  ├─ Discord Enabled
│  ├─ Email Enabled
│  └─ Alert Thresholds
│
└─ Learning Settings
   ├─ History Retention: 30 days
   ├─ Accuracy Window: 7 days
   ├─ Adaptation Interval: 24h
   └─ Improvement Threshold: +2%
        │
        ▼ LOADED INTO SCANNER
        │
        └─ Applied to all processes
           ├─ Market analysis uses weights
           ├─ Signals use thresholds
           ├─ AI agent uses check weights
           ├─ Alerts use enabled flags
           └─ Learning uses windows
```

---

## Summary Table: Data Transformations

| Step | Input | Process | Output |
|------|-------|---------|--------|
| 1 | Market Data | Market Sentiment Engine | MarketSentimentScore |
| 2 | Sentiment Score | AI Analyzer | Risk Level, Recommendations |
| 3 | Prev + Current Sentiment | Trend Alert Engine | List[TrendAlert] |
| 4 | All Coins | Coin Filter Engine | Ranked Top Coins |
| 5 | Top Coins + OHLCV | MTF/PRD Strategy | List[Signal] |
| 6 | Signals | Enrichment (Confluence, Position, Risk) | Enhanced Signals |
| 7 | Enhanced Signals + Sentiment | AI Validation Agent | SignalValidationResult |
| 8 | Validated Signals | Market Filter | Sentiment-Aligned Signals |
| 9 | Filtered Signals | Alert Manager | Alerts Sent (Telegram, Discord) |
| 10 | Sent Signals | Tracker + Resolution Checker | Resolution (WIN/LOSS) |
| 11 | Resolutions | Accuracy Scorer | Accuracy Stats |
| 12 | Stats | Learning Engine | Patterns Identified |
| 13 | Patterns | Self-Adaptation | Updated Parameters |
| 14 | Updated Parameters | → Next Scan | Improved Signals |

---

**This comprehensive flow guide helps you understand exactly how data moves through the entire system!** 🚀
