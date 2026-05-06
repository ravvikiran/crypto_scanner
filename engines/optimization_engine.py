"""
Optimization Engine
Strategy performance tracking and auto-optimization.
Uses JSON files for persistence (no SQLite).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from loguru import logger

from config import get_config
from models import TradingSignal, StrategyType


@dataclass
class StrategyPerformance:
    """Performance metrics for a strategy"""
    strategy_type: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_rr: float = 0.0
    max_drawdown: float = 0.0
    weight: float = 1.0
    is_enabled: bool = True
    last_updated: datetime = field(default_factory=datetime.now)


class TradeJournal:
    """
    Trade journal system for tracking all trades and outcomes.
    Uses JSON file for persistence.
    
    Data Model:
    - trade_id
    - coin
    - strategy
    - timeframe
    - entry
    - stop
    - targets
    - outcome (win/loss)
    - RR achieved
    - market_regime
    - timestamp
    """
    
    def __init__(self):
        self.config = get_config()
        self._data_dir = Path(self.config.logging.log_file).parent.parent / "data"
        self._data_dir.mkdir(exist_ok=True)
        self._journal_file = self._data_dir / "optimization_journal.json"
        self._trades: List[Dict] = self._load_trades()
        logger.info(f"Trade journal initialized (JSON) with {len(self._trades)} trades")
    
    def _load_trades(self) -> List[Dict]:
        """Load trades from JSON file."""
        if not self._journal_file.exists():
            return []
        try:
            with open(self._journal_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load trade journal: {e}")
            return []
    
    def _save_trades(self):
        """Save trades to JSON file atomically."""
        tmp = self._journal_file.with_suffix('.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._trades, f, indent=2, default=str)
            tmp.replace(self._journal_file)
        except Exception as e:
            logger.error(f"Failed to save trade journal: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
    
    def log_trade(self, signal: TradingSignal, outcome: str, exit_price: float, pnl_percent: float, rr_achieved: float, market_regime: str = "UNKNOWN"):
        """Log a completed trade"""
        try:
            trade_data = {
                "trade_id": signal.id,
                "symbol": signal.symbol,
                "coin_name": signal.name,
                "strategy_type": signal.strategy_type.value,
                "timeframe": signal.timeframe,
                "direction": signal.direction.value,
                "entry_price": signal.entry_zone_min,
                "stop_loss": signal.stop_loss,
                "target_1": signal.target_1,
                "target_2": signal.target_2,
                "exit_price": exit_price,
                "outcome": outcome,
                "pnl_percent": pnl_percent,
                "rr_achieved": rr_achieved,
                "market_regime": market_regime,
                "btc_trend": signal.btc_trend.value if hasattr(signal, 'btc_trend') and signal.btc_trend else "UNKNOWN",
                "entry_timestamp": signal.timestamp.isoformat(),
                "exit_timestamp": datetime.now().isoformat(),
                "notes": "",
                "created_at": datetime.now().isoformat()
            }
            
            # Replace if exists, otherwise append
            existing_idx = next(
                (i for i, t in enumerate(self._trades) if t.get("trade_id") == signal.id),
                None
            )
            if existing_idx is not None:
                self._trades[existing_idx] = trade_data
            else:
                self._trades.append(trade_data)
            
            # Keep only last 1000 trades to prevent unbounded growth
            if len(self._trades) > 1000:
                self._trades = self._trades[-1000:]
            
            self._save_trades()
            logger.info(f"Logged trade {signal.id}: {outcome} ({pnl_percent:.2f}%, RR: {rr_achieved:.2f})")
            
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
    
    def get_trades(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get trades from journal"""
        try:
            filtered = self._trades
            
            if strategy:
                filtered = [t for t in filtered if t.get("strategy_type") == strategy]
            
            if symbol:
                filtered = [t for t in filtered if t.get("symbol") == symbol]
            
            # Sort by entry_timestamp descending
            filtered = sorted(
                filtered,
                key=lambda t: t.get("entry_timestamp", ""),
                reverse=True
            )
            
            return filtered[:limit]
            
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    def get_journal_stats(
        self,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        lookback_trades: int = 50
    ) -> Dict:
        """
        Get journal statistics for a strategy/symbol/timeframe.
        
        Returns:
            Dictionary with:
            - sample_size: number of trades
            - win_rate: percentage of winning trades
            - avg_rr: average risk/reward achieved
            - avg_win: average win percentage
            - avg_loss: average loss percentage
            - by_regime: performance by market regime
        """
        try:
            # Filter trades with outcomes
            filtered = [t for t in self._trades if t.get("outcome")]
            
            if strategy:
                filtered = [t for t in filtered if t.get("strategy_type") == strategy]
            
            if symbol:
                filtered = [t for t in filtered if t.get("symbol") == symbol]
            
            if timeframe:
                filtered = [t for t in filtered if t.get("timeframe") == timeframe]
            
            # Sort by timestamp descending and limit
            filtered = sorted(
                filtered,
                key=lambda t: t.get("entry_timestamp", ""),
                reverse=True
            )[:lookback_trades]
            
            if not filtered:
                return {
                    "sample_size": 0,
                    "win_rate": 0.5,
                    "avg_rr": 0,
                    "avg_win": 0,
                    "avg_loss": 0,
                    "by_regime": {},
                    "by_timeframe": {}
                }
            
            wins = [t for t in filtered if t.get("outcome") == "WIN"]
            losses = [t for t in filtered if t.get("outcome") == "LOSS"]
            
            win_rate = len(wins) / len(filtered) if filtered else 0.5
            
            rr_values = [t.get("rr_achieved", 0) for t in filtered if t.get("rr_achieved")]
            avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0
            
            avg_win = sum(t.get("pnl_percent", 0) for t in wins) / len(wins) if wins else 0
            avg_loss = abs(sum(t.get("pnl_percent", 0) for t in losses) / len(losses)) if losses else 0
            
            # Performance by regime
            by_regime = {}
            for t in filtered:
                regime = t.get("market_regime") or "UNKNOWN"
                if regime not in by_regime:
                    by_regime[regime] = {"total": 0, "wins": 0}
                by_regime[regime]["total"] += 1
                if t.get("outcome") == "WIN":
                    by_regime[regime]["wins"] += 1
            
            for regime in by_regime:
                total = by_regime[regime]["total"]
                wins_count = by_regime[regime]["wins"]
                by_regime[regime]["win_rate"] = wins_count / total if total > 0 else 0
            
            return {
                "sample_size": len(filtered),
                "win_rate": win_rate,
                "avg_rr": avg_rr,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "by_regime": by_regime,
                "trades": filtered[:10]
            }
            
        except Exception as e:
            logger.error(f"Error getting journal stats: {e}")
            return {
                "sample_size": 0,
                "win_rate": 0.5,
                "avg_rr": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "by_regime": {},
                "by_timeframe": {}
            }


class OptimizationEngine:
    """
    Auto-optimization engine.
    
    Features:
    - Disable weak strategies
    - Increase weight of strong strategies
    - Adjust thresholds dynamically
    """
    
    def __init__(self):
        self.config = get_config()
        self.journal = TradeJournal()
        self.strategy_weights: Dict[str, float] = {}
        self._initialize_weights()
    
    def _initialize_weights(self):
        """Initialize strategy weights"""
        for st in StrategyType:
            if st != StrategyType.NONE:
                self.strategy_weights[st.value] = 1.0
    
    def get_strategy_weight(self, strategy_type: str) -> float:
        """Get weight for a strategy type"""
        return self.strategy_weights.get(strategy_type, 1.0)
    
    def update_strategy_performance(self, strategy_type: str, performance: StrategyPerformance):
        """Update strategy performance and adjust weight"""
        weight = self._calculate_weight(performance)
        self.strategy_weights[strategy_type] = weight
        
        logger.info(f"Strategy {strategy_type}: weight = {weight:.2f} (WR: {performance.win_rate:.1%}, trades: {performance.total_trades})")
    
    def _calculate_weight(self, perf: StrategyPerformance) -> float:
        """Calculate weight based on performance"""
        if perf.total_trades < 10:
            return 1.0
        
        if perf.win_rate < 0.40:
            return 0.5
        elif perf.win_rate < 0.50:
            return 0.75
        elif perf.win_rate > 0.60:
            return 1.25
        elif perf.win_rate > 0.55:
            return 1.1
        
        return 1.0
    
    def analyze_performance(
        self,
        strategy: Optional[str] = None,
        lookback_trades: int = 50
    ) -> Dict[str, StrategyPerformance]:
        """
        Analyze performance for all strategies.
        
        Returns:
            Dictionary of strategy performances
        """
        results = {}
        
        for st in StrategyType:
            if st == StrategyType.NONE:
                continue
            
            strategy_name = st.value
            
            stats = self.journal.get_journal_stats(
                strategy=strategy_name,
                lookback_trades=lookback_trades
            )
            
            perf = StrategyPerformance(
                strategy_type=strategy_name,
                total_trades=stats.get("sample_size", 0),
                winning_trades=int(stats.get("win_rate", 0) * stats.get("sample_size", 0)),
                losing_trades=int((1 - stats.get("win_rate", 0)) * stats.get("sample_size", 0)),
                win_rate=stats.get("win_rate", 0.5),
                avg_rr=stats.get("avg_rr", 0),
                weight=self.get_strategy_weight(strategy_name)
            )
            
            results[strategy_name] = perf
        
        return results
    
    def get_adjusted_threshold(
        self,
        base_threshold: float,
        strategy: str,
        market_regime: str
    ) -> float:
        """
        Get adjusted threshold based on strategy performance and regime.
        
        Args:
            base_threshold: Original threshold
            strategy: Strategy type
            market_regime: Current market regime
            
        Returns:
            Adjusted threshold
        """
        weight = self.get_strategy_weight(strategy)
        
        if market_regime == "LOW_VOL":
            return base_threshold + 1.0
        
        if weight < 0.8:
            return base_threshold + 0.5
        elif weight > 1.2:
            return max(5.0, base_threshold - 0.5)
        
        return base_threshold
    
    def should_take_trade(
        self,
        strategy: str,
        confidence: float,
        market_regime: str
    ) -> Tuple[bool, str]:
        """
        Determine if a trade should be taken based on optimization.
        
        Returns:
            (should_take, reason)
        """
        weight = self.get_strategy_weight(strategy)
        
        if weight < 0.5:
            return False, f"Strategy {strategy} disabled (weight: {weight:.2f})"
        
        if market_regime == "LOW_VOL":
            if confidence < 8.5:
                return False, "Low volatility - skip low confidence trades"
        
        if weight < 0.8 and confidence < 7.5:
            return False, f"Weak strategy performance - requires higher confidence"
        
        return True, "Trade allowed"
    
    def optimize_all(self) -> Dict[str, StrategyPerformance]:
        """Run full optimization on all strategies"""
        logger.info("Running strategy optimization...")
        
        performances = self.analyze_performance()
        
        for strategy, perf in performances.items():
            self.update_strategy_performance(strategy, perf)
        
        logger.info(f"Optimization complete. {len(performances)} strategies analyzed")
        
        return performances
    
    def get_recommendations(self) -> List[Dict]:
        """Get optimization recommendations"""
        performances = self.analyze_performance()
        
        recommendations = []
        
        for strategy, perf in performances.items():
            if perf.total_trades >= 10:
                if perf.win_rate < 0.40:
                    recommendations.append({
                        "type": "DISABLE",
                        "strategy": strategy,
                        "reason": f"Win rate too low ({perf.win_rate:.1%})",
                        "action": "Reduce weight to 0.5"
                    })
                elif perf.win_rate > 0.60:
                    recommendations.append({
                        "type": "BOOST",
                        "strategy": strategy,
                        "reason": f"Win rate excellent ({perf.win_rate:.1%})",
                        "action": "Increase weight to 1.25"
                    })
        
        return recommendations
