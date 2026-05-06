"""
Performance Tracking
Stores and tracks trade results for analysis and AI improvement.
Uses JSON files for persistence (no SQLite).
"""

import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from loguru import logger

from models import TradingSignal, TradeRecord, SignalDirection
from config import get_config


class PerformanceTracker:
    """Track and analyze trading performance using JSON storage"""
    
    def __init__(self):
        self.config = get_config()
        self.data_dir = self._get_data_dir()
        self._signals_file = self.data_dir / "signals.json"
        self._trades_file = self.data_dir / "trades.json"
        self._scans_file = self.data_dir / "scans.json"
        self._outcomes_file = self.data_dir / "signal_outcomes.json"
        
        # In-memory caches loaded from JSON
        self._signals: List[Dict] = []
        self._trades: List[Dict] = []
        self._scans: List[Dict] = []
        self._outcomes: List[Dict] = []
        
        self._load_all()
        logger.info(f"PerformanceTracker initialized (JSON) at {self.data_dir}")
    
    def _get_data_dir(self) -> Path:
        """Get data directory path"""
        data_dir = Path(self.config.logging.log_file).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir
    
    def _load_json(self, path: Path, default=None):
        """Load JSON file safely."""
        if default is None:
            default = []
        if not path.exists():
            return default
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
            return default
    
    def _save_json(self, path: Path, data):
        """Save JSON file atomically."""
        tmp = path.with_suffix('.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            tmp.replace(path)
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")
            # Clean up temp file if it exists
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
    
    def _load_all(self):
        """Load all data from JSON files."""
        self._signals = self._load_json(self._signals_file, [])
        self._trades = self._load_json(self._trades_file, [])
        self._scans = self._load_json(self._scans_file, [])
        self._outcomes = self._load_json(self._outcomes_file, [])
    
    def save_signal(self, signal: TradingSignal):
        """Save a trading signal"""
        try:
            signal_data = {
                "id": signal.id,
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "name": signal.name,
                "direction": signal.direction.value,
                "strategy_type": signal.strategy_type.value,
                "timeframe": signal.timeframe,
                "entry_zone_min": signal.entry_zone_min,
                "entry_zone_max": signal.entry_zone_max,
                "stop_loss": signal.stop_loss,
                "target_1": signal.target_1,
                "target_2": signal.target_2,
                "risk_reward": signal.risk_reward,
                "confidence_score": signal.confidence_score,
                "reasoning": signal.reasoning,
                "status": "ACTIVE"
            }
            
            # Replace if exists, otherwise append
            existing_idx = next(
                (i for i, s in enumerate(self._signals) if s.get("id") == signal.id),
                None
            )
            if existing_idx is not None:
                self._signals[existing_idx] = signal_data
            else:
                self._signals.append(signal_data)
            
            self._save_json(self._signals_file, self._signals)
            
        except Exception as e:
            logger.error(f"Error saving signal: {e}")
    
    def save_scan_result(self, signals: List[TradingSignal], scan_duration: float, btc_trend: str, btc_price: float, market_regime: str, detailed_regime: str = None):
        """Save scan results"""
        try:
            long_count = sum(1 for s in signals if s.direction == SignalDirection.LONG)
            short_count = sum(1 for s in signals if s.direction == SignalDirection.SHORT)
            
            regime = detailed_regime if detailed_regime else market_regime
            
            scan_data = {
                "timestamp": datetime.now().isoformat(),
                "btc_trend": btc_trend,
                "btc_price": btc_price,
                "total_signals": len(signals),
                "long_signals": long_count,
                "short_signals": short_count,
                "scan_duration": scan_duration,
                "market_regime": regime
            }
            
            self._scans.append(scan_data)
            
            # Keep only last 500 scans to prevent unbounded growth
            if len(self._scans) > 500:
                self._scans = self._scans[-500:]
            
            self._save_json(self._scans_file, self._scans)
            
            # Save individual signals
            for signal in signals:
                self.save_signal(signal)
            
        except Exception as e:
            logger.error(f"Error saving scan result: {e}")
    
    def update_trade(self, trade: TradeRecord):
        """Update trade with actual results"""
        try:
            trade_data = {
                "signal_id": trade.signal_id,
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "entry_price": trade.entry_price,
                "stop_loss": trade.stop_loss,
                "target_1": trade.target_1,
                "target_2": trade.target_2,
                "actual_exit": trade.actual_exit,
                "actual_direction": trade.actual_direction.value,
                "status": trade.status,
                "pnl_percent": trade.pnl_percent,
                "notes": trade.notes
            }
            
            # Replace if exists, otherwise append
            existing_idx = next(
                (i for i, t in enumerate(self._trades) if t.get("signal_id") == trade.signal_id),
                None
            )
            if existing_idx is not None:
                self._trades[existing_idx] = trade_data
            else:
                self._trades.append(trade_data)
            
            # Update signal status
            for sig in self._signals:
                if sig.get("id") == trade.signal_id:
                    sig["status"] = trade.status
                    break
            
            self._save_json(self._trades_file, self._trades)
            self._save_json(self._signals_file, self._signals)
            
        except Exception as e:
            logger.error(f"Error updating trade: {e}")
    
    def get_statistics(self) -> Dict:
        """Get performance statistics"""
        try:
            stats = {}
            
            # Total signals
            stats["total_signals"] = len(self._signals)
            
            # Signals by direction
            stats["long_signals"] = sum(1 for s in self._signals if s.get("direction") == "LONG")
            stats["short_signals"] = sum(1 for s in self._signals if s.get("direction") == "SHORT")
            
            # Average confidence
            confidence_scores = [s.get("confidence_score", 0) for s in self._signals if s.get("confidence_score")]
            stats["avg_confidence"] = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            
            # Closed trades
            stats["winning_trades"] = sum(1 for t in self._trades if t.get("status") == "CLOSED_WIN")
            stats["losing_trades"] = sum(1 for t in self._trades if t.get("status") == "CLOSED_LOSS")
            stats["closed_trades"] = stats["winning_trades"] + stats["losing_trades"]
            
            # Win rate
            if stats["closed_trades"] > 0:
                stats["win_rate"] = (stats["winning_trades"] / stats["closed_trades"]) * 100
            else:
                stats["win_rate"] = 0
            
            # Average PnL
            win_pnls = [t.get("pnl_percent", 0) for t in self._trades if t.get("status") == "CLOSED_WIN"]
            loss_pnls = [t.get("pnl_percent", 0) for t in self._trades if t.get("status") == "CLOSED_LOSS"]
            stats["avg_win"] = sum(win_pnls) / len(win_pnls) if win_pnls else 0
            stats["avg_loss"] = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0
            
            # Recent scans (last 7 days)
            seven_days_ago = datetime.now().isoformat()[:10]  # Just date part for comparison
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            stats["scans_last_7_days"] = sum(
                1 for s in self._scans 
                if s.get("timestamp", "") >= cutoff
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    def get_recent_signals(self, limit: int = 20) -> List[Dict]:
        """Get most recent signals, sorted by timestamp descending."""
        sorted_signals = sorted(
            self._signals,
            key=lambda s: s.get("timestamp", ""),
            reverse=True
        )
        return sorted_signals[:limit]
    
    def get_top_signals(self, limit: int = 5) -> List[Dict]:
        """Get top signals by confidence score from recent signals."""
        recent = self.get_recent_signals(limit=20)
        sorted_by_score = sorted(
            recent,
            key=lambda s: s.get("confidence_score", 0),
            reverse=True
        )
        return sorted_by_score[:limit]
    
    def export_signals_csv(self, filepath: str):
        """Export signals to CSV"""
        try:
            import csv
            
            if not self._signals:
                logger.warning("No signals to export")
                return
            
            # Get all keys from signals
            all_keys = set()
            for sig in self._signals:
                all_keys.update(sig.keys())
            columns = sorted(all_keys)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self._signals)
            
            logger.info(f"Exported {len(self._signals)} signals to {filepath}")
            
        except Exception as e:
            logger.error(f"Error exporting signals: {e}")
