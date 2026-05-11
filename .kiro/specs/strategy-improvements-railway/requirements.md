# Requirements Document

## Introduction

This feature implements 8 strategy improvements to the existing crypto momentum scanner plus Railway deployment configuration. The improvements address over-filtering, static symbol lists, limited entry types, slow warmup, missing volatility gates, lack of trailing stops, no status messages, and missing extended targets. Railway deployment enables cloud hosting as a worker process.

## Glossary

- **Scanner**: The crypto momentum scanning engine (`core/momentum_scanner.py`) that orchestrates the event-driven pipeline
- **BTC_Regime_Filter**: The market regime filter (`filters/market_regime_filter.py`) that gates LONG setups based on BTC conditions
- **Trend_Filter**: The per-coin 4H trend assessment (`filters/trend_filter.py`) that evaluates trend conditions before setup detection
- **Setup_Detector**: The module (`detectors/setup_detector.py`) that identifies Compression Breakout and Pullback Continuation patterns
- **Universe_Manager**: A new component responsible for dynamically selecting and managing the set of monitored trading pairs
- **Volatility_Gate**: A new pre-detection filter that validates per-coin ATR-based volatility is within acceptable bounds
- **Trailing_Stop_Monitor**: A new component that tracks open positions and adjusts stop-loss levels based on price progression toward targets
- **Status_Reporter**: A new component that sends periodic status and summary messages via Telegram
- **Scoring_Engine**: The deterministic composite scoring module (`scoring/scoring_engine.py`)
- **Alert_Manager**: The alert deduplication and Telegram delivery module (`alerts/momentum_alert_manager.py`)
- **Journal_Store**: The signal and rejection persistence module (`storage/journal_store.py`)
- **ATR14**: 14-period Average True Range indicator calculated on the 1H timeframe
- **EMA20**: 20-period Exponential Moving Average
- **RVOL**: Relative Volume ratio (current volume divided by 20-period volume moving average)
- **R**: Risk unit defined as the distance from entry price to stop-loss price
- **T1**: Target 1, equal to entry price plus 1R
- **T2**: Target 2, equal to entry price plus 2R
- **T3**: Target 3, equal to entry price plus 5R
- **USDT_Pair**: A Binance trading pair denominated in USDT (e.g., BTCUSDT, ETHUSDT)
- **Railway**: A cloud deployment platform that runs containerized applications
- **Procfile**: A Railway/Heroku-style file declaring process types for deployment

## Requirements

### Requirement 1: Relaxed BTC Regime Filter

**User Story:** As a trader, I want the BTC regime filter to only block signals when BTC is actively crashing, so that I receive signals during sideways and mildly bearish markets.

#### Acceptance Criteria

1. WHEN BTC price has declined more than 3% across the last 4 consecutive 1H candles, THE BTC_Regime_Filter SHALL block all new LONG setup detection
2. WHEN BTC price has NOT declined more than 3% across the last 4 consecutive 1H candles, THE BTC_Regime_Filter SHALL allow LONG setup detection to proceed
3. THE BTC_Regime_Filter SHALL calculate the decline as the percentage change from the open of the oldest of the 4 candles to the close of the most recent candle
4. THE Scoring_Engine SHALL use the existing 5-condition regime evaluation (trend, momentum, direction, volatility, breadth) as the market_alignment scoring component with a weight of 10%
5. WHEN all 5 existing regime conditions are bullish, THE Scoring_Engine SHALL assign a market_alignment score of 100
6. WHEN fewer than 5 existing regime conditions are bullish, THE Scoring_Engine SHALL assign a market_alignment score proportional to the number of bullish conditions (each condition contributing 20 points)

### Requirement 2: Dynamic Universe Selection

**User Story:** As a trader, I want the scanner to automatically track the most actively traded coins, so that I receive signals on liquid, high-volume pairs without manual configuration.

#### Acceptance Criteria

1. WHEN the Scanner starts, THE Universe_Manager SHALL fetch the top 100 USDT trading pairs by 24-hour volume from the Binance REST API
2. THE Universe_Manager SHALL refresh the universe list every 60 minutes by re-fetching the top 100 USDT pairs by 24-hour volume
3. THE Universe_Manager SHALL exclude pairs with 24-hour USD volume below 50 million
4. THE Universe_Manager SHALL exclude pairs with a current price below 0.10 USD
5. THE Universe_Manager SHALL always include BTCUSDT in the active universe regardless of volume or price filters
6. WHEN the universe list changes, THE Scanner SHALL subscribe to WebSocket streams for newly added symbols within 30 seconds
7. WHEN the universe list changes, THE Scanner SHALL unsubscribe from WebSocket streams for removed symbols within 30 seconds
8. IF the Binance REST API request fails, THEN THE Universe_Manager SHALL retain the previous universe list and retry after 5 minutes
9. THE Universe_Manager SHALL log each universe refresh with the count of added and removed symbols

### Requirement 3: Simple Momentum Breakout Entry

**User Story:** As a trader, I want a simple momentum-based entry signal in addition to the complex pattern-based entries, so that I can capture strong directional moves that do not form compression or pullback patterns.

#### Acceptance Criteria

1. THE Setup_Detector SHALL support a third setup type named MOMENTUM_BREAKOUT
2. WHEN the 1H close price is above EMA20 on the 1H timeframe AND the last 3 consecutive 1H candles each have a higher high than the previous candle AND the current 1H candle volume exceeds 2.5 times the 20-period volume moving average, THE Setup_Detector SHALL emit a MOMENTUM_BREAKOUT signal
3. WHEN a MOMENTUM_BREAKOUT signal is emitted, THE Setup_Detector SHALL set the entry price to the current 1H candle close price
4. WHEN a MOMENTUM_BREAKOUT signal is emitted, THE Setup_Detector SHALL calculate the stop-loss as the tighter (higher) of: the swing low of the last 3 candles multiplied by 0.995, or the entry price minus 1.5 times ATR14
5. WHEN a MOMENTUM_BREAKOUT signal is emitted, THE Setup_Detector SHALL enforce a minimum stop-loss distance of 0.8% from entry price
6. WHEN a MOMENTUM_BREAKOUT signal is emitted, THE Setup_Detector SHALL enforce a maximum stop-loss distance of 2.5% from entry price
7. IF the calculated stop-loss distance falls outside the 0.8% to 2.5% range, THEN THE Setup_Detector SHALL clamp the stop-loss to the nearest boundary of that range

### Requirement 4: Relaxed Trend Filter for Momentum Entries

**User Story:** As a trader, I want momentum entries to require only a simple trend confirmation, so that signals can fire much sooner after scanner startup without waiting 33 days for warmup data.

#### Acceptance Criteria

1. WHEN evaluating a MOMENTUM_BREAKOUT setup, THE Trend_Filter SHALL require only that the 1H close price is above EMA20 on the 1H timeframe
2. WHEN evaluating a MOMENTUM_BREAKOUT setup, THE Trend_Filter SHALL NOT require any 4H timeframe conditions
3. WHEN evaluating a COMPRESSION_BREAKOUT or PULLBACK_CONTINUATION setup, THE Trend_Filter SHALL require all 3 existing 4H conditions (price above EMA200, EMA20 above EMA50, EMA200 rising)
4. WHEN evaluating a COMPRESSION_BREAKOUT or PULLBACK_CONTINUATION setup, THE Trend_Filter SHALL require a minimum of 50 candles on the 4H timeframe instead of 200
5. IF fewer than 50 candles are available on the 4H timeframe for a COMPRESSION_BREAKOUT or PULLBACK_CONTINUATION evaluation, THEN THE Trend_Filter SHALL reject the coin with an insufficient data status

### Requirement 5: Per-Coin ATR Volatility Gate

**User Story:** As a trader, I want coins with abnormally low or high volatility to be filtered out before setup detection, so that I avoid dead coins and scam pump coins.

#### Acceptance Criteria

1. WHEN a coin is evaluated for setup detection, THE Volatility_Gate SHALL calculate ATR14 divided by the current price as a percentage
2. WHEN the ATR14-to-price ratio is below 1.5%, THE Volatility_Gate SHALL reject the coin from setup detection
3. WHEN the ATR14-to-price ratio is above 8.0%, THE Volatility_Gate SHALL reject the coin from setup detection
4. WHEN the ATR14-to-price ratio is between 1.5% and 8.0% inclusive, THE Volatility_Gate SHALL allow the coin to proceed to setup detection
5. WHEN a coin is rejected by the Volatility_Gate, THE Journal_Store SHALL log the rejection with the symbol, ATR14 value, current price, and calculated ratio

### Requirement 6: Trailing Stop Monitoring

**User Story:** As a trader, I want the scanner to monitor my open positions and automatically trail the stop-loss as price progresses toward targets, so that I can lock in profits without manual monitoring.

#### Acceptance Criteria

1. WHEN a signal is emitted, THE Trailing_Stop_Monitor SHALL begin monitoring the coin price on each closed 15-minute candle
2. WHEN the monitored price reaches T1, THE Trailing_Stop_Monitor SHALL move the stop-loss to the entry price (breakeven)
3. WHEN the monitored price reaches T2, THE Trailing_Stop_Monitor SHALL begin trailing the stop-loss at 1% below the highest price reached since T2 was hit
4. WHILE trailing after T2, THE Trailing_Stop_Monitor SHALL update the trailing stop on each 15-minute candle close to 1% below the highest close observed since T2 was hit
5. WHEN the stop-loss level is moved (to breakeven or to a new trailing level), THE Alert_Manager SHALL send a Telegram message indicating the new stop-loss level for the symbol
6. WHEN the trailing stop-loss is hit (15-minute candle closes below the trailing stop), THE Trailing_Stop_Monitor SHALL record the exit price and calculate the actual risk-reward achieved
7. WHEN an exit is recorded, THE Journal_Store SHALL update the signal outcome with the exit price, actual risk-reward, and duration in minutes
8. IF no price data is received for a monitored coin for 30 minutes, THEN THE Trailing_Stop_Monitor SHALL log a warning and continue monitoring on the next available candle

### Requirement 7: Periodic Status Messages

**User Story:** As a trader, I want to receive periodic status updates from the scanner, so that I know the system is running and can review daily performance without checking logs.

#### Acceptance Criteria

1. WHEN the Scanner starts, THE Status_Reporter SHALL send a Telegram message containing "🟢 Scanner started" and the count of monitored symbols
2. THE Status_Reporter SHALL send a daily summary Telegram message at 00:00 UTC containing: total signals emitted today, win rate percentage, and the best performing symbol of the day
3. WHEN no signals have been emitted for 4 or more consecutive hours, THE Status_Reporter SHALL send a Telegram message containing "✅ Scanner active. No setups found." and the current BTC regime status
4. THE Status_Reporter SHALL NOT send the "no setups" message more than once per 4-hour window
5. IF the Telegram delivery fails for a status message, THEN THE Status_Reporter SHALL retry up to 2 times with 5-second intervals between retries

### Requirement 8: T3 Target (5R)

**User Story:** As a trader, I want a third target level at 5R for letting a portion of the position run, so that I can capture extended moves while taking profits at T1 and T2.

#### Acceptance Criteria

1. WHEN a setup signal is emitted, THE Setup_Detector SHALL calculate T3 as entry price plus 5 times the risk (5R)
2. THE Alert_Manager SHALL include T3 in the Telegram alert message alongside T1 and T2
3. THE Alert_Manager SHALL include the position sizing recommendation "Take 40% at T1, 40% at T2, let 20% run to T3" in the Telegram alert message
4. THE Journal_Store SHALL persist the T3 value alongside T1 and T2 for each logged signal
5. WHEN the monitored price reaches T3, THE Trailing_Stop_Monitor SHALL record the exit as a win with the actual risk-reward achieved

### Requirement 9: Railway Deployment Configuration

**User Story:** As a developer, I want the scanner to be deployable on Railway as a worker process, so that it runs continuously in the cloud without requiring a dedicated server.

#### Acceptance Criteria

1. THE Scanner SHALL include a Procfile declaring a worker process type that runs the main_momentum.py entry point
2. THE Scanner SHALL include a railway.toml file specifying the build configuration and worker process settings
3. THE Scanner SHALL include a nixpacks.toml file specifying Python as the build provider if required by Railway
4. THE Scanner SHALL read all configuration values from environment variables with no hard-coded secrets
5. WHEN the PORT environment variable is set, THE Scanner SHALL start a minimal HTTP health check endpoint on that port responding with HTTP 200 and a JSON body containing uptime and status
6. WHEN a SIGTERM signal is received, THE Scanner SHALL complete graceful shutdown within 10 seconds including state persistence
7. THE Scanner SHALL include a .dockerignore file excluding data directories, log files, virtual environments, and git metadata from the build context
8. THE Scanner SHALL include ccxt in requirements.txt for Binance REST API calls used by the Universe_Manager
9. IF the health check endpoint receives a request, THEN THE Scanner SHALL respond within 1 second
