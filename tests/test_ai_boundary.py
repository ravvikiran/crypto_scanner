"""
Tests for AI boundary enforcement in MomentumScanner.

Validates Requirements 19.1–19.6:
- No AI/LLM calls in the filter-detect-score pipeline
- Optional AI integration points only execute when ai_enabled=True
- Deterministic output regardless of ai_enabled flag
"""

import pytest
from unittest.mock import patch, MagicMock

from core.momentum_scanner import MomentumScanner


class TestAIBoundaryEnforcement:
    """Test AI boundary enforcement in MomentumScanner."""

    def _create_scanner(self, ai_enabled: bool = False):
        """Create a MomentumScanner with mocked dependencies."""
        with patch("core.momentum_scanner.WebSocketManager"), \
             patch("core.momentum_scanner.EventBus"), \
             patch("core.momentum_scanner.StateManager"), \
             patch("core.momentum_scanner.MarketRegimeFilter"), \
             patch("core.momentum_scanner.TrendFilter"), \
             patch("core.momentum_scanner.RelativeStrengthEngine"), \
             patch("core.momentum_scanner.MomentumAlertManager"), \
             patch("core.momentum_scanner.JournalStore"):
            scanner = MomentumScanner(ai_enabled=ai_enabled)
        return scanner

    def test_ai_disabled_by_default(self):
        """AI should be disabled by default (Req 19.6)."""
        scanner = self._create_scanner(ai_enabled=False)
        assert scanner.ai_enabled is False

    def test_ai_enabled_flag(self):
        """AI can be explicitly enabled via constructor parameter."""
        scanner = self._create_scanner(ai_enabled=True)
        assert scanner.ai_enabled is True

    def test_eod_summary_returns_none_when_disabled(self):
        """_ai_generate_eod_summary returns None when ai_enabled=False (Req 19.5)."""
        scanner = self._create_scanner(ai_enabled=False)
        result = scanner._ai_generate_eod_summary()
        assert result is None

    def test_eod_summary_returns_none_when_enabled_no_provider(self):
        """_ai_generate_eod_summary returns None when enabled but no provider configured."""
        scanner = self._create_scanner(ai_enabled=True)
        result = scanner._ai_generate_eod_summary()
        assert result is None

    def test_journal_commentary_returns_none_when_disabled(self):
        """_ai_add_journal_commentary returns None when ai_enabled=False (Req 19.5)."""
        scanner = self._create_scanner(ai_enabled=False)
        result = scanner._ai_add_journal_commentary("signal_123")
        assert result is None

    def test_journal_commentary_returns_none_when_enabled_no_provider(self):
        """_ai_add_journal_commentary returns None when enabled but no provider configured."""
        scanner = self._create_scanner(ai_enabled=True)
        result = scanner._ai_add_journal_commentary("signal_123")
        assert result is None

    def test_analytics_narrative_returns_none_when_disabled(self):
        """_ai_format_analytics_narrative returns None when ai_enabled=False (Req 19.5)."""
        scanner = self._create_scanner(ai_enabled=False)
        analytics = {"win_rate": 0.65, "avg_rr": 1.8, "best_setup_type": "compression_breakout"}
        result = scanner._ai_format_analytics_narrative(analytics)
        assert result is None

    def test_analytics_narrative_returns_none_when_enabled_no_provider(self):
        """_ai_format_analytics_narrative returns None when enabled but no provider configured."""
        scanner = self._create_scanner(ai_enabled=True)
        analytics = {"win_rate": 0.65, "avg_rr": 1.8, "best_setup_type": "compression_breakout"}
        result = scanner._ai_format_analytics_narrative(analytics)
        assert result is None

    def test_ai_methods_do_not_affect_pipeline_state(self):
        """AI methods should not modify any internal pipeline state (Req 19.6)."""
        scanner = self._create_scanner(ai_enabled=True)

        # Capture state before AI calls
        running_before = scanner.is_running

        # Call all AI methods
        scanner._ai_generate_eod_summary()
        scanner._ai_add_journal_commentary("test_signal")
        scanner._ai_format_analytics_narrative({"win_rate": 0.5})

        # State should be unchanged
        assert scanner.is_running == running_before

    def test_no_ai_imports_in_pipeline_methods(self):
        """
        Verify that the core pipeline methods do not reference AI modules.

        This is a structural test ensuring the filter-detect-score pipeline
        has no coupling to AI/LLM code (Req 19.1, 19.2, 19.3, 19.4).
        """
        import inspect
        import ast

        source = inspect.getsource(MomentumScanner)
        tree = ast.parse(source)

        # Pipeline method names that must NEVER call AI
        pipeline_methods = {
            "_process_event",
            "_handle_btc_4h",
            "_handle_4h_event",
            "_handle_1h_event",
            "_handle_15m_event",
            "_score_setup",
            "_try_emit_alert",
            "_update_rankings",
            "_emit_alerts",
        }

        # AI method names that are the only allowed AI integration points
        ai_methods = {
            "_ai_generate_eod_summary",
            "_ai_add_journal_commentary",
            "_ai_format_analytics_narrative",
        }

        # Walk the AST and check that pipeline methods don't call AI methods
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in pipeline_methods:
                # Check all calls within this method
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute):
                        if child.attr in ai_methods:
                            pytest.fail(
                                f"Pipeline method '{node.name}' calls AI method "
                                f"'{child.attr}' — this violates the AI boundary "
                                f"(Requirements 19.1–19.4)"
                            )
