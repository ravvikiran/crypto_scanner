"""
Strategy Optimizer - Tracks performance and auto-adjusts strategy weights.
"""

from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict
from loguru import logger


class StrategyOptimizer:
    """
    Tracks strategy performance and adjusts weights dynamically.

    - Calculates win rate, avg R:R, profit factor per strategy
    - Adjusts weights: increase if WR > 55%, decrease if WR < 45%
    - Runs after every 20+ closed trades
    """

    DEFAULT_WEIGHTS = {
        'TREND': 1.0,
        'VERC': 0.8,
        'MTF': 0.9,
        'BREAKOUT': 1.0,
        'PULLBACK': 0.9,
        'PRD': 1.0
    }

    def __init__(self, trade_journal=None):
        """
        Initialize optimizer.

        Args:
            trade_journal: TradeJournal instance to fetch outcomes
        """
        self.trade_journal = trade_journal
        self.weights = self.DEFAULT_WEIGHTS.copy()
        self.min_trades_for_adjustment = 10

    def calculate_strategy_stats(self, strategy: str, days: int = 30) -> Dict:
        """
        Calculate performance stats for a strategy.

        Returns:
            {win_rate, avg_rr, profit_factor, trades}
        """
        if not self.trade_journal:
            return {'win_rate': 0, 'avg_rr': 0, 'profit_factor': 0, 'trades': 0}

        # Get trades for strategy
        strategy_trades = self.trade_journal.get_trades_by_strategy(strategy)

        # Filter to recent N days
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent_trades = [
            t for t in strategy_trades
            if datetime.fromisoformat(t.get('timestamp', '')) > cutoff
        ]

        if not recent_trades:
            return {'win_rate': 0, 'avg_rr': 0, 'profit_factor': 0, 'trades': 0}

        wins = [t for t in recent_trades if t.get('outcome') in ['TARGET_1_HIT', 'TARGET_2_HIT']]
        losses = [t for t in recent_trades if t.get('outcome') == 'STOP_LOSS_HIT']

        win_rate = len(wins) / len(recent_trades) if recent_trades else 0

        avg_rr = 0
        if wins:
            # Simplified: each win contributes 1R per target hit
            total_rr = sum(1 for _ in wins)  # Could use actual RR if stored
            avg_rr = total_rr / len(wins)

        # Profit factor = gross profit / gross loss
        gross_profit = len(wins)  # Simplified: 1R per win
        gross_loss = len(losses)   # Simplified: 1R per loss
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        return {
            'trades': len(recent_trades),
            'win_rate': round(win_rate, 3),
            'avg_rr': round(avg_rr, 2),
            'profit_factor': round(profit_factor, 2)
        }

    def optimize_weights(self) -> Dict[str, float]:
        """
        Adjust strategy weights based on recent 30-day performance.

        Rules:
        - Win rate > 55% → weight *= 1.1 (max 2.0)
        - Win rate < 45% → weight *= 0.9 (min 0.5)
        - Otherwise → keep unchanged
        """
        if not self.trade_journal:
            logger.warning("No trade journal - skipping optimization")
            return self.weights

        total_closed = len(self.trade_journal.get_outcomes())
        if total_closed < self.min_trades_for_adjustment:
            logger.info(f"Not enough trades for optimization ({total_closed}/{self.min_trades_for_adjustment})")
            return self.weights

        logger.info("Running strategy weight optimization...")
        changes = []

        for strategy in list(self.weights.keys()):
            stats = self.calculate_strategy_stats(strategy, days=30)

            if stats['trades'] < 5:
                continue  # Skip if not enough recent data

            win_rate = stats['win_rate']
            old_weight = self.weights[strategy]

            if win_rate > 0.55:
                new_weight = min(2.0, old_weight * 1.1)
            elif win_rate < 0.45:
                new_weight = max(0.5, old_weight * 0.9)
            else:
                new_weight = old_weight

            if abs(new_weight - old_weight) > 0.01:
                self.weights[strategy] = new_weight
                changes.append(f"{strategy}: {old_weight:.2f} → {new_weight:.2f} (WR: {win_rate:.1%})")

        if changes:
            logger.info(f"Optimized weights: {changes}")
        else:
            logger.info("No weight changes needed")

        return self.weights

    def get_weights(self) -> Dict[str, float]:
        """Get current strategy weights."""
        return self.weights.copy()

    def get_performance_report(self) -> Dict:
        """
        Generate performance report for all strategies.

        Returns:
            Dict with stats per strategy
        """
        report = {}
        for strategy in self.weights:
            stats = self.calculate_strategy_stats(strategy)
            report[strategy] = {
                **stats,
                'weight': self.weights[strategy]
            }
        return report
