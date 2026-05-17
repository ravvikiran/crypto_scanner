"""
Scoring Engine - Deterministic composite scoring with fixed weights.

Calculates a composite momentum score from 5 normalized inputs using
a fixed, transparent formula. No AI/ML involvement.

Requirements: 12.1, 12.2, 12.6
"""

from typing import Dict, List, Optional

from streaming.models import OHLCV
from streaming.models import BreakoutQualityScore, OIFundingData, ScoreInputs, ScoredSetup


# Fixed scoring weights - deterministic, no AI/ML adjustment
WEIGHTS: Dict[str, float] = {
    "relative_strength": 0.30,
    "relative_volume": 0.25,
    "breakout_quality": 0.20,
    "trend_quality": 0.15,
    "market_alignment": 0.10,
}


def _clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Clamp a value to the [min_val, max_val] range."""
    return max(min_val, min(value, max_val))


def score(inputs: ScoreInputs) -> float:
    """
    Calculate composite score using fixed formula.

    Formula:
        composite = RS*0.30 + RVOL*0.25 + breakout_quality*0.20
                  + trend_quality*0.15 + market_alignment*0.10

    All inputs are clamped to 0-100 before calculation.
    Result is rounded to 2 decimal places.

    Args:
        inputs: ScoreInputs dataclass with 5 normalized values (0-100 each).

    Returns:
        Composite score as a float, rounded to 2 decimal places.
    """
    rs = _clamp(inputs.relative_strength)
    rvol = _clamp(inputs.relative_volume)
    bq = _clamp(inputs.breakout_quality)
    tq = _clamp(inputs.trend_quality)
    ma = _clamp(inputs.market_alignment)

    composite = (
        rs * WEIGHTS["relative_strength"]
        + rvol * WEIGHTS["relative_volume"]
        + bq * WEIGHTS["breakout_quality"]
        + tq * WEIGHTS["trend_quality"]
        + ma * WEIGHTS["market_alignment"]
    )

    return round(composite, 2)


def normalize_inputs(raw_values: Dict[str, List[float]]) -> Dict[str, float]:
    """
    Min-max normalize all inputs to 0-100 scale across the current set.

    For each scoring dimension, the lowest observed value maps to 0
    and the highest maps to 100. If all values are identical (max == min),
    all normalize to 50.0.

    Args:
        raw_values: Dict mapping dimension name to list of raw values
                    across all current valid setups.

    Returns:
        Dict mapping dimension name to normalized value (0-100).
        Returns the normalized value for the LAST element in each list
        (representing the current setup being scored).
    """
    normalized: Dict[str, float] = {}

    for dimension, values in raw_values.items():
        if not values:
            normalized[dimension] = 0.0
            continue

        min_val = min(values)
        max_val = max(values)

        # Current value is the last in the list
        current = values[-1]

        if max_val == min_val:
            # All values identical - normalize to 50
            normalized[dimension] = 50.0
        else:
            normalized[dimension] = round(
                ((current - min_val) / (max_val - min_val)) * 100.0, 2
            )

    return normalized


def normalize_rvol(rvol: float, volume_history_count: int) -> Optional[float]:
    """
    Normalize relative volume (RVOL) to a 0-100 scale using linear interpolation.

    Mapping:
        RVOL 1.0 → 0
        RVOL 3.0 → 100
        Linear interpolation between, clamped to [0, 100].

    Args:
        rvol: Raw relative volume value (current volume / MA30 volume).
        volume_history_count: Number of volume periods available for the coin.

    Returns:
        Normalized RVOL score (0-100), or None if data is insufficient or invalid.
        - Returns None if volume_history_count < 30 (insufficient data, exclude from scoring).
        - Returns None if rvol <= 0 (invalid/missing volume).
        - Returns 0.0 if rvol < 1.0 (below baseline, no contribution).

    Requirements: 14.1, 14.2, 14.3, 14.5, 14.6
    """
    # Insufficient volume history — exclude from scoring
    if volume_history_count < 30:
        return None

    # Zero or missing volume — invalid
    if rvol <= 0:
        return None

    # Below baseline — no volume contribution
    if rvol < 1.0:
        return 0.0

    # Linear interpolation: RVOL 1.0 → 0, RVOL 3.0 → 100
    normalized = ((rvol - 1.0) / (3.0 - 1.0)) * 100.0

    # Clamp to 0-100 range
    return _clamp(normalized, 0.0, 100.0)


def _linear_map(value: float, in_min: float, in_max: float, out_max: float = 20.0) -> int:
    """
    Linearly map a value from [in_min, in_max] to [0, out_max].

    Values below in_min map to 0, values above in_max map to out_max.
    Result is rounded to the nearest integer.

    Args:
        value: The input value to map.
        in_min: The lower bound of the input range (maps to 0).
        in_max: The upper bound of the input range (maps to out_max).
        out_max: The maximum output value (default 20).

    Returns:
        Integer score in [0, out_max].
    """
    if value <= in_min:
        return 0
    if value >= in_max:
        return int(out_max)
    return int(round(((value - in_min) / (in_max - in_min)) * out_max))


def score_breakout_quality(candle: OHLCV, atr14: float, rvol: float) -> BreakoutQualityScore:
    """
    Score the quality of a breakout candle using 5 sub-scores.

    Each sub-score ranges from 0 to 20 points (total 0-100).

    Sub-scores:
        1. Body ratio: abs(close - open) / (high - low), linearly mapped 0.0-1.0 → 0-20
        2. Close position: (close - low) / (high - low), linearly mapped 0.0-1.0 → 0-20
        3. Range expansion: (high - low) / ATR14, linearly mapped 1.0-3.0 → 0-20
           (below 1.0 = 0, above 3.0 = 20)
        4. Momentum acceleration: RS acceleration value, linearly mapped 0.0-10.0 → 0-20
        5. RVOL: relative volume ratio, linearly mapped 1.0-3.0 → 0-20

    Args:
        candle: The breakout candle (OHLCV dataclass).
        atr14: The 14-period Average True Range value.
        rvol: The relative volume ratio (current volume / MA30 volume).

    Returns:
        BreakoutQualityScore dataclass with all 5 sub-scores populated.

    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7
    """
    candle_range = candle.high - candle.low

    # Edge case: zero-range candle (doji with no movement) → all zeros
    if candle_range == 0:
        return BreakoutQualityScore(
            body_ratio_score=0,
            close_position_score=0,
            range_expansion_score=0,
            momentum_acceleration_score=0,
            relative_volume_score=0,
        )

    # 1. Body ratio: abs(close - open) / (high - low)
    body_ratio = abs(candle.close - candle.open) / candle_range
    body_ratio_score = _linear_map(body_ratio, 0.0, 1.0)

    # 2. Close position: (close - low) / (high - low)
    close_position = (candle.close - candle.low) / candle_range
    close_position_score = _linear_map(close_position, 0.0, 1.0)

    # 3. Range expansion: (high - low) / ATR14
    # Below 1.0 = 0, above 3.0 = 20, linear between
    if atr14 > 0:
        range_expansion = candle_range / atr14
    else:
        range_expansion = 0.0
    range_expansion_score = _linear_map(range_expansion, 1.0, 3.0)

    # 4. Momentum acceleration: RS acceleration value
    # Linearly mapped from 0.0-10.0 → 0-20
    # Use percentage price change of the breakout candle as momentum proxy
    momentum_accel = abs(candle.close - candle.open) / candle.open * 100.0 if candle.open > 0 else 0.0
    momentum_acceleration_score = _linear_map(momentum_accel, 0.0, 10.0)

    # 5. RVOL: relative volume ratio, linearly mapped 1.0-3.0 → 0-20
    relative_volume_score = _linear_map(rvol, 1.0, 3.0)

    return BreakoutQualityScore(
        body_ratio_score=body_ratio_score,
        close_position_score=close_position_score,
        range_expansion_score=range_expansion_score,
        momentum_acceleration_score=momentum_acceleration_score,
        relative_volume_score=relative_volume_score,
    )


def apply_oi_adjustments(composite_score: float, oi_data: OIFundingData) -> float:
    """
    Apply open interest and funding rate adjustments to a composite score.

    Adjustments are multiplicative:
        - If overcrowded (extreme funding > 0.1% or < -0.1%): reduce by 20%
        - If weak OI participation (OI declining >5% while price rising >1%): reduce by 15%
        - If both conditions apply: score * 0.80 * 0.85
        - If data is unavailable: return score unchanged (no penalty)

    Args:
        composite_score: The raw composite score (0-100).
        oi_data: OIFundingData with overcrowded/weak_oi flags and data_available status.

    Returns:
        Adjusted score, rounded to 2 decimal places.

    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
    """
    # If OI/funding data is unavailable, return score unchanged
    if not oi_data.data_available:
        return round(composite_score, 2)

    adjusted = composite_score

    # Apply overcrowded penalty (-20%)
    if oi_data.is_overcrowded:
        adjusted *= 0.80

    # Apply weak OI participation penalty (-15%)
    if oi_data.weak_oi_participation:
        adjusted *= 0.85

    return round(adjusted, 2)


def rank_setups(scored_setups: List[ScoredSetup]) -> List[ScoredSetup]:
    """
    Rank scored setups and return the top 5.

    Sorting:
        - Primary: composite_score descending (higher is better)
        - Tie-break: relative_volume descending (higher volume wins)

    Returns at most 5 setups, or all if fewer than 5 exist.

    Args:
        scored_setups: List of ScoredSetup instances to rank.

    Returns:
        Top 5 setups sorted by composite score (descending), with
        tie-breaking by relative_volume (descending).

    Requirements: 12.3, 12.4, 12.5
    """
    sorted_setups = sorted(
        scored_setups,
        key=lambda s: (s.composite_score, s.inputs.relative_volume),
        reverse=True,
    )

    return sorted_setups[:5]


def calculate_risk_levels(
    entry_price: float,
    structure_stop: float,
    atr14: float,
) -> Optional[Dict[str, float]]:
    """
    Calculate direction-agnostic ATR-based risk management levels for a setup.

    The risk distance is always |entry - stop| so this function works for both
    LONG setups (stop below entry) and SHORT setups (stop above entry).

    Uses the wider of the structure stop and atr_stop (further from entry) to
    set final stop_loss, then derives Target1 (1R) and Target2 (2R).
    Rejects setups where the risk distance is <= 0 or where the resulting
    risk-reward ratio would be below 2.0.

    Args:
        entry_price: The entry price for the setup.
        structure_stop: The structure-based stop-loss price.
        atr14: The 14-period Average True Range, used to compute an ATR-based
               stop at entry ± 1.2×ATR14 (minus for longs, plus for shorts will
               be supplied by the caller as the appropriate sign).

    Returns:
        Dict with risk management levels, or None if the setup is invalid:
            - stop_loss: Final stop-loss (wider of structure stop and ATR stop)
            - target_1: Entry ± 1R (first target; + for long, - for short)
            - target_2: Entry ± 2R (second target)
            - risk: Distance from entry to stop-loss (1R, always positive)
            - risk_reward: Risk-reward ratio (always 2.0 by construction)
            - risk_percent: Risk as percentage of entry price

        Returns None if:
            - risk distance <= 0 (invalid setup where stop is at or equal to entry)
            - risk_reward < 2.0 (rejected)
    """
    valid_atr = max(atr14, 0.0)

    # ATR stop: entry − 1.2 × ATR (designed for LONG side)
    # If structure_stop > entry this function still works correctly because
    # risk = abs(entry - min_or_max_stop) is used below.
    atr_stop = entry_price - 1.2 * valid_atr

    # Use the wider (further from entry) stop — the safer of the two
    stop_loss = min(structure_stop, atr_stop)

    # Direction-agnostic risk distance (Requirement 9.x)
    risk = abs(entry_price - stop_loss)

    if risk <= 0:
        return None

    target_1 = entry_price + risk       # 1R target
    target_2 = entry_price + 2 * risk   # 2R target
    risk_reward = (target_2 - entry_price) / risk

    if risk_reward < 2.0:
        return None

    risk_percent = (risk / entry_price) * 100.0

    return {
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk": risk,
        "risk_reward": risk_reward,
        "risk_percent": risk_percent,
    }
