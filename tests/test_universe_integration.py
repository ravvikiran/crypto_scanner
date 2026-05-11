"""
Tests for UniverseManager integration into MomentumScanner.

Verifies:
- UniverseManager is initialized in MomentumScanner.__init__()
- initialize() is called during start() to get initial symbol list
- refresh() is scheduled every 60 minutes
- On refresh: subscribe(added) and unsubscribe(removed) are called

Requirements: 2.6, 2.7
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.momentum_scanner import MomentumScanner


class TestUniverseManagerInitialization:
    """Test that UniverseManager is properly initialized in MomentumScanner."""

    def test_universe_manager_attribute_exists(self):
        """MomentumScanner should have a _universe_manager attribute."""
        scanner = MomentumScanner()
        assert hasattr(scanner, "_universe_manager")

    def test_universe_manager_is_universe_manager_instance(self):
        """_universe_manager should be a UniverseManager instance."""
        from universe.universe_manager import UniverseManager

        scanner = MomentumScanner()
        assert isinstance(scanner._universe_manager, UniverseManager)

    def test_universe_manager_uses_config_values(self):
        """UniverseManager should use config values for min_volume and min_price."""
        scanner = MomentumScanner()
        config = scanner._config
        assert scanner._universe_manager.min_volume_usd == config.universe_min_volume_usd
        assert scanner._universe_manager.min_price == config.universe_min_price

    def test_universe_refresh_task_initialized_to_none(self):
        """_universe_refresh_task should be None before start()."""
        scanner = MomentumScanner()
        assert scanner._universe_refresh_task is None

    def test_universe_manager_property_exposed(self):
        """universe_manager property should be accessible."""
        scanner = MomentumScanner()
        assert scanner.universe_manager is scanner._universe_manager


class TestUniverseInitializeDuringStart:
    """Test that initialize() is called during start()."""

    def test_start_calls_universe_initialize(self):
        """start() should call universe_manager.initialize()."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.initialize = AsyncMock(
                return_value=["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            )
            scanner._ws_manager.start = AsyncMock()
            scanner._ws_manager.set_failure_callback = MagicMock()

            await scanner.start()
            scanner._universe_manager.initialize.assert_called_once()
            await scanner.stop()

        asyncio.run(_run())

    def test_start_updates_symbols_from_universe(self):
        """start() should update _symbols with universe results."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            expected_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
            scanner._universe_manager.initialize = AsyncMock(
                return_value=expected_symbols
            )
            scanner._ws_manager.start = AsyncMock()
            scanner._ws_manager.set_failure_callback = MagicMock()

            await scanner.start()
            assert scanner._symbols == expected_symbols
            await scanner.stop()

        asyncio.run(_run())

    def test_start_continues_on_universe_failure(self):
        """start() should continue with configured symbols if universe init fails."""

        async def _run():
            original_symbols = ["BTCUSDT", "ETHUSDT"]
            scanner = MomentumScanner(symbols=original_symbols)
            scanner._universe_manager.initialize = AsyncMock(
                side_effect=RuntimeError("API unavailable")
            )
            scanner._ws_manager.start = AsyncMock()
            scanner._ws_manager.set_failure_callback = MagicMock()

            await scanner.start()
            assert scanner._symbols == original_symbols
            await scanner.stop()

        asyncio.run(_run())


class TestUniverseRefreshScheduling:
    """Test that refresh() is scheduled periodically."""

    def test_start_creates_refresh_task(self):
        """start() should create a universe refresh task."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.initialize = AsyncMock(return_value=["BTCUSDT"])
            scanner._ws_manager.start = AsyncMock()
            scanner._ws_manager.set_failure_callback = MagicMock()

            await scanner.start()
            assert scanner._universe_refresh_task is not None
            assert not scanner._universe_refresh_task.done()
            await scanner.stop()

        asyncio.run(_run())

    def test_stop_cancels_refresh_task(self):
        """stop() should cancel the universe refresh task."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.initialize = AsyncMock(return_value=["BTCUSDT"])
            scanner._ws_manager.start = AsyncMock()
            scanner._ws_manager.stop = AsyncMock()
            scanner._ws_manager.set_failure_callback = MagicMock()
            scanner._universe_manager.close = AsyncMock()

            await scanner.start()
            refresh_task = scanner._universe_refresh_task

            await scanner.stop()
            assert refresh_task.done() or refresh_task.cancelled()

        asyncio.run(_run())


class TestUniverseRefreshSubscribeUnsubscribe:
    """Test that refresh triggers subscribe/unsubscribe on WebSocketManager."""

    def test_refresh_subscribes_added_symbols(self):
        """On refresh with added symbols, subscribe() should be called."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.refresh = AsyncMock(
                return_value=(["NEWCOIN1USDT", "NEWCOIN2USDT"], [])
            )
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            scanner._ws_manager.subscribe.assert_called_once_with(
                ["NEWCOIN1USDT", "NEWCOIN2USDT"]
            )

        asyncio.run(_run())

    def test_refresh_unsubscribes_removed_symbols(self):
        """On refresh with removed symbols, unsubscribe() should be called."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT", "OLDCOINUSDT"])
            scanner._universe_manager.refresh = AsyncMock(
                return_value=([], ["OLDCOINUSDT"])
            )
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            scanner._ws_manager.unsubscribe.assert_called_once_with(["OLDCOINUSDT"])

        asyncio.run(_run())

    def test_refresh_handles_both_added_and_removed(self):
        """On refresh with both added and removed, both methods should be called."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT", "OLDUSDT"])
            scanner._universe_manager.refresh = AsyncMock(
                return_value=(["NEWUSDT"], ["OLDUSDT"])
            )
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            scanner._ws_manager.subscribe.assert_called_once_with(["NEWUSDT"])
            scanner._ws_manager.unsubscribe.assert_called_once_with(["OLDUSDT"])

        asyncio.run(_run())

    def test_refresh_no_changes_does_not_call_subscribe(self):
        """On refresh with no changes, subscribe/unsubscribe should not be called."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.refresh = AsyncMock(return_value=([], []))
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            scanner._ws_manager.subscribe.assert_not_called()
            scanner._ws_manager.unsubscribe.assert_not_called()

        asyncio.run(_run())

    def test_refresh_updates_internal_symbols_on_add(self):
        """On refresh with added symbols, _symbols should be updated."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._symbols = ["BTCUSDT"]
            scanner._universe_manager.refresh = AsyncMock(
                return_value=(["ETHUSDT"], [])
            )
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            assert "ETHUSDT" in scanner._symbols
            assert "BTCUSDT" in scanner._symbols

        asyncio.run(_run())

    def test_refresh_updates_internal_symbols_on_remove(self):
        """On refresh with removed symbols, _symbols should be updated."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT", "OLDUSDT"])
            scanner._symbols = ["BTCUSDT", "OLDUSDT"]
            scanner._universe_manager.refresh = AsyncMock(
                return_value=([], ["OLDUSDT"])
            )
            scanner._ws_manager.subscribe = AsyncMock()
            scanner._ws_manager.unsubscribe = AsyncMock()

            await scanner._refresh_universe()
            assert "OLDUSDT" not in scanner._symbols
            assert "BTCUSDT" in scanner._symbols

        asyncio.run(_run())

    def test_refresh_handles_exception_gracefully(self):
        """If refresh raises an exception, it should not crash."""

        async def _run():
            scanner = MomentumScanner(symbols=["BTCUSDT"])
            scanner._universe_manager.refresh = AsyncMock(
                side_effect=Exception("Network error")
            )

            # Should not raise
            await scanner._refresh_universe()

        asyncio.run(_run())
