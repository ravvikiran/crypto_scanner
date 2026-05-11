"""
Test suite for Crypto Scanner - basic import and config validation.
"""

import pytest


def test_imports():
    """Test that all main modules can be imported."""
    from config import get_config
    from indicators import IndicatorEngine
    from alerts.momentum_alert_manager import MomentumAlertManager
    from engines.relative_strength_engine import RelativeStrengthEngine
    from filters.market_regime_filter import MarketRegimeFilter
    from filters.trend_filter import TrendFilter
    from filters.volatility_gate import VolatilityGate
    from detectors.setup_detector import (
        detect_compression_breakout,
        detect_pullback_continuation,
        detect_momentum_breakout,
    )
    from scoring.scoring_engine import score
    from storage.journal_store import JournalStore
    from universe.universe_manager import UniverseManager
    from monitors.trailing_stop_monitor import TrailingStopMonitor
    from monitors.status_reporter import StatusReporter
    from health.health_server import HealthCheckServer
    from core.momentum_scanner import MomentumScanner

    assert True


def test_config():
    """Test configuration loading."""
    from config import get_config
    cfg = get_config()
    assert cfg.scanner.min_signal_score == 5.5


if __name__ == "__main__":
    test_imports()
    test_config()
    print("All basic tests passed!")