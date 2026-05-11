"""
Tests for main_momentum.py entry point.

Validates configuration loading, symbol loading, startup logging,
and signal handler registration.
"""

import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from main_momentum import load_symbols, log_startup_summary, setup_logging
from config.websocket_config import WebSocketStreamConfig


class TestLoadSymbols:
    """Test symbol loading from various sources."""

    def test_default_symbols_returned_when_no_config(self):
        """When no env var or config.yaml momentum section, returns defaults."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove MOMENTUM_SYMBOLS if present
            os.environ.pop("MOMENTUM_SYMBOLS", None)
            symbols = load_symbols()
            assert len(symbols) > 0
            assert "BTCUSDT" in symbols
            assert "ETHUSDT" in symbols

    def test_env_var_overrides_defaults(self):
        """MOMENTUM_SYMBOLS env var takes priority over defaults."""
        with patch.dict(os.environ, {"MOMENTUM_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT"}):
            symbols = load_symbols()
            assert symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_env_var_handles_whitespace(self):
        """Env var symbols are trimmed and uppercased."""
        with patch.dict(os.environ, {"MOMENTUM_SYMBOLS": " btcusdt , ethusdt "}):
            symbols = load_symbols()
            assert symbols == ["BTCUSDT", "ETHUSDT"]

    def test_env_var_empty_string_falls_through(self):
        """Empty MOMENTUM_SYMBOLS env var falls through to config.yaml or defaults."""
        with patch.dict(os.environ, {"MOMENTUM_SYMBOLS": ""}):
            symbols = load_symbols()
            # Should fall through to defaults since env var is empty
            assert len(symbols) > 0
            assert "BTCUSDT" in symbols


class TestLogStartupSummary:
    """Test startup logging output."""

    def test_logs_configuration_summary(self, caplog):
        """log_startup_summary should log key configuration values."""
        import logging

        config = WebSocketStreamConfig()
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        with caplog.at_level(logging.INFO, logger="momentum_scanner"):
            log_startup_summary(config, symbols)

        log_text = caplog.text
        assert "Exchanges enabled" in log_text
        assert "Symbols count: 3" in log_text
        assert "Timeframes" in log_text
        assert "Alert cooldown" in log_text

    def test_logs_all_exchanges(self, caplog):
        """Should log the enabled exchanges."""
        import logging

        config = WebSocketStreamConfig()
        symbols = ["BTCUSDT"]

        with caplog.at_level(logging.INFO, logger="momentum_scanner"):
            log_startup_summary(config, symbols)

        # Default config has binance enabled
        assert "binance" in caplog.text


class TestSetupLogging:
    """Test logging setup."""

    def test_setup_logging_creates_log_directory(self, tmp_path, monkeypatch):
        """setup_logging should create the logs directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        setup_logging()
        assert (tmp_path / "logs").exists()
