"""
Unit tests for MomentumAlertManager.

Tests cooldown enforcement, volume-override bypass, score threshold override,
cache invalidation, LRU eviction, and cache reset.

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.models import SetupType, AlertCacheEntry

# Import directly to avoid alerts/__init__.py pulling in telebot dependency
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "momentum_alert_manager",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "alerts", "momentum_alert_manager.py")
)
_mam_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mam_module)
MomentumAlertManager = _mam_module.MomentumAlertManager


class TestCooldownEnforcement:
    """Tests for Requirement 15.2: Configurable cooldown period."""

    def test_first_alert_always_allowed(self):
        """First alert for a symbol+setup_type should always be allowed."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_alert_blocked_within_cooldown(self):
        """Alert should be blocked if within cooldown period."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is False

    def test_alert_allowed_after_cooldown_expires(self):
        """Alert should be allowed after cooldown period expires."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        # Manually set sent_at to 5 hours ago
        key = manager._make_key("BTCUSDT", SetupType.COMPRESSION_BREAKOUT)
        manager._cache[key].sent_at = datetime.utcnow() - timedelta(hours=5)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_different_symbols_independent_cooldown(self):
        """Different symbols should have independent cooldowns."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="ETHUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_different_setup_types_independent_cooldown(self):
        """Different setup types for same symbol should have independent cooldowns."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.PULLBACK_CONTINUATION,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_cooldown_clamped_to_min(self):
        """Cooldown below 1 hour should be clamped to 1 hour."""
        manager = MomentumAlertManager(cooldown_hours=0.5)
        assert manager.cooldown_hours == 1.0

    def test_cooldown_clamped_to_max(self):
        """Cooldown above 48 hours should be clamped to 48 hours."""
        manager = MomentumAlertManager(cooldown_hours=100.0)
        assert manager.cooldown_hours == 48.0

    def test_default_cooldown_is_4_hours(self):
        """Default cooldown should be 4 hours."""
        manager = MomentumAlertManager()
        assert manager.cooldown_hours == 4.0


class TestVolumeOverride:
    """Tests for Requirement 15.3: Volume-based cooldown override."""

    def test_volume_override_bypasses_cooldown(self):
        """Alert should be sent if RVOL exceeds previous by 50+ pp."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 100.0, 70.0)

        # Current RVOL is 150+ pp above previous (100 + 50 = 150)
        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=150.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_volume_override_exactly_50pp(self):
        """Alert should be sent if RVOL exceeds previous by exactly 50 pp."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 100.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=150.0,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is True

    def test_volume_override_not_triggered_below_50pp(self):
        """Alert should NOT be sent if RVOL difference is below 50 pp."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 100.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=149.9,
            current_score=70.0,
            trend_score=80.0,
        )
        assert result is False


class TestScoreThresholdOverride:
    """Tests for Requirement 15.4: Score threshold crossing override."""

    def test_score_crossing_threshold_bypasses_cooldown(self):
        """Alert should be sent when score crosses 80.0 threshold."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        # Previous score was below threshold
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 75.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=80.0,  # Crosses threshold
            trend_score=80.0,
        )
        assert result is True

    def test_score_above_threshold_both_times_no_override(self):
        """No override if both previous and current are above threshold."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        # Previous score was already above threshold
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 85.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=90.0,
            trend_score=80.0,
        )
        assert result is False

    def test_score_below_threshold_no_override(self):
        """No override if current score is still below threshold."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 60.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=79.9,
            trend_score=80.0,
        )
        assert result is False


class TestCacheInvalidation:
    """Tests for Requirement 15.5: Cache invalidation on stop-loss or trend drop."""

    def test_stop_loss_breach_invalidates_and_allows(self):
        """Stop-loss breach should invalidate cache and allow alert."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=80.0,
            stop_loss_breached=True,
        )
        assert result is True
        # Entry should be removed from cache
        assert manager.get_entry("BTCUSDT", SetupType.COMPRESSION_BREAKOUT) is None

    def test_trend_score_below_40_invalidates_and_allows(self):
        """Trend score below 40 should invalidate cache and allow alert."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=39.0,  # Below 40
        )
        assert result is True
        assert manager.get_entry("BTCUSDT", SetupType.COMPRESSION_BREAKOUT) is None

    def test_trend_score_exactly_40_no_invalidation(self):
        """Trend score of exactly 40 should NOT invalidate cache."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        result = manager.should_send(
            symbol="BTCUSDT",
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            current_rvol=2.0,
            current_score=70.0,
            trend_score=40.0,  # Exactly 40, not below
        )
        assert result is False

    def test_external_invalidate_removes_entry(self):
        """External invalidate() call should remove the cache entry."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        manager.invalidate("BTCUSDT", SetupType.COMPRESSION_BREAKOUT)
        assert manager.get_entry("BTCUSDT", SetupType.COMPRESSION_BREAKOUT) is None


class TestCacheManagement:
    """Tests for Requirement 15.1: State cache with max 500 entries and LRU eviction."""

    def test_max_500_entries_lru_eviction(self):
        """Cache should evict LRU entries when exceeding 500."""
        manager = MomentumAlertManager(cooldown_hours=4.0, max_entries=5)

        # Fill cache with 5 entries
        for i in range(5):
            manager.mark_sent(f"COIN{i}", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        assert manager.cache_size == 5

        # Add one more - should evict COIN0 (oldest/LRU)
        manager.mark_sent("COIN5", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)

        assert manager.cache_size == 5
        assert manager.get_entry("COIN0", SetupType.COMPRESSION_BREAKOUT) is None
        assert manager.get_entry("COIN5", SetupType.COMPRESSION_BREAKOUT) is not None

    def test_mark_sent_updates_existing_entry(self):
        """Marking sent for existing key should update the entry."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 3.0, 85.0)

        entry = manager.get_entry("BTCUSDT", SetupType.COMPRESSION_BREAKOUT)
        assert entry is not None
        assert entry.volume_ratio_at_send == 3.0
        assert entry.score_at_send == 85.0
        assert manager.cache_size == 1

    def test_cache_key_format(self):
        """Cache key should be symbol_setup_type.value."""
        manager = MomentumAlertManager()
        key = manager._make_key("BTCUSDT", SetupType.COMPRESSION_BREAKOUT)
        assert key == "BTCUSDT_compression_breakout"

    def test_reset_cache_clears_all(self):
        """reset_cache() should clear all entries (Requirement 15.6)."""
        manager = MomentumAlertManager(cooldown_hours=4.0)
        manager.mark_sent("BTCUSDT", SetupType.COMPRESSION_BREAKOUT, 2.0, 70.0)
        manager.mark_sent("ETHUSDT", SetupType.PULLBACK_CONTINUATION, 3.0, 80.0)

        manager.reset_cache()
        assert manager.cache_size == 0


# Import additional models needed for formatting tests
from streaming.models import (
    ScoredSetup, SetupSignal, ScoreInputs, OIFundingData, SetupType
)


class TestTelegramMessageFormatting:
    """Tests for Requirement 16.1, 16.2, 16.3, 16.5, 16.7, 16.8, 10.3, 10.4."""

    def _make_scored_setup(self, symbol="ETHUSDT", composite_score=78.50):
        """Helper to create a ScoredSetup for testing."""
        signal = SetupSignal(
            symbol=symbol,
            setup_type=SetupType.COMPRESSION_BREAKOUT,
            entry_price=2450.00,
            stop_loss=2400.00,
            target_1=2500.00,
            target_2=2550.00,
            target_3=2700.00,
            risk_reward=2.0,
            timeframe="1h",
            trigger_timeframe="15m",
        )
        inputs = ScoreInputs(
            relative_strength=72.5,
            relative_volume=65.0,
            breakout_quality=80.0,
            trend_quality=70.0,
            market_alignment=85.0,
        )
        return ScoredSetup(
            signal=signal,
            composite_score=composite_score,
            inputs=inputs,
            oi_adjustment=0.0,
            labels=[],
        )

    def _make_risk_levels(self):
        """Helper to create risk_levels dict."""
        return {
            "entry": 2450.00,
            "stop_loss": 2400.00,
            "risk_pct": 2.04,
            "target_1": 2500.00,
            "target_2": 2550.00,
        }

    def _make_oi_data(self, available=True):
        """Helper to create OIFundingData."""
        return OIFundingData(
            oi_change_4h_pct=7.5,
            funding_rate=0.01,
            is_overcrowded=False,
            weak_oi_participation=False,
            data_available=available,
            score_adjustment=0.0,
        )

    def test_message_contains_signal_section(self):
        """Message should contain directional emoji and signal info."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "\U0001f7e2 LONG SIGNAL" in msg
        assert "ETHUSDT" in msg
        assert "Compression Breakout" in msg

    def test_message_contains_entry_exit_section(self):
        """Message should contain entry, stop-loss, risk, targets."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "Entry:" in msg
        assert "Stop-Loss:" in msg
        assert "Risk:" in msg
        assert "Target1 (1R):" in msg
        assert "Target2 (2R):" in msg
        assert "Target3 (5R):" in msg

    def test_message_contains_market_context_section(self):
        """Message should contain RS, RVOL, OI change, funding rate."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "RS vs BTC:" in msg
        assert "RVOL:" in msg
        assert "OI Change (4H):" in msg
        assert "Funding Rate:" in msg

    def test_message_contains_scoring_section(self):
        """Message should contain trend score and composite score."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "Trend Score: 75.00" in msg
        assert "Composite Score: 78.50" in msg

    def test_message_contains_exit_strategy(self):
        """Message should contain position sizing recommendation."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "Take 40% at T1, 40% at T2, let 20% run to T3" in msg

    def test_message_contains_iso8601_timestamp(self):
        """Message should contain UTC timestamp in ISO-8601 format."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        # Check ISO-8601 pattern (YYYY-MM-DDTHH:MM:SSZ)
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", msg)

    def test_na_for_unavailable_oi_data(self):
        """Should display N/A when OI/funding data is unavailable."""
        manager = MomentumAlertManager()
        oi_data = self._make_oi_data(available=False)
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            oi_data,
            trend_score=75.0,
        )
        assert "OI Change (4H): N/A" in msg
        assert "Funding Rate: N/A" in msg

    def test_na_for_missing_target2(self):
        """Should display N/A when Target2 is None."""
        manager = MomentumAlertManager()
        risk_levels = self._make_risk_levels()
        risk_levels["target_2"] = None
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            risk_levels,
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert "Target2 (2R): N/A" in msg

    def test_message_within_4096_char_limit(self):
        """Message should never exceed 4096 characters."""
        manager = MomentumAlertManager()
        msg = manager._format_telegram_message(
            self._make_scored_setup(),
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert len(msg) <= 4096

    def test_long_message_truncated_to_4096(self):
        """If message would exceed 4096 chars, it should be truncated."""
        manager = MomentumAlertManager()
        # Use a very long symbol name to force truncation
        scored_setup = self._make_scored_setup(symbol="A" * 4000)
        msg = manager._format_telegram_message(
            scored_setup,
            self._make_risk_levels(),
            self._make_oi_data(),
            trend_score=75.0,
        )
        assert len(msg) <= 4096
        assert msg.endswith("...")


class TestSendWithRetry:
    """Tests for Requirement 16.6: Telegram delivery retry logic."""

    def test_successful_send_on_first_attempt(self):
        """Message should be sent successfully on first attempt."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                return await manager._send_with_retry(
                    message="Test alert",
                    chat_id="123456",
                    bot_token="bot_token_123",
                )

        result = asyncio.run(_run())
        assert result is True

    def test_returns_false_after_all_retries_exhausted(self):
        """Should return False after 3 failed attempts."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    result = await manager._send_with_retry(
                        message="Test alert",
                        chat_id="123456",
                        bot_token="bot_token_123",
                    )
                    return result, mock_sleep.call_count

        result, sleep_count = asyncio.run(_run())
        assert result is False
        # Should have slept twice (between attempt 1-2 and 2-3)
        assert sleep_count == 2

    def test_succeeds_on_second_attempt(self):
        """Should succeed if second attempt returns 200."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        # First call fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.__aenter__ = AsyncMock(return_value=mock_response_fail)
        mock_response_fail.__aexit__ = AsyncMock(return_value=False)

        mock_response_ok = AsyncMock()
        mock_response_ok.status = 200
        mock_response_ok.__aenter__ = AsyncMock(return_value=mock_response_ok)
        mock_response_ok.__aexit__ = AsyncMock(return_value=False)

        call_count = {"n": 0}

        def make_post_response(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_response_fail
            return mock_response_ok

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=make_post_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    return await manager._send_with_retry(
                        message="Test alert",
                        chat_id="123456",
                        bot_token="bot_token_123",
                    )

        result = asyncio.run(_run())
        assert result is True

    def test_handles_timeout_error(self):
        """Should handle asyncio.TimeoutError and retry."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=asyncio.TimeoutError("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    result = await manager._send_with_retry(
                        message="Test alert",
                        chat_id="123456",
                        bot_token="bot_token_123",
                    )
                    return result, mock_sleep.call_count

        result, sleep_count = asyncio.run(_run())
        assert result is False
        assert sleep_count == 2

    def test_handles_client_error(self):
        """Should handle aiohttp.ClientError and retry."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(
            side_effect=aiohttp.ClientError("connection failed")
        )
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    result = await manager._send_with_retry(
                        message="Test alert",
                        chat_id="123456",
                        bot_token="bot_token_123",
                    )
                    return result, mock_sleep.call_count

        result, sleep_count = asyncio.run(_run())
        assert result is False
        assert sleep_count == 2

    def test_retry_interval_is_5_seconds(self):
        """Should wait 5 seconds between retry attempts."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    await manager._send_with_retry(
                        message="Test alert",
                        chat_id="123456",
                        bot_token="bot_token_123",
                    )
                    return mock_sleep.call_args_list

        sleep_calls = asyncio.run(_run())
        # Verify sleep was called with 5.0 seconds
        for call in sleep_calls:
            assert call[0][0] == 5.0

    def test_uses_correct_telegram_api_url(self):
        """Should POST to the correct Telegram Bot API endpoint."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        import aiohttp

        manager = MomentumAlertManager(cooldown_hours=4.0)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        async def _run():
            with patch("aiohttp.ClientSession", return_value=mock_session):
                await manager._send_with_retry(
                    message="Test alert",
                    chat_id="123456",
                    bot_token="my_bot_token",
                )

        asyncio.run(_run())

        # Verify the URL used
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "https://api.telegram.org/botmy_bot_token/sendMessage"
        assert call_args[1]["json"]["chat_id"] == "123456"
        assert call_args[1]["json"]["text"] == "Test alert"
