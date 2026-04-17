# Market Sentiment Analysis - Quick Reference

## What's Been Added ✨

```
┌─────────────────────────────────────────────────────────┐
│         Market Sentiment Analysis System                │
│                                                         │
│  📊 Analyzes:     📈 Filters:       🧠 Uses AI:        │
│  • BTC trend      • LONG → Bullish  • Risk level       │
│  • Market breadth • SHORT → Bearish • Insights         │
│  • Coin strength  • 75+ conf        • Recommend        │
│  • Volatility     • NEUTRAL         • Market health    │
│  • Volume         • Sentiment       •                  │
│  • Dominance      • Shifts          •                  │
└─────────────────────────────────────────────────────────┘
```

## The Flow

```
Scan Starts
    ↓
📈 Market Sentiment Analysis
    ├─ Analyze Bitcoin trend
    ├─ Check market breadth (% gainers/losers)
    ├─ Calculate market strength
    ├─ Assess altcoin performance
    └─ Get AI insights
    ↓
🎯 Run Technical Strategies (Breakouts, etc.)
    ↓
🔍 Filter Signals by Sentiment
    ├─ LONG signals: Keep if BULLISH or VERY_BULLISH
    ├─ SHORT signals: Keep if BEARISH or VERY_BEARISH
    └─ NEUTRAL: Keep only very high confidence (75+)
    ↓
📬 Send Alerts with Market Context
    ├─ Sentiment score and metrics
    ├─ Market reasoning
    └─ AI insights included
```

## Sentiment Levels

```
100  ████████████████ VERY_BULLISH 🟢
 80  ████████████ BULLISH 🟢
 50  ████ NEUTRAL 🟡
 20  █ BEARISH 🔴
  0  VERY_BEARISH 🔴
```

## Alert Filtering Rules

```
IF signal is LONG:
  IF market = BULLISH OR VERY_BULLISH
    → ✅ SEND
  ELSE IF market = NEUTRAL AND confidence >= 75
    → ✅ SEND
  ELSE
    → ❌ BLOCK

IF signal is SHORT:
  IF market = BEARISH OR VERY_BEARISH
    → ✅ SEND
  ELSE IF market = NEUTRAL AND confidence >= 75
    → ✅ SEND
  ELSE
    → ❌ BLOCK
```

## Files Created

| File | Purpose |
|------|---------|
| `engines/market_sentiment_engine.py` | Core sentiment analysis engine |
| `ai/market_sentiment_analyzer.py` | AI insights & sentiment monitoring |
| `MARKET_SENTIMENT_GUIDE.md` | Comprehensive documentation |
| `MARKET_SENTIMENT_FEATURES.md` | Feature overview & examples |

## Files Updated

| File | Changes |
|------|---------|
| `scanner.py` | Added sentiment analysis to scan flow |
| `alerts/alert_manager.py` | Added sentiment-based filtering |
| `engines/__init__.py` | Export new classes |

## Configuration

**Default**: Enabled ✅
To disable:
```yaml
alerts:
  use_market_sentiment_filter: false
```

## Key Metrics Analyzed

| Metric | What It Measures | Impact |
|--------|-----------------|--------|
| Market Breadth | % Gainers vs Losers | Trend strength |
| Market Strength | Average move magnitude | Confidence |
| Altcoin Strength | Alts vs BTC performance | Risk appetite |
| BTC Trend | Bitcoin direction | Market leader |
| BTC Dominance | BTC market share trend | Altseason vs BTC season |
| Volatility | Price turbulence level | Market stress |

## Example Outputs

### Console (Scan Log)
```
Market Sentiment: VERY_BULLISH
Score: 82.3/100
Gainers: 78.5% | Losers: 21.5%
Market Strength: 78.2/100
Altcoin Strength: 72.1/100

🤖 AI Insight: Strong bullish momentum...
Risk Level: LOW
Recommendation: Focus on LONG breakouts
```

### Alert Message
```
🟢 LONG - BTC
Entry: $45,000-$45,500
Stop: $44,500
Target: $46,000

📊 Market Context
Sentiment: VERY_BULLISH (82/100)
Gainers: 78% | Losers: 22%
Altcoin Strength: 72/100
```

## Benefits

- ✅ Fewer false alerts (no trades against market)
- ✅ Better trade quality (aligned with sentiment)
- ✅ Market context included (understand the why)
- ✅ AI insights (deeper analysis)
- ✅ Sentiment shift detection (catch changes)
- ✅ Configurable filtering (adjust as needed)

## Enable/Run

Just run normally:
```bash
python main.py
```

Sentiment analysis is **automatic**! Check logs for:
- Market Sentiment section
- AI insights
- Filtered signals

## Customization

### Disable Entirely
```yaml
alerts:
  use_market_sentiment_filter: false
```

### Adjust Thresholds
Edit `market_sentiment_engine.py`:
- Change score weights
- Adjust sentiment level breakpoints
- Modify filtering rules

### Extend AI Analysis
Edit `ai/market_sentiment_analyzer.py`:
- Add custom analysis methods
- Customize AI prompts
- Change risk assessments

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No alerts sent | Check if sentiment blocks them (see logs) |
| AI not working | Verify AI provider configured |
| Sentiment always NEUTRAL | May need more coins or data |
| Prefer raw alerts | Disable filter in config |

## Documentation Files

1. **MARKET_SENTIMENT_FEATURES.md** ← You are here!
2. **MARKET_SENTIMENT_GUIDE.md** - Detailed guide with examples
3. **Code comments** - In-line documentation

---

**Ready to use!** Run scanner and watch for market sentiment analysis in logs. 🚀
