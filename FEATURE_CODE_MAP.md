# 🗺️ Crypto Scanner - Feature to Code Mapping Quick Reference

A quick guide for developers to find code for specific features.

---

## 📊 Market Analysis Features

### Feature: Market Sentiment Analysis
**What it does:** Analyzes whether market is BULLISH or BEARISH

**Files:**
- Primary: `engines/market_sentiment_engine.py`
- AI Layer: `ai/market_sentiment_analyzer.py`
- Configuration: `config.yaml` (market_sentiment section)

**Key Classes:**
- `MarketSentimentEngine.analyze_market_sentiment()`
- `MarketSentimentScore` (output dataclass)
- `MarketSentiment` (enum: VERY_BEARISH, BEARISH, NEUTRAL, BULLISH, VERY_BULLISH)

**Integration Point:** `scanner.py` line ~300-350 (after get_market_data)

**How to customize:**
```yaml
# config.yaml
market_sentiment:
  btc_weight: 0.25  # Increase to prioritize BTC trend
  breadth_weight: 0.25  # Adjust market breadth weight
  very_bullish_threshold: 75  # Score threshold for VERY_BULLISH
```

**Example Output:**
```python
sentiment = engine.analyze_market_sentiment(market_data)
# Returns: MarketSentimentScore
#   sentiment: MarketSentiment.BULLISH
#   score: 68.5
#   favorable_for: "LONG"
```

---

### Feature: AI Market Interpretation
**What it does:** Uses LLM to interpret market conditions deeper

**Files:**
- Primary: `ai/market_sentiment_analyzer.py`
- Configuration: `config.yaml` (ai section)

**Key Classes:**
- `AIMarketSentimentAnalyzer.analyze_sentiment_with_ai()`
- `MarketSentimentMonitor.check_sentiment_shift()`

**Integration Point:** `scanner.py` line ~380 (optional, for deeper analysis)

**How to customize:**
```yaml
# config.yaml
ai:
  ai_provider: "openai"  # or "gemini"
  ai_temperature: 0.3  # Lower = more focused
  ai_max_tokens: 800  # Max response length
```

**Example Usage:**
```python
analyzer = AIMarketSentimentAnalyzer()
ai_analysis = await analyzer.analyze_sentiment_with_ai(
    sentiment_score=sentiment,
    recent_history=history
)
# Returns: {
#   "risk_level": "MEDIUM",
#   "market_interpretation": "...",
#   "recommendations": "..."
# }
```

---

### Feature: Market Trend Alerts
**What it does:** Alerts when market enters BULLISH/BEARISH phases

**Files:**
- Primary: `engines/trend_alert_engine.py`
- Alert Dispatch: `alerts/alert_manager.py` (send_trend_alerts method)
- Telegram: `alerts/telegram_bot.py`

**Key Classes:**
- `MarketTrendAlertEngine.check_trend_alerts()`
- `TrendAlert` (output dataclass)
- `TrendAlertType` (enum: ENTERING_VERY_BULLISH, ENTERING_BULLISH, etc)

**Integration Point:** `scanner.py` line ~400-420 (after sentiment analysis)

**Alerts Sent:**
- 🚀 ENTERING_VERY_BULLISH (Score 75-100)
- 📈 ENTERING_BULLISH (Score 60-74)
- 📉 ENTERING_BEARISH (Score 25-39)
- 🔴 ENTERING_VERY_BEARISH (Score 0-24)

**Example:**
```python
trend_engine = MarketTrendAlertEngine()
alerts = trend_engine.check_trend_alerts(
    previous_sentiment=old_sentiment,
    current_sentiment=new_sentiment
)
# Returns: List[TrendAlert]
#   alert_type: TrendAlertType.ENTERING_BULLISH
#   message: "MARKET ENTERED BULLISH PHASE"
#   impact_level: "high"
```

---

## 🎯 Signal Generation Features

### Feature: Multi-Timeframe Signal Generation
**What it does:** Generates LONG/SHORT signals using 1H, 4H, 1D analysis

**Files:**
- Primary: `strategies/mtf_engine.py`
- Configuration: `config.yaml` (strategies section)

**Key Classes:**
- `MTFEngine.generate_mtf_signals(coin_data)`
- `Signal` (output object)

**Integration Point:** `scanner.py` in `process_coins()` method

**How it works:**
1. Analyzes 1D for direction (trend)
2. Analyzes 4H for entry setup
3. Analyzes 1H for confirmation
4. Generates signal with entry, stop, targets

**Customize Entry Rules:**
```python
# In strategies/mtf_engine.py
# Modify breakout detection logic around line 150-200
# Adjust confluence thresholds
# Change support/resistance calculation
```

**Example Output:**
```python
signals = await mtf_engine.generate_mtf_signals(coin_data)
# Returns: List[Signal]
# Signal {
#   symbol: "BTC",
#   type: "LONG",
#   entry_low: 45000,
#   entry_high: 45500,
#   stop_loss: 44500,
#   target_1: 46000,
#   target_2: 47000,
#   confidence: 8.2/10,
#   strategy: "mtf_breakout"
# }
```

---

### Feature: PRD Signal Generation
**What it does:** Price-Reversal-Direction signal strategy

**Files:**
- Primary: `strategies/prd_signal_engine.py`
- Configuration: `config.yaml` (strategies section)

**Key Classes:**
- `PRDSignalEngine.generate_prd_signals(coin_data)`

**Integration Point:** `scanner.py` in `process_coins()` method

**How it works:**
1. Identifies key price levels (support/resistance)
2. Detects reversal patterns
3. Confirms with directional indicators
4. Generates signal if all align

**Customize:**
```python
# In strategies/prd_signal_engine.py
# Modify price level detection (line ~80-120)
# Adjust reversal pattern scoring (line ~150-200)
# Change direction confirmation logic (line ~220-280)
```

---

### Feature: Coin Filtering & Ranking
**What it does:** Filters coins by market cap, volume; ranks by quality

**Files:**
- Primary: `engines/coin_filter_engine.py`
- Configuration: `config.yaml` (market_analysis section)

**Key Classes:**
- `CoinFilterEngine.filter_and_rank_coins(all_coins)`

**Integration Point:** `scanner.py` around line 250-280

**Filters Applied:**
- Market cap > $10M
- Daily volume > $1M
- 24h volume increase > 1.5x average
- Exclude stablecoins

**Customize Filters:**
```yaml
# config.yaml
market_analysis:
  min_market_cap: 10000000  # Increase for safer coins
  min_volume: 1000000  # Increase for more liquid
  max_market_cap: 1000000000000  # Cap very large coins
```

---

### Feature: Confluence Analysis
**What it does:** Checks if multiple indicators agree on signal

**Files:**
- Primary: `engines/confluence_engine.py`

**Key Classes:**
- `ConfluenceEngine.check_confluence(signal, coin_data)`

**Integration Point:** `scanner.py` in `process_coins()` after signal generation

**What it checks:**
- Moving average alignment
- Oscillator agreement
- Volume confirmation
- Pattern confirmation

---

### Feature: Position Sizing
**What it does:** Calculates how much to risk per trade

**Files:**
- Primary: `engines/position_sizer.py`

**Key Classes:**
- `PositionSizer.calculate_position_size(signal, account_size)`

**Integration Point:** `scanner.py` in signal enrichment

**How it works:**
- Takes risk per trade (e.g., 2% of account)
- Calculates based on stop loss distance
- Returns position size in coins/contracts

---

### Feature: Risk Management
**What it does:** Validates signal meets risk criteria

**Files:**
- Primary: `engines/risk_management_engine.py`

**Key Classes:**
- `RiskManagementEngine.validate_risk(signal)`

**Integration Point:** `scanner.py` during signal filtering

**Validations:**
- Stop loss distance appropriate (1-5%)
- Risk/reward >= 1:1.5
- Entry zone not too wide
- Position size appropriate

---

## 🤖 AI Agent Features

### Feature: AI Signal Validation
**What it does:** Intelligent validation of signals before sending

**Files:**
- Primary: `ai/signal_validation_agent.py`
- Integration: `scanner.py` (run_scan method, around line 600-650)

**Key Classes:**
- `AISignalValidationAgent.validate_signal(signal, coin, sentiment)`
- `SignalValidationResult` (output)
- `SignalDecision` (enum: APPROVE, REJECT, HOLD)

**Validation Framework (8 points):**
1. Market alignment check (20 pts)
2. Risk/reward check (15 pts)
3. Entry zone check (10 pts)
4. Stop loss check (10 pts)
5. Confidence check (10 pts)
6. Market cap check (10 pts)
7. Volume check (10 pts)
8. Strategy type check (5 pts)

**Decision Logic:**
- Score >= 70 → APPROVE (+1.0 confidence)
- Score 40-70 → HOLD (0.0 adjustment)
- Score < 40 → REJECT (-2.0 confidence)

**How to customize:**
```python
# In ai/signal_validation_agent.py
# Modify _perform_rule_based_checks() to add/remove checks
# Adjust point allocations in check_weights
# Change decision thresholds (approval_threshold, hold_threshold)
```

**Example Usage:**
```python
result = await agent.validate_signal(
    signal=signal,
    coin=coin_data,
    market_sentiment=sentiment
)
# Returns: SignalValidationResult {
#   decision: SignalDecision.APPROVE,
#   adjusted_confidence: 9.2,
#   setup_quality_score: 78.0,
#   reasoning: "Strong breakout in bullish market..."
# }
```

---

### Feature: AI Decision Logging
**What it does:** Logs all AI agent decisions for audit trail

**Files:**
- Primary: `ai/signal_validation_agent.py`
- Access: `AISignalValidationAgent.get_decision_log(limit)`

**Key Methods:**
- `get_decision_log(limit)` - Get recent decisions
- `get_decision_summary()` - Get statistics

**Logged Information:**
- Signal ID and symbol
- Decision (APPROVE/REJECT/HOLD)
- Setup quality score
- Market alignment score
- All checks passed/failed
- Reasoning
- Timestamp

**Example Usage:**
```python
agent = scanner.signal_validation_agent
decisions = agent.get_decision_log(20)

for decision in decisions:
    print(f"{decision.symbol}: {decision.decision.value}")
    print(f"  Setup Quality: {decision.setup_quality_score:.0f}/100")
    print(f"  Alignment: {decision.market_alignment_score:.0f}/100")
    print(f"  Reasoning: {decision.reasoning}")
```

---

## 📢 Alert & Notification Features

### Feature: Telegram Alerts
**What it does:** Sends trading signals and trend alerts via Telegram

**Files:**
- Primary: `alerts/telegram_bot.py`
- Integration: `alerts/alert_manager.py` (send_signal_alerts)
- Configuration: `config.yaml` (alerts section)

**Configuration:**
```yaml
# config.yaml
alerts:
  telegram_enabled: true
  telegram_bot_token: "YOUR_BOT_TOKEN"
  telegram_chat_id: "YOUR_CHAT_ID"
```

**How it sends alerts:**
1. Format signal data
2. Add market context
3. Add AI agent decision
4. Send to Telegram API

**Example:**
```python
await telegram_bot.send_signal(
    signal=signal,
    market_sentiment=sentiment,
    validation_result=ai_result
)
```

---

### Feature: Discord Alerts
**What it does:** Sends alerts via Discord with rich formatting

**Files:**
- Primary: `alerts/alert_manager.py` (_send_discord_signal_alert)
- Configuration: `config.yaml` (alerts section)

**Configuration:**
```yaml
# config.yaml
alerts:
  discord_enabled: true
  discord_webhook_url: "YOUR_WEBHOOK_URL"
```

**Formatting:**
- Color-coded by signal strength (green=strong, red=weak)
- Embedded format with fields
- AI agent decision highlighted

---

### Feature: Signal Publishing
**What it does:** Publishes signals to other channels/services

**Files:**
- Primary: `alerts/signal_publisher.py`

**Integration Points:**
- Email notifications
- Custom webhooks
- 3rd party APIs

---

## 📊 Learning & Adaptation Features

### Feature: Signal Accuracy Tracking
**What it does:** Tracks if signals hit target or stop loss

**Files:**
- Primary: `learning/signal_tracker.py` and `learning/resolution_checker.py`
- Storage: `data/learning_history.json`

**Key Classes:**
- `SignalTracker.track_signal(signal)`
- `ResolutionChecker.check_resolution(signal)`

**What it tracks:**
- Entry price
- Stop loss
- Targets
- Resolution (WIN/LOSS/PARTIAL)
- P&L

**Integration Point:** `scanner.py` in `check_signal_resolution()` method

**Example:**
```python
# Track signal when sent
tracker.track_signal(signal)

# Later, check if it resolved
resolution = resolution_checker.check_resolution(signal)
# Returns: {
#   "status": "WIN",
#   "exit_price": 46000,
#   "pnl_percent": 2.2,
#   "target_hit": 1
# }
```

---

### Feature: Accuracy Scoring
**What it does:** Calculates win rate and accuracy per strategy

**Files:**
- Primary: `learning/accuracy_scorer.py`
- Storage: `data/learning_history.json`

**Key Classes:**
- `AccuracyScorer.score_signal(signal, resolution)`
- `AccuracyScorer.calculate_statistics()`

**Metrics Calculated:**
- Win rate % (per strategy, per timeframe)
- Average R:R achieved
- Average winning trade
- Average losing trade
- Profit factor

**Integration Point:** `scanner.py` in `update_accuracy()` method

**Example:**
```python
stats = scorer.calculate_statistics()
# Returns: {
#   "mtf_strategy_accuracy": 65.0,
#   "prd_strategy_accuracy": 72.0,
#   "overall_accuracy": 68.5,
#   "win_count": 68,
#   "loss_count": 32,
#   "avg_rr_achieved": 2.1
# }
```

---

### Feature: Learning Engine
**What it does:** Identifies patterns in successful signals

**Files:**
- Primary: `learning/learning_engine.py`

**Key Classes:**
- `LearningEngine.learn_from_history(history_data)`
- `LearningEngine.identify_success_patterns()`

**What it learns:**
- Successful signals have avg confidence 7.8+
- Successful signals have R:R 1:2+
- Best strategy in current market condition
- Optimal entry zone width

**Integration Point:** `scanner.py` in `self_adapt_parameters()` method

---

### Feature: Self-Adaptation
**What it does:** Adjusts parameters based on learning

**Files:**
- Primary: `learning/self_adaptation.py`

**Key Classes:**
- `SelfAdaptationEngine.propose_adaptations(stats)`
- `SelfAdaptationEngine.apply_parameter_updates()`

**Adaptations Made:**
- Confidence threshold (increase if too many false signals)
- Risk/reward minimum (increase if profitability down)
- Entry zone width (tighten if accuracy down)
- Strategy weights (prioritize better strategies)

**Integration Point:** `scanner.py` in `self_adapt_parameters()` method

**Example:**
```python
adaptations = adaptation_engine.propose_adaptations(current_stats)
# Returns: {
#   "min_confidence": 7.0,  # Was 6.0
#   "min_risk_reward": 2.0,  # Was 1.5
#   "strategy_weights": {
#     "mtf": 0.6,
#     "prd": 0.4
#   }
# }

# Apply changes
adaptation_engine.apply_parameter_updates(adaptations)
```

---

### Feature: Trade Journal
**What it does:** Maintains detailed journal of all trades

**Files:**
- Primary: `learning/trade_journal.py`

**Key Classes:**
- `TradeJournal.record_trade(signal, resolution)`
- `TradeJournal.get_recent_trades(limit)`

**Information Stored:**
- Signal details
- Entry/exit prices
- P&L
- Timestamp
- Strategy used
- Market conditions

---

## 🔧 Configuration Features

### Feature: Configuration Management
**What it does:** Centralized configuration for entire system

**Files:**
- Primary: `config.yaml`
- Loading: `scanner.py` (load_config method)

**Key Sections:**
```yaml
market_sentiment:      # Market analysis thresholds
  - btc_weight, breadth_weight, etc.

signals:               # Signal generation params
  - min_confidence, min_risk_reward

strategies:            # Strategy-specific params
  - mtf_params, prd_params

ai:                    # AI provider configuration
  - ai_provider, ai_temperature

alerts:                # Alert channel settings
  - telegram_enabled, discord_enabled

learning:              # Learning system config
  - history_retention_days
```

**How to customize:**
- Edit `config.yaml`
- Parameters reload on scanner restart
- No code changes needed

---

## 📁 Database & Storage

### Feature: Learning History Storage
**What it does:** Stores signal accuracy history

**Files:**
- Storage: `data/learning_history.json`
- Write: `learning/accuracy_scorer.py`
- Read: `learning/learning_engine.py`

**Data Format:**
```json
{
  "signals": [
    {
      "signal_id": "BTC_1h_123",
      "symbol": "BTC",
      "strategy": "mtf",
      "entry": 45000,
      "stop": 44500,
      "target": 46000,
      "resolution": "WIN",
      "exit_price": 46000,
      "date": "2026-04-18"
    }
  ],
  "accuracy_stats": {
    "mtf_accuracy": 65.0,
    "prd_accuracy": 72.0,
    "overall": 68.5
  }
}
```

---

## 🔗 Quick Cross-Reference

### By Feature Type

**Market Analysis:**
- Market Sentiment → `engines/market_sentiment_engine.py`
- AI Analysis → `ai/market_sentiment_analyzer.py`
- Trend Alerts → `engines/trend_alert_engine.py`

**Signal Generation:**
- MTF Strategy → `strategies/mtf_engine.py`
- PRD Strategy → `strategies/prd_signal_engine.py`
- Coin Filtering → `engines/coin_filter_engine.py`
- Confluence → `engines/confluence_engine.py`
- Position Sizing → `engines/position_sizer.py`
- Risk Management → `engines/risk_management_engine.py`

**AI & Validation:**
- Signal Validation → `ai/signal_validation_agent.py`
- Reasoning → `reasoning/hybrid_reasoner.py`

**Alerts:**
- Telegram → `alerts/telegram_bot.py`
- Discord → `alerts/alert_manager.py`
- All Alerts → `alerts/alert_manager.py`

**Learning:**
- Tracking → `learning/signal_tracker.py`
- Resolution → `learning/resolution_checker.py`
- Accuracy → `learning/accuracy_scorer.py`
- Learning → `learning/learning_engine.py`
- Adaptation → `learning/self_adaptation.py`
- Journal → `learning/trade_journal.py`

**Orchestration:**
- Main Loop → `scanner.py`
- Entry Point → `main.py`
- Scheduling → `src/scheduler/scanner_scheduler.py`

---

## 📚 For Quick Understanding

### Read in This Order (New Developers)
1. `PROJECT_STRUCTURE.md` (you're reading it!)
2. `AI_AGENT_QUICK_START.md` (understand AI agent)
3. `config.yaml` (understand configuration)
4. `scanner.py` (understand main flow)
5. `engines/market_sentiment_engine.py` (understand sentiment)
6. `strategies/mtf_engine.py` (understand signal generation)
7. `ai/signal_validation_agent.py` (understand validation)

### One-Page Code Reference
```python
# Scan flow (scanner.py)
1. get_market_data()
2. analyze_market_sentiment() → engines/market_sentiment_engine.py
3. check_trend_alerts() → engines/trend_alert_engine.py
4. process_coins() 
   → strategies/mtf_engine.py (generate signals)
   → strategies/prd_signal_engine.py
   → engines/confluence_engine.py
   → engines/risk_management_engine.py
5. validate_signals_with_agent() → ai/signal_validation_agent.py
6. apply_market_filter()
7. send_alerts() → alerts/alert_manager.py
8. check_signal_resolution() → learning/resolution_checker.py
9. self_adapt_parameters() → learning/self_adaptation.py
```

---

**Use this document to quickly find where to look for any feature!** 🎯
