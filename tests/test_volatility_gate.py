"""
Unit tests for VolatilityGate filter.

Tests the ATR14/price ratio calculation and threshold logic.
Requirements: 5.1, 5.2, 5.3, 5.4
"""

import pytest

from filters.volatility_gate import VolatilityGate


class TestVolatilityGate:
    """Tests for VolatilityGate.evaluate()."""

    def setup_method(self):
        """Create a VolatilityGate with default thresholds."""
        self.gate = VolatilityGate(min_ratio_pct=1.5, max_ratio_pct=8.0)

    def test_ratio_within_bounds_passes(self):
        """Coin with ratio in [1.5%, 8.0%] should pass."""
        # ATR14=500, price=10000 → ratio = 5.0%
        passed, ratio = self.gate.evaluate(atr14=500.0, current_price=10000.0)
        assert passed is True
        assert ratio == pytest.approx(5.0)

    def test_ratio_at_lower_bound_passes(self):
        """Coin with ratio exactly at 1.5% should pass (inclusive)."""
        # ATR14=150, price=10000 → ratio = 1.5%
        passed, ratio = self.gate.evaluate(atr14=150.0, current_price=10000.0)
        assert passed is True
        assert ratio == pytest.approx(1.5)

    def test_ratio_at_upper_bound_passes(self):
        """Coin with ratio exactly at 8.0% should pass (inclusive)."""
        # ATR14=800, price=10000 → ratio = 8.0%
        passed, ratio = self.gate.evaluate(atr14=800.0, current_price=10000.0)
        assert passed is True
        assert ratio == pytest.approx(8.0)

    def test_ratio_below_minimum_fails(self):
        """Coin with ratio below 1.5% should be rejected (dead coin)."""
        # ATR14=100, price=10000 → ratio = 1.0%
        passed, ratio = self.gate.evaluate(atr14=100.0, current_price=10000.0)
        assert passed is False
        assert ratio == pytest.approx(1.0)

    def test_ratio_above_maximum_fails(self):
        """Coin with ratio above 8.0% should be rejected (pump coin)."""
        # ATR14=1000, price=10000 → ratio = 10.0%
        passed, ratio = self.gate.evaluate(atr14=1000.0, current_price=10000.0)
        assert passed is False
        assert ratio == pytest.approx(10.0)

    def test_ratio_just_below_minimum_fails(self):
        """Coin with ratio just below 1.5% should be rejected."""
        # ATR14=149, price=10000 → ratio = 1.49%
        passed, ratio = self.gate.evaluate(atr14=149.0, current_price=10000.0)
        assert passed is False
        assert ratio == pytest.approx(1.49)

    def test_ratio_just_above_maximum_fails(self):
        """Coin with ratio just above 8.0% should be rejected."""
        # ATR14=801, price=10000 → ratio = 8.01%
        passed, ratio = self.gate.evaluate(atr14=801.0, current_price=10000.0)
        assert passed is False
        assert ratio == pytest.approx(8.01)

    def test_custom_thresholds(self):
        """Custom min/max thresholds should be respected."""
        gate = VolatilityGate(min_ratio_pct=2.0, max_ratio_pct=6.0)

        # 1.5% is below custom min of 2.0%
        passed, ratio = gate.evaluate(atr14=150.0, current_price=10000.0)
        assert passed is False
        assert ratio == pytest.approx(1.5)

        # 3.0% is within custom bounds
        passed, ratio = gate.evaluate(atr14=300.0, current_price=10000.0)
        assert passed is True
        assert ratio == pytest.approx(3.0)

    def test_ratio_calculation_correctness(self):
        """Verify ratio = (ATR14 / price) × 100."""
        # ATR14=0.05, price=1.0 → ratio = 5.0%
        passed, ratio = self.gate.evaluate(atr14=0.05, current_price=1.0)
        assert ratio == pytest.approx(5.0)

        # ATR14=2500, price=50000 → ratio = 5.0%
        passed, ratio = self.gate.evaluate(atr14=2500.0, current_price=50000.0)
        assert ratio == pytest.approx(5.0)
