# PRD: Hybrid Reasoning + Learning System for Crypto Scanner

## 1. Overview

**Project Name:** Hybrid Reasoning + Learning System

**Type:** Feature Enhancement

**Core Functionality:** Enhance the crypto scanner with a hybrid reasoning system combining rule-based algorithms, weighted scoring, and AI reasoning, plus a feedback loop system to learn from signal outcomes and improve accuracy over time.

**Target Users:** Crypto traders using the scanner for automated signal generation and decision support.

---

## 2. Background & Context

### Current System Architecture

The application currently implements:

1. **Rule-Based Strategy Engines (4 engines):**
   - Trend Continuation Engine - momentum-based entries
   - Bearish Trend Engine - short setups
   - Liquidity Sweep Engine - fake breakout detection
   - Volatility Breakout Engine - compression/expansion trades

2. **Weighted Scoring System (0-10 scale):**
   - Trend alignment (+3)
   - Volume confirmation (+2)
   - BTC alignment (+2)
   - Volatility expansion (+2)
   - Liquidity sweep (+1)

3. **AI Integration:**
   - AISignalAnalyzer - enhances existing signals with LLM analysis
   - AISignalGenerator - generates pure AI signals
   - Multi-provider support (OpenAI, Anthropic, Groq, Ollama)

4. **Storage & Tracking:**
   - SQLite database for signals and trades
   - Performance statistics tracking

### Gap Analysis

- **Reasoning:** Current AI is used mainly for signal enhancement, not as a core reasoning component alongside rules
- **Learning:** No feedback loop exists - signals are generated but their outcomes aren't used to improve the system
- **Tracking:** While trade records exist, there's no automated outcome tracking or accuracy scoring

---

## 3. Feature Requirements

### 3.1 Hybrid Reasoning System

**Feature: Combined Reasoning Engine**

**Description:** Enhance the signal generation process to use three components in parallel:
1. Rule-based algorithms (existing)
2. Weighted scoring (existing)
3. AI Reasoning (new - deeper integration)

**Requirements:**

#### 3.1.1 Reasoning Component Architecture

Signal Generation Flow:
- Rule-Based Algorithms (4 Strategies)
- Weighted Scoring (0-10 scale)
- AI Reasoning (LLM Analysis)
=> Combined into Hybrid Signal Output

#### 3.1.2 AI Reasoning Prompt Enhancement

Create a new `HybridReasoner` module that sends structured prompts to LLM including:
- Strategy type and entry conditions met
- Score breakdown from weighted scorer
- Technical indicators values
- BTC trend alignment

**Prompt Structure:**
```
Analyze this trading signal and provide:
1. Direction confirmation (LONG/SHORT/NO_TRADE)
2. Confidence adjustment (+/- points based on your analysis)
3. Key observations that rule-based might miss
4. Risk assessment
5. Suggested entry refinements

Signal Data:
- Strategy: {strategy_type}
- Score: {confidence_score}/10
- Breakdown: {score_breakdown}
- Entry Zone: {entry_min} - {entry_max}
- Stop Loss: {stop_loss}
- Risk/Reward: 1:{risk_reward}
- RSI: {rsi_value}
- EMA Alignment: {ema_alignment}
- Volume: {volume_ratio}x
- BTC Trend: {btc_trend}
```

#### 3.1.3 Confidence Score Integration

- **Base Score:** From weighted scoring system (existing)
- **AI Adjustment:** From AI reasoning (-2 to +2 points)
- **Final Score:** Base + AI Adjustment (capped at 0-10)

#### 3.1.4 Reasoning Output Fields

Add to TradingSignal model:
- `hybrid_reasoning: str` - Combined reasoning text from all three sources
- `ai_reasoning_contribution: float` - AI adjustment value
- `rule_based_confidence: float` - Confidence from rules alone
- `reasoning_components: Dict` - Detailed breakdown of each component

### 3.2 Learning System (Feedback Loop)

**Feature: Signal Outcome Tracking & Learning**

**Description:** Implement a continuous feedback loop that:
1. Tracks all generated signals until resolution
2. Scores accuracy based on actual outcomes
3. Uses insights to refine signal generation
4. Notifies users of resolved signals

**Requirements:**

#### 3.2.1 Signal Tracking Module

Create new `SignalTracker` class in `learning/` module:

- `add_signal(signal)` - Add signal to active tracking
- `check_resolutions()` - Check all active signals for resolution
- `record_outcome(signal_id, outcome)` - Record the outcome of a resolved signal

#### 3.2.2 Resolution Detection Logic

For each tracked signal, check:

1. **Stop Loss Hit:**
   - For LONG: Current price <= stop_loss
   - For SHORT: Current price >= stop_loss

2. **Target 1 Hit:**
   - For LONG: Current price >= target_1
   - For SHORT: Current price <= target_1

3. **Target 2 Hit:**
   - For LONG: Current price >= target_2
   - For SHORT: Current price <= target_2

4. **Timeout (No resolution):**
   - Default: 7 days for 4h/daily timeframes
   - Mark as "EXPIRED" after timeout

#### 3.2.3 Outcome Data Model

```python
@dataclass
class SignalOutcome:
    signal_id: str
    symbol: str
    resolution: str  # TARGET_1_HIT, TARGET_2_HIT, STOP_LOSS_HIT, EXPIRED
    pnl_percent: float
    duration_hours: float
    timestamp: datetime
    price_at_resolution: float
    expected_direction_correct: bool
```

#### 3.2.4 Accuracy Scoring System

Create `AccuracyScorer` module that calculates:

1. **Per Strategy Accuracy:**
   ```
   Strategy Accuracy = (Winning Signals) / (Total Resolved Signals) * 100
   ```

2. **Per Timeframe Accuracy:**
   ```
   Timeframe Accuracy = (Winning Signals) / (Total Resolved Signals) * 100
   ```

3. **Per Coin Accuracy:**
   ```
   Coin Accuracy = (Winning Signals for Coin) / (Total Signals for Coin) * 100
   ```

4. **Overall Accuracy:**
   ```
   Overall Accuracy = (Total Wins) / (Total Resolved) * 100
   ```

5. **Signal Quality Score (0-100):**
   ```
   Quality Score = (Win Rate * 0.4) + (Avg Risk/Reward * 0.3) + (Avg Confidence * 0.3)
   ```

#### 3.2.5 Learning Insights Module

Create `LearningEngine` that analyzes outcomes and generates insights:

**Insights to Generate:**
- Which strategies perform best in different market conditions
- Optimal timeframes for different coin types
- Patterns in winning vs losing signals
- Recommended score thresholds based on historical accuracy
- Strategy adjustments (e.g., "Reduce TREND_CONTINUATION weight in BEAR markets")

#### 3.2.6 User Notifications

Send Telegram/Discord notifications when signals resolve:

**Notification Message:**
```
SIGNAL RESOLUTION

{symbol} {direction}
Strategy: {strategy_type}
Timeframe: {timeframe}

Resolution: {TARGET_1_HIT / STOP_LOSS_HIT / etc.}
Entry: ${entry}
Exit: ${exit_price}
PnL: {pnl_percent}%

Accuracy Stats:
- Win Rate: {overall_win_rate}%
- Strategy Win Rate: {strategy_win_rate}%

Generated: {signal_timestamp}
Resolved: {resolution_timestamp}
```

#### 3.2.7 Feedback History Storage

Maintain JSON file for feedback history (as requested):

**File: `data/learning_history.json`**
```json
{
  "last_updated": "2024-01-15T10:30:00",
  "total_signals_tracked": 150,
  "resolved_signals": 120,
  "win_rate": 65.5,
  "accuracy_scores": {
    "overall": 65.5,
    "by_strategy": {
      "TREND_CONTINUATION": 72.0,
      "BEARISH_SHORT": 58.0,
      "LIQUIDITY_SWEEP": 60.0,
      "VOLATILITY_BREAKOUT": 55.0
    },
    "by_timeframe": {
      "1h": 60.0,
      "4h": 70.0,
      "daily": 65.0
    }
  },
  "insights": [
    {
      "type": "STRATEGY_PERFORMANCE",
      "description": "Trend Continuation performs best in BULL markets",
      "confidence": 85.0,
      "recommendation": "Increase weight for TREND_CONTINUATION when BTC=BULLISH"
    }
  ],
  "recent_outcomes": [
    {
      "signal_id": "202401151030001",
      "symbol": "ETH",
      "resolution": "TARGET_1_HIT",
      "pnl_percent": 3.5,
      "duration_hours": 48
    }
  ]
}
```

### 3.3 Scheduled Learning Check

**Feature: Background Resolution Checking**

**Description:** Run periodic checks to detect signal resolutions

**Implementation:**
- Run check every 15 minutes during scanner operation
- Check all active signals against current prices
- Record outcomes and generate insights
- Send notifications for resolved signals

---

## 4. Technical Architecture

### 4.1 New Module Structure

```
crypto_scanner/
├── learning/
│   ├── __init__.py
│   ├── signal_tracker.py    # Track active signals
│   ├── accuracy_scorer.py   # Calculate accuracy scores
│   ├── learning_engine.py  # Generate insights
│   └── notifier.py          # Send resolution notifications
├── reasoning/
│   ├── __init__.py
│   └── hybrid_reasoner.py   # Combined reasoning logic
└── data/
    └── learning_history.json  # Feedback history (new file)
```

### 4.2 Database Schema Updates

Add to existing `performance.db`:

```sql
-- Signal outcomes table
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy_type TEXT,
    timeframe TEXT,
    direction TEXT,
    entry_price REAL,
    resolution TEXT,
    exit_price REAL,
    pnl_percent REAL,
    duration_hours REAL,
    expected_correct BOOLEAN,
    resolved_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Learning insights table
CREATE TABLE IF NOT EXISTS learning_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_type TEXT,
    description TEXT,
    confidence REAL,
    recommendation TEXT,
    affected_strategies TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 Configuration Additions

Add to `config/__init__.py`:

```python
@dataclass
class LearningConfig:
    """Learning System Configuration"""
    enable_learning: bool = os.getenv("ENABLE_LEARNING", "true").lower() == "true"
    check_interval_minutes: int = int(os.getenv("LEARNING_CHECK_INTERVAL", "15"))
    signal_timeout_days: int = int(os.getenv("SIGNAL_TIMEOUT_DAYS", "7"))
    min_signals_for_insights: int = int(os.getenv("MIN_SIGNALS_FOR_INSIGHTS", "20"))
    notify_on_resolution: bool = os.getenv("NOTIFY_ON_RESOLUTION", "true").lower() == "true"
    history_file: str = os.getenv("LEARNING_HISTORY_FILE", "data/learning_history.json")
```

---

## 5. Phased Implementation

### Phase 1: Core Infrastructure (Week 1)
- Create learning/ module structure
- Implement SignalTracker class
- Add database schema updates
- Create learning_history.json file

### Phase 2: Resolution Detection (Week 2)
- Implement accuracy scoring
- Add resolution detection logic
- Implement scheduled checking
- Test with sample signals

### Phase 3: AI Reasoning Enhancement (Week 3)
- Implement HybridReasoner
- Update signal generation flow
- Add new fields to TradingSignal model
- Update scoring integration

### Phase 4: Insights & Notifications (Week 4)
- Implement LearningEngine
- Add notification templates
- Configure Telegram/Discord integration
- Create dashboard updates

---

## 6. Success Metrics

1. **Reasoning Quality:**
   - Signals include comprehensive reasoning from all three components
   - AI adjustments are meaningful and improve signal quality

2. **Learning Effectiveness:**
   - Win rate tracking is accurate
   - Insights are generated after minimum signals
   - System adapts to market conditions

3. **User Value:**
   - Resolution notifications are timely and informative
   - Accuracy scores are visible to users
   - Historical performance data is accessible

---

## 7. Open Questions

1. **Q: Should we use a different name for the learning system?**
   - Suggested names: "Signal Intelligence", "Adaptive Scanner", "Learning Engine"
   - User can decide on final naming

2. **Q: How aggressive should the learning adjustments be?**
   - Option A: Conservative - only adjust scoring weights slightly
   - Option B: Moderate - adjust strategy selection
   - Recommend starting with conservative approach

3. **Q: Should we track paper trades or only real trades for learning?**
   - Initially track all signals regardless of whether user traded
   - Add toggle to filter by "user_confirms_trade" flag later

---

*Document Version: 1.0*
*Created: 2024-01-15*
*Status: Draft for Review*
