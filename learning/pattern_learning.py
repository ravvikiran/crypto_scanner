"""
Pattern Learning - Analyzes trade journal to learn which patterns work best.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
from loguru import logger


class PatternLearning:
    """
    Analyzes historical trades to generate insights about:
    - Best/worst performing strategies
    - Optimal timeframes
    - Market regime suitability
    - Pattern effectiveness
    """

    def __init__(self, trade_journal=None):
        self.trade_journal = trade_journal
        self.min_trades_for_insight = 10

    def analyze_patterns(self, limit: int = 100) -> Dict:
        """
        Analyze recent trades and generate insights.

        Args:
            limit: Max number of recent trades to analyze

        Returns:
            {'insights': [], 'summary': ''}
        """
        if not self.trade_journal:
            return {'insights': [], 'message': 'No trade journal available'}

        closed_trades = self.trade_journal.get_closed_trades(limit=limit)

        if len(closed_trades) < self.min_trades_for_insight:
            return {
                'insights': [],
                'message': f'Need {self.min_trades_for_insight}+ trades for analysis (have {len(closed_trades)})'
            }

        insights = []

        # 1. Group by strategy
        by_strategy = defaultdict(list)
        for t in closed_trades:
            strategy = t.get('strategy_type', 'Unknown')
            by_strategy[strategy].append(t)

        for strategy, trades in by_strategy.items():
            if len(trades) < 5:
                continue  # Need minimum trades

            wins = [t for t in trades if t.get('outcome') in ['TARGET_1_HIT', 'TARGET_2_HIT']]
            losses = [t for t in trades if t.get('outcome') == 'STOP_LOSS_HIT']

            win_rate = len(wins) / len(trades) if trades else 0

            # Avg R:R achieved (simplified)
            avg_rr = 0
            if wins:
                # Count each target hit as 1R
                total_rr = sum(1 for _ in wins)  # Simplified
                avg_rr = total_rr / len(wins)

            recommendation = self._get_recommendation(win_rate, avg_rr)

            insights.append({
                'type': 'STRATEGY_PERFORMANCE',
                'strategy': strategy,
                'trades': len(trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(win_rate * 100, 1),
                'avg_rr': round(avg_rr, 2),
                'recommendation': recommendation
            })

        # 2. Group by market regime/context
        by_regime = defaultdict(list)
        for t in closed_trades:
            regime = t.get('market_context', t.get('market_regime', 'UNKNOWN'))
            by_regime[regime].append(t)

        for regime, trades in by_regime.items():
            if len(trades) < 10:
                continue

            wins = [t for t in trades if t.get('outcome') in ['TARGET_1_HIT', 'TARGET_2_HIT']]
            win_rate = len(wins) / len(trades) if trades else 0

            insights.append({
                'type': 'REGIME_ANALYSIS',
                'regime': regime,
                'trades': len(trades),
                'win_rate': round(win_rate * 100, 1),
                'recommendation': f"Performance in {regime} regime: {win_rate:.0%} win rate"
            })

        # 3. Group by timeframe
        by_timeframe = defaultdict(list)
        for t in closed_trades:
            tf = t.get('timeframe', 'Unknown')
            by_timeframe[tf].append(t)

        for tf, trades in by_timeframe.items():
            if len(trades) < 5:
                continue

            wins = [t for t in trades if t.get('outcome') in ['TARGET_1_HIT', 'TARGET_2_HIT']]
            win_rate = len(wins) / len(trades) if trades else 0

            insights.append({
                'type': 'TIMEFRAME_PERFORMANCE',
                'timeframe': tf,
                'trades': len(trades),
                'win_rate': round(win_rate * 100, 1),
                'recommendation': f"{tf} timeframe: {win_rate:.0%} win rate"
            })

        return {
            'insights': insights,
            'total_trades_analyzed': len(closed_trades),
            'generated_at': datetime.utcnow().isoformat()
        }

    def _get_recommendation(self, win_rate: float, avg_rr: float) -> str:
        """Generate actionable recommendation based on performance."""
        if win_rate > 0.65 and avg_rr >= 2.0:
            return "INCREASE allocation - excellent performance"
        elif win_rate > 0.55 and avg_rr >= 1.5:
            return "MAINTAIN allocation - good performance"
        elif win_rate < 0.40:
            return "DECREASE allocation - poor win rate"
        elif avg_rr < 1.0:
            return "REVIEW risk management - low R:R"
        else:
            return "MONITOR closely - mixed results"

    def get_best_performing_strategy(self, days: int = 30) -> Optional[Dict]:
        """Get the best performing strategy in recent period."""
        if not self.trade_journal:
            return None

        cutoff = datetime.utcnow() - timedelta(days=days)
        all_trades = self.trade_journal.get_outcomes()

        recent = [
            t for t in all_trades
            if datetime.fromisoformat(t.get('timestamp', '')) > cutoff
        ]

        if not recent:
            return None

        by_strategy = defaultdict(list)
        for t in recent:
            by_strategy[t.get('strategy_type', 'Unknown')].append(t)

        best = None
        best_wr = -1

        for strategy, trades in by_strategy.items():
            if len(trades) < 3:
                continue
            wins = sum(1 for t in trades if t.get('outcome') in ['TARGET_1_HIT', 'TARGET_2_HIT'])
            wr = wins / len(trades)
            if wr > best_wr:
                best_wr = wr
                best = {
                    'strategy': strategy,
                    'win_rate': wr,
                    'trades': len(trades)
                }

        return best
