"""
Unit tests for the TrailingStopMonitor class.

Tests the trailing stop logic:
- T1 hit moves stop to breakeven
- T2 hit begins trailing at 1% below highest close
- Trailing stop never decreases
- Exit on trailing stop hit or T3 reached
- Data gap warning after 30 minutes
- Journal outcome recording on exit

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 8.5
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitors.trailing_stop_monitor import TrailingStopMonitor
from streaming.models import OHLCV, MonitoredPosition, SetupSignal, SetupType


@pytest.fixture
def mock_alert_manager():
    """Create a mock AlertManager with async _send_with_retry."""
    manager = MagicMock()
    manager._send_with_retry = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_journal():
    """Create a mock JournalStore."""
    journal = MagicMock()
    journal.record_outcome = MagicMock(return_value=True)
    return journal


@pytest.fixture
def monitor(mock_alert_manager, mock_journal):
    """Create a TrailingStopMonitor instance with mocked dependencies."""
    return TrailingStopMonitor(
        alert_manager=mock_alert_manager,
        journal=mock_journal,
    )


@pytest.fixture
def sample_signal():
    """Create a sample SetupSignal for testing."""
    return SetupSignal(
        symbol="ETHUSDT",
        setup_type=SetupType.MOMENTUM_BREAKOUT,
        entry_price=2000.0,
        stop_loss=1960.0,  # Risk = 40
        target_1=2040.0,   # 1R
        target_2=2080.0,   # 2R
        target_3=2200.0,   # 5R
        risk_reward=1.0,
    )


def make_candle(close: float, timestamp: datetime = None) -> OHLCV:
    """Helper to create a candle with a specific close price."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return OHLCV(
        timestamp=timestamp,
        open=close - 1.0,
        high=close + 5.0,
        low=close - 5.0,
        close=close,
        volume=1000.0,
    )


class TestStartMonitoring:
    """Tests for start_monitoring method."""

    def test_starts_monitoring_valid_signal(self, monitor, sample_signal):
        """Should create a MonitoredPosition from a valid signal."""
        monitor.start_monitoring(sample_signal, "signal-123")

        positions = monitor.get_monitored_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "ETHUSDT"
        assert pos.entry_price == 2000.0
        assert pos.stop_loss == 1960.0
        assert pos.current_stop == 1960.0
        assert pos.target_1 == 2040.0
        assert pos.target_2 == 2080.0
        assert pos.target_3 == 2200.0
        assert pos.signal_id == "signal-123"
        assert pos.t1_hit is False
        assert pos.t2_hit is False
        assert pos.t3_hit is False

    def test_skips_signal_without_t2(self, monitor):
        """Should not monitor if T2 is missing."""
        signal = SetupSignal(
            symbol="BTCUSDT",
            setup_type=SetupType.MOMENTUM_BREAKOUT,
            entry_price=50000.0,
            stop_loss=49000.0,
            target_1=51000.0,
            target_2=None,
            target_3=55000.0,
        )
        monitor.start_monitoring(signal, "signal-456")
        assert len(monitor.get_monitored_positions()) == 0

    def test_skips_signal_without_t3(self, monitor):
        """Should not monitor if T3 is missing."""
        signal = SetupSignal(
            symbol="BTCUSDT",
            setup_type=SetupType.MOMENTUM_BREAKOUT,
            entry_price=50000.0,
            stop_loss=49000.0,
            target_1=51000.0,
            target_2=52000.0,
            target_3=None,
        )
        monitor.start_monitoring(signal, "signal-789")
        assert len(monitor.get_monitored_positions()) == 0


class TestT1Breakeven:
    """Tests for T1 hit → breakeven logic (Requirement 6.2)."""

    @pytest.mark.asyncio
    async def test_t1_hit_moves_stop_to_entry(self, monitor, sample_signal):
        """When price reaches T1, stop should move to entry price."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # Price reaches T1 (2040)
        candle = make_candle(2040.0)
        await monitor.on_15m_candle("ETHUSDT", candle)

        pos = monitor.get_monitored_positions()[0]
        assert pos.t1_hit is True
        assert pos.current_stop == 2000.0  # Entry price (breakeven)

    @pytest.mark.asyncio
    async def test_t1_hit_above_t1(self, monitor, sample_signal):
        """When price exceeds T1, stop should still move to entry."""
        monitor.start_monitoring(sample_signal, "signal-123")

        candle = make_candle(2050.0)
        await monitor.on_15m_candle("ETHUSDT", candle)

        pos = monitor.get_monitored_positions()[0]
        assert pos.t1_hit is True
        assert pos.current_stop == 2000.0

    @pytest.mark.asyncio
    async def test_below_t1_no_change(self, monitor, sample_signal):
        """When price is below T1, stop should remain at original."""
        monitor.start_monitoring(sample_signal, "signal-123")

        candle = make_candle(2020.0)
        await monitor.on_15m_candle("ETHUSDT", candle)

        pos = monitor.get_monitored_positions()[0]
        assert pos.t1_hit is False
        assert pos.current_stop == 1960.0  # Original stop


class TestT2Trailing:
    """Tests for T2 hit → trailing logic (Requirements 6.3, 6.4)."""

    @pytest.mark.asyncio
    async def test_t2_hit_starts_trailing(self, monitor, sample_signal):
        """When price reaches T2, trailing should begin at 1% below close."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # First hit T1
        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        # Then hit T2
        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))

        pos = monitor.get_monitored_positions()[0]
        assert pos.t2_hit is True
        assert pos.highest_since_t2 == 2080.0
        # Trailing stop = 2080 * 0.99 = 2059.2
        assert pos.current_stop == pytest.approx(2080.0 * 0.99, rel=1e-6)

    @pytest.mark.asyncio
    async def test_trailing_increases_with_higher_close(self, monitor, sample_signal):
        """Trailing stop should increase when price makes new highs."""
        monitor.start_monitoring(sample_signal, "signal-123")

        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))
        # New high
        await monitor.on_15m_candle("ETHUSDT", make_candle(2100.0))

        pos = monitor.get_monitored_positions()[0]
        assert pos.highest_since_t2 == 2100.0
        # Trailing stop = 2100 * 0.99 = 2079.0
        assert pos.current_stop == pytest.approx(2100.0 * 0.99, rel=1e-6)

    @pytest.mark.asyncio
    async def test_trailing_never_decreases(self, monitor, sample_signal):
        """Trailing stop should never decrease even if price drops."""
        monitor.start_monitoring(sample_signal, "signal-123")

        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))
        # New high
        await monitor.on_15m_candle("ETHUSDT", make_candle(2120.0))
        stop_after_high = 2120.0 * 0.99  # 2098.8

        # Price drops but stays ABOVE trailing stop (2098.8)
        await monitor.on_15m_candle("ETHUSDT", make_candle(2105.0))

        pos = monitor.get_monitored_positions()[0]
        # Stop should remain at the higher level (not decrease to 2105*0.99=2083.95)
        assert pos.current_stop == pytest.approx(stop_after_high, rel=1e-6)
        # Highest should still be 2120
        assert pos.highest_since_t2 == 2120.0


class TestExitConditions:
    """Tests for exit conditions (Requirements 6.6, 8.5)."""

    @pytest.mark.asyncio
    async def test_exit_on_trailing_stop_hit(self, monitor, sample_signal, mock_journal):
        """Should exit when close < trailing stop."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # Progress to T2 and set trailing
        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2100.0))

        # Trailing stop is 2100 * 0.99 = 2079.0
        # Close below trailing stop
        await monitor.on_15m_candle("ETHUSDT", make_candle(2070.0))

        # Position should be removed
        assert len(monitor.get_monitored_positions()) == 0

        # Journal should be updated
        mock_journal.record_outcome.assert_called_once()
        call_kwargs = mock_journal.record_outcome.call_args[1]
        assert call_kwargs["signal_id"] == "signal-123"
        assert call_kwargs["exit_price"] == 2070.0
        # RR = (2070 - 2000) / (2000 - 1960) = 70/40 = 1.75
        assert call_kwargs["actual_rr"] == pytest.approx(1.75, rel=1e-3)

    @pytest.mark.asyncio
    async def test_exit_on_t3_reached(self, monitor, sample_signal, mock_journal):
        """Should exit as win when T3 is reached (Requirement 8.5)."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # Progress through targets
        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))
        await monitor.on_15m_candle("ETHUSDT", make_candle(2200.0))  # T3

        # Position should be removed
        assert len(monitor.get_monitored_positions()) == 0

        # Journal should record win
        mock_journal.record_outcome.assert_called_once()
        call_kwargs = mock_journal.record_outcome.call_args[1]
        assert call_kwargs["signal_id"] == "signal-123"
        assert call_kwargs["exit_price"] == 2200.0
        # RR = (2200 - 2000) / (2000 - 1960) = 200/40 = 5.0
        assert call_kwargs["actual_rr"] == pytest.approx(5.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_exit_on_original_stop_hit(self, monitor, sample_signal, mock_journal):
        """Should exit when close < original stop (before T1)."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # Price drops below original stop (1960)
        await monitor.on_15m_candle("ETHUSDT", make_candle(1950.0))

        # Position should be removed
        assert len(monitor.get_monitored_positions()) == 0

        # Journal should record loss
        mock_journal.record_outcome.assert_called_once()
        call_kwargs = mock_journal.record_outcome.call_args[1]
        assert call_kwargs["exit_price"] == 1950.0
        # RR = (1950 - 2000) / (2000 - 1960) = -50/40 = -1.25
        assert call_kwargs["actual_rr"] == pytest.approx(-1.25, rel=1e-3)


class TestDataGapWarning:
    """Tests for 30-minute data gap warning (Requirement 6.8)."""

    @pytest.mark.asyncio
    async def test_warns_on_30min_gap(self, monitor, sample_signal, caplog):
        """Should log warning when no data for 30+ minutes."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # First candle
        t1 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        await monitor.on_15m_candle("ETHUSDT", make_candle(2010.0, t1))

        # Next candle 35 minutes later
        t2 = t1 + timedelta(minutes=35)
        with patch("monitors.trailing_stop_monitor.logger") as mock_logger:
            await monitor.on_15m_candle("ETHUSDT", make_candle(2015.0, t2))
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "No data" in warning_msg
            assert "ETHUSDT" in warning_msg

    @pytest.mark.asyncio
    async def test_no_warning_within_30min(self, monitor, sample_signal):
        """Should not warn when data arrives within 30 minutes."""
        monitor.start_monitoring(sample_signal, "signal-123")

        t1 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        await monitor.on_15m_candle("ETHUSDT", make_candle(2010.0, t1))

        # Next candle 15 minutes later (normal)
        t2 = t1 + timedelta(minutes=15)
        with patch("monitors.trailing_stop_monitor.logger") as mock_logger:
            await monitor.on_15m_candle("ETHUSDT", make_candle(2015.0, t2))
            # No warning should be logged
            mock_logger.warning.assert_not_called()


class TestTelegramNotifications:
    """Tests for Telegram notifications on stop changes (Requirement 6.5)."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
    async def test_sends_notification_on_t1_hit(self, monitor, sample_signal, mock_alert_manager):
        """Should send Telegram message when stop moves to breakeven."""
        monitor.start_monitoring(sample_signal, "signal-123")

        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))

        mock_alert_manager._send_with_retry.assert_called()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"})
    async def test_sends_notification_on_trailing_update(self, monitor, sample_signal, mock_alert_manager):
        """Should send Telegram message when trailing stop updates."""
        monitor.start_monitoring(sample_signal, "signal-123")

        await monitor.on_15m_candle("ETHUSDT", make_candle(2040.0))
        mock_alert_manager._send_with_retry.reset_mock()

        await monitor.on_15m_candle("ETHUSDT", make_candle(2080.0))
        mock_alert_manager._send_with_retry.assert_called()


class TestIgnoredSymbols:
    """Tests for symbols not being monitored."""

    @pytest.mark.asyncio
    async def test_ignores_unmonitored_symbol(self, monitor, sample_signal):
        """Should silently ignore candles for unmonitored symbols."""
        monitor.start_monitoring(sample_signal, "signal-123")

        # Send candle for a different symbol
        await monitor.on_15m_candle("BTCUSDT", make_candle(50000.0))

        # ETHUSDT position should be unchanged
        pos = monitor.get_monitored_positions()[0]
        assert pos.current_stop == 1960.0
