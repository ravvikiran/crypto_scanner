"""
Test suite for Crypto Scanner.
"""

import pytest


def test_imports():
    """Test that all main modules can be imported."""
    from ai import AISignalAnalyzer
    from alerts import AlertManager
    from collectors import MarketDataCollector
    from config import get_config
    from engines import MarketRegimeEngine
    from filters import BitcoinFilter
    from indicators import IndicatorEngine
    from scorer import SignalScorer
    from strategies import StrategyEngine

    assert True


def test_config():
    """Test configuration loading."""
    from config import get_config
    cfg = get_config()
    assert cfg.scanner.min_signal_score == 7.0


if __name__ == "__main__":
    test_imports()
    test_config()
    print("All basic tests passed!")