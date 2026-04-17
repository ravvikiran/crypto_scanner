# Market Sentiment Analysis - Implementation Guide

## Overview

Your crypto scanner now includes **AI-powered market sentiment analysis**! This feature analyzes the overall cryptocurrency market conditions alongside technical breakout detection to provide smarter, contextualized trading alerts.

## What Was Added

### 1. **Market Sentiment Engine** (`engines/market_sentiment_engine.py`)

A comprehensive market analysis system that evaluates:

#### Sentiment Metrics:
- **Bitcoin Trend**: Direction of BTC (Bullish, Bearish, Neutral)
- **Market Breadth**: % of gainers vs losers across the market
- **Market Strength**: Overall strength of market movements (0-100 scale)
- **Altcoin Strength**: How well altcoins are performing relative to BTC
- **BTC Dominance**: Whether BTC is increasing or decreasing dominance
- **Volatility Level**: Low, Normal, or High
- **Volume Patterns**: Average 24h volume change across market

#### Sentiment Levels (0-100 score):
- **VERY_BULLISH** (75-100): Excellent conditions for long trades
- **BULLISH** (60-74): Good conditions for breakout longs
- **NEUTRAL** (40-59): Consolidation, be selective
- **BEARISH** (25-39): Caution advised, shorts favorable
- **VERY_BEARISH** (0-24): High risk, market struggling

### 2. **AI Market Sentiment Analyzer** (`ai/market_sentiment_analyzer.py`)

Enhances sentiment analysis with AI insights:

- **AI Market Insights**: Uses LLM to provide deeper market interpretation
- **Risk Assessment**: AI evaluates current risk level (low/medium/high)
- **Trading Recommendations**: AI suggests focus on longs, shorts, or caution
- **Sentiment Monitoring**: Tracks sentiment shifts and detects significant changes

### 3. **Intelligent Alert Filtering**

The alert system now intelligently filters signals based on market sentiment:

#### Filtering Logic:
- **LONG signals** → Only alert if market is BULLISH or VERY_BULLISH
- **SHORT signals** → Only alert if market is BEARISH or VERY_BEARISH
- **NEUTRAL sentiment** → Only send very high-confidence signals (75+)
- **Overrides**: Extreme signals can still trigger in neutral conditions

### 4. **Enhanced Alert Messages**

Alerts now include market context:

```
🟢 LONG - BTC/USDT
Entry: $45,000 - $45,500
Stop: $44,500
Target 1: $46,000
Confidence: 8.2/10

📊 Market Context
Sentiment: VERY_BULLISH (82/100)
Gainers: 78% | Losers: 22%
Market Strength: 78/100
Altcoin Strength: 72/100
Volatility: NORMAL
BTC Trend: BULLISH

ℹ️ Strong market breadth (78% gainers) | BTC trending higher | Altseason indicators
```

## How It Works

### Scan Flow Integration

```
1. Get BTC Trend & Market Regime
   ↓
2. Fetch Top Coins Data
   ↓
3. ✨ NEW: Analyze Market Sentiment
   ├─ Calculate sentiment metrics
   ├─ Get AI market insights
   └─ Check for sentiment shifts
   ↓
4. Run Technical Strategies (Breakouts, etc.)
   ↓
5. Score & Filter Signals
   ↓
6. ✨ NEW: Filter by Market Sentiment
   ├─ Match signal direction with sentiment
   └─ Keep only favorable trades
   ↓
7. Generate Alerts with Sentiment Context
```

### Sentiment Calculation

The sentiment score is a weighted combination of:

| Factor | Weight | Impact |
|--------|--------|--------|
| Market Breadth | 40% | % of gainers |
| Market Strength | 30% | Overall price movement |
| Bitcoin Trend | 20% | BTC direction & strength |
| BTC Dominance | 5% | Change in BTC vs alts |
| Volatility | 5% | Market turbulence |

## Examples

### Scenario 1: Bearish Market, LONG Signal

**Without Sentiment Filter**: Alert sent ❌ Wrong direction
**With Sentiment Filter**: Alert blocked ✅ Signal ignored safely

Market: BEARISH (35/100)
Signal: LONG on ETH
Result: **BLOCKED** - LONG not favorable in bearish market

### Scenario 2: Bullish Market, Breakout Signal

**Before**: Maybe I missed this because I wasn't watching
**After**: **ALERT! Breakout detected + Market is BULLISH**

```
Market: VERY_BULLISH (82/100)
Signal: LONG BTC Breakout at $45,000
Result: ✅ SENT - Perfect alignment!
```

### Scenario 3: Multiple Coins, Selective Alerts

**Before**: 5 coins breaking out, which ones matter?
**After**: Alerts prioritize coins aligned with sentiment

```
BTC Breakout (LONG) + BULLISH Market → ✅ SENT
ETH Pullback (SHORT) + BULLISH Market → ⛔ BLOCKED
SOL Breakout (LONG) + BULLISH Market → ✅ SENT
XRP Breakdown (SHORT) + BULLISH Market → ⛔ BLOCKED
```

## Configuration

### Enable/Disable Market Sentiment Filtering

In your `config.yaml`:

```yaml
alerts:
  use_market_sentiment_filter: true  # Set to false to disable
  confidence_threshold: 6.0
```

### AI Settings for Sentiment Analysis

```yaml
ai:
  enabled: true
  ai_provider: "openai"  # or "gemini", "ollama", etc.
  ai_temperature: 0.3    # Lower = more focused analysis
  ai_max_tokens: 500
```

## Console Output Example

```
============================================================
📈 Analyzing Market Sentiment...
============================================================
Market Sentiment: VERY_BULLISH
  Score: 82.3/100
  Gainers: 78.5% | Losers: 21.5%
  Market Strength: 78.2/100
  Altcoin Strength: 72.1/100
  Volatility: NORMAL
  Reason: Strong market breadth (78% gainers) | Altseason indicators | BTC in uptrend

🤖 AI Market Insight: Strong bullish momentum with healthy altcoin participation. Breakout trades highly favorable...
   Risk Level: LOW
   Recommendation: Focus on LONG breakouts
```

## Benefits

### ✅ Fewer False Alerts
- Reduces noise by filtering trades against market sentiment
- Blocks shorts during strong uptrends
- Blocks longs during strong downtrends

### ✅ Better Context
- Each alert shows you the market condition
- Understand WHY the signal is happening
- Make informed decisions on trade size

### ✅ AI-Powered Insights
- Market analysis from AI perspective
- Risk assessment for current conditions
- Recommendations for trade direction

### ✅ Sentiment Shifts Detection
- Alerts you to significant market changes
- Helps you adapt your strategy in real-time
- Shows you when momentum is breaking down

## FAQ

### Q: Why wasn't my coin alert sent?
**A**: Could be one of these reasons:
1. Sentiment not favorable (e.g., LONG signal in BEARISH market)
2. Signal confidence too low in NEUTRAL market
3. Already on cooldown from previous signal

Check logs: `Log filter signal {coin} - not favorable for {sentiment}`

### Q: Can I get more aggressive with alerts?
**A**: Yes! Two options:
1. **Disable sentiment filter**: Set `use_market_sentiment_filter: false`
2. **Lower confidence threshold**: Reduce `confidence_threshold` in config

### Q: How is sentiment different from market regime?
- **Market Regime**: Trading condition (TRENDING/RANGING/HIGH_VOL)
- **Sentiment**: Market psychology (BULLISH/BEARISH/NEUTRAL)

Both are useful - regime for strategy selection, sentiment for signal filtering.

### Q: What if I disagree with AI sentiment?
- Override by disabling sentiment filter
- Adjust weights in `MarketSentimentEngine._calculate_sentiment_score()`
- Trust your trading judgment - this is assistance, not gospel

## Advanced Customization

### Change Sentiment Filter Thresholds

In `alert_manager.py`, modify `_filter_signals_by_sentiment()`:

```python
# Currently: LONG keeps only if BULLISH or VERY_BULLISH
# Change to also include NEUTRAL:
if is_long and market_sentiment.market_strength > 45:
    is_favorable = True
```

### Adjust Sentiment Score Weights

In `market_sentiment_engine.py`, modify `_calculate_sentiment_score()`:

```python
# Increase BTC trend weight
score += 15  # Was 10

# Decrease altcoin impact
if altcoin_strength > 60:
    score += 3  # Was 5
```

### Custom AI Analysis

Extend `AIMarketSentimentAnalyzer` to add your own analysis:

```python
async def custom_analysis(self, sentiment_score):
    # Your custom logic here
    pass
```

## Troubleshooting

### Market Sentiment Analysis Failing

**Problem**: "Market sentiment analysis failed"
**Solution**: 
- Check if AI provider is configured
- Verify you have at least 50 coins fetched
- Check logs for specific error

### No Alerts Despite Signals

**Problem**: Signals generated but no alerts
**Solution**:
- Check sentiment filter is not blocking them
- View filtered signals in logs
- Temporarily disable sentiment filter to test

### AI Not Providing Insights

**Problem**: "AI sentiment analysis failed"
**Solution**:
- Ensure AI provider (OpenAI/Gemini) is configured
- Check API key and rate limits
- Try with fewer coins (too much data might exceed token limit)

## Next Steps

1. **Monitor your alerts** - Watch the sentiment-filtered alerts for a few days
2. **Tune the thresholds** - Adjust based on your trading style
3. **Experiment with disabling** - Compare results with/without filter
4. **Customize the weights** - Adjust sentiment calculation if desired

---

## Files Modified/Created

- ✅ `engines/market_sentiment_engine.py` - NEW
- ✅ `ai/market_sentiment_analyzer.py` - NEW
- ✅ `engines/__init__.py` - Updated exports
- ✅ `scanner.py` - Integrated sentiment analysis
- ✅ `alerts/alert_manager.py` - Added sentiment filtering

Enjoy smarter, sentiment-aware trading alerts! 🚀
