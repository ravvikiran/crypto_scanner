"""
Tests for JournalStore analytics generation methods.

Tests generate_daily_analytics() and get_rolling_stats() functionality.

Requirements: 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from streaming.models import JournalEntry, SetupType, SignalOutcomeType
from storage.journal_store import JournalStore


@pytest.fixture
def temp_journal_dir():
    """Create a temporary directory for journal files."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def journal(temp_journal_dir):
    """Create a JournalStore with a temporary directory."""
    return JournalStore(journal_dir=temp_journal_dir)


def _make_entry(
    symbol="ETHUSDT",
    setup_type=SetupType.COMPRESSION_BREAKOUT,
    entry_price=2000.0,
    stop_loss=1950.0,
    composite_score=75.0,
    btc_regime="bullish",
    timestamp=None,
):
    """Helper to create a JournalEntry."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    return JournalEntry(
        symbol=symbol,
        setup_type=setup_type,
        entry_price=entry_price,
        stop_loss=stop_loss,
        composite_score=composite_score,
        relative_strength=60.0,
        relative_volume=2.0,
        oi_change_pct=3.5,
        funding_rate=0.01,
        ema20=1980.0,
        ema50=1960.0,
        ema200=1900.0,
        atr14=25.0,
        btc_regime=btc_regime,
        timestamp=timestamp,
    )


class TestGenerateDailyAnalytics:
    """Tests for generate_daily_analytics()."""

    def test_zero_signal_day(self, journal):
        """Zero-signal days should return all zeros/empty. Requirement 17.6."""
        result = journal.generate_daily_analytics()

        assert result["total_signals"] == 0
        assert result["wins"] == 0
        assert result["losses"] == 0
        assert result["expiries"] == 0
        assert result["win_rate"] == 0.0
        assert result["avg_rr"] == 0.0
        assert result["best_setup_type"] == ""
        assert result["best_btc_regime"] == ""
        assert result["best_hour_utc"] == -1

    def test_analytics_with_resolved_signals(self, journal):
        """Analytics should correctly calculate win rate and avg RR. Requirement 17.5."""
        now = datetime.utcnow()

        # Log 4 signals and record outcomes
        ids = []
        for i in range(4):
            entry = _make_entry(
                symbol=f"COIN{i}USDT",
                timestamp=now,
            )
            signal_id = journal.log_signal(entry)
            ids.append(signal_id)

        # 2 wins, 1 loss, 1 expiry
        journal.record_outcome(ids[0], SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)
        journal.record_outcome(ids[1], SignalOutcomeType.WIN, 2.0, 240.0, 2100.0)
        journal.record_outcome(ids[2], SignalOutcomeType.LOSS, -1.0, 60.0, 1950.0)
        journal.record_outcome(ids[3], SignalOutcomeType.EXPIRY, 0.3, 10080.0, 2015.0)

        result = journal.generate_daily_analytics(now)

        assert result["total_signals"] == 4
        assert result["wins"] == 2
        assert result["losses"] == 1
        assert result["expiries"] == 1
        assert result["win_rate"] == 50.0
        # avg_rr = (1.5 + 2.0 + (-1.0) + 0.3) / 4 = 0.7
        assert result["avg_rr"] == 0.7

    def test_best_setup_type(self, journal):
        """Should identify setup type with highest win rate. Requirement 18.5."""
        now = datetime.utcnow()

        # Compression breakout: 1 win, 1 loss (50% WR)
        id1 = journal.log_signal(_make_entry(
            symbol="ETH1", setup_type=SetupType.COMPRESSION_BREAKOUT, timestamp=now
        ))
        id2 = journal.log_signal(_make_entry(
            symbol="ETH2", setup_type=SetupType.COMPRESSION_BREAKOUT, timestamp=now
        ))
        journal.record_outcome(id1, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)
        journal.record_outcome(id2, SignalOutcomeType.LOSS, -1.0, 60.0, 1950.0)

        # Pullback continuation: 2 wins (100% WR)
        id3 = journal.log_signal(_make_entry(
            symbol="SOL1", setup_type=SetupType.PULLBACK_CONTINUATION, timestamp=now
        ))
        id4 = journal.log_signal(_make_entry(
            symbol="SOL2", setup_type=SetupType.PULLBACK_CONTINUATION, timestamp=now
        ))
        journal.record_outcome(id3, SignalOutcomeType.WIN, 2.0, 180.0, 2100.0)
        journal.record_outcome(id4, SignalOutcomeType.WIN, 1.8, 200.0, 2090.0)

        result = journal.generate_daily_analytics(now)
        assert result["best_setup_type"] == "pullback_continuation"

    def test_best_btc_regime(self, journal):
        """Should identify BTC regime with highest win rate. Requirement 18.3."""
        now = datetime.utcnow()

        # Bullish regime: 1 win, 1 loss
        id1 = journal.log_signal(_make_entry(symbol="A", btc_regime="bullish", timestamp=now))
        id2 = journal.log_signal(_make_entry(symbol="B", btc_regime="bullish", timestamp=now))
        journal.record_outcome(id1, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)
        journal.record_outcome(id2, SignalOutcomeType.LOSS, -1.0, 60.0, 1950.0)

        # Not bullish regime: 2 wins
        id3 = journal.log_signal(_make_entry(symbol="C", btc_regime="not_bullish", timestamp=now))
        id4 = journal.log_signal(_make_entry(symbol="D", btc_regime="not_bullish", timestamp=now))
        journal.record_outcome(id3, SignalOutcomeType.WIN, 2.0, 180.0, 2100.0)
        journal.record_outcome(id4, SignalOutcomeType.WIN, 1.8, 200.0, 2090.0)

        result = journal.generate_daily_analytics(now)
        assert result["best_btc_regime"] == "not_bullish"

    def test_best_hour_utc(self, journal):
        """Should identify UTC hour with highest win rate. Requirement 18.4."""
        now = datetime.utcnow()
        # Create signals at specific hours
        hour_10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
        hour_14 = now.replace(hour=14, minute=0, second=0, microsecond=0)

        # Hour 10: 1 win, 1 loss (50%)
        id1 = journal.log_signal(_make_entry(symbol="A", timestamp=hour_10))
        id2 = journal.log_signal(_make_entry(symbol="B", timestamp=hour_10))
        journal.record_outcome(id1, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)
        journal.record_outcome(id2, SignalOutcomeType.LOSS, -1.0, 60.0, 1950.0)

        # Hour 14: 2 wins (100%)
        id3 = journal.log_signal(_make_entry(symbol="C", timestamp=hour_14))
        id4 = journal.log_signal(_make_entry(symbol="D", timestamp=hour_14))
        journal.record_outcome(id3, SignalOutcomeType.WIN, 2.0, 180.0, 2100.0)
        journal.record_outcome(id4, SignalOutcomeType.WIN, 1.8, 200.0, 2090.0)

        result = journal.generate_daily_analytics(now)
        assert result["best_hour_utc"] == 14

    def test_analytics_file_saved(self, journal, temp_journal_dir):
        """Analytics should be saved to analytics_YYYY-MM-DD.json. Requirement 18.5."""
        now = datetime.utcnow()
        journal.generate_daily_analytics(now)

        expected_file = Path(temp_journal_dir) / f"analytics_{now.strftime('%Y-%m-%d')}.json"
        assert expected_file.exists()

        with open(expected_file, "r") as f:
            data = json.load(f)
        assert "win_rate" in data
        assert "avg_rr" in data


class TestGetRollingStats:
    """Tests for get_rolling_stats()."""

    def test_empty_rolling_stats(self, journal):
        """Should return empty stats when no signals exist."""
        result = journal.get_rolling_stats(days=30)

        assert result["days"] == 30
        assert result["total_signals"] == 0
        assert result["by_setup_type"] == {}

    def test_rolling_stats_by_setup_type(self, journal):
        """Should group stats by setup type. Requirements 18.1, 18.2."""
        now = datetime.utcnow()

        # Compression breakout signals
        for i in range(6):
            entry = _make_entry(
                symbol=f"CB{i}",
                setup_type=SetupType.COMPRESSION_BREAKOUT,
                timestamp=now,
            )
            signal_id = journal.log_signal(entry)
            if i < 4:  # 4 wins
                journal.record_outcome(signal_id, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)
            else:  # 2 losses
                journal.record_outcome(signal_id, SignalOutcomeType.LOSS, -1.0, 60.0, 1950.0)

        # Pullback continuation signals
        for i in range(3):
            entry = _make_entry(
                symbol=f"PC{i}",
                setup_type=SetupType.PULLBACK_CONTINUATION,
                timestamp=now,
            )
            signal_id = journal.log_signal(entry)
            journal.record_outcome(signal_id, SignalOutcomeType.WIN, 2.0, 180.0, 2100.0)

        result = journal.get_rolling_stats(days=30)

        assert result["total_signals"] == 9
        cb_stats = result["by_setup_type"]["compression_breakout"]
        assert cb_stats["total_trades"] == 6
        # 4 wins / 6 total = 66.67%
        assert cb_stats["win_rate"] == 66.67
        assert cb_stats["insufficient_data"] is False

        pc_stats = result["by_setup_type"]["pullback_continuation"]
        assert pc_stats["total_trades"] == 3
        assert pc_stats["win_rate"] == 100.0
        # <5 trades → insufficient data (Requirement 18.6)
        assert pc_stats["insufficient_data"] is True

    def test_insufficient_data_threshold(self, journal):
        """Setup types with <5 trades should be marked insufficient. Requirement 18.6."""
        now = datetime.utcnow()

        # Only 4 trades for compression breakout
        for i in range(4):
            entry = _make_entry(
                symbol=f"CB{i}",
                setup_type=SetupType.COMPRESSION_BREAKOUT,
                timestamp=now,
            )
            signal_id = journal.log_signal(entry)
            journal.record_outcome(signal_id, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)

        result = journal.get_rolling_stats(days=30)
        cb_stats = result["by_setup_type"]["compression_breakout"]
        assert cb_stats["total_trades"] == 4
        assert cb_stats["insufficient_data"] is True

    def test_rolling_stats_respects_window(self, journal, temp_journal_dir):
        """Should only include signals within the rolling window."""
        now = datetime.utcnow()

        # Signal from today (within 7-day window)
        entry_today = _make_entry(symbol="TODAY", timestamp=now)
        id_today = journal.log_signal(entry_today)
        journal.record_outcome(id_today, SignalOutcomeType.WIN, 1.5, 120.0, 2075.0)

        # Manually create a signal file for 40 days ago (outside 30-day window)
        old_date = now - timedelta(days=40)
        old_file = Path(temp_journal_dir) / f"signals_{old_date.strftime('%Y-%m-%d')}.json"
        old_data = {
            "signals": [{
                "signal_id": "old-signal",
                "symbol": "OLDCOIN",
                "setup_type": "compression_breakout",
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "composite_score": 70.0,
                "relative_strength": 50.0,
                "relative_volume": 1.5,
                "oi_change_pct": 2.0,
                "funding_rate": 0.01,
                "ema20": 99.0,
                "ema50": 98.0,
                "ema200": 95.0,
                "atr14": 3.0,
                "btc_regime": "bullish",
                "timestamp": old_date.isoformat(),
                "outcome": "win",
                "actual_rr": 2.0,
                "duration_minutes": 300.0,
                "exit_price": 110.0,
            }],
            "rejections": [],
        }
        with open(old_file, "w") as f:
            json.dump(old_data, f)

        result = journal.get_rolling_stats(days=30)
        # Only today's signal should be included
        assert result["total_signals"] == 1


class TestAnalyticsRetention:
    """Tests for analytics file retention."""

    def test_analytics_retention_enforcement(self, temp_journal_dir):
        """Analytics files older than 90 days should be deleted. Requirement 18.7."""
        journal_dir = Path(temp_journal_dir)

        # Create an old analytics file (100 days ago)
        old_date = datetime.utcnow() - timedelta(days=100)
        old_file = journal_dir / f"analytics_{old_date.strftime('%Y-%m-%d')}.json"
        old_file.write_text(json.dumps({"win_rate": 50.0}))

        # Create a recent analytics file (10 days ago)
        recent_date = datetime.utcnow() - timedelta(days=10)
        recent_file = journal_dir / f"analytics_{recent_date.strftime('%Y-%m-%d')}.json"
        recent_file.write_text(json.dumps({"win_rate": 60.0}))

        # Initialize journal (triggers retention on startup for signals)
        journal = JournalStore(journal_dir=temp_journal_dir)

        # Generate analytics to trigger analytics retention
        journal.generate_daily_analytics()

        # Old file should be deleted, recent should remain
        assert not old_file.exists()
        assert recent_file.exists()
