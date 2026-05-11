# Requirements Document

## Introduction

The Crypto Momentum Scanner is a deterministic, rule-based, real-time momentum scanning engine designed to detect early-stage breakout and continuation setups across major crypto pairs. It uses websocket streaming for low-latency data ingestion, event-driven architecture for incremental signal detection, and a fixed scoring formula for ranking setups. The scanner is NOT an autonomous trader — it surfaces high-quality momentum setups for discretionary traders to act on. AI/LLM usage is strictly limited to post-signal formatting, journaling summaries, and analytics commentary. AI must never generate signals, approve/reject trades, modify thresholds, or alter strategy logic.

## Glossary

- **Scanner**: The core momentum scanning engine that processes market data and detects setups
- **Market_Regime_Filter**: The BTC-based global market condition filter that gates LONG setup detection
- **Trend_Filter**: The per-coin trend assessment module using EMA structure on the 4H timeframe
- **Relative_Strength_Engine**: The module that calculates coin performance relative to BTC
- **Setup_Detector**: The module that identifies Compression Breakout and Pullback Continuation patterns
- **Scoring_Engine**: The deterministic ranking module that produces a composite score for each setup
- **Alert_Manager**: The module responsible for deduplication, cooldown enforcement, and Telegram delivery
- **Journal_Store**: The persistence layer that logs all signals, rejections, scores, and outcomes
- **Data_Collector**: The websocket-based module that ingests real-time OHLCV, volume, open interest, and funding rate data
- **ATR**: Average True Range — a volatility indicator used for stop-loss calculation (14-period default)
- **EMA**: Exponential Moving Average — a trend-following indicator
- **RVOL**: Relative Volume — current volume divided by MA30 volume
- **OI**: Open Interest — total outstanding derivative contracts
- **OHLCV**: Open, High, Low, Close, Volume — standard candlestick data
- **RR**: Risk-to-Reward ratio — distance to target divided by distance to stop-loss
- **Compression_Breakout**: Setup A — tight consolidation followed by volume-driven breakout
- **Pullback_Continuation**: Setup B — trend pullback to EMA support followed by continuation
- **Cooldown**: Minimum time between duplicate alerts for the same coin and setup type

## Requirements

### Requirement 1: Websocket Data Ingestion

**User Story:** As a momentum trader, I want real-time streaming market data from crypto exchanges, so that the scanner detects setups with minimal latency.

#### Acceptance Criteria

1. WHEN the Scanner starts, THE Data_Collector SHALL establish a websocket connection to Binance for real-time OHLCV streaming within 10 seconds
2. WHERE Bybit websocket is configured, THE Data_Collector SHALL establish a secondary websocket connection to Bybit
3. WHERE OKX websocket is configured, THE Data_Collector SHALL establish a tertiary websocket connection to OKX
4. WHILE a websocket connection is active, THE Data_Collector SHALL receive and validate live OHLCV, volume, open interest, and funding rate data, discarding messages with zero volume or malformed fields before emission
5. IF a websocket connection drops, THEN THE Data_Collector SHALL attempt reconnection starting within 5 seconds using exponential backoff with an initial interval of 1 second, up to a maximum of 5 attempts
6. THE Data_Collector SHALL stream data for the 4H, 1H, and 15m timeframes
7. WHEN new candle data arrives via websocket, THE Data_Collector SHALL emit an event to downstream processing modules within 50ms
8. IF the initial websocket connection to Binance cannot be established within 10 seconds on startup, THEN THE Data_Collector SHALL log an error indicating connection failure and retry connection using the same exponential backoff strategy as criterion 5
9. IF all reconnection attempts are exhausted for an exchange, THEN THE Data_Collector SHALL emit a connection failure event to the Alert_Manager and cease reconnection attempts for that exchange until the next Scanner restart

### Requirement 2: Event-Driven Architecture

**User Story:** As a momentum trader, I want the scanner to process data incrementally on each new event rather than performing periodic full rescans, so that detection latency is minimized.

#### Acceptance Criteria

1. WHEN a new candle close event is received, THE Scanner SHALL trigger incremental processing for the affected coin and timeframe only
2. THE Scanner SHALL maintain stateful signal tracking for each monitored coin across the 4H, 1H, and 15m timeframes, including current trend state, active setup status, pending entry triggers, and last signal score
3. WHILE processing events, THE Scanner SHALL use async processing to handle up to 50 concurrent coin updates without blocking event ingestion
4. THE Scanner SHALL NOT perform periodic full rescans of all coins
5. WHEN a coin's trend state, setup status, or signal score changes as a result of incremental processing, THE Scanner SHALL propagate the update through the filter chain within 100ms
6. IF an event processing error occurs for a coin, THEN THE Scanner SHALL log the error, skip the affected coin for that event cycle, and continue processing remaining events without interruption
7. IF the inbound event rate exceeds processing capacity, THEN THE Scanner SHALL process the most recent event per coin and discard stale intermediate events

### Requirement 3: Market Regime Filter

**User Story:** As a momentum trader, I want the scanner to only surface LONG setups when BTC structure is bullish, so that I avoid trading against the macro trend.

#### Acceptance Criteria

1. THE Market_Regime_Filter SHALL evaluate BTC 4H structure by computing all five BTC conditions (trend, momentum, direction, volatility, breadth) and producing a composite bullish/not-bullish gate result
2. WHILE BTC price is above EMA200 on the 4H timeframe, THE Market_Regime_Filter SHALL mark the BTC trend condition as bullish
3. WHILE BTC EMA20 is above EMA50 on the 4H timeframe, THE Market_Regime_Filter SHALL mark the BTC momentum condition as bullish
4. WHILE the BTC EMA200 value on the current 4H candle is greater than the BTC EMA200 value 5 candles prior on the 4H timeframe, THE Market_Regime_Filter SHALL mark the BTC direction condition as bullish
5. WHILE BTC ATR(14) as a percentage of price is between 1.0% and 3.0% on the 4H timeframe, THE Market_Regime_Filter SHALL mark the BTC volatility condition as healthy
6. WHILE the percentage of coins in the scanned universe with a positive 24-hour price change exceeds 50%, THE Market_Regime_Filter SHALL mark the breadth condition as bullish
7. WHEN all five BTC conditions (trend, momentum, direction, volatility, breadth) are bullish, THE Market_Regime_Filter SHALL allow LONG setup detection to proceed
8. WHEN any of the five BTC conditions is not bullish, THE Market_Regime_Filter SHALL suppress all LONG setup alerts
9. IF BTC 4H candle data is unavailable or contains fewer than 200 candles, THEN THE Market_Regime_Filter SHALL suppress all LONG setup alerts and mark the regime status as indeterminate

### Requirement 4: Multi-Timeframe Trend Filter

**User Story:** As a momentum trader, I want each coin evaluated on a 4H trend bias before setup detection, so that I only see setups aligned with the higher timeframe trend.

#### Acceptance Criteria

1. WHILE a coin's most recent completed 4H candle close price is above the EMA200 value on the 4H timeframe, THE Trend_Filter SHALL mark the coin's price position as bullish
2. WHILE a coin's EMA20 is above EMA50 on the 4H timeframe, THE Trend_Filter SHALL mark the coin's momentum structure as bullish
3. WHILE a coin's EMA200 value on the 4H timeframe is higher than its EMA200 value from 5 candles prior, THE Trend_Filter SHALL mark the coin's trend direction as bullish
4. WHEN all three trend conditions are bullish for a coin, THE Trend_Filter SHALL pass the coin to the Setup_Detector
5. WHEN any trend condition is not bullish for a coin, THE Trend_Filter SHALL reject the coin from setup detection
6. THE Trend_Filter SHALL NOT require EMA50 above EMA100 above EMA200 alignment
7. IF a coin has fewer than 200 completed 4H candles available, THEN THE Trend_Filter SHALL reject the coin from setup detection with a status indicating insufficient data

### Requirement 5: Relative Strength vs BTC

**User Story:** As a momentum trader, I want to see which coins are outperforming BTC, so that I focus on the strongest momentum candidates.

#### Acceptance Criteria

1. THE Relative_Strength_Engine SHALL calculate rolling 4-hour percentage price change of each coin minus BTC percentage price change over the same rolling 4-hour window
2. THE Relative_Strength_Engine SHALL calculate rolling 24-hour percentage price change of each coin minus BTC percentage price change over the same rolling 24-hour window
3. THE Relative_Strength_Engine SHALL calculate momentum acceleration as the difference between the current 4-hour relative performance and the previous 4-hour relative performance for each coin
4. WHEN ranking setups, THE Scoring_Engine SHALL weight relative strength at 30% of the composite score
5. THE Relative_Strength_Engine SHALL normalize all relative strength values to a 0-100 scale by ranking all monitored coins and assigning percentile scores based on their position in the ranked distribution
6. IF BTC price data is unavailable or stale for more than 60 seconds, THEN THE Relative_Strength_Engine SHALL hold the last valid relative strength scores and flag them as stale

### Requirement 6: Compression Breakout Detection (Setup A)

**User Story:** As a momentum trader, I want the scanner to detect tight consolidation patterns that break out with volume expansion, so that I catch early-stage breakout moves.

#### Acceptance Criteria

1. WHEN 3 to 8 consecutive candles on the 1H timeframe each have an ATR value less than 75% of the ATR14 measured at the start of the sequence, THE Setup_Detector SHALL identify a compression zone defined by the highest high and lowest low of those candles
2. WHILE a compression zone is active, THE Setup_Detector SHALL monitor for decreasing sell pressure, defined as each successive candle within the zone closing in the upper 50% of its range or showing lower sell-side volume compared to the prior candle
3. WHEN a breakout candle closes above the compression zone high with volume greater than 1.5 times the 30-period moving average volume on the 1H timeframe, THE Setup_Detector SHALL generate a Compression_Breakout signal
4. IF a breakout candle does not close in the upper 33% of its range, THEN THE Setup_Detector SHALL discard the Compression_Breakout signal as invalid
5. WHEN a valid Compression_Breakout is detected, THE Setup_Detector SHALL set the entry price at the breakout candle high
6. WHEN a valid Compression_Breakout is detected, THE Setup_Detector SHALL set the stop-loss at the lower of the compression zone low or Entry minus 1.2 times ATR14
7. IF no breakout occurs within 12 candles after the compression zone is identified, THEN THE Setup_Detector SHALL expire the compression zone and cease monitoring it

### Requirement 7: Pullback Continuation Detection (Setup B)

**User Story:** As a momentum trader, I want the scanner to detect pullbacks to moving average support in established trends, so that I enter continuation moves at favorable prices.

#### Acceptance Criteria

1. WHILE a coin has an established uptrend on the 4H timeframe, THE Setup_Detector SHALL monitor for pullbacks toward EMA20 or EMA50 on the 1H timeframe
2. WHEN price pulls back to within 0.5% of EMA20 or EMA50 on the 1H timeframe and a bullish reclaim candle forms that closes above the EMA with its close in the upper 50% of the candle range, THE Setup_Detector SHALL identify a pullback candidate
3. WHEN the trigger candle (the bullish reclaim candle from criterion 2) shows volume greater than 1.5 times MA30 volume, THE Setup_Detector SHALL generate a Pullback_Continuation signal
4. WHEN a valid Pullback_Continuation is detected, THE Setup_Detector SHALL set the entry price at the trigger candle high
5. WHEN a valid Pullback_Continuation is detected, THE Setup_Detector SHALL set the stop-loss at the lower of the trigger candle low or Entry minus 1.2 times ATR14
6. IF price closes below the relevant EMA (EMA20 or EMA50) by more than 1.0% on the 1H timeframe while a pullback candidate is pending, THEN THE Setup_Detector SHALL invalidate the pullback candidate and discard the setup

### Requirement 8: Entry Trigger on 15m Timeframe

**User Story:** As a momentum trader, I want the final entry trigger confirmed on the 15m timeframe, so that I get precise entry timing within the higher timeframe setup.

#### Acceptance Criteria

1. WHEN a setup is detected on the 1H timeframe, THE Setup_Detector SHALL monitor the 15m timeframe for entry confirmation starting from the next 15m candle close
2. WHEN the 15m candle closes above the defined entry price with volume greater than 1.5 times MA30 volume, THE Setup_Detector SHALL confirm the entry trigger
3. IF the 15m entry trigger is not confirmed within 4 candles (1 hour), THEN THE Setup_Detector SHALL expire the pending setup and log the expiry with coin symbol, setup type, and reason to the Journal_Store
4. IF the 15m candle closes above the defined entry price but volume is less than or equal to 1.5 times MA30 volume, THEN THE Setup_Detector SHALL reject the candle as a valid trigger and continue monitoring within the remaining confirmation window
5. IF the 1H setup is invalidated (price closes below stop-loss level or trend condition turns not bullish) while awaiting 15m confirmation, THEN THE Setup_Detector SHALL cancel the pending entry trigger and log the cancellation to the Journal_Store

### Requirement 9: ATR-Based Risk Management

**User Story:** As a momentum trader, I want stop-losses calculated using ATR so that risk is calibrated to current volatility conditions.

#### Acceptance Criteria

1. THE Scanner SHALL calculate ATR using a 14-period lookback on the setup timeframe (1H)
2. WHEN calculating a stop-loss, THE Scanner SHALL compute ATR stop as Entry minus 1.2 times ATR14
3. WHEN both a structure stop and an ATR stop are available, THE Scanner SHALL use the safer (wider) of the two values as the final stop-loss
4. THE Scanner SHALL calculate minimum risk-reward ratio as distance from entry to Target1 divided by distance from entry to stop-loss
5. WHEN the calculated risk-reward ratio is below 2.0, THE Scanner SHALL reject the setup and log the rejection with the calculated RR value to the Journal_Store

### Requirement 10: Target Management

**User Story:** As a momentum trader, I want dynamic target management without fixed take-profit levels, so that I can ride strong momentum moves.

#### Acceptance Criteria

1. THE Scanner SHALL NOT set fixed auto-exit take-profit orders; Target1 and Target2 are reference levels for discretionary decision-making only
2. THE Scanner SHALL calculate Target1 as entry price plus 1R (where 1R equals the distance from entry to stop-loss)
3. THE Scanner SHALL recommend a 50% position exit at Target1 (1R) in the alert
4. THE Scanner SHALL recommend an EMA20 trailing stop on the 1H timeframe for the remaining 50% position after Target1 is reached
5. WHEN the calculated risk-reward ratio is 2.0 or greater, THE Scanner SHALL include Target2 at 2R distance from entry in the alert
6. IF Target1 is not reached and the stop-loss is hit, THEN THE Scanner SHALL not include any partial exit recommendation in the outcome log

### Requirement 11: Open Interest and Funding Analysis

**User Story:** As a momentum trader, I want open interest and funding rate context included in setup evaluation, so that I avoid overcrowded trades.

#### Acceptance Criteria

1. WHEN evaluating a setup, THE Scanner SHALL check that open interest has increased by at least 5% over the previous 4 hours for the coin
2. WHEN evaluating a setup, THE Scanner SHALL verify funding rate is not at extreme levels (above 0.1% or below -0.1% per 8 hours)
3. IF funding rate is extreme for a coin, THEN THE Scanner SHALL label the setup as "overcrowded" in the output and reduce its composite score by 20%
4. IF open interest has declined by more than 5% over the previous 4 hours while price has increased by more than 1% over the same period, THEN THE Scanner SHALL label the setup as "weak OI participation" in the output and reduce its composite score by 15%
5. IF open interest or funding rate data is unavailable for a coin, THEN THE Scanner SHALL proceed with setup evaluation without applying OI or funding adjustments and include a "data unavailable" indicator in the output

### Requirement 12: Deterministic Scoring and Ranking

**User Story:** As a momentum trader, I want setups ranked by a fixed, transparent formula so that the best opportunities surface consistently.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL calculate composite score as: (relative_strength * 0.30) + (relative_volume * 0.25) + (breakout_quality * 0.20) + (trend_quality * 0.15) + (market_alignment * 0.10), rounded to two decimal places
2. THE Scoring_Engine SHALL normalize all input values to a 0-100 scale using min-max normalization across the current set of valid setups, where the lowest observed value maps to 0 and the highest maps to 100
3. THE Scoring_Engine SHALL rank all valid setups by composite score in descending order, where a valid setup is one that has passed all upstream filter criteria and has non-null values for all five scoring inputs
4. IF two or more setups have an identical composite score, THEN THE Scoring_Engine SHALL break the tie by ranking the setup with the higher relative_volume value first
5. THE Scoring_Engine SHALL return the top 5 setups from the ranked list, or all valid setups if fewer than 5 exist
6. THE Scoring_Engine SHALL NOT use AI, machine learning, or self-modifying logic to adjust weights or thresholds

### Requirement 13: Breakout Quality Scoring

**User Story:** As a momentum trader, I want breakout quality assessed by measurable candle characteristics, so that I can distinguish strong breakouts from weak ones.

#### Acceptance Criteria

1. WHEN scoring a breakout candle, THE Scoring_Engine SHALL calculate body ratio as the absolute difference between close and open divided by the total candle range (high minus low), and SHALL assign a sub-score of 20 points when body ratio is at or above 75%, 15 points when at or above 60%, 10 points when at or above 45%, and 5 points otherwise
2. WHEN scoring a breakout candle, THE Scoring_Engine SHALL calculate close position ratio as (close minus low) divided by (high minus low), and SHALL assign a sub-score of 20 points when close position ratio is at or above 85%, 15 points when at or above 70%, 10 points when at or above 50%, and 5 points otherwise
3. WHEN scoring a breakout candle, THE Scoring_Engine SHALL calculate range expansion ratio as the breakout candle range (high minus low) divided by the average range of candles within the compression zone, and SHALL assign a sub-score of 20 points when range expansion ratio is at or above 2.0, 15 points when at or above 1.5, 10 points when at or above 1.2, and 5 points otherwise
4. WHEN scoring a breakout candle, THE Scoring_Engine SHALL calculate momentum acceleration as the percentage price change of the breakout candle (close minus open divided by open) minus the average percentage price change of the preceding 3 candles, and SHALL assign a sub-score of 20 points when momentum acceleration is at or above 2.0%, 15 points when at or above 1.0%, 10 points when at or above 0.5%, and 5 points otherwise
5. WHEN scoring a breakout candle, THE Scoring_Engine SHALL calculate relative volume (RVOL) as breakout candle volume divided by MA30 volume, and SHALL assign a sub-score of 20 points when RVOL is at or above 2.5, 15 points when at or above 2.0, 10 points when at or above 1.5, and 5 points otherwise
6. THE Scoring_Engine SHALL calculate the breakout_quality score as the sum of the five sub-scores (body ratio, close position ratio, range expansion, momentum acceleration, and relative volume), producing a value from 0 to 100
7. IF the breakout candle range (high minus low) is zero, THEN THE Scoring_Engine SHALL assign a breakout_quality score of 0

### Requirement 14: Relative Volume Calculation

**User Story:** As a momentum trader, I want relative volume calculated against a 30-period moving average, so that I can identify abnormal volume expansion.

#### Acceptance Criteria

1. THE Scanner SHALL calculate relative volume as current candle volume divided by the 30-period simple moving average of volume on the same timeframe as the setup detection (1H)
2. WHEN relative volume exceeds 1.5, THE Scanner SHALL classify the volume condition as expanded
3. THE Scoring_Engine SHALL weight relative volume at 25% of the composite score, normalizing the raw RVOL value to a 0-100 scale where RVOL of 1.0 or below maps to 0 and RVOL of 3.0 or above maps to 100, with linear interpolation between
4. WHEN a new candle close event is received, THE Scanner SHALL update the relative volume calculation for the affected coin and timeframe
5. IF fewer than 30 periods of volume history are available for a coin, THEN THE Scanner SHALL exclude that coin from relative volume scoring until sufficient data is accumulated
6. IF the current candle volume or any volume value in the 30-period lookback is zero or missing, THEN THE Scanner SHALL treat the relative volume as 0 and classify the volume condition as invalid for that candle

### Requirement 15: Duplicate Alert Protection

**User Story:** As a momentum trader, I want protection against repeated alerts for the same setup, so that I am not overwhelmed by redundant notifications.

#### Acceptance Criteria

1. THE Alert_Manager SHALL maintain a state cache of sent alerts keyed by the combination of coin symbol and setup type, retaining each entry for the duration of the configured cooldown period and holding a maximum of 500 entries
2. THE Alert_Manager SHALL enforce a configurable cooldown period between duplicate alerts for the same coin symbol and setup type, with a default of 4 hours and a permitted configuration range of 1 to 48 hours
3. WHEN a new breakout alert is generated for a coin symbol and setup type that is currently in cooldown, THE Alert_Manager SHALL send the alert only if the current candle volume divided by the 20-period average volume exceeds the same ratio recorded at the time of the previous alert by at least 50 percentage points
4. WHEN a setup transitions from a state where the rule engine score is below the send threshold to a state where the score meets or exceeds the send threshold, THE Alert_Manager SHALL send an update alert regardless of cooldown status
5. WHEN a setup is invalidated by a stop-loss price being breached or by the trend score component dropping below 40 out of 100, THE Alert_Manager SHALL remove the corresponding coin symbol and setup type entry from the state cache within the next scan cycle
6. IF the state cache cannot be read or is corrupted at startup, THEN THE Alert_Manager SHALL initialize an empty cache and log a warning indicating the cache was reset

### Requirement 16: Telegram Alert Delivery

**User Story:** As a momentum trader, I want structured Telegram alerts with all relevant setup data, so that I can make quick trading decisions from my phone.

#### Acceptance Criteria

1. WHEN a top-5 setup is confirmed, THE Alert_Manager SHALL send a Telegram message containing: coin symbol, setup type (strategy name), entry price, stop-loss price, risk percentage, Target1, and Target2
2. WHEN a Telegram alert is sent, THE Alert_Manager SHALL include in each message: relative strength vs BTC, relative volume ratio, OI change percentage, and funding rate with direction indicator (positive or negative)
3. WHEN a Telegram alert is sent, THE Alert_Manager SHALL include: trend score, final composite score (0–100), and UTC timestamp in ISO-8601 format
4. WHERE chart snapshot generation is configured, THE Alert_Manager SHALL attach a chart image to the Telegram alert
5. WHEN a Telegram alert is sent, THE Alert_Manager SHALL format the message using labeled sections (Signal, Entry/Exit, Market Context, Scoring) separated by line breaks, with directional emoji (green circle for LONG, red circle for SHORT) preceding the signal header
6. IF the Telegram API returns a non-success response or times out after 10 seconds, THEN THE Alert_Manager SHALL retry delivery up to 2 additional times with 5-second intervals and log the failure if all attempts fail
7. IF a market context field (relative strength, relative volume, OI change, or funding rate) is unavailable, THEN THE Alert_Manager SHALL send the alert with the available fields and display "N/A" for any missing field
8. THE Alert_Manager SHALL limit each Telegram alert message to a maximum of 4096 characters, truncating the reasoning section if necessary to remain within the limit

### Requirement 17: Signal Journaling and Logging

**User Story:** As a momentum trader, I want all signals logged with full context, so that I can review performance and refine my discretionary process.

#### Acceptance Criteria

1. THE Journal_Store SHALL persist every generated signal with: coin symbol, setup type, entry price, stop-loss price, composite score, relative strength score, relative volume, OI change percentage, funding rate, EMA20 value, EMA50 value, EMA200 value, ATR14 value, BTC regime state, and UTC timestamp
2. THE Journal_Store SHALL persist every rejected setup with: coin symbol, rejection reason, rejection stage (Market_Regime_Filter, Trend_Filter, Setup_Detector, or Scoring_Engine), indicator values at rejection time, and UTC timestamp
3. THE Journal_Store SHALL determine signal outcome by monitoring price against the signal's stop-loss and Target1 levels: a win is recorded when price reaches Target1 (1R), a loss is recorded when price hits the stop-loss, and an expiry is recorded if neither level is reached within 7 days
4. WHEN a signal outcome is determined, THE Journal_Store SHALL record: outcome (win, loss, or expiry), actual RR achieved as a decimal value, time from signal generation to outcome in minutes, and the exit price
5. WHEN a trading day ends (00:00 UTC), THE Journal_Store SHALL generate end-of-day analytics including: win rate as a percentage, average RR achieved as a decimal, setup type with highest win rate, BTC regime state with highest win rate, and UTC hour with highest win rate, calculated over signals resolved in the preceding 24 hours
6. IF zero signals were generated or resolved in the preceding 24 hours, THEN THE Journal_Store SHALL generate the end-of-day analytics report with zero values and a count of zero for all metrics
7. THE Journal_Store SHALL retain all signal and rejection records for a minimum of 90 days

### Requirement 18: Performance Analytics

**User Story:** As a momentum trader, I want automated performance tracking, so that I can identify which setups and conditions produce the best results.

#### Acceptance Criteria

1. THE Journal_Store SHALL calculate rolling win rate for each setup type over the last 30 days, where a win is defined as a trade that hit Target1 or Target2 before hitting stop-loss or expiring
2. THE Journal_Store SHALL calculate average risk-reward achieved for each setup type over the last 30 days, where risk-reward achieved is the actual exit distance from entry divided by the stop-loss distance from entry
3. THE Journal_Store SHALL identify the BTC regime state (all five conditions bullish vs any not bullish) that produced the highest win rate over the last 30 days
4. THE Journal_Store SHALL identify the hour of day (0-23 UTC, based on signal entry time) that produced the highest win rate over the last 30 days
5. WHEN end-of-day analytics are generated, THE Journal_Store SHALL store the analytics report containing: per-setup-type win rate, per-setup-type average risk-reward, best BTC regime state, best hour of day, and total number of signals evaluated
6. IF fewer than 5 closed trades exist for a given setup type within the 30-day window, THEN THE Journal_Store SHALL mark that setup type's analytics as insufficient data and exclude it from best/worst comparisons
7. THE Journal_Store SHALL retain stored end-of-day analytics reports for a minimum of 90 days for historical comparison

### Requirement 19: AI Usage Boundary

**User Story:** As a momentum trader, I want AI strictly limited to non-signal tasks, so that the scanner remains deterministic and repeatable.

#### Acceptance Criteria

1. THE Scanner SHALL NOT use AI or LLM models to generate, score, or influence trading signals at any point in the filter-detect-score pipeline
2. THE Scanner SHALL NOT use AI or LLM models to approve, reject, or modify the ranking of setups
3. THE Scanner SHALL NOT use AI or LLM models to modify scoring weights, thresholds, or any numeric parameter used in signal detection
4. THE Scanner SHALL NOT use AI or LLM models to adjust strategy logic, filter conditions, or detection rules at runtime
5. WHERE AI integration is configured, THE Scanner SHALL use AI only for: end-of-day summary generation, journal commentary, analytics narrative formatting, and Telegram message formatting
6. THE Scanner SHALL produce identical outputs (same signals, same scores, same rankings) given identical input data regardless of whether AI integration is enabled or disabled

### Requirement 20: System Performance and Reliability

**User Story:** As a momentum trader, I want the scanner to operate with low latency and high reliability, so that I never miss a setup due to system lag or failure.

#### Acceptance Criteria

1. WHEN a new candle event is received, THE Scanner SHALL complete the full filter-detect-score pipeline and produce a scored result within 500ms measured from websocket message receipt to score output availability, at the 95th percentile under concurrent load
2. THE Scanner SHALL use async processing for all I/O-bound operations including websocket reads, database writes, and Telegram sends
3. IF the primary exchange websocket produces no data for 5 seconds or the connection is closed unexpectedly, THEN THE Data_Collector SHALL detect the failure and failover to the configured secondary exchange within 10 seconds while preserving all pending setup states
4. THE Scanner SHALL support monitoring up to 300 coin pairs concurrently while maintaining the 500ms pipeline target at the 95th percentile
5. WHEN the Scanner process restarts, THE Scanner SHALL restore all active signal states including pending setups, cooldown timers, and in-progress confirmations from the Journal_Store within 30 seconds, and SHALL resume event processing only after restoration is complete
6. IF both primary and all configured fallback exchange websockets fail, THEN THE Data_Collector SHALL log the failure, send an alert notification via Telegram, and retry all connections with exponential backoff starting at 5 seconds up to a maximum interval of 60 seconds
7. WHILE the Data_Collector is failing over between exchanges, THE Scanner SHALL queue incoming events and SHALL NOT discard any candle close events received during the failover window
