"""
Unit tests for the StatusReporter class.

Tests: startup message, daily summary, idle status with rate limiting,
retry logic, and BTC regime status integration.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from monitors.status_reporter import StatusReporter

pytestmark = pytest.mark.asyncio


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_alert_manager():
    """Create a mock AlertManager with _send_with_retry."""
    manager = MagicMock()
    manager._send_with_retry = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_journal_store():
    """Create a mock JournalStore."""
    store = MagicMock()
    store.get_signals_for_date = MagicMock(return_value=[])
    return store


@pytest.fixture
def mock_regime_filter():
    """Create a mock MarketRegimeFilter."""
    regime = MagicMock()
    regime.last_result = MagicMock()
    regime.last_result.status = "bullish"
    regime.get_alignment_score = MagicMock(return_value=80.0)
    regime.is_crashing = MagicMock(return_value=False)
    regime._btc_candles_1h = []
    return regime


@pytest.fixture
def reporter(mock_alert_manager, mock_journal_store, mock_regime_filter):
    """Create a StatusReporter with mocked dependencies."""
    return StatusReporter(
        alert_manager=mock_alert_manager,
        journal_store=mock_journal_store,
        regime_filter=mock_regime_filter,
        bot_token="test_token",
        chat_id="test_chat_id",
    )


# ─── Startup Message Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_startup_message(reporter, mock_alert_manager):
    """Test startup message contains scanner started and symbol count."""
    await reporter.send_startup_message(42)

    mock_alert_manager._send_with_retry.assert_called_once()
    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "🟢 Scanner started" in message
    assert "42" in message


@pytest.mark.asyncio
async def test_send_startup_message_zero_symbols(reporter, mock_alert_manager):
    """Test startup message with zero symbols."""
    await reporter.send_startup_message(0)

    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "🟢 Scanner started" in message
    assert "0" in message


# ─── Daily Summary Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_daily_summary_no_signals(reporter, mock_alert_manager, mock_journal_store):
    """Test daily summary with no signals today."""
    mock_journal_store.get_signals_for_date.return_value = []

    await reporter.send_daily_summary()

    mock_alert_manager._send_with_retry.assert_called_once()
    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "Daily Summary" in message
    assert "Total signals: 0" in message
    assert "Win rate: 0.0%" in message


@pytest.mark.asyncio
async def test_send_daily_summary_with_signals(reporter, mock_alert_manager, mock_journal_store):
    """Test daily summary with resolved signals."""
    mock_journal_store.get_signals_for_date.return_value = [
        {"symbol": "ETHUSDT", "outcome": "win", "actual_rr": 1.5, "composite_score": 75.0},
        {"symbol": "BTCUSDT", "outcome": "loss", "actual_rr": -1.0, "composite_score": 60.0},
        {"symbol": "SOLUSDT", "outcome": "win", "actual_rr": 2.0, "composite_score": 80.0},
        {"symbol": "ADAUSDT", "outcome": None, "composite_score": 55.0},
    ]

    await reporter.send_daily_summary()

    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "Total signals: 4" in message
    # 2 wins out of 3 resolved = 66.7%
    assert "66.7%" in message
    # Best symbol should be SOLUSDT (highest RR among wins)
    assert "SOLUSDT" in message


# ─── Idle Status Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_idle_no_signal_ever(reporter, mock_alert_manager):
    """Test idle check when no signal has ever been emitted."""
    await reporter.check_idle_status(last_signal_time=None)

    mock_alert_manager._send_with_retry.assert_called_once()
    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "✅ Scanner active. No setups found." in message
    assert "BTC regime:" in message


@pytest.mark.asyncio
async def test_check_idle_signal_recent(reporter, mock_alert_manager):
    """Test idle check when signal was emitted recently (< 4 hours)."""
    recent_time = datetime.utcnow() - timedelta(hours=2)

    await reporter.check_idle_status(last_signal_time=recent_time)

    # Should NOT send a message since we're not idle
    mock_alert_manager._send_with_retry.assert_not_called()


@pytest.mark.asyncio
async def test_check_idle_signal_old(reporter, mock_alert_manager):
    """Test idle check when signal was emitted 5 hours ago."""
    old_time = datetime.utcnow() - timedelta(hours=5)

    await reporter.check_idle_status(last_signal_time=old_time)

    mock_alert_manager._send_with_retry.assert_called_once()
    call_args = mock_alert_manager._send_with_retry.call_args
    message = call_args[0][0]

    assert "✅ Scanner active. No setups found." in message


@pytest.mark.asyncio
async def test_check_idle_rate_limiting(reporter, mock_alert_manager):
    """Test that idle messages are rate-limited to one per 4-hour window."""
    old_time = datetime.utcnow() - timedelta(hours=5)

    # First call should send
    await reporter.check_idle_status(last_signal_time=old_time)
    assert mock_alert_manager._send_with_retry.call_count == 1

    # Second call within 4 hours should NOT send
    await reporter.check_idle_status(last_signal_time=old_time)
    assert mock_alert_manager._send_with_retry.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_check_idle_rate_limit_expires(reporter, mock_alert_manager):
    """Test that rate limit expires after 4 hours."""
    old_time = datetime.utcnow() - timedelta(hours=5)

    # First call sends
    await reporter.check_idle_status(last_signal_time=old_time)
    assert mock_alert_manager._send_with_retry.call_count == 1

    # Simulate time passing beyond the rate limit window
    reporter._last_idle_message_time = datetime.utcnow() - timedelta(hours=4, minutes=1)

    # Now it should send again
    await reporter.check_idle_status(last_signal_time=old_time)
    assert mock_alert_manager._send_with_retry.call_count == 2


# ─── BTC Regime Status Tests ─────────────────────────────────────────────────


def test_btc_regime_status_bullish(reporter, mock_regime_filter):
    """Test BTC regime status when bullish."""
    mock_regime_filter.last_result.status = "bullish"
    mock_regime_filter.get_alignment_score.return_value = 100.0
    mock_regime_filter.is_crashing.return_value = False

    status = reporter._get_btc_regime_status()
    assert "Bullish" in status
    assert "100" in status


def test_btc_regime_status_crashing(reporter, mock_regime_filter):
    """Test BTC regime status when crashing."""
    mock_regime_filter.is_crashing.return_value = True

    status = reporter._get_btc_regime_status()
    assert "Crashing" in status


def test_btc_regime_status_no_filter(mock_alert_manager, mock_journal_store):
    """Test BTC regime status when no filter is available."""
    reporter = StatusReporter(
        alert_manager=mock_alert_manager,
        journal_store=mock_journal_store,
        regime_filter=None,
        bot_token="test_token",
        chat_id="test_chat_id",
    )
    status = reporter._get_btc_regime_status()
    assert status == "unknown"


# ─── Retry Logic Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_with_retry_success(reporter, mock_alert_manager):
    """Test successful delivery on first attempt."""
    mock_alert_manager._send_with_retry.return_value = True

    result = await reporter._send_with_retry("test message")
    assert result is True


@pytest.mark.asyncio
async def test_send_with_retry_failure(reporter, mock_alert_manager):
    """Test delivery failure after all retries."""
    mock_alert_manager._send_with_retry.return_value = False

    result = await reporter._send_with_retry("test message")
    assert result is False


@pytest.mark.asyncio
async def test_send_with_retry_no_credentials():
    """Test that missing credentials returns False without attempting delivery."""
    reporter = StatusReporter(
        alert_manager=MagicMock(),
        journal_store=MagicMock(),
        bot_token="",
        chat_id="",
    )
    result = await reporter._send_with_retry("test message")
    assert result is False


# ─── Best Symbol Tests ────────────────────────────────────────────────────────


def test_find_best_symbol_no_signals(reporter):
    """Test best symbol with empty signal list."""
    result = reporter._find_best_symbol([])
    assert result is None


def test_find_best_symbol_with_wins(reporter):
    """Test best symbol picks highest RR win."""
    signals = [
        {"symbol": "ETHUSDT", "outcome": "win", "actual_rr": 1.5},
        {"symbol": "SOLUSDT", "outcome": "win", "actual_rr": 3.0},
        {"symbol": "BTCUSDT", "outcome": "loss", "actual_rr": -1.0},
    ]
    result = reporter._find_best_symbol(signals)
    assert result == "SOLUSDT"


def test_find_best_symbol_no_wins_fallback_to_score(reporter):
    """Test best symbol falls back to highest composite score when no wins."""
    signals = [
        {"symbol": "ETHUSDT", "outcome": "loss", "composite_score": 70.0},
        {"symbol": "SOLUSDT", "outcome": None, "composite_score": 85.0},
    ]
    result = reporter._find_best_symbol(signals)
    assert result == "SOLUSDT"
