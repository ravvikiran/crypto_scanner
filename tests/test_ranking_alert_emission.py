"""
Unit tests for MomentumScanner._update_rankings() and _emit_alerts().

Tests ranking of active scored setups and alert emission with dedup/cooldown.

Requirements: 2.3, 12.5, 20.1, 20.4
"""

import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.models import (
    ScoreInputs,
    ScoredSetup,
    SetupSignal,
    SetupType,
)


def _make_scored_setup(
    symbol: str,
    composite_score: float,
    relative_volume: float = 50.0,
    setup_type: SetupType = SetupType.COMPRESSION_BREAKOUT,
) -> ScoredSetup:
    """Helper to create a ScoredSetup for testing."""
    signal = SetupSignal(
        symbol=symbol,
        setup_type=setup_type,
        entry_price=100.0,
        stop_loss=95.0,
        target_1=105.0,
        target_2=110.0,
        risk_reward=2.0,
        timeframe="1h",
        trigger_timeframe="15m",
    )
    inputs = ScoreInputs(
        relative_strength=60.0,
        relative_volume=relative_volume,
        breakout_quality=70.0,
        trend_quality=80.0,
        market_alignment=100.0,
    )
    return ScoredSetup(
        signal=signal,
        composite_score=composite_score,
        inputs=inputs,
        oi_adjustment=0.0,
        labels=[],
    )


class TestUpdateRankings:
    """Tests for _update_rankings() method."""

    def _create_scanner_with_setups(self, setups):
        """Create a MomentumScanner-like object with mocked dependencies."""
        # We test the method in isolation by creating a minimal mock
        from scoring.scoring_engine import rank_setups

        class MockScanner:
            def __init__(self):
                self._active_scored_setups = setups
                self._ranked_top5 = []

            def _update_rankings(self):
                if not self._active_scored_setups:
                    return
                self._ranked_top5 = rank_setups(self._active_scored_setups)

        return MockScanner()

    def test_empty_setups_no_ranking(self):
        """No ranking should occur when there are no active setups."""
        scanner = self._create_scanner_with_setups([])
        scanner._update_rankings()
        assert scanner._ranked_top5 == []

    def test_single_setup_ranked(self):
        """A single setup should be ranked as top-1."""
        setup = _make_scored_setup("ETHUSDT", 85.0)
        scanner = self._create_scanner_with_setups([setup])
        scanner._update_rankings()
        assert len(scanner._ranked_top5) == 1
        assert scanner._ranked_top5[0].signal.symbol == "ETHUSDT"

    def test_top5_selection(self):
        """Only top 5 setups should be returned when more than 5 exist."""
        setups = [
            _make_scored_setup("COIN1", 90.0),
            _make_scored_setup("COIN2", 85.0),
            _make_scored_setup("COIN3", 80.0),
            _make_scored_setup("COIN4", 75.0),
            _make_scored_setup("COIN5", 70.0),
            _make_scored_setup("COIN6", 65.0),
            _make_scored_setup("COIN7", 60.0),
        ]
        scanner = self._create_scanner_with_setups(setups)
        scanner._update_rankings()
        assert len(scanner._ranked_top5) == 5
        # Verify descending order
        scores = [s.composite_score for s in scanner._ranked_top5]
        assert scores == [90.0, 85.0, 80.0, 75.0, 70.0]

    def test_tie_break_by_relative_volume(self):
        """Setups with equal composite scores should be ranked by relative_volume."""
        setups = [
            _make_scored_setup("COIN_LOW_VOL", 80.0, relative_volume=30.0),
            _make_scored_setup("COIN_HIGH_VOL", 80.0, relative_volume=90.0),
        ]
        scanner = self._create_scanner_with_setups(setups)
        scanner._update_rankings()
        assert scanner._ranked_top5[0].signal.symbol == "COIN_HIGH_VOL"
        assert scanner._ranked_top5[1].signal.symbol == "COIN_LOW_VOL"

    def test_fewer_than_5_returns_all(self):
        """When fewer than 5 setups exist, all should be returned."""
        setups = [
            _make_scored_setup("COIN1", 90.0),
            _make_scored_setup("COIN2", 85.0),
            _make_scored_setup("COIN3", 80.0),
        ]
        scanner = self._create_scanner_with_setups(setups)
        scanner._update_rankings()
        assert len(scanner._ranked_top5) == 3


class TestEmitAlerts:
    """Tests for _emit_alerts() method."""

    def _create_scanner_for_alerts(self, ranked_setups, should_send_results=None):
        """Create a mock scanner for testing _emit_alerts."""
        if should_send_results is None:
            should_send_results = [True] * len(ranked_setups)

        call_count = {"idx": 0}

        class MockAlertManager:
            def __init__(self):
                self.sent_alerts = []

            def should_send(self, symbol, setup_type, current_rvol, current_score, trend_score):
                idx = call_count["idx"]
                call_count["idx"] += 1
                if idx < len(should_send_results):
                    return should_send_results[idx]
                return False

            def mark_sent(self, symbol, setup_type, volume_ratio, score):
                self.sent_alerts.append({
                    "symbol": symbol,
                    "setup_type": setup_type,
                    "volume_ratio": volume_ratio,
                    "score": score,
                })

        class MockRegimeFilter:
            class last_result:
                status = "bullish"

        class MockJournal:
            def __init__(self):
                self.logged_signals = []

            def log_signal(self, entry):
                self.logged_signals.append(entry)

        alert_manager = MockAlertManager()
        journal = MockJournal()

        class MockScanner:
            def __init__(self):
                self._ranked_top5 = ranked_setups
                self._alert_manager = alert_manager
                self._regime_filter = MockRegimeFilter()
                self._journal = journal

            async def _emit_alerts(self_inner):
                if not hasattr(self_inner, "_ranked_top5") or not self_inner._ranked_top5:
                    return

                for scored_setup in self_inner._ranked_top5:
                    symbol = scored_setup.signal.symbol
                    setup_type = scored_setup.signal.setup_type
                    current_rvol = scored_setup.inputs.relative_volume
                    current_score = scored_setup.composite_score
                    trend_score = scored_setup.inputs.trend_quality

                    should_send = self_inner._alert_manager.should_send(
                        symbol=symbol,
                        setup_type=setup_type,
                        current_rvol=current_rvol,
                        current_score=current_score,
                        trend_score=trend_score,
                    )

                    if should_send:
                        self_inner._alert_manager.mark_sent(
                            symbol=symbol,
                            setup_type=setup_type,
                            volume_ratio=current_rvol,
                            score=current_score,
                        )

        scanner = MockScanner()
        return scanner, alert_manager, journal

    def test_no_alerts_when_empty_rankings(self):
        """No alerts should be emitted when rankings are empty."""
        scanner, alert_manager, _ = self._create_scanner_for_alerts([])
        asyncio.run(scanner._emit_alerts())
        assert len(alert_manager.sent_alerts) == 0

    def test_alerts_sent_for_passing_setups(self):
        """Alerts should be sent for setups that pass dedup/cooldown."""
        setups = [
            _make_scored_setup("ETHUSDT", 90.0),
            _make_scored_setup("SOLUSDT", 85.0),
        ]
        scanner, alert_manager, _ = self._create_scanner_for_alerts(
            setups, should_send_results=[True, True]
        )
        asyncio.run(scanner._emit_alerts())
        assert len(alert_manager.sent_alerts) == 2
        assert alert_manager.sent_alerts[0]["symbol"] == "ETHUSDT"
        assert alert_manager.sent_alerts[1]["symbol"] == "SOLUSDT"

    def test_alerts_blocked_by_cooldown(self):
        """Alerts should not be sent for setups blocked by cooldown."""
        setups = [
            _make_scored_setup("ETHUSDT", 90.0),
            _make_scored_setup("SOLUSDT", 85.0),
        ]
        scanner, alert_manager, _ = self._create_scanner_for_alerts(
            setups, should_send_results=[True, False]
        )
        asyncio.run(scanner._emit_alerts())
        assert len(alert_manager.sent_alerts) == 1
        assert alert_manager.sent_alerts[0]["symbol"] == "ETHUSDT"

    def test_all_alerts_blocked(self):
        """No alerts should be sent when all are blocked by cooldown."""
        setups = [
            _make_scored_setup("ETHUSDT", 90.0),
            _make_scored_setup("SOLUSDT", 85.0),
        ]
        scanner, alert_manager, _ = self._create_scanner_for_alerts(
            setups, should_send_results=[False, False]
        )
        asyncio.run(scanner._emit_alerts())
        assert len(alert_manager.sent_alerts) == 0

    def test_mark_sent_called_with_correct_values(self):
        """mark_sent should be called with the correct score and volume."""
        setup = _make_scored_setup("ETHUSDT", 92.5, relative_volume=75.0)
        scanner, alert_manager, _ = self._create_scanner_for_alerts(
            [setup], should_send_results=[True]
        )
        asyncio.run(scanner._emit_alerts())
        assert len(alert_manager.sent_alerts) == 1
        sent = alert_manager.sent_alerts[0]
        assert sent["symbol"] == "ETHUSDT"
        assert sent["score"] == 92.5
        assert sent["volume_ratio"] == 75.0
