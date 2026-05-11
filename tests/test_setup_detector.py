"""
Unit tests for Compression Breakout detection in SetupDetector.

Tests compression zone identification, breakout validation, and zone expiry.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

import pytest
from datetime import datetime, timedelta

from streaming.models import OHLCV
from streaming.models import CompressionZone, SetupType, SetupState
from detectors.setup_detector import (
    detect_compression_breakout,
    _detect_compression_zone,
    _calculate_atr14,
    _calculate_volume_ma30,
    _is_decreasing_sell_pressure,
)


def _make_candle(
    timestamp: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> OHLCV:
    """Helper to create a single OHLCV candle."""
    return OHLCV(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_normal_candles(
    count: int,
    base_price: float = 100.0,
    volatility: float = 2.0,
    base_volume: float = 1000.0,
    start_time: datetime = None,
) -> list:
    """
    Generate normal-volatility candles (for ATR14 baseline).

    Each candle has a range of approximately `volatility`.
    """
    if start_time is None:
        start_time = datetime(2024, 1, 1)

    candles = []
    for i in range(count):
        mid = base_price + (i * 0.1)
        open_price = mid - volatility * 0.2
        close = mid + volatility * 0.2
        high = mid + volatility / 2
        low = mid - volatility / 2
        volume = base_volume + (i * 5)

        candles.append(
            _make_candle(
                timestamp=start_time + timedelta(hours=i),
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return candles


def _make_compressed_candles(
    count: int,
    base_price: float = 100.0,
    narrow_range: float = 0.5,
    base_volume: float = 800.0,
    start_time: datetime = None,
) -> list:
    """
    Generate compressed candles with narrow range (for compression zone).

    Each candle has a range of `narrow_range`, closing in upper half.
    """
    if start_time is None:
        start_time = datetime(2024, 6, 1)

    candles = []
    for i in range(count):
        mid = base_price
        low = mid - narrow_range / 2
        high = mid + narrow_range / 2
        # Close in upper 50% to satisfy decreasing sell pressure
        close = mid + narrow_range * 0.2
        open_price = mid - narrow_range * 0.1
        # Decreasing volume
        volume = base_volume - (i * 50)

        candles.append(
            _make_candle(
                timestamp=start_time + timedelta(hours=i),
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                volume=max(volume, 100.0),
            )
        )
    return candles


def _build_test_candles_with_breakout(
    normal_count: int = 25,
    compressed_count: int = 5,
    breakout_volume_multiplier: float = 2.0,
) -> list:
    """
    Build a full candle sequence: normal candles + compressed zone + breakout candle.

    Returns a list of candles where the last candle is a valid breakout.
    """
    start = datetime(2024, 1, 1)

    # Normal candles to establish ATR14 baseline
    normal = _make_normal_candles(
        count=normal_count,
        base_price=100.0,
        volatility=2.0,
        base_volume=1000.0,
        start_time=start,
    )

    # Compressed candles (narrow range)
    compressed_start = start + timedelta(hours=normal_count)
    compressed = _make_compressed_candles(
        count=compressed_count,
        base_price=100.0,
        narrow_range=0.5,
        base_volume=800.0,
        start_time=compressed_start,
    )

    # Breakout candle: closes above zone high, in upper 33%, high volume
    zone_high = max(c.high for c in compressed)
    breakout_time = compressed_start + timedelta(hours=compressed_count)

    # Calculate expected volume MA30 (approximate)
    all_prior = normal + compressed
    avg_volume = sum(c.volume for c in all_prior[-30:]) / min(len(all_prior), 30)
    breakout_volume = avg_volume * breakout_volume_multiplier

    # Breakout candle: strong bullish, close in upper 33%
    breakout_low = zone_high - 0.3
    breakout_high = zone_high + 2.0
    breakout_close = zone_high + 1.5  # Close well above zone high, in upper 33%
    breakout_open = zone_high + 0.2

    breakout_candle = _make_candle(
        timestamp=breakout_time,
        open_price=breakout_open,
        high=breakout_high,
        low=breakout_low,
        close=breakout_close,
        volume=breakout_volume,
    )

    return normal + compressed + [breakout_candle]


class TestATR14Calculation:
    """Tests for ATR14 calculation helper."""

    def test_returns_none_with_insufficient_candles(self):
        """ATR14 needs at least 15 candles."""
        candles = _make_normal_candles(count=10)
        assert _calculate_atr14(candles) is None

    def test_returns_value_with_sufficient_candles(self):
        """ATR14 returns a positive float with enough data."""
        candles = _make_normal_candles(count=20, volatility=2.0)
        atr = _calculate_atr14(candles)
        assert atr is not None
        assert atr > 0

    def test_higher_volatility_gives_higher_atr(self):
        """Higher volatility candles should produce higher ATR."""
        low_vol = _make_normal_candles(count=20, volatility=1.0)
        high_vol = _make_normal_candles(count=20, volatility=5.0)
        assert _calculate_atr14(high_vol) > _calculate_atr14(low_vol)


class TestVolumeMA30:
    """Tests for volume MA30 calculation."""

    def test_returns_none_with_insufficient_candles(self):
        """Volume MA30 needs at least 30 candles."""
        candles = _make_normal_candles(count=20)
        assert _calculate_volume_ma30(candles) is None

    def test_returns_value_with_sufficient_candles(self):
        """Volume MA30 returns a positive float with enough data."""
        candles = _make_normal_candles(count=35, base_volume=1000.0)
        ma = _calculate_volume_ma30(candles)
        assert ma is not None
        assert ma > 0


class TestDecreasingSellingPressure:
    """Tests for sell pressure detection within compression zones."""

    def test_candles_closing_in_upper_half(self):
        """Candles closing in upper 50% satisfy the condition."""
        candles = _make_compressed_candles(count=5, base_price=100.0)
        assert _is_decreasing_sell_pressure(candles) is True

    def test_single_candle_always_passes(self):
        """A single candle trivially passes."""
        candle = _make_candle(
            datetime(2024, 1, 1), 100.0, 101.0, 99.0, 99.5, 1000.0
        )
        assert _is_decreasing_sell_pressure([candle]) is True


class TestCompressionZoneDetection:
    """Tests for compression zone identification (Requirement 6.1)."""

    def test_detects_zone_with_3_compressed_candles(self):
        """Minimum 3 compressed candles should form a zone."""
        # Normal candles for ATR baseline + 3 compressed + 1 extra (breakout slot)
        normal = _make_normal_candles(count=20, volatility=2.0)
        compressed = _make_compressed_candles(count=3, narrow_range=0.5)
        # Add a dummy last candle (breakout slot)
        dummy = _make_candle(
            datetime(2024, 7, 1), 100.0, 102.0, 99.0, 101.5, 2000.0
        )
        candles = normal + compressed + [dummy]

        atr14 = _calculate_atr14(candles)
        assert atr14 is not None

        zone = _detect_compression_zone(candles, atr14)
        assert zone is not None
        assert zone.candle_count >= 3

    def test_no_zone_with_only_2_compressed_candles(self):
        """Fewer than 3 compressed candles should not form a zone."""
        normal = _make_normal_candles(count=20, volatility=2.0)
        compressed = _make_compressed_candles(count=2, narrow_range=0.5)
        dummy = _make_candle(
            datetime(2024, 7, 1), 100.0, 102.0, 99.0, 101.5, 2000.0
        )
        candles = normal + compressed + [dummy]

        atr14 = _calculate_atr14(candles)
        zone = _detect_compression_zone(candles, atr14)
        assert zone is None

    def test_zone_capped_at_8_candles(self):
        """Zone should not exceed 8 candles even if more are compressed."""
        normal = _make_normal_candles(count=20, volatility=2.0)
        compressed = _make_compressed_candles(count=12, narrow_range=0.5)
        dummy = _make_candle(
            datetime(2024, 7, 1), 100.0, 102.0, 99.0, 101.5, 2000.0
        )
        candles = normal + compressed + [dummy]

        atr14 = _calculate_atr14(candles)
        zone = _detect_compression_zone(candles, atr14)
        assert zone is not None
        assert zone.candle_count <= 8

    def test_zone_high_low_correct(self):
        """Zone high/low should be the max high and min low of zone candles."""
        normal = _make_normal_candles(count=20, volatility=2.0)
        compressed = _make_compressed_candles(count=5, narrow_range=0.5)
        dummy = _make_candle(
            datetime(2024, 7, 1), 100.0, 102.0, 99.0, 101.5, 2000.0
        )
        candles = normal + compressed + [dummy]

        atr14 = _calculate_atr14(candles)
        zone = _detect_compression_zone(candles, atr14)
        assert zone is not None

        expected_high = max(c.high for c in compressed)
        expected_low = min(c.low for c in compressed)
        assert zone.high == pytest.approx(expected_high)
        assert zone.low == pytest.approx(expected_low)


class TestBreakoutDetection:
    """Tests for breakout validation (Requirements 6.3, 6.4, 6.5, 6.6)."""

    def test_valid_breakout_returns_setup(self):
        """A valid breakout should return an ActiveSetup."""
        candles = _build_test_candles_with_breakout(
            normal_count=25,
            compressed_count=5,
            breakout_volume_multiplier=2.0,
        )
        result = detect_compression_breakout(candles)
        assert result is not None
        assert result.setup_type == SetupType.COMPRESSION_BREAKOUT
        assert result.state == SetupState.DETECTED

    def test_entry_price_is_breakout_candle_high(self):
        """Entry should be set at the breakout candle's high (Req 6.5)."""
        candles = _build_test_candles_with_breakout()
        result = detect_compression_breakout(candles)
        assert result is not None
        assert result.entry_price == candles[-1].high

    def test_stop_loss_is_min_of_zone_low_and_atr_stop(self):
        """Stop-loss should be min(zone_low, entry - 1.2*ATR14) (Req 6.6)."""
        candles = _build_test_candles_with_breakout()
        result = detect_compression_breakout(candles)
        assert result is not None

        atr14 = _calculate_atr14(candles)
        entry = candles[-1].high
        atr_stop = entry - 1.2 * atr14

        # Stop should be the lower of zone low and ATR stop
        assert result.stop_loss <= entry
        assert result.stop_loss == pytest.approx(
            min(result.compression_zone.low, atr_stop)
        )

    def test_no_breakout_when_close_below_zone_high(self):
        """No breakout if candle closes below zone high."""
        normal = _make_normal_candles(count=25, volatility=2.0)
        compressed = _make_compressed_candles(count=5, narrow_range=0.5)
        zone_high = max(c.high for c in compressed)

        # Candle that closes below zone high
        weak_candle = _make_candle(
            datetime(2024, 7, 1),
            zone_high - 0.5,
            zone_high + 0.1,
            zone_high - 1.0,
            zone_high - 0.2,  # Close below zone high
            5000.0,
        )
        candles = normal + compressed + [weak_candle]
        result = detect_compression_breakout(candles)
        assert result is None

    def test_no_breakout_when_volume_insufficient(self):
        """No breakout if volume <= 1.5x MA30."""
        candles = _build_test_candles_with_breakout(
            breakout_volume_multiplier=1.0,  # Not enough volume
        )
        result = detect_compression_breakout(candles)
        assert result is None

    def test_no_breakout_when_close_not_in_upper_third(self):
        """No breakout if close is not in upper 33% of candle range (Req 6.4)."""
        normal = _make_normal_candles(count=25, volatility=2.0)
        compressed = _make_compressed_candles(count=5, narrow_range=0.5)
        zone_high = max(c.high for c in compressed)

        # Candle that closes above zone high but in lower portion of its range
        avg_vol = sum(c.volume for c in (normal + compressed)[-30:]) / 30
        bad_close_candle = _make_candle(
            datetime(2024, 7, 1),
            zone_high + 1.5,  # Open high
            zone_high + 2.0,  # High
            zone_high - 1.0,  # Low
            zone_high + 0.1,  # Close barely above zone high, in lower portion
            avg_vol * 2.0,
        )
        candles = normal + compressed + [bad_close_candle]
        result = detect_compression_breakout(candles)
        assert result is None


class TestZoneExpiry:
    """Tests for zone expiry after 12 candles (Requirement 6.7)."""

    def test_zone_expires_after_12_candles(self):
        """Zone should expire when candles_since_zone >= 12."""
        zone = CompressionZone(
            high=100.25,
            low=99.75,
            candle_count=5,
            start_atr14=2.0,
            candles=[],
            expired=False,
        )
        candles = _make_normal_candles(count=30, volatility=2.0)

        result = detect_compression_breakout(
            candles, candles_since_zone=12, existing_zone=zone
        )
        assert result is None
        assert zone.expired is True

    def test_zone_not_expired_before_12_candles(self):
        """Zone should remain active before 12 candles."""
        normal = _make_normal_candles(count=25, volatility=2.0)
        compressed = _make_compressed_candles(count=5, narrow_range=0.5)
        zone_high = max(c.high for c in compressed)

        zone = CompressionZone(
            high=zone_high,
            low=min(c.low for c in compressed),
            candle_count=5,
            start_atr14=2.0,
            candles=compressed,
            expired=False,
        )

        # Build a breakout candle
        avg_vol = sum(c.volume for c in (normal + compressed)[-30:]) / 30
        breakout = _make_candle(
            datetime(2024, 7, 1),
            zone_high + 0.2,
            zone_high + 2.0,
            zone_high - 0.3,
            zone_high + 1.5,
            avg_vol * 2.0,
        )
        candles = normal + compressed + [breakout]

        result = detect_compression_breakout(
            candles, candles_since_zone=5, existing_zone=zone
        )
        # Should detect breakout since zone is still active
        assert result is not None
        assert zone.expired is False


class TestInsufficientData:
    """Tests for edge cases with insufficient data."""

    def test_returns_none_with_too_few_candles(self):
        """Should return None with fewer than 30 candles."""
        candles = _make_normal_candles(count=10)
        result = detect_compression_breakout(candles)
        assert result is None

    def test_returns_none_when_no_compression_zone(self):
        """Should return None when all candles are normal volatility."""
        candles = _make_normal_candles(count=35, volatility=2.0)
        result = detect_compression_breakout(candles)
        assert result is None



# ─── 15m Entry Trigger Confirmation Tests (Requirements 8.1-8.5) ─────────────

from streaming.models import PendingTrigger
from detectors.setup_detector import check_15m_trigger


def _make_15m_candle_history(
    count: int = 35,
    base_price: float = 100.0,
    base_volume: float = 500.0,
    start_time: datetime = None,
) -> list:
    """Generate 15m candle history for volume MA30 calculation."""
    if start_time is None:
        start_time = datetime(2024, 1, 1)

    candles = []
    for i in range(count):
        mid = base_price + (i * 0.05)
        candles.append(
            _make_candle(
                timestamp=start_time + timedelta(minutes=15 * i),
                open_price=mid - 0.3,
                high=mid + 0.5,
                low=mid - 0.5,
                close=mid + 0.3,
                volume=base_volume,
            )
        )
    return candles


def _make_pending_trigger(
    symbol: str = "ETHUSDT",
    entry_price: float = 102.0,
    stop_loss: float = 98.0,
    target_1: float = 106.0,
    target_2: float = 110.0,
    candles_remaining: int = 4,
) -> PendingTrigger:
    """Helper to create a PendingTrigger for testing."""
    return PendingTrigger(
        symbol=symbol,
        setup_type=SetupType.COMPRESSION_BREAKOUT,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        candles_remaining=candles_remaining,
        created_at=datetime(2024, 6, 1, 12, 0, 0),
    )


class TestCheck15mTriggerConfirmation:
    """Tests for 15m entry trigger confirmation (Requirement 8.2)."""

    def test_confirms_when_price_and_volume_pass(self):
        """Trigger confirms when close > entry AND volume > 1.5x MA30."""
        pending = _make_pending_trigger(entry_price=102.0)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # Confirming candle: close above entry, volume well above 1.5x MA30
        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,  # Above entry of 102.0
            volume=900.0,  # 1.8x the MA30 of 500
        )

        result = check_15m_trigger(confirm_candle, pending, candles_15m)
        assert result is not None
        assert result.state == SetupState.CONFIRMED
        assert result.symbol == "ETHUSDT"
        assert result.entry_price == 102.0
        assert result.stop_loss == 98.0
        assert result.confirmed_at is not None

    def test_confirmed_setup_has_correct_targets(self):
        """Confirmed setup preserves target levels from pending trigger."""
        pending = _make_pending_trigger(
            entry_price=102.0, target_1=106.0, target_2=110.0
        )
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,
            volume=900.0,
        )

        result = check_15m_trigger(confirm_candle, pending, candles_15m)
        assert result is not None
        assert result.target_1 == 106.0
        assert result.target_2 == 110.0


class TestCheck15mTriggerRejection:
    """Tests for 15m trigger rejection with insufficient volume (Req 8.4)."""

    def test_rejects_when_volume_insufficient(self):
        """Price above entry but volume <= 1.5x MA30 should reject, not expire."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # Candle with price above entry but low volume
        low_vol_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,  # Above entry
            volume=600.0,  # Only 1.2x MA30, below 1.5x threshold
        )

        result = check_15m_trigger(low_vol_candle, pending, candles_15m)
        assert result is None
        # Should decrement but not fully expire
        assert pending.candles_remaining == 3

    def test_rejection_does_not_prevent_later_confirmation(self):
        """After a rejection, a subsequent valid candle can still confirm."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # First candle: rejected (low volume)
        low_vol_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,
            volume=600.0,
        )
        result = check_15m_trigger(low_vol_candle, pending, candles_15m)
        assert result is None
        assert pending.candles_remaining == 3

        # Second candle: valid confirmation
        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 30),
            open_price=102.0,
            high=103.5,
            low=101.5,
            close=102.8,
            volume=900.0,
        )
        result = check_15m_trigger(confirm_candle, pending, candles_15m)
        assert result is not None
        assert result.state == SetupState.CONFIRMED


class TestCheck15mTriggerExpiry:
    """Tests for 15m trigger expiry after 4 candles (Requirement 8.3)."""

    def test_expires_after_4_candles_without_confirmation(self):
        """Trigger should expire after 4 candles pass without confirmation."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # 4 candles that don't confirm (price below entry)
        base_time = datetime(2024, 6, 1, 12, 0)
        for i in range(4):
            candle = _make_candle(
                timestamp=base_time + timedelta(minutes=15 * (i + 1)),
                open_price=100.0,
                high=101.0,
                low=99.5,
                close=100.5,  # Below entry of 102.0
                volume=500.0,
            )
            result = check_15m_trigger(candle, pending, candles_15m)
            assert result is None

        # After 4 candles, candles_remaining should be 0
        assert pending.candles_remaining == 0

    def test_already_expired_trigger_returns_none(self):
        """A trigger with 0 candles remaining should immediately return None."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=0)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # Even a valid candle should not confirm an expired trigger
        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 13, 0),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,
            volume=900.0,
        )
        result = check_15m_trigger(confirm_candle, pending, candles_15m)
        assert result is None


class TestCheck15mTriggerCancellation:
    """Tests for 15m trigger cancellation on 1H invalidation (Req 8.5)."""

    def test_cancels_when_setup_invalidated(self):
        """Trigger should cancel immediately when parent setup is invalidated."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        # Even with a valid confirming candle, invalidation takes priority
        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,
            volume=900.0,
        )

        result = check_15m_trigger(
            confirm_candle, pending, candles_15m, setup_invalidated=True
        )
        assert result is None
        assert pending.candles_remaining == 0

    def test_cancellation_sets_candles_remaining_to_zero(self):
        """After cancellation, candles_remaining should be 0."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=3)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        candle = _make_candle(
            datetime(2024, 6, 1, 12, 15), 100.0, 101.0, 99.0, 100.5, 500.0
        )
        check_15m_trigger(candle, pending, candles_15m, setup_invalidated=True)
        assert pending.candles_remaining == 0


class TestCheck15mTriggerEdgeCases:
    """Edge case tests for 15m trigger confirmation."""

    def test_returns_none_with_insufficient_volume_history(self):
        """Should not confirm if fewer than 30 candles for MA30."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        # Only 20 candles - insufficient for MA30
        candles_15m = _make_15m_candle_history(count=20, base_volume=500.0)

        confirm_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=101.5,
            high=103.0,
            low=101.0,
            close=102.5,
            volume=900.0,
        )
        result = check_15m_trigger(confirm_candle, pending, candles_15m)
        assert result is None
        # Should still decrement candles_remaining
        assert pending.candles_remaining == 3

    def test_price_below_entry_does_not_confirm(self):
        """Candle closing below entry price should not confirm."""
        pending = _make_pending_trigger(entry_price=102.0, candles_remaining=4)
        candles_15m = _make_15m_candle_history(count=35, base_volume=500.0)

        below_entry_candle = _make_candle(
            timestamp=datetime(2024, 6, 1, 12, 15),
            open_price=100.0,
            high=101.5,
            low=99.5,
            close=101.0,  # Below entry of 102.0
            volume=900.0,  # High volume but price not confirmed
        )
        result = check_15m_trigger(below_entry_candle, pending, candles_15m)
        assert result is None
        assert pending.candles_remaining == 3
