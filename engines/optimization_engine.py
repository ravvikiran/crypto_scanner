"""
Optimization Engine
Strategy performance tracking and auto-optimization.
"""

import sqlite3
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
        self.db_path = self._get_db_path()
        self._init_database()
    
    def _get_db_path(self) -> Path:
        """Get database file path"""
        data_dir = Path(self.config.logging.log_file).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir / "trade_journal.db"
    
    def _init_database(self):
        """Initialize trade journal database"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    coin_name TEXT,
                    strategy_type TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    exit_price REAL,
                    outcome TEXT,
                    pnl_percent REAL,
                    rr_achieved REAL,
                    market_regime TEXT,
                    btc_trend TEXT,
                    entry_timestamp TEXT,
                    exit_timestamp TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol ON trades(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategy ON trades(strategy_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON trades(entry_timestamp)
            """)
            
            conn.commit()
            conn.close()
            
            logger.info(f"Trade journal initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Trade journal initialization error: {e}")
    
    def log_trade(self, signal: TradingSignal, outcome: str, exit_price: float, pnl_percent: float, rr_achieved: float, market_regime: str = "UNKNOWN"):
        """Log a completed trade"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    trade_id, symbol, coin_name, strategy_type, timeframe,
                    direction, entry_price, stop_loss, target_1, target_2,
                    exit_price, outcome, pnl_percent, rr_achieved, market_regime,
                    btc_trend, entry_timestamp, exit_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.id,
                signal.symbol,
                signal.name,
                signal.strategy_type.value,
                signal.timeframe,
                signal.direction.value,
                signal.entry_zone_min,
                signal.stop_loss,
                signal.target_1,
                signal.target_2,
                exit_price,
                outcome,
                pnl_percent,
                rr_achieved,
                market_regime,
                signal.btc_trend.value,
                signal.timestamp.isoformat(),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
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
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades WHERE 1=1"
            params = []
            
            if strategy:
                query += " AND strategy_type = ?"
                params.append(strategy)
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY entry_timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            columns = ["trade_id", "symbol", "coin_name", "strategy_type", "timeframe",
                       "direction", "entry_price", "stop_loss", "target_1", "target_2",
                       "exit_price", "outcome", "pnl_percent", "rr_achieved", "market_regime",
                       "btc_trend", "entry_timestamp", "exit_timestamp", "notes", "created_at"]
            
            return [dict(zip(columns, row)) for row in rows]
            
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
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades WHERE outcome IS NOT NULL"
            params = []
            
            if strategy:
                query += " AND strategy_type = ?"
                params.append(strategy)
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if timeframe:
                query += " AND timeframe = ?"
                params.append(timeframe)
            
            query += " ORDER BY entry_timestamp DESC LIMIT ?"
            params.append(lookback_trades)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {
                    "sample_size": 0,
                    "win_rate": 0.5,
                    "avg_rr": 0,
                    "avg_win": 0,
                    "avg_loss": 0,
                    "by_regime": {},
                    "by_timeframe": {}
                }
            
            columns = ["trade_id", "symbol", "coin_name", "strategy_type", "timeframe",
                       "direction", "entry_price", "stop_loss", "target_1", "target_2",
                       "exit_price", "outcome", "pnl_percent", "rr_achieved", "market_regime",
                       "btc_trend", "entry_timestamp", "exit_timestamp", "notes", "created_at"]
            
            trades = [dict(zip(columns, row)) for row in rows]
            
            wins = [t for t in trades if t["outcome"] == "WIN"]
            losses = [t for t in trades if t["outcome"] == "LOSS"]
            
            win_rate = len(wins) / len(trades) if trades else 0.5
            
            avg_rr = sum(t["rr_achieved"] for t in trades if t["rr_achieved"]) / len(trades) if trades else 0
            
            avg_win = sum(t["pnl_percent"] for t in wins) / len(wins) if wins else 0
            avg_loss = abs(sum(t["pnl_percent"] for t in losses) / len(losses)) if losses else 0
            
            by_regime = {}
            for t in trades:
                regime = t["market_regime"] or "UNKNOWN"
                if regime not in by_regime:
                    by_regime[regime] = {"total": 0, "wins": 0}
                by_regime[regime]["total"] += 1
                if t["outcome"] == "WIN":
                    by_regime[regime]["wins"] += 1
            
            for regime in by_regime:
                total = by_regime[regime]["total"]
                wins_count = by_regime[regime]["wins"]
                by_regime[regime]["win_rate"] = wins_count / total if total > 0 else 0
            
            return {
                "sample_size": len(trades),
                "win_rate": win_rate,
                "avg_rr": avg_rr,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "by_regime": by_regime,
                "trades": trades[:10]
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