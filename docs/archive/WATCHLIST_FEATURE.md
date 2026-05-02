# Watchlist Feature

## Overview
The Watchlist feature allows users to add stocks/crypto symbols to monitor with real-time price updates, technical analysis, and AI-powered buy/sell/hold recommendations.

## Features

### Core Functionality
- **Add Stocks**: Add single or multiple stock symbols (comma-separated)
- **Real-time Quotes**: Current price, daily change, OHLC data
- **Technical Analysis**: RSI, MACD, Moving Averages
- **AI Suggestions**: Buy/Hold/Sell recommendations with confidence scores
- **Quick Add**: Pre-configured lists for Top Tech, Top Crypto, Major ETFs
- **Persistent Storage**: Watchlist saved in browser localStorage
- **Detailed Analysis**: Modal with charts and technical indicators per stock

### Suggestion Ratings
- **STRONG BUY**: All indicators bullish, high confidence (>75%)
- **BUY**: Positive momentum, good entry opportunity
- **HOLD**: Consolidating or mixed signals
- **SELL**: Downtrend forming, consider exiting
- **STRONG SELL**: Major breakdown, high risk

## API Endpoints

### 1. Get Stock Quote
```
GET /api/watchlist/quote?symbol={SYMBOL}
```
Returns: Current price, change, volume, OHLC data

### 2. Get Technical Analysis
```
GET /api/watchlist/analysis?symbol={SYMBOL}
```
Returns: Suggestion, confidence, RSI, MACD, MAs, support/resistance

### 3. Batch Update Watchlist
```
GET /api/watchlist/all?symbols={SYM1,SYM2,SYM3}
```
Returns: Quotes and analysis for all symbols

### 4. Watchlist Page
```
GET /watchlist
```
Renders the watchlist UI page

## Usage

### Adding Stocks
1. Navigate to the Watchlist tab
2. Enter symbol(s) in the input field (e.g., "AAPL, GOOGL, TSLA")
3. Click "Add to Watchlist"
4. Use Quick Add buttons for pre-configured lists

### Removing Stocks
- Click the trash icon next to any stock to remove it
- Use "Clear All" to empty the entire watchlist

### Viewing Details
- Click the chart icon to open detailed analysis modal
- Shows charts, technical indicators, support/resistance levels

### Refreshing Data
- Click "Refresh" button to update all prices and analysis
- Data updates every 30 seconds automatically (when page is open)

## Technical Indicators

### RSI (Relative Strength Index)
- Range: 0-100
- >70: Overbought (potential sell signal)
- <30: Oversold (potential buy signal)

### MACD (Moving Average Convergence Divergence)
- Shows momentum direction
- Positive: Bullish momentum
- Negative: Bearish momentum

### Moving Averages
- MA 20: Short-term trend
- MA 50: Medium-term trend  
- MA 200: Long-term trend
- Price above MAs: Bullish
- Price below MAs: Bearish

## Configuration

### LocalStorage Key
- `crypto_watchlist`: Stores the watchlist array

### Chart Colors
- Price up: Green (#198754)
- Price down: Red (#dc3545)
- Neutral: Blue (#0d6efd)

## Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- Requires JavaScript and localStorage enabled

## Future Enhancements
- Email/telegram alerts for price targets
- Custom technical indicator settings
- Historical chart data with multiple timeframes
- Integration with live trading APIs
- User-defined watchlists (multiple lists)
- Export watchlist to CSV
- Technical pattern recognition