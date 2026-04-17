# ⚡ Crypto Scanner - Quick Reference Card

## 📋 One-Page Developer Quick Reference

### What is the Crypto Scanner?

An AI-powered automated cryptocurrency trading signal scanner that:
- Analyzes market sentiment
- Generates technical signals
- Validates signals with AI agent
- Alerts on trend changes
- Learns from accuracy
- Self-adapts parameters

---

## 🏗️ System Architecture (10 seconds)

```
Market Data → Sentiment → Trend Alerts
              ↓
          Filter Coins → Generate Signals → Enrich Signals
                                             ↓
                                        🤖 AI Validate
                                             ↓
                              Apply Market Filter
                                             ↓
                                    Send Alerts
                                             ↓
                            Track & Learn System
```

---

## 📂 Key Directory Structure

```
crypto_scanner/
├── scanner.py              ⭐ Main orchestrator
├── main.py                 Entry point
├── config.yaml             All configuration
│
├── engines/
│  ├── market_sentiment_engine.py    ← Market analysis
│  ├── trend_alert_engine.py         ← Trend alerts
│  ├── coin_filter_engine.py         ← Coin filtering
│  ├── risk_management_engine.py     ← Risk checks
│  └── position_sizer.py             ← Position sizing
│
├── strategies/
│  ├── mtf_engine.py                 ← Multi-timeframe signals
│  └── prd_signal_engine.py          ← PRD signals
│
├── ai/
│  ├── market_sentiment_analyzer.py  ← AI sentiment analysis
│  └── signal_validation_agent.py    ← 🤖 AI validation (NEW)
│
├── alerts/
│  ├── alert_manager.py              ← Dispatch alerts
│  ├── telegram_bot.py               ← Telegram sending
│  └── signal_publisher.py           ← Other channels
│
└── learning/
   ├── accuracy_scorer.py            ← Score accuracy
   ├── signal_tracker.py             ← Track signals
   ├── learning_engine.py            ← Learn patterns
   └── self_adaptation.py            ← Adapt parameters
```

---

## 🔄 Single Scan Cycle (High Level)

```
1. Fetch market data
2. Calculate market sentiment
3. Check for trend alerts → Send alerts if new phase
4. Filter & rank coins
5. Generate signals (MTF + PRD strategies)
6. Enrich signals (confluence, position sizing, risk)
7. 🤖 AI agent validates each signal
8. Filter by market sentiment (LONG in BULLISH?)
9. Send approved signals → Telegram, Discord
10. Track signal performance
11. Update accuracy stats
12. Self-adapt parameters
```

**Time:** ~45 seconds per scan  
**Signals Generated:** 0-50+  
**Signals Sent:** 0-20 (after AI validation)

---

## 🤖 AI Agent Validation (8 Points)

| Check | Points | Good | Bad |
|-------|--------|------|-----|
| Market Alignment | 20 | LONG in BULLISH | LONG in BEARISH |
| Risk/Reward | 15 | 1:3.0 | < 1:1.5 |
| Entry Zone | 10 | < 2% width | > 5% width |
| Stop Loss | 10 | 1-3% away | > 5% away |
| Confidence | 10 | >= 8.0/10 | <= 6.0/10 |
| Market Cap | 10 | > $100M | < $10M |
| Volume | 10 | > 1.5x avg | Low volume |
| Strategy | 5 | Established | Unknown |
| **TOTAL** | **100** | | |

**Decision Logic:**
- Score >= 70 → ✅ APPROVE (+1.0 confidence)
- Score 40-70 → ⏸️ HOLD (0.0 adjustment)
- Score < 40 → ❌ REJECT (-2.0 confidence)

---

## 📊 Market Sentiment Levels

| Sentiment | Score | Emoji | Meaning | Action |
|-----------|-------|-------|---------|--------|
| VERY_BULLISH | 75-100 | 🚀 | Excellent LONG | Send LONG signals |
| BULLISH | 60-74 | 📈 | Good for LONG | Send LONG signals |
| NEUTRAL | 40-59 | ➖ | Uncertain | Be cautious |
| BEARISH | 25-39 | 📉 | Good for SHORT | Send SHORT signals |
| VERY_BEARISH | 0-24 | 🔴 | HIGH RISK | Avoid trading |

---

## 🎯 Key Files to Know

| File | Purpose | Modify When |
|------|---------|-------------|
| scanner.py | Main orchestrator | Adding workflow steps |
| engines/market_sentiment_engine.py | Market analysis | Changing sentiment calc |
| strategies/mtf_engine.py | Signal generation | Adding new strategy |
| ai/signal_validation_agent.py | AI validation | Changing validation rules |
| alerts/alert_manager.py | Alert dispatch | Adding alert channel |
| config.yaml | Configuration | Adjusting parameters |
| learning/learning_engine.py | Learning system | Changing adaptation logic |

---

## ⚙️ Configuration Essentials

```yaml
# config.yaml key sections

market_sentiment:
  btc_weight: 0.25              # BTC importance
  very_bullish_threshold: 75    # VERY_BULLISH score

signals:
  min_confidence: 6.0           # Skip below this
  min_risk_reward: 1.5          # Minimum R:R

ai:
  enabled: true                 # Enable AI features
  ai_provider: "openai"         # or "gemini"

ai_validation:
  approval_threshold: 70        # Score >= 70 = APPROVE
  hold_threshold: 40            # Score < 40 = REJECT

alerts:
  telegram_enabled: true
  discord_enabled: true
  min_signal_confidence_to_alert: 6.0

learning:
  history_retention_days: 30    # Keep 30 days data
  accuracy_calculation_window: 7  # Calculate on 7 days
```

---

## 🔍 Understanding Data Flow

```
Market Input
    ↓
Market Sentiment (0-100 score)
    ↓
Trend Alert? (if phase changed)
    ↓
Filter Coins (top 20-30 by quality)
    ↓
For Each Coin:
  Signal Generation (MTF/PRD)
    ↓
  Enrich (confluence, risk, position)
    ↓
🤖 AI Agent Validation
    ├─ Rule-based checks → Score 0-100
    ├─ AI analysis → Decision
    └─ Decision: APPROVE/HOLD/REJECT
    ↓
Market Sentiment Filter
  (LONG only in BULLISH?)
    ↓
Alert Dispatch
  ├─ Telegram
  ├─ Discord
  └─ Email
    ↓
Track Performance
  Signal Resolution (WIN/LOSS)
    ↓
Learn & Adapt
  Update parameters based on accuracy
```

---

## 📈 Signal Example

```
Signal: BTC LONG (Breakout)

Technical:
├─ Entry: $45,000 - $45,500
├─ Stop: $44,500
├─ Target 1: $46,000
├─ Target 2: $47,000
├─ Risk/Reward: 1:2.2
├─ Confidence: 8.2/10
└─ Strategy: mtf_breakout

Market:
├─ Sentiment: VERY_BULLISH (82/100)
├─ Gainers: 78%
└─ Strength: 78/100

🤖 AI Agent:
├─ Market Alignment: 95/100 ✅
├─ Setup Quality: 78/100 ✅
├─ Decision: APPROVE
├─ Adjusted Confidence: 9.2/10 (+1.0 boost)
└─ Reasoning: "Strong breakout in VERY_BULLISH market"

Status: ✅ READY TO SEND
```

---

## 🚀 Common Tasks

### Add New Signal Strategy
1. Create file: `strategies/my_strategy.py`
2. Implement: `generate_signals(coin_data)` method
3. Call from: `scanner.py` in `process_coins()`
4. Add config params

### Modify AI Validation
1. Edit: `ai/signal_validation_agent.py`
2. Update: `_perform_rule_based_checks()`
3. Change: Check weights/thresholds
4. Test: Run scanner, verify decisions

### Add Alert Channel
1. Create handler (like `telegram_bot.py`)
2. Implement: `send_alert()` method
3. Call from: `alert_manager.py`
4. Update: `config.yaml`

### Change Sentiment Thresholds
1. Edit: `config.yaml`
2. Update: Threshold values
3. Restart: Scanner picks up new values

### Adjust AI Approval Threshold
1. Edit: `config.yaml`
2. Update: `ai_validation.approval_threshold`
3. Higher = stricter, fewer alerts
4. Lower = lenient, more alerts

---

## 🐛 Debugging Quick Tips

### Check Market Sentiment
```python
sentiment = scanner.current_market_sentiment
print(f"Score: {sentiment.score} | Sentiment: {sentiment.sentiment}")
```

### View AI Decisions
```python
agent = scanner.signal_validation_agent
decisions = agent.get_decision_log(10)
for d in decisions:
    print(f"{d.symbol}: {d.decision.value} ({d.setup_quality_score:.0f}/100)")
```

### Check Signal Count
```python
print(f"Signals generated: {len(all_signals)}")
print(f"Signals approved: {len(validated_signals)}")
print(f"Signals sent: {len(sent_signals)}")
```

### See Accuracy Stats
```python
stats = scanner.accuracy_tracker.get_statistics()
print(f"Win rate: {stats['accuracy']:.1f}%")
print(f"Strategy accuracy: {stats['per_strategy']}")
```

---

## 📊 Performance Metrics

**Typical Performance:**
- Scan duration: 30-60 seconds
- Coins scanned: 200+
- Signals generated: 30-50
- Signals approved (AI): 5-15
- Signals sent: 5-15
- Trend alerts: 0-2 per scan

**Accuracy Targets:**
- Win rate: 60-70%
- Average R:R: 1:2+
- Approval rate: 30-40% of signals

---

## 🔑 Key Concepts

**Market Sentiment** - Overall market direction (BULLISH/BEARISH)  
**Signal** - Trading opportunity with entry/stop/targets  
**Confidence** - Quality score 0-10, higher = better  
**R:R Ratio** - Risk/Reward, 1:2 means risk $1 to earn $2  
**Confluence** - Multiple indicators agreeing = stronger signal  
**Validation** - AI checks if signal is good quality  
**Trend Alert** - Notification when market enters new phase  
**Accuracy** - % of signals that hit target (win rate)

---

## 📖 Documentation Files

| File | Purpose | Read Time |
|------|---------|-----------|
| PROJECT_STRUCTURE.md | Architecture overview | 30 min |
| DATA_FLOW.md | Complete data flow | 40 min |
| FEATURE_CODE_MAP.md | Feature location map | 15 min |
| AI_AGENT_GUIDE.md | AI validation details | 40 min |
| AI_AGENT_QUICK_START.md | AI quick reference | 15 min |
| config.yaml | Configuration reference | 10 min |

---

## 🎯 Getting Started Checklist

- [ ] Read this quick reference (5 min)
- [ ] Read PROJECT_STRUCTURE.md (30 min)
- [ ] Skim DATA_FLOW.md (20 min)
- [ ] Review config.yaml (10 min)
- [ ] Run scanner: `python main.py`
- [ ] Observe output in console
- [ ] Check Telegram/Discord alerts
- [ ] Review decision logs
- [ ] Make first modification
- [ ] Test & verify
- [ ] Deploy!

---

## 🆘 Quick Help

**Q: Where does X happen?**  
A: FEATURE_CODE_MAP.md → Search for X

**Q: How do I add Y?**  
A: PROJECT_STRUCTURE.md → Development Guide section

**Q: How does Z work?**  
A: DATA_FLOW.md → Find Z in flow diagram

**Q: What's the config option?**  
A: config.yaml → Search for option

**Q: Where's the AI logic?**  
A: ai/signal_validation_agent.py

**Q: How do alerts work?**  
A: DATA_FLOW.md → Alert Dispatch Flow

---

## 💡 Pro Tips

✅ Always check `config.yaml` before coding (parameter exists?)  
✅ Use FEATURE_CODE_MAP.md for quick lookups  
✅ Read DATA_FLOW.md to understand signal journey  
✅ Check AI decision logs to debug validation issues  
✅ Monitor accuracy stats to know if system improving  
✅ Test modifications with small market first  
✅ Keep deployment environment synced with dev  

---

**Print this page for your desk! 📌**

**Next: Read PROJECT_STRUCTURE.md for full details** 👉
