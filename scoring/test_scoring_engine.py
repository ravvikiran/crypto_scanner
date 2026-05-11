"""
Unit tests for the composite scoring engine.

Tests cover:
- Composite score calculation with known inputs
- Input clamping for out-of-range values
- Min-max normalization
- Rounding to 2 decimal places
- Edge cases (all zeros, all 100s, identical values)
"""

import pytest

from streaming.models import ScoreInputs
from scoring.scoring_engine import score, normalize_inputs, _clamp, WEIGHTS


class TestScore:
    """Tests for the composite score() function."""

    def test_all_zeros(self):
        """All zero inputs produce a score of 0."""
        inputs = ScoreInputs(
            relative_strength=0.0,
            relative_volume=0.0,
            breakout_quality=0.0,
            trend_quality=0.0,
            market_alignment=0.0,
        )
        assert score(inputs) == 0.0

    def test_all_hundreds(self):
        """All inputs at 100 produce a score of 100."""
        inputs = ScoreInputs(
            relative_strength=100.0,
            relative_volume=100.0,
            breakout_quality=100.0,
            trend_quality=100.0,
            market_alignment=100.0,
        )
        assert score(inputs) == 100.0

    def test_known_values(self):
        """Verify composite calculation with specific known inputs."""
        inputs = ScoreInputs(
            relative_strength=80.0,
            relative_volume=60.0,
            breakout_quality=70.0,
            trend_quality=50.0,
            market_alignment=90.0,
        )
        # 80*0.30 + 60*0.25 + 70*0.20 + 50*0.15 + 90*0.10
        # = 24 + 15 + 14 + 7.5 + 9 = 69.5
        assert score(inputs) == 69.5

    def test_weights_sum_to_one(self):
        """Verify that all weights sum to 1.0."""
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 1e-10

    def test_rounding_to_two_decimals(self):
        """Score is rounded to exactly 2 decimal places."""
        inputs = ScoreInputs(
            relative_strength=33.33,
            relative_volume=66.67,
            breakout_quality=11.11,
            trend_quality=44.44,
            market_alignment=77.77,
        )
        result = score(inputs)
        # Verify it's rounded to 2 decimal places
        assert result == round(result, 2)

    def test_clamping_above_100(self):
        """Inputs above 100 are clamped to 100."""
        inputs = ScoreInputs(
            relative_strength=150.0,
            relative_volume=200.0,
            breakout_quality=100.0,
            trend_quality=100.0,
            market_alignment=100.0,
        )
        # Clamped: 100*0.30 + 100*0.25 + 100*0.20 + 100*0.15 + 100*0.10 = 100
        assert score(inputs) == 100.0

    def test_clamping_below_zero(self):
        """Inputs below 0 are clamped to 0."""
        inputs = ScoreInputs(
            relative_strength=-10.0,
            relative_volume=-5.0,
            breakout_quality=50.0,
            trend_quality=50.0,
            market_alignment=50.0,
        )
        # Clamped: 0*0.30 + 0*0.25 + 50*0.20 + 50*0.15 + 50*0.10
        # = 0 + 0 + 10 + 7.5 + 5 = 22.5
        assert score(inputs) == 22.5

    def test_single_dimension_contribution(self):
        """Only one dimension at 100, rest at 0 gives that dimension's weight * 100."""
        # RS only
        inputs = ScoreInputs(relative_strength=100.0)
        assert score(inputs) == 30.0

        # RVOL only
        inputs = ScoreInputs(relative_volume=100.0)
        assert score(inputs) == 25.0

        # Breakout quality only
        inputs = ScoreInputs(breakout_quality=100.0)
        assert score(inputs) == 20.0

        # Trend quality only
        inputs = ScoreInputs(trend_quality=100.0)
        assert score(inputs) == 15.0

        # Market alignment only
        inputs = ScoreInputs(market_alignment=100.0)
        assert score(inputs) == 10.0


class TestClamp:
    """Tests for the _clamp helper."""

    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_above_max(self):
        assert _clamp(150.0) == 100.0

    def test_below_min(self):
        assert _clamp(-10.0) == 0.0


class TestNormalizeInputs:
    """Tests for the normalize_inputs function."""

    def test_basic_normalization(self):
        """Min maps to 0, max maps to 100."""
        raw = {"relative_strength": [10.0, 50.0, 90.0]}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 100.0  # 90 is max

    def test_min_value_normalizes_to_zero(self):
        """The minimum value in the set normalizes to 0."""
        raw = {"relative_strength": [50.0, 90.0, 10.0]}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 0.0  # 10 is min and is last

    def test_middle_value(self):
        """A middle value normalizes proportionally."""
        raw = {"relative_strength": [0.0, 100.0, 50.0]}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 50.0

    def test_identical_values_normalize_to_50(self):
        """When all values are the same, normalize to 50."""
        raw = {"relative_strength": [42.0, 42.0, 42.0]}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 50.0

    def test_empty_list_returns_zero(self):
        """Empty value list returns 0."""
        raw = {"relative_strength": []}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 0.0

    def test_single_value_normalizes_to_50(self):
        """A single value (min == max) normalizes to 50."""
        raw = {"relative_strength": [75.0]}
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 50.0

    def test_multiple_dimensions(self):
        """Multiple dimensions are normalized independently."""
        raw = {
            "relative_strength": [10.0, 90.0, 50.0],
            "relative_volume": [1.0, 3.0, 2.0],
        }
        result = normalize_inputs(raw)
        assert result["relative_strength"] == 50.0  # (50-10)/(90-10) * 100
        assert result["relative_volume"] == 50.0  # (2-1)/(3-1) * 100


class TestNormalizeRvol:
    """Tests for the normalize_rvol function.

    Requirements: 14.1, 14.2, 14.3, 14.5, 14.6
    """

    def test_rvol_1_maps_to_0(self):
        """RVOL of 1.0 maps to normalized score of 0."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(1.0, 30) == 0.0

    def test_rvol_3_maps_to_100(self):
        """RVOL of 3.0 maps to normalized score of 100."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(3.0, 30) == 100.0

    def test_rvol_2_maps_to_50(self):
        """RVOL of 2.0 maps to normalized score of 50 (midpoint)."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(2.0, 30) == 50.0

    def test_linear_interpolation(self):
        """RVOL of 1.5 maps to 25, RVOL of 2.5 maps to 75."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(1.5, 30) == 25.0
        assert normalize_rvol(2.5, 30) == 75.0

    def test_rvol_above_3_clamped_to_100(self):
        """RVOL above 3.0 is clamped to 100."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(5.0, 30) == 100.0
        assert normalize_rvol(10.0, 50) == 100.0

    def test_rvol_below_1_returns_0(self):
        """RVOL below 1.0 (but positive) returns 0 — below baseline."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(0.5, 30) == 0.0
        assert normalize_rvol(0.99, 30) == 0.0

    def test_insufficient_history_returns_none(self):
        """Fewer than 30 periods of volume history returns None."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(2.0, 29) is None
        assert normalize_rvol(2.0, 0) is None
        assert normalize_rvol(2.0, 10) is None

    def test_exactly_30_periods_is_sufficient(self):
        """Exactly 30 periods is the minimum — should return a value."""
        from scoring.scoring_engine import normalize_rvol

        result = normalize_rvol(2.0, 30)
        assert result is not None
        assert result == 50.0

    def test_zero_rvol_returns_none(self):
        """RVOL of 0 is invalid (zero volume) — returns None."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(0.0, 30) is None

    def test_negative_rvol_returns_none(self):
        """Negative RVOL is invalid — returns None."""
        from scoring.scoring_engine import normalize_rvol

        assert normalize_rvol(-1.0, 30) is None
        assert normalize_rvol(-0.5, 50) is None


class TestCalculateRiskLevels:
    """Tests for the calculate_risk_levels function.

    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.5
    """

    def test_atr_stop_wider_than_structure(self):
        """When ATR stop is lower (wider) than structure stop, ATR stop is used."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, structure_stop=97, atr_stop = 100 - 1.2*5 = 94
        result = calculate_risk_levels(entry_price=100.0, structure_stop=97.0, atr14=5.0)
        assert result is not None
        assert result["stop_loss"] == 94.0  # ATR stop is wider (lower)
        assert result["risk"] == 6.0
        assert result["target_1"] == 106.0  # entry + 1R
        assert result["target_2"] == 112.0  # entry + 2R
        assert result["risk_reward"] == 2.0

    def test_structure_stop_wider_than_atr(self):
        """When structure stop is lower (wider) than ATR stop, structure stop is used."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, structure_stop=90, atr_stop = 100 - 1.2*2 = 97.6
        result = calculate_risk_levels(entry_price=100.0, structure_stop=90.0, atr14=2.0)
        assert result is not None
        assert result["stop_loss"] == 90.0  # Structure stop is wider (lower)
        assert result["risk"] == 10.0
        assert result["target_1"] == 110.0
        assert result["target_2"] == 120.0
        assert result["risk_reward"] == 2.0

    def test_risk_reward_always_2(self):
        """Risk-reward is always 2.0 by construction (target_2 = entry + 2R)."""
        from scoring.scoring_engine import calculate_risk_levels

        result = calculate_risk_levels(entry_price=50000.0, structure_stop=49000.0, atr14=1000.0)
        assert result is not None
        assert result["risk_reward"] == 2.0

    def test_risk_percent_calculation(self):
        """Risk percent is correctly calculated as (risk / entry) * 100."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, stop=94, risk=6, risk_percent = 6/100 * 100 = 6.0%
        result = calculate_risk_levels(entry_price=100.0, structure_stop=97.0, atr14=5.0)
        assert result is not None
        assert result["risk_percent"] == 6.0

    def test_zero_risk_returns_none(self):
        """When stop equals entry (risk=0), returns None."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, structure_stop=100, atr_stop = 100 - 1.2*0 = 100
        result = calculate_risk_levels(entry_price=100.0, structure_stop=100.0, atr14=0.0)
        assert result is None

    def test_negative_risk_returns_none(self):
        """When stop is above entry (negative risk), returns None."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, structure_stop=105 (above entry), atr_stop = 100 - 1.2*(-5) = 106
        # Both stops above entry → risk is negative
        result = calculate_risk_levels(entry_price=100.0, structure_stop=105.0, atr14=-5.0)
        assert result is None

    def test_equal_stops(self):
        """When ATR stop and structure stop are equal, either is used."""
        from scoring.scoring_engine import calculate_risk_levels

        # entry=100, structure_stop=94, atr_stop = 100 - 1.2*5 = 94
        result = calculate_risk_levels(entry_price=100.0, structure_stop=94.0, atr14=5.0)
        assert result is not None
        assert result["stop_loss"] == 94.0
        assert result["risk"] == 6.0

    def test_realistic_crypto_values(self):
        """Test with realistic crypto price values (BTC-like)."""
        from scoring.scoring_engine import calculate_risk_levels

        # BTC at 67000, structure stop at 66000, ATR14 = 1200
        # atr_stop = 67000 - 1.2*1200 = 67000 - 1440 = 65560
        result = calculate_risk_levels(entry_price=67000.0, structure_stop=66000.0, atr14=1200.0)
        assert result is not None
        assert result["stop_loss"] == 65560.0  # ATR stop is wider
        assert result["risk"] == 1440.0
        assert result["target_1"] == 68440.0
        assert result["target_2"] == 69880.0
        assert result["risk_reward"] == 2.0
        # risk_percent = 1440/67000 * 100 ≈ 2.149%
        assert abs(result["risk_percent"] - (1440.0 / 67000.0 * 100.0)) < 1e-10


class TestApplyOiAdjustments:
    """Tests for the apply_oi_adjustments function.

    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
    """

    def test_no_adjustments_when_data_unavailable(self):
        """When data_available is False, score is returned unchanged."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=True,
            weak_oi_participation=True,
            data_available=False,
        )
        assert apply_oi_adjustments(80.0, oi_data) == 80.0

    def test_overcrowded_reduces_by_20_percent(self):
        """Extreme funding reduces score by 20%."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=True,
            weak_oi_participation=False,
            data_available=True,
        )
        # 80 * 0.80 = 64.0
        assert apply_oi_adjustments(80.0, oi_data) == 64.0

    def test_weak_oi_reduces_by_15_percent(self):
        """Declining OI with rising price reduces score by 15%."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=False,
            weak_oi_participation=True,
            data_available=True,
        )
        # 80 * 0.85 = 68.0
        assert apply_oi_adjustments(80.0, oi_data) == 68.0

    def test_both_conditions_multiplicative(self):
        """Both overcrowded and weak OI apply multiplicatively."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=True,
            weak_oi_participation=True,
            data_available=True,
        )
        # 80 * 0.80 * 0.85 = 54.4
        assert apply_oi_adjustments(80.0, oi_data) == 54.4

    def test_no_conditions_no_adjustment(self):
        """When neither condition is true, score is unchanged."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=False,
            weak_oi_participation=False,
            data_available=True,
        )
        assert apply_oi_adjustments(80.0, oi_data) == 80.0

    def test_result_rounded_to_2_decimals(self):
        """Result is always rounded to 2 decimal places."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=True,
            weak_oi_participation=True,
            data_available=True,
        )
        # 73.33 * 0.80 * 0.85 = 49.8644
        result = apply_oi_adjustments(73.33, oi_data)
        assert result == round(result, 2)

    def test_zero_score_remains_zero(self):
        """A score of 0 remains 0 regardless of adjustments."""
        from scoring.scoring_engine import apply_oi_adjustments
        from streaming.models import OIFundingData

        oi_data = OIFundingData(
            is_overcrowded=True,
            weak_oi_participation=True,
            data_available=True,
        )
        assert apply_oi_adjustments(0.0, oi_data) == 0.0


class TestRankSetups:
    """Tests for the rank_setups function.

    Requirements: 12.3, 12.4, 12.5
    """

    def test_returns_top_5(self):
        """Returns only top 5 setups when more than 5 are provided."""
        from scoring.scoring_engine import rank_setups
        from streaming.models import ScoredSetup, SetupSignal, SetupType, ScoreInputs

        setups = []
        for i in range(8):
            signal = SetupSignal(symbol=f"COIN{i}", setup_type=SetupType.COMPRESSION_BREAKOUT, entry_price=100.0, stop_loss=95.0, target_1=105.0)
            scored = ScoredSetup(
                signal=signal,
                composite_score=float(i * 10),
                inputs=ScoreInputs(relative_volume=float(i)),
            )
            setups.append(scored)

        result = rank_setups(setups)
        assert len(result) == 5

    def test_sorted_descending_by_score(self):
        """Setups are sorted by composite_score in descending order."""
        from scoring.scoring_engine import rank_setups
        from streaming.models import ScoredSetup, SetupSignal, SetupType, ScoreInputs

        setups = []
        for score_val in [30.0, 90.0, 50.0, 70.0, 10.0]:
            signal = SetupSignal(symbol="TEST", setup_type=SetupType.COMPRESSION_BREAKOUT, entry_price=100.0, stop_loss=95.0, target_1=105.0)
            scored = ScoredSetup(
                signal=signal,
                composite_score=score_val,
                inputs=ScoreInputs(relative_volume=50.0),
            )
            setups.append(scored)

        result = rank_setups(setups)
        scores = [s.composite_score for s in result]
        assert scores == sorted(scores, reverse=True)

    def test_tie_break_by_relative_volume(self):
        """When scores are tied, higher relative_volume wins."""
        from scoring.scoring_engine import rank_setups
        from streaming.models import ScoredSetup, SetupSignal, SetupType, ScoreInputs

        signal_a = SetupSignal(symbol="COIN_A", setup_type=SetupType.COMPRESSION_BREAKOUT, entry_price=100.0, stop_loss=95.0, target_1=105.0)
        signal_b = SetupSignal(symbol="COIN_B", setup_type=SetupType.COMPRESSION_BREAKOUT, entry_price=100.0, stop_loss=95.0, target_1=105.0)

        setup_a = ScoredSetup(
            signal=signal_a,
            composite_score=75.0,
            inputs=ScoreInputs(relative_volume=30.0),
        )
        setup_b = ScoredSetup(
            signal=signal_b,
            composite_score=75.0,
            inputs=ScoreInputs(relative_volume=80.0),
        )

        result = rank_setups([setup_a, setup_b])
        assert result[0].signal.symbol == "COIN_B"  # Higher volume wins tie
        assert result[1].signal.symbol == "COIN_A"

    def test_fewer_than_5_returns_all(self):
        """When fewer than 5 setups exist, all are returned."""
        from scoring.scoring_engine import rank_setups
        from streaming.models import ScoredSetup, SetupSignal, SetupType, ScoreInputs

        setups = []
        for i in range(3):
            signal = SetupSignal(symbol=f"COIN{i}", setup_type=SetupType.COMPRESSION_BREAKOUT, entry_price=100.0, stop_loss=95.0, target_1=105.0)
            scored = ScoredSetup(
                signal=signal,
                composite_score=float(i * 10),
                inputs=ScoreInputs(relative_volume=50.0),
            )
            setups.append(scored)

        result = rank_setups(setups)
        assert len(result) == 3

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        from scoring.scoring_engine import rank_setups

        result = rank_setups([])
        assert result == []

    def test_single_setup_returned(self):
        """A single setup is returned as-is."""
        from scoring.scoring_engine import rank_setups
        from streaming.models import ScoredSetup, SetupSignal, SetupType, ScoreInputs

        signal = SetupSignal(symbol="SOLO", setup_type=SetupType.PULLBACK_CONTINUATION, entry_price=100.0, stop_loss=95.0, target_1=105.0)
        setup = ScoredSetup(
            signal=signal,
            composite_score=85.0,
            inputs=ScoreInputs(relative_volume=60.0),
        )

        result = rank_setups([setup])
        assert len(result) == 1
        assert result[0].signal.symbol == "SOLO"
