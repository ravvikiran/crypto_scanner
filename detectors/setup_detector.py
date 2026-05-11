"""
Setup Detector - Compression Breakout and Pullback Continuation Detection.

Identifies compression zones on the 1H timeframe and detects breakout
signals with volume confirmation. Also detects pullback continuation
setups when price pulls back to EMA20/EMA50 support.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

from streaming.models import OHLCV
from streaming.models import (
    ActiveSetup,
    CompressionZone,
    PendingTrigger,
    SetupSignal,
    SetupState,
    SetupType,
)


def _calculate_atr14(candles: List[OHLCV]) -> Optional[float]:
    """
    Calculate ATR with a 14-period lookback from a list of OHLCV candles.

    Returns None if fewer than 15 candles are available (need at least
    14 true range values, which requires 15 candles for prev close).
    """
    if len(candles) < 15:
        return None

    df = pd.DataFrame(
        [
            {"high": c.high, "low": c.low, "close": c.close}
            for c in candles
        ]
    )

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()

    last_atr = atr.iloc[-1]
    if pd.isna(last_atr):
        return None
    return float(last_atr)


def _calculate_volume_ma30(candles: List[OHLCV]) -> Optional[float]:
    """
    Calculate the 30-period simple moving average of volume.

    Returns None if fewer than 30 candles are available.
    """
    if len(candles) < 30:
        return None

    volumes = pd.Series([c.volume for c in candles])
    ma = volumes.rolling(window=30).mean()
    last_ma = ma.iloc[-1]
    if pd.isna(last_ma):
        return None
    return float(last_ma)


def _candle_range(candle: OHLCV) -> float:
    """Return the high-low range of a candle."""
    return candle.high - candle.low


def _is_decreasing_sell_pressure(candles: List[OHLCV]) -> bool:
    """
    Check for decreasing sell pressure within a compression zone.

    Requirement 6.2: each successive candle closes in the upper 50% of its
    range OR shows lower sell-side volume compared to the prior candle.

    We use a relaxed check: at least half of the candles (after the first)
    satisfy one of the two conditions.
    """
    if len(candles) < 2:
        return True

    satisfied = 0
    total = len(candles) - 1

    for i in range(1, len(candles)):
        candle = candles[i]
        prev_candle = candles[i - 1]
        rng = _candle_range(candle)

        # Condition 1: close in upper 50% of range
        if rng > 0:
            close_position = (candle.close - candle.low) / rng
            if close_position >= 0.50:
                satisfied += 1
                continue

        # Condition 2: lower volume than previous candle (proxy for lower
        # sell-side volume)
        if candle.volume < prev_candle.volume:
            satisfied += 1
            continue

    # At least half of the candles should show decreasing sell pressure
    return satisfied >= (total / 2)


def detect_compression_breakout(
    candles_1h: List[OHLCV],
    candles_since_zone: int = 0,
    existing_zone: Optional[CompressionZone] = None,
) -> Optional[ActiveSetup]:
    """
    Detect a Compression Breakout setup on the 1H timeframe.

    This function performs two roles:
    1. Identifies new compression zones (3-8 consecutive candles with
       range < 75% of ATR14).
    2. Checks if the latest candle breaks out of an existing or newly
       detected compression zone.

    Parameters
    ----------
    candles_1h : List[OHLCV]
        The 1H candle history. Needs at least 15 candles for ATR14
        calculation and 30 for volume MA.
    candles_since_zone : int
        Number of candles elapsed since the zone was first identified.
        Used for zone expiry (12 candle limit).
    existing_zone : Optional[CompressionZone]
        A previously detected compression zone that is still active.

    Returns
    -------
    Optional[ActiveSetup]
        An ActiveSetup if a valid breakout is detected, otherwise None.
        Returns None with zone expiry if candles_since_zone >= 12.

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
    """
    # Need enough candles for ATR14 and volume MA30
    if len(candles_1h) < 30:
        return None

    # Calculate ATR14 using candles up to (but not including) the latest
    # candle for zone detection context
    atr14 = _calculate_atr14(candles_1h)
    if atr14 is None or atr14 <= 0:
        return None

    # Calculate 30-period volume MA
    volume_ma30 = _calculate_volume_ma30(candles_1h)
    if volume_ma30 is None or volume_ma30 <= 0:
        return None

    # --- Zone Expiry Check (Requirement 6.7) ---
    if existing_zone is not None and candles_since_zone >= 12:
        existing_zone.expired = True
        return None

    # --- Try to detect a new compression zone if none exists ---
    zone = existing_zone
    if zone is None:
        zone = _detect_compression_zone(candles_1h, atr14)

    if zone is None:
        return None

    # --- Check for breakout on the latest candle (Requirements 6.3, 6.4) ---
    latest_candle = candles_1h[-1]
    setup = _check_breakout(latest_candle, zone, volume_ma30, atr14)
    return setup


def _detect_compression_zone(
    candles_1h: List[OHLCV], atr14: float
) -> Optional[CompressionZone]:
    """
    Scan the recent candle history for a compression zone.

    Requirement 6.1: 3-8 consecutive candles where each candle's range
    (high - low) is less than 75% of ATR14.

    We look backwards from the second-to-last candle (the last candle is
    the potential breakout candle).
    """
    threshold = 0.75 * atr14

    # We scan backwards from the second-to-last candle to find the longest
    # valid compression sequence (3-8 candles)
    # Exclude the last candle as it's the potential breakout candle
    search_candles = candles_1h[:-1]

    if len(search_candles) < 3:
        return None

    # Find the longest trailing sequence of compressed candles
    compressed_count = 0
    for i in range(len(search_candles) - 1, -1, -1):
        candle = search_candles[i]
        rng = _candle_range(candle)
        if rng < threshold:
            compressed_count += 1
        else:
            break

        # Cap at 8 candles max
        if compressed_count >= 8:
            break

    # Need at least 3 candles for a valid zone
    if compressed_count < 3:
        return None

    # Extract the zone candles
    zone_start_idx = len(search_candles) - compressed_count
    zone_candles = search_candles[zone_start_idx:]

    # Check for decreasing sell pressure (Requirement 6.2)
    if not _is_decreasing_sell_pressure(zone_candles):
        return None

    # Build the CompressionZone
    zone_high = max(c.high for c in zone_candles)
    zone_low = min(c.low for c in zone_candles)

    return CompressionZone(
        high=zone_high,
        low=zone_low,
        candle_count=compressed_count,
        start_atr14=atr14,
        candles=zone_candles,
        created_at=datetime.utcnow(),
        expired=False,
    )


def _check_breakout(
    candle: OHLCV,
    zone: CompressionZone,
    volume_ma30: float,
    atr14: float,
) -> Optional[ActiveSetup]:
    """
    Check if a candle constitutes a valid breakout from the compression zone.

    Requirement 6.3: close above zone high, volume > 1.5x MA30
    Requirement 6.4: close in upper 33% of candle range
    Requirement 6.5: entry at breakout candle high
    Requirement 6.6: stop-loss at min(zone_low, entry - 1.2 * ATR14)
    """
    # Breakout condition: close above zone high
    if candle.close <= zone.high:
        return None

    # Volume condition: volume > 1.5x the 30-period volume MA
    if candle.volume <= 1.5 * volume_ma30:
        return None

    # Close position condition: close in upper 33% of candle range
    candle_rng = _candle_range(candle)
    if candle_rng <= 0:
        return None

    close_position = (candle.close - candle.low) / candle_rng
    if close_position < (2.0 / 3.0):  # upper 33% means >= 0.6667
        return None

    # --- Valid breakout detected ---

    # Entry price: breakout candle high (Requirement 6.5)
    entry_price = candle.high

    # Stop-loss: lower of zone low or entry - 1.2 * ATR14 (Requirement 6.6)
    atr_stop = entry_price - 1.2 * atr14
    stop_loss = min(zone.low, atr_stop)

    # Calculate risk and targets
    risk = entry_price - stop_loss
    if risk <= 0:
        return None

    target_1 = entry_price + risk  # 1R
    target_2 = entry_price + 2 * risk  # 2R
    target_3 = entry_price + 5 * risk  # 5R (Requirement 8.1)

    # Risk-reward ratio (target_1 is 1R by definition, so RR = 1.0 for T1)
    # We use target_2 for the RR check (must be >= 2.0)
    risk_reward = (target_2 - entry_price) / risk  # Should be 2.0

    return ActiveSetup(
        symbol="",  # To be filled by caller
        setup_type=SetupType.COMPRESSION_BREAKOUT,
        state=SetupState.DETECTED,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        risk_reward=risk_reward,
        timeframe="1h",
        trigger_timeframe="15m",
        compression_zone=zone,
        detected_at=datetime.utcnow(),
    )


def _calculate_ema(values: pd.Series, span: int) -> pd.Series:
    """
    Calculate Exponential Moving Average using pandas EWM.

    Parameters
    ----------
    values : pd.Series
        The series of values to compute EMA over.
    span : int
        The span (period) for the EMA calculation.

    Returns
    -------
    pd.Series
        The EMA series.
    """
    return values.ewm(span=span, adjust=False).mean()


def detect_pullback_continuation(
    candles_1h: List[OHLCV],
) -> Optional[ActiveSetup]:
    """
    Detect a Pullback Continuation setup on the 1H timeframe.

    This function monitors for pullbacks to EMA20 or EMA50 and detects
    bullish reclaim candles that signal trend continuation.

    Detection logic:
    1. Calculate EMA20 and EMA50 from the 1H close prices.
    2. Check if the latest candle's low touched or came within 0.5% of
       EMA20 or EMA50 (pullback detection).
    3. Verify the latest candle is a bullish reclaim: closes above the
       relevant EMA, close is in the upper 50% of the candle range.
    4. Confirm volume > 1.5x MA30 volume.
    5. Check invalidation: if price closes below EMA by > 1.0%, discard.

    Parameters
    ----------
    candles_1h : List[OHLCV]
        The 1H candle history. Needs at least 50 candles for EMA50
        calculation and 30 for volume MA.

    Returns
    -------
    Optional[ActiveSetup]
        An ActiveSetup if a valid pullback continuation is detected,
        otherwise None.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
    """
    # Need enough candles for EMA50 (at least 50) and volume MA30
    if len(candles_1h) < 50:
        return None

    # Calculate ATR14
    atr14 = _calculate_atr14(candles_1h)
    if atr14 is None or atr14 <= 0:
        return None

    # Calculate 30-period volume MA
    volume_ma30 = _calculate_volume_ma30(candles_1h)
    if volume_ma30 is None or volume_ma30 <= 0:
        return None

    # Build a DataFrame of close prices for EMA calculation
    closes = pd.Series([c.close for c in candles_1h])

    # Calculate EMA20 and EMA50 using pandas EWM
    ema20_series = _calculate_ema(closes, span=20)
    ema50_series = _calculate_ema(closes, span=50)

    # Get the current EMA values (at the latest candle)
    ema20 = float(ema20_series.iloc[-1])
    ema50 = float(ema50_series.iloc[-1])

    # The latest candle is the potential trigger candle
    trigger_candle = candles_1h[-1]

    # --- Requirement 7.6: Invalidation check ---
    # If price closes below the relevant EMA by more than 1.0%, invalidate
    # Check against both EMAs - if close is below either by > 1.0%, invalidate
    # We check invalidation against the EMA that the pullback is targeting
    ema20_invalidation_threshold = ema20 * (1 - 0.01)  # 1.0% below EMA20
    ema50_invalidation_threshold = ema50 * (1 - 0.01)  # 1.0% below EMA50

    # If price closes below both EMAs by > 1.0%, the setup is invalid
    if (trigger_candle.close < ema20_invalidation_threshold and
            trigger_candle.close < ema50_invalidation_threshold):
        return None

    # --- Requirement 7.1 & 7.2: Pullback detection ---
    # Check if the candle's low came within 0.5% of EMA20 or EMA50
    ema20_proximity_threshold = ema20 * 0.005  # 0.5% of EMA20
    ema50_proximity_threshold = ema50 * 0.005  # 0.5% of EMA50

    touched_ema20 = abs(trigger_candle.low - ema20) <= ema20_proximity_threshold
    touched_ema50 = abs(trigger_candle.low - ema50) <= ema50_proximity_threshold

    if not touched_ema20 and not touched_ema50:
        return None

    # Determine which EMA was touched (prefer EMA20 if both)
    relevant_ema = ema20 if touched_ema20 else ema50

    # --- Requirement 7.2: Bullish reclaim candle ---
    # Close must be above the relevant EMA
    if trigger_candle.close <= relevant_ema:
        return None

    # Close must be in the upper 50% of the candle range
    candle_rng = _candle_range(trigger_candle)
    if candle_rng <= 0:
        return None

    close_position = (trigger_candle.close - trigger_candle.low) / candle_rng
    if close_position < 0.50:
        return None

    # --- Requirement 7.3: Volume confirmation ---
    # Volume must be > 1.5x MA30 volume
    if trigger_candle.volume <= 1.5 * volume_ma30:
        return None

    # --- Requirement 7.6: Specific invalidation for the relevant EMA ---
    # If price closes below the relevant EMA by > 1.0%, invalidate
    relevant_ema_invalidation = relevant_ema * (1 - 0.01)
    if trigger_candle.close < relevant_ema_invalidation:
        return None

    # --- Valid Pullback Continuation detected ---

    # Requirement 7.4: Entry price at trigger candle high
    entry_price = trigger_candle.high

    # Requirement 7.5: Stop-loss at min(trigger candle low, entry - 1.2 * ATR14)
    atr_stop = entry_price - 1.2 * atr14
    stop_loss = min(trigger_candle.low, atr_stop)

    # Calculate risk and targets
    risk = entry_price - stop_loss
    if risk <= 0:
        return None

    target_1 = entry_price + risk  # 1R
    target_2 = entry_price + 2 * risk  # 2R
    target_3 = entry_price + 5 * risk  # 5R (Requirement 8.1)

    # Risk-reward ratio using target_2
    risk_reward = (target_2 - entry_price) / risk  # Should be 2.0

    return ActiveSetup(
        symbol="",  # To be filled by caller
        setup_type=SetupType.PULLBACK_CONTINUATION,
        state=SetupState.DETECTED,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        risk_reward=risk_reward,
        timeframe="1h",
        trigger_timeframe="15m",
        compression_zone=None,
        detected_at=datetime.utcnow(),
    )



def _calculate_volume_ma20(candles: List[OHLCV]) -> Optional[float]:
    """
    Calculate the 20-period simple moving average of volume.

    Returns None if fewer than 20 candles are available.
    """
    if len(candles) < 20:
        return None

    volumes = pd.Series([c.volume for c in candles])
    ma = volumes.rolling(window=20).mean()
    last_ma = ma.iloc[-1]
    if pd.isna(last_ma):
        return None
    return float(last_ma)


def detect_momentum_breakout(
    candles_1h: List[OHLCV],
) -> Optional[ActiveSetup]:
    """
    Detect a Momentum Breakout setup on the 1H timeframe.

    This function identifies strong directional moves that do not form
    compression or pullback patterns. It uses a simple momentum-based
    approach: price above EMA20, consecutive higher highs, and volume
    surge confirmation.

    Detection logic:
    1. Close > EMA20 on the 1H timeframe.
    2. Last 3 consecutive 1H candles each have a higher high than the
       previous candle.
    3. Current 1H candle volume > 2.5× the 20-period volume MA.

    Stop-loss calculation:
    - Raw stop = tighter (higher) of: swing_low_3 × 0.995, or entry − 1.5 × ATR14
    - Clamp stop distance to [0.8%, 2.5%] of entry price.

    Parameters
    ----------
    candles_1h : List[OHLCV]
        The 1H candle history. Needs at least 20 candles for EMA20
        calculation and volume MA20.

    Returns
    -------
    Optional[ActiveSetup]
        An ActiveSetup if a valid momentum breakout is detected,
        otherwise None.

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 8.1
    """
    # Need enough candles for EMA20, volume MA20, and ATR14
    # At least 20 candles for EMA20/volume MA, and 15 for ATR14
    if len(candles_1h) < 20:
        return None

    # --- Condition 1: Close > EMA20 (1H) ---
    closes = pd.Series([c.close for c in candles_1h])
    ema20_series = _calculate_ema(closes, span=20)
    ema20 = float(ema20_series.iloc[-1])

    latest_candle = candles_1h[-1]
    if latest_candle.close <= ema20:
        return None

    # --- Condition 2: Last 3 candles have higher highs ---
    # We need at least 4 candles to check 3 consecutive higher highs
    # (candle[-3].high > candle[-4].high, candle[-2].high > candle[-3].high,
    #  candle[-1].high > candle[-2].high)
    if len(candles_1h) < 4:
        return None

    for i in range(-3, 0):
        if candles_1h[i].high <= candles_1h[i - 1].high:
            return None

    # --- Condition 3: Volume > 2.5× 20-period volume MA ---
    volume_ma20 = _calculate_volume_ma20(candles_1h)
    if volume_ma20 is None or volume_ma20 <= 0:
        return None

    if latest_candle.volume <= 2.5 * volume_ma20:
        return None

    # --- All conditions met: Calculate entry and stop-loss ---

    # Entry price: current 1H candle close (Requirement 3.3)
    entry_price = latest_candle.close

    # Calculate ATR14
    atr14 = _calculate_atr14(candles_1h)
    if atr14 is None or atr14 <= 0:
        return None

    # Swing low of last 3 candles (Requirement 3.4)
    swing_low_3 = min(c.low for c in candles_1h[-3:])

    # Raw stop-loss: tighter (higher) of the two options (Requirement 3.4)
    stop_option_1 = swing_low_3 * 0.995  # swing_low_3 × 0.995
    stop_option_2 = entry_price - 1.5 * atr14  # entry − 1.5 × ATR14
    raw_stop = max(stop_option_1, stop_option_2)  # tighter = higher value

    # --- Clamp stop-loss distance to [0.8%, 2.5%] range ---
    # (Requirements 3.5, 3.6, 3.7)
    min_stop_distance = entry_price * 0.008  # 0.8% of entry
    max_stop_distance = entry_price * 0.025  # 2.5% of entry

    raw_distance = entry_price - raw_stop

    # Clamp the distance
    clamped_distance = max(min_stop_distance, min(raw_distance, max_stop_distance))

    # Final stop-loss
    stop_loss = entry_price - clamped_distance

    # Calculate risk and targets
    risk = entry_price - stop_loss
    if risk <= 0:
        return None

    target_1 = entry_price + risk        # 1R
    target_2 = entry_price + 2 * risk    # 2R
    target_3 = entry_price + 5 * risk    # 5R (Requirement 8.1)

    # Risk-reward ratio (using T2)
    risk_reward = (target_2 - entry_price) / risk  # Should be 2.0

    return ActiveSetup(
        symbol="",  # To be filled by caller
        setup_type=SetupType.MOMENTUM_BREAKOUT,
        state=SetupState.DETECTED,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        risk_reward=risk_reward,
        timeframe="1h",
        trigger_timeframe="15m",
        compression_zone=None,
        detected_at=datetime.utcnow(),
    )


def check_15m_trigger(
    candle_15m: OHLCV,
    pending: PendingTrigger,
    candles_15m: List[OHLCV],
    setup_invalidated: bool = False,
) -> Optional[ActiveSetup]:
    """
    Check if a 15m candle confirms the pending entry trigger.

    This function implements the 15m entry confirmation logic:
    - Confirmation: 15m candle closes above entry price AND volume > 1.5x
      the 15m 30-period volume MA.
    - Expiry: if 4 consecutive 15m candles pass without confirmation, the
      trigger expires (returns None and decrements candles_remaining).
    - Rejection: if volume is insufficient, log rejection but don't expire
      (wait for next candle within the remaining window).
    - Cancellation: if the parent 1H setup is invalidated, cancel the
      pending trigger immediately.

    Parameters
    ----------
    candle_15m : OHLCV
        The latest closed 15m candle to evaluate.
    pending : PendingTrigger
        The pending trigger awaiting confirmation. Its `candles_remaining`
        field is decremented on each call (mutated in place).
    candles_15m : List[OHLCV]
        The 15m candle history (including the current candle). Needs at
        least 30 candles for volume MA30 calculation.
    setup_invalidated : bool
        True if the parent 1H setup has been invalidated (price closed
        below stop-loss or trend turned not bullish). Triggers immediate
        cancellation.

    Returns
    -------
    Optional[ActiveSetup]
        A confirmed ActiveSetup (state=CONFIRMED) if the trigger is
        confirmed, otherwise None.

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """
    # --- Cancellation: 1H setup invalidated (Requirement 8.5) ---
    if setup_invalidated:
        logger.info(
            "15m trigger cancelled for %s (%s): parent 1H setup invalidated",
            pending.symbol,
            pending.setup_type.value,
        )
        pending.candles_remaining = 0
        return None

    # --- Expiry check (Requirement 8.3) ---
    # If no candles remaining before this evaluation, the trigger has expired
    if pending.candles_remaining <= 0:
        logger.info(
            "15m trigger expired for %s (%s): 4-candle confirmation window exhausted",
            pending.symbol,
            pending.setup_type.value,
        )
        return None

    # Calculate 15m volume MA30
    volume_ma30_15m = _calculate_volume_ma30(candles_15m)

    # If insufficient history for volume MA, we cannot confirm but don't expire
    if volume_ma30_15m is None or volume_ma30_15m <= 0:
        logger.warning(
            "15m trigger for %s: insufficient volume history for MA30 calculation",
            pending.symbol,
        )
        pending.candles_remaining -= 1
        return None

    # --- Check confirmation conditions (Requirement 8.2) ---
    price_confirmed = candle_15m.close > pending.entry_price
    volume_confirmed = candle_15m.volume > 1.5 * volume_ma30_15m

    if price_confirmed and volume_confirmed:
        # --- Trigger confirmed ---
        logger.info(
            "15m trigger CONFIRMED for %s (%s): close=%.4f > entry=%.4f, "
            "volume=%.2f > 1.5x MA30=%.2f",
            pending.symbol,
            pending.setup_type.value,
            candle_15m.close,
            pending.entry_price,
            candle_15m.volume,
            1.5 * volume_ma30_15m,
        )

        # Calculate risk-reward from pending trigger levels
        risk = pending.entry_price - pending.stop_loss
        risk_reward = 0.0
        if risk > 0:
            target_2_distance = (
                (pending.target_2 - pending.entry_price) if pending.target_2 else 0.0
            )
            risk_reward = target_2_distance / risk if target_2_distance > 0 else 0.0

        return ActiveSetup(
            symbol=pending.symbol,
            setup_type=pending.setup_type,
            state=SetupState.CONFIRMED,
            entry_price=pending.entry_price,
            stop_loss=pending.stop_loss,
            target_1=pending.target_1,
            target_2=pending.target_2,
            risk_reward=risk_reward,
            timeframe="1h",
            trigger_timeframe="15m",
            detected_at=pending.created_at,
            confirmed_at=datetime.utcnow(),
        )

    # --- Rejection: price above entry but insufficient volume (Req 8.4) ---
    if price_confirmed and not volume_confirmed:
        logger.info(
            "15m trigger rejected for %s (%s): price confirmed (close=%.4f > "
            "entry=%.4f) but volume insufficient (%.2f <= 1.5x MA30=%.2f). "
            "Candles remaining: %d",
            pending.symbol,
            pending.setup_type.value,
            candle_15m.close,
            pending.entry_price,
            candle_15m.volume,
            1.5 * volume_ma30_15m,
            pending.candles_remaining - 1,
        )

    # Decrement candles remaining for this evaluation cycle
    pending.candles_remaining -= 1

    # Check if this was the last candle (expiry after decrement)
    if pending.candles_remaining <= 0:
        logger.info(
            "15m trigger expired for %s (%s): 4-candle confirmation window "
            "exhausted without valid confirmation",
            pending.symbol,
            pending.setup_type.value,
        )

    return None


def expire_stale_setups(
    active_setups: List[ActiveSetup],
    pending_triggers: List[PendingTrigger],
) -> tuple:
    """
    Expire stale setups and pending triggers based on time/candle limits.

    This function performs lifecycle management for active setups and
    pending entry triggers:

    1. Active setups with compression zones expire after 12 candles from
       detection (Requirement 6.7).
    2. Pending triggers expire when their candles_remaining reaches 0
       (Requirement 8.3).
    3. All expirations and cancellations are logged to a journal list
       (Requirement 8.5).

    Parameters
    ----------
    active_setups : List[ActiveSetup]
        Currently tracked active setups. Each setup's compression_zone
        candle_count is used to determine age for compression breakout
        setups.
    pending_triggers : List[PendingTrigger]
        Currently pending 15m entry triggers awaiting confirmation.

    Returns
    -------
    Tuple[List[ActiveSetup], List[dict]]
        A tuple of:
        - List of setups that were expired/removed (for caller to clean up)
        - List of journal log entries (dicts with symbol, setup_type,
          reason, timestamp) for each expiration/cancellation

    Requirements: 6.7, 8.3, 8.5
    """
    expired_setups: List[ActiveSetup] = []
    journal_entries: List[dict] = []
    now = datetime.utcnow()

    # --- Expire active setups that exceeded maximum age ---
    for setup in active_setups:
        should_expire = False
        reason = ""

        if setup.setup_type == SetupType.COMPRESSION_BREAKOUT:
            # Compression zones expire after 12 candles from detection
            # (Requirement 6.7)
            if (
                setup.compression_zone is not None
                and setup.compression_zone.candle_count >= 12
            ):
                should_expire = True
                reason = "no_breakout_12_candles"
                setup.compression_zone.expired = True
            elif setup.state == SetupState.DETECTED:
                # If no compression zone attached but state is still DETECTED
                # and it's a compression breakout, check candle count via zone
                if setup.compression_zone is not None and not setup.compression_zone.expired:
                    # Zone exists but hasn't hit 12 yet - skip
                    continue
                elif setup.compression_zone is not None and setup.compression_zone.expired:
                    should_expire = True
                    reason = "no_breakout_12_candles"

        elif setup.setup_type == SetupType.PULLBACK_CONTINUATION:
            # Pullback setups in DETECTED state that haven't progressed
            # to pending confirmation are expired if stale
            if setup.state == SetupState.DETECTED:
                # Pullback setups don't have a candle-count expiry like
                # compression zones, but if they're still in DETECTED state
                # they should transition to pending or be cleaned up
                pass

        if should_expire:
            setup.state = SetupState.EXPIRED
            expired_setups.append(setup)

            entry = {
                "symbol": setup.symbol,
                "setup_type": setup.setup_type.value,
                "reason": reason,
                "timestamp": now.isoformat(),
            }
            journal_entries.append(entry)

            logger.info(
                "Setup expired: %s %s - reason: %s",
                setup.symbol,
                setup.setup_type.value,
                reason,
            )

    # --- Expire pending triggers with no candles remaining ---
    # (Requirement 8.3, 8.5)
    for trigger in pending_triggers:
        if trigger.candles_remaining <= 0:
            # Create an ActiveSetup representation for the expired trigger
            expired_setup = ActiveSetup(
                symbol=trigger.symbol,
                setup_type=trigger.setup_type,
                state=SetupState.EXPIRED,
                entry_price=trigger.entry_price,
                stop_loss=trigger.stop_loss,
                target_1=trigger.target_1,
                target_2=trigger.target_2,
                timeframe="1h",
                trigger_timeframe="15m",
                detected_at=trigger.created_at,
            )
            expired_setups.append(expired_setup)

            reason = "no_15m_confirm_4_candles"
            entry = {
                "symbol": trigger.symbol,
                "setup_type": trigger.setup_type.value,
                "reason": reason,
                "timestamp": now.isoformat(),
            }
            journal_entries.append(entry)

            logger.info(
                "Pending trigger expired: %s %s - reason: %s",
                trigger.symbol,
                trigger.setup_type.value,
                reason,
            )

    return (expired_setups, journal_entries)
