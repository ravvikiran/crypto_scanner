"""
Performance Tracking
Stores and tracks trade results for analysis and AI improvement.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from loguru import logger

from models import TradingSignal, TradeRecord, SignalDirection
from config import get_config


class PerformanceTracker:
    """Track and analyze trading performance"""
    
    def __init__(self):
        self.config = get_config()
        self.db_path = self._get_db_path()
        self._init_database()
    
    def _get_db_path(self) -> Path:
        """Get database file path"""
        data_dir = Path(self.config.logging.log_file).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir / "performance.db"
    
    def _init_database(self):
        """Initialize SQLite database"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    symbol TEXT,
                    name TEXT,
                    direction TEXT,
                    strategy_type TEXT,
                    timeframe TEXT,
                    entry_zone_min REAL,
                    entry_zone_max REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    risk_reward REAL,
                    confidence_score REAL,
                    reasoning TEXT,
                    status TEXT DEFAULT 'ACTIVE'
                )
            """)
            
            # Create trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    timestamp TEXT,
                    symbol TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    target_2 REAL,
                    actual_exit REAL,
                    actual_direction TEXT,
                    status TEXT DEFAULT 'OPEN',
                    pnl_percent REAL,
                    notes TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals(id)
                )
            """)
            
            # Create scans table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    btc_trend TEXT,
                    btc_price REAL,
                    total_signals INTEGER,
                    long_signals INTEGER,
                    short_signals INTEGER,
                    scan_duration REAL,
                    market_regime TEXT
                )
            """)
            
            # Create signal_outcomes table for learning system
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy_type TEXT,
                    timeframe TEXT,
                    direction TEXT,
                    entry_price REAL,
                    resolution TEXT,
                    exit_price REAL,
                    pnl_percent REAL,
                    duration_hours REAL,
                    expected_correct BOOLEAN,
                    resolved_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
            
            logger.info(f"Database initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def save_signal(self, signal: TradingSignal):
        """Save a trading signal to database"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO signals (
                    id, timestamp, symbol, name, direction, strategy_type,
                    timeframe, entry_zone_min, entry_zone_max, stop_loss,
                    target_1, target_2, risk_reward, confidence_score, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.id,
                signal.timestamp.isoformat(),
                signal.symbol,
                signal.name,
                signal.direction.value,
                signal.strategy_type.value,
                signal.timeframe,
                signal.entry_zone_min,
                signal.entry_zone_max,
                signal.stop_loss,
                signal.target_1,
                signal.target_2,
                signal.risk_reward,
                signal.confidence_score,
                signal.reasoning
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving signal: {e}")
    
    def save_scan_result(self, signals: List[TradingSignal], scan_duration: float, btc_trend: str, btc_price: float, market_regime: str, detailed_regime: str = None):
        """Save scan results"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            long_count = sum(1 for s in signals if s.direction == SignalDirection.LONG)
            short_count = sum(1 for s in signals if s.direction == SignalDirection.SHORT)
            
            # Use detailed regime if provided, otherwise use market_regime
            regime = detailed_regime if detailed_regime else market_regime
            
            cursor.execute("""
                INSERT INTO scans (
                    timestamp, btc_trend, btc_price, total_signals,
                    long_signals, short_signals, scan_duration, market_regime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                btc_trend,
                btc_price,
                len(signals),
                long_count,
                short_count,
                scan_duration,
                regime
            ))
            
            conn.commit()
            conn.close()
            
            # Save individual signals
            for signal in signals:
                self.save_signal(signal)
            
        except Exception as e:
            logger.error(f"Error saving scan result: {e}")
    
    def update_trade(self, trade: TradeRecord):
        """Update trade with actual results"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    signal_id, timestamp, symbol, entry_price, stop_loss,
                    target_1, target_2, actual_exit, actual_direction,
                    status, pnl_percent, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.signal_id,
                trade.timestamp.isoformat(),
                trade.symbol,
                trade.entry_price,
                trade.stop_loss,
                trade.target_1,
                trade.target_2,
                trade.actual_exit,
                trade.actual_direction.value,
                trade.status,
                trade.pnl_percent,
                trade.notes
            ))
            
            # Update signal status
            cursor.execute("""
                UPDATE signals SET status = ? WHERE id = ?
            """, (trade.status, trade.signal_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating trade: {e}")
    
    def get_statistics(self) -> Dict:
        """Get performance statistics"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            stats = {}
            
            # Total signals
            cursor.execute("SELECT COUNT(*) FROM signals")
            stats["total_signals"] = cursor.fetchone()[0]
            
            # Signals by direction
            cursor.execute("SELECT direction, COUNT(*) FROM signals GROUP BY direction")
            direction_counts = {row[0]: row[1] for row in cursor.fetchall()}
            stats["long_signals"] = direction_counts.get("LONG", 0)
            stats["short_signals"] = direction_counts.get("SHORT", 0)
            
            # Average confidence
            cursor.execute("SELECT AVG(confidence_score) FROM signals")
            stats["avg_confidence"] = cursor.fetchone()[0] or 0
            
            # Closed trades
            cursor.execute("SELECT status, COUNT(*) FROM trades GROUP BY status")
            trade_status = {row[0]: row[1] for row in cursor.fetchall()}
            stats["closed_trades"] = trade_status.get("CLOSED_WIN", 0) + trade_status.get("CLOSED_LOSS", 0)
            stats["winning_trades"] = trade_status.get("CLOSED_WIN", 0)
            stats["losing_trades"] = trade_status.get("CLOSED_LOSS", 0)
            
            # Win rate
            if stats["closed_trades"] > 0:
                stats["win_rate"] = (stats["winning_trades"] / stats["closed_trades"]) * 100
            else:
                stats["win_rate"] = 0
            
            # Average PnL
            cursor.execute("SELECT AVG(pnl_percent) FROM trades WHERE status = 'CLOSED_WIN'")
            stats["avg_win"] = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT AVG(pnl_percent) FROM trades WHERE status = 'CLOSED_LOSS'")
            stats["avg_loss"] = cursor.fetchone()[0] or 0
            
            # Recent scans
            cursor.execute("SELECT COUNT(*) FROM scans WHERE timestamp > datetime('now', '-7 days')")
            stats["scans_last_7_days"] = cursor.fetchone()[0]
            
            conn.close()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    def export_signals_csv(self, filepath: str):
        """Export signals to CSV"""
        try:
            import csv
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM signals ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning("No signals to export")
                return
            
            # Get column names
            cursor.execute("PRAGMA table_info(signals)")
            columns = [row[1] for row in cursor.fetchall()]
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            
            conn.close()
            
            logger.info(f"Exported {len(rows)} signals to {filepath}")
            
        except Exception as e:
            logger.error(f"Error exporting signals: {e}")
