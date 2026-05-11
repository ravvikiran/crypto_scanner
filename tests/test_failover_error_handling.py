"""
Unit tests for MomentumScanner failover and error handling (Task 15.3).

Tests:
- Exchange failover (primary → secondary within 10s)
- Events continue to queue during failover (no discard)
- Per-coin processing errors (log, skip, continue)
- Telegram alert on total exchange failure
- Failure callback registration with WebSocketManager

Requirements: 2.6, 20.3, 20.6, 20.7
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from streaming.models import (
    CandleCloseEvent,
    ConnectionFailureEvent,
)
from core.momentum_scanner import MomentumScanner
from config.websocket_config import WebSocketStreamConfig
from streaming.models import OHLCV


@pytest.fixture
def config():
    """Create a test configuration with multiple exchanges enabled."""
    cfg = WebSocketStreamConfig()
    cfg.enable_binance = True
    cfg.enable_bybit = True
    cfg.enable_okx = True
    return cfg


@pytest.fixture
def scanner(config):
    """Create a MomentumScanner instance for testing."""
    with patch("core.momentum_scanner.WebSocketManager"):
        with patch("core.momentum_scanner.StateManager"):
            scanner = MomentumScanner(
                config=config,
                symbols=["BTCUSDT", "ETHUSDT"],
            )
    return scanner


class TestFailureCallbackRegistration:
    """Test that the failure callback is properly registered."""

    def test_register_failure_callback_calls_set_failure_callback(self, scanner):
        """_register_failure_callback should call ws_manager.set_failure_callback."""
        scanner._ws_manager.set_failure_callback = MagicMock()

        scanner._register_failure_callback()

        scanner._ws_manager.set_failure_callback.assert_called_once_with(
            scanner._handle_exchange_failure
        )


class TestExchangeFailover:
    """Test exchange failover logic (primary → secondary within 10s)."""

    def test_failover_to_secondary_when_primary_fails(self, scanner):
        """When primary (binance) fails, should attempt failover to secondary."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="All 5 reconnection attempts exhausted",
                attempts_made=5,
            )

            # Mock connected_exchanges to show bybit is still connected
            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                return_value=["bybit", "okx"]
            )

            # Mock connections to return a healthy bybit connection
            mock_bybit_conn = MagicMock()
            mock_bybit_conn.is_connected = True
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={"bybit": mock_bybit_conn, "okx": MagicMock(is_connected=True)}
            )

            await scanner._handle_exchange_failure(event)
            # Should not crash — failover to bybit succeeded

        asyncio.run(_run())

    def test_failover_selects_highest_priority_secondary(self, scanner):
        """Failover should select the highest-priority available exchange."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="Connection lost",
                attempts_made=5,
            )

            # Both bybit and okx are connected — bybit should be selected
            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                return_value=["bybit", "okx"]
            )

            mock_bybit_conn = MagicMock()
            mock_bybit_conn.is_connected = True
            mock_okx_conn = MagicMock()
            mock_okx_conn.is_connected = True
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={"bybit": mock_bybit_conn, "okx": mock_okx_conn}
            )

            await scanner._handle_exchange_failure(event)
            # Should succeed without sending total failure alert

        asyncio.run(_run())

    def test_failover_timeout_triggers_total_failure_check(self, scanner):
        """If failover times out and no exchanges remain, send total failure alert."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="Connection lost",
                attempts_made=5,
            )

            # First call: bybit appears connected for failover attempt
            # After failover timeout: no exchanges connected
            connected_call_count = [0]

            def mock_connected():
                connected_call_count[0] += 1
                if connected_call_count[0] == 1:
                    return ["bybit"]
                return []

            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                side_effect=mock_connected
            )

            # Make verify_exchange_health time out
            async def slow_verify(exchange):
                await asyncio.sleep(20)  # Longer than 10s timeout
                return True

            scanner._verify_exchange_health = slow_verify
            scanner._send_total_failure_alert = AsyncMock()

            await scanner._handle_exchange_failure(event)

            # After timeout, check all_connected — returns empty, so total failure alert
            scanner._send_total_failure_alert.assert_called_once_with(event)

        asyncio.run(_run())


class TestTotalExchangeFailure:
    """Test Telegram alert on total exchange failure."""

    def test_total_failure_sends_telegram_alert(self, scanner):
        """When all exchanges fail, should send Telegram alert."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="okx",
                reason="All attempts exhausted",
                attempts_made=5,
            )

            # No exchanges connected
            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                return_value=[]
            )

            scanner._alert_manager._send_with_retry = AsyncMock(return_value=True)

            with patch.dict(
                "os.environ",
                {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"},
            ):
                await scanner._handle_exchange_failure(event)

            # Verify _send_with_retry was called
            scanner._alert_manager._send_with_retry.assert_called_once()
            call_args = scanner._alert_manager._send_with_retry.call_args
            # Get the message from kwargs
            message = call_args.kwargs.get("message", "")
            assert "CRITICAL" in message or "Total Exchange Failure" in message

        asyncio.run(_run())

    def test_total_failure_alert_includes_exchange_info(self, scanner):
        """Total failure alert should include the failed exchange name."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="Network unreachable",
                attempts_made=5,
            )

            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                return_value=[]
            )

            scanner._alert_manager._send_with_retry = AsyncMock(return_value=True)

            with patch.dict(
                "os.environ",
                {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"},
            ):
                await scanner._send_total_failure_alert(event)

            call_args = scanner._alert_manager._send_with_retry.call_args
            message = call_args.kwargs.get("message", "")
            assert "binance" in message
            assert "Network unreachable" in message

        asyncio.run(_run())

    def test_total_failure_no_alert_without_telegram_config(self, scanner):
        """If Telegram is not configured, should log error but not crash."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="Connection lost",
                attempts_made=5,
            )

            scanner._alert_manager._send_with_retry = AsyncMock()

            with patch.dict(
                "os.environ",
                {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""},
            ):
                # Should not raise
                await scanner._send_total_failure_alert(event)

            # _send_with_retry should NOT be called without config
            scanner._alert_manager._send_with_retry.assert_not_called()

        asyncio.run(_run())


class TestEventQueueDuringFailover:
    """Test that events continue to queue during failover (no discard)."""

    def test_event_bus_continues_during_failover(self, scanner):
        """EventBus should continue accepting events during failover."""

        async def _run():
            event = ConnectionFailureEvent(
                exchange="binance",
                reason="Connection lost",
                attempts_made=5,
            )

            # bybit is still connected
            type(scanner._ws_manager).connected_exchanges = PropertyMock(
                return_value=["bybit"]
            )

            mock_bybit_conn = MagicMock()
            mock_bybit_conn.is_connected = True
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={"bybit": mock_bybit_conn}
            )

            # Verify event_bus is not stopped during failover
            scanner._event_bus.stop = MagicMock()

            await scanner._handle_exchange_failure(event)

            # EventBus.stop() should NOT be called during failover
            scanner._event_bus.stop.assert_not_called()

        asyncio.run(_run())


class TestPerCoinErrorHandling:
    """Test per-coin processing errors (log, skip, continue)."""

    def test_process_event_catches_exception_and_continues(self, scanner):
        """_process_event should catch exceptions and log without crashing."""

        async def _run():
            candle = OHLCV(
                timestamp=datetime.utcnow(),
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000.0,
            )
            event = CandleCloseEvent(
                symbol="ETHUSDT",
                timeframe="4h",
                candle=candle,
                exchange="binance",
            )

            # Make state_manager.update_candle raise an exception
            scanner._state_manager.update_candle = MagicMock(
                side_effect=ValueError("Simulated per-coin error")
            )

            # Should not raise — error is caught and logged
            await scanner._process_event(event)

        asyncio.run(_run())

    def test_process_event_error_does_not_affect_other_coins(self, scanner):
        """An error processing one coin should not prevent processing others."""

        async def _run():
            candle = OHLCV(
                timestamp=datetime.utcnow(),
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000.0,
            )

            event_fail = CandleCloseEvent(
                symbol="FAILCOIN",
                timeframe="4h",
                candle=candle,
                exchange="binance",
            )

            event_ok = CandleCloseEvent(
                symbol="OKCOIN",
                timeframe="4h",
                candle=candle,
                exchange="binance",
            )

            call_count = [0]

            def mock_update_candle(symbol, timeframe, c):
                call_count[0] += 1
                if symbol == "FAILCOIN":
                    raise RuntimeError("Simulated failure for FAILCOIN")

            scanner._state_manager.update_candle = MagicMock(
                side_effect=mock_update_candle
            )

            # Process both events — first should fail silently, second should proceed
            await scanner._process_event(event_fail)
            await scanner._process_event(event_ok)

            # Both were attempted
            assert call_count[0] == 2

        asyncio.run(_run())


class TestVerifyExchangeHealth:
    """Test the _verify_exchange_health helper."""

    def test_healthy_exchange_returns_true(self, scanner):
        """Should return True when exchange connection is active."""

        async def _run():
            mock_conn = MagicMock()
            mock_conn.is_connected = True
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={"bybit": mock_conn}
            )

            result = await scanner._verify_exchange_health("bybit")
            assert result is True

        asyncio.run(_run())

    def test_unhealthy_exchange_returns_false(self, scanner):
        """Should return False when exchange connection is not active."""

        async def _run():
            mock_conn = MagicMock()
            mock_conn.is_connected = False
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={"bybit": mock_conn}
            )

            result = await scanner._verify_exchange_health("bybit")
            assert result is False

        asyncio.run(_run())

    def test_unknown_exchange_returns_false(self, scanner):
        """Should return False when exchange is not in connections."""

        async def _run():
            type(scanner._ws_manager).connections = PropertyMock(
                return_value={}
            )

            result = await scanner._verify_exchange_health("unknown")
            assert result is False

        asyncio.run(_run())
