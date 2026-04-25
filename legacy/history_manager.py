"""
LEGACY HISTORY MANAGER - NSE Stock Scanner (Deprecated)
This file is kept for reference only. DO NOT USE for crypto scanner.
Crypto uses learning.signal_tracker and storage.performance_tracker instead.
"""

import os
import json
import logging
import shutil
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)

DATA_DIR = 'data'


@dataclass
class TradeSetup:
    """Trade setup parameters - EVERY signal must have these."""
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward_1: float
    risk_reward_2: float
    atr_at_entry: float


@dataclass
class PositionState:
    """Position management state."""
    signal_id: str
    entry_price: float
    current_price: float
    quantity: int
    stop_loss: float
    target_1: float
    target_2: float
    initial_risk: float
    partial_exits: List[Dict[str, Any]] = field(default_factory=list)
    trailing_sl: Optional[float] = None
    last_updated: Optional[str] = None


class PerformanceAnalyzer:
    """
    Analyzes historical signal performance to learn and improve.
    Tracks win rate, returns, best parameters per setup.
    """
    
    def __init__(self, history_manager):
        self.hm = history_manager
        self.min_samples = 10  # Minimum trades needed for reliable stats
    
    def analyze_all_setups(self) -> Dict[str, Any]:
        """Analyze all trading setups and return performance metrics."""
        history = self.hm.get_history(limit=-1)  # Get all
        
        if len(history) < self.min_samples:
            logger.warning(f"Not enough history for analysis: {len(history)} < {self.min_samples}")
            return {}
        
        # Group by setup type
        setup_results = self._group_by_setup(history)
        
        # Calculate metrics per setup
        metrics = {}
        for setup_type, signals in setup_results.items():
            metrics[setup_type] = self._calculate_setup_metrics(signals)
        
        return {
            'setup_metrics': metrics,
            'overall': self._calculate_overall_metrics(history),
            'generated_at': datetime.now().isoformat()
        }
    
    def _group_by_setup(self, history: List[Dict]) -> Dict[str, List[Dict]]:
        """Group signals by their setup configuration."""
        setups = defaultdict(list)
        
        for signal in history:
            key = self._get_setup_key(signal)
            setups[key].append(signal)
        
        return dict(setups)
    
    def _get_setup_key(self, signal: Dict) -> str:
        """Create a unique key for the setup configuration."""
        ema_fast = signal.get('ema_fast', 'default')
        ema_slow = signal.get('ema_slow', 'default')
        rsi_zone = signal.get('rsi_zone', 'default')
        volume_ratio = signal.get('volume_ratio', 'default')
        timeframe = signal.get('timeframe', '15m')
        
        return f"{ema_fast}_{ema_slow}_{rsi_zone}_{volume_ratio}_{timeframe}"
    
    def _is_win(self, signal: Dict) -> bool:
        """Check if signal was a win."""
        outcome = signal.get('outcome', '')
        return outcome in ['WIN', 'TARGET_HIT', 'PARTIAL']
    
    def _is_loss(self, signal: Dict) -> bool:
        """Check if signal was a loss."""
        outcome = signal.get('outcome', '')
        return outcome in ['LOSS', 'SL_HIT', 'TIMEOUT']
    
    def _calculate_setup_metrics(self, signals: List[Dict]) -> Dict[str, Any]:
        """Calculate metrics for a specific setup."""
        wins = [s for s in signals if self._is_win(s)]
        losses = [s for s in signals if self._is_loss(s)]
        
        total = len(signals)
        if total == 0:
            return {}
        
        win_rate = len(wins) / total
        
        returns = []
        rr_ratios = []
        cumulative = 0
        peak = 0
        max_drawdown = 0
        
        for s in signals:
            ret = s.get('return_pct', 0)
            if ret != 0 or s.get('outcome') in ['WIN', 'LOSS']:
                returns.append(ret)
            
            rr = s.get('risk_reward_1') or s.get('risk_reward_2') or 0
            if rr > 0:
                rr_ratios.append(rr)
            
            cumulative += ret
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        avg_return = statistics.mean(returns) if returns else 0
        best_return = max(returns) if returns else 0
        worst_return = min(returns) if returns else 0
        avg_rr = statistics.mean(rr_ratios) if rr_ratios else 0
        
        return {
            'total_trades': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate * 100, 2),
            'avg_return_pct': round(avg_return, 2),
            'best_return_pct': round(best_return, 2),
            'worst_return_pct': round(worst_return, 2),
            'avg_rr': round(avg_rr, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'profit_factor': self._calculate_profit_factor(wins, losses),
            'sample_size': total
        }
    
    def _calculate_overall_metrics(self, history: List[Dict]) -> Dict[str, Any]:
        """Calculate overall performance metrics."""
        completed = [s for s in history if self._is_win(s) or self._is_loss(s)]
        
        if not completed:
            return {}
        
        wins = [s for s in completed if self._is_win(s)]
        losses = [s for s in completed if self._is_loss(s)]
        
        all_returns = [s.get('return_pct', 0) for s in completed]
        
        rr_ratios = []
        for s in completed:
            rr = s.get('risk_reward_1') or s.get('risk_reward_2') or 0
            if rr > 0:
                rr_ratios.append(rr)
        
        cumulative = 0
        peak = 0
        max_drawdown = 0
        for ret in all_returns:
            cumulative += ret
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'total_trades': len(completed),
            'win_rate': round(len(wins) / len(completed) * 100, 2),
            'avg_return': round(statistics.mean(all_returns), 2),
            'median_return': round(statistics.median(all_returns), 2),
            'avg_rr': round(statistics.mean(rr_ratios), 2) if rr_ratios else 0,
            'max_drawdown_pct': round(max_drawdown, 2),
            'best_setup': self._find_best_setup(history),
            'worst_setup': self._find_worst_setup(history)
        }
    
    def _calculate_profit_factor(self, wins: List[Dict], losses: List[Dict]) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        gross_profit = sum(s.get('return_pct', 0) for s in wins if s.get('return_pct', 0) > 0)
        gross_loss = abs(sum(s.get('return_pct', 0) for s in losses if s.get('return_pct', 0) < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0
        
        return round(gross_profit / gross_loss, 2)
    
    def _find_best_setup(self, history: List[Dict]) -> str:
        """Find the best performing setup."""
        setup_results = self._group_by_setup(history)
        
        best_setup = None
        best_win_rate = 0
        
        for setup, signals in setup_results.items():
            if len(signals) >= self.min_samples:
                wins = len([s for s in signals if self._is_win(s)])
                win_rate = wins / len(signals)
                if win_rate > best_win_rate:
                    best_win_rate = win_rate
                    best_setup = setup
        
        return best_setup or "insufficient_data"
    
    def _find_worst_setup(self, history: List[Dict]) -> str:
        """Find the worst performing setup."""
        setup_results = self._group_by_setup(history)
        
        worst_setup = None
        worst_win_rate = 1.0
        
        for setup, signals in setup_results.items():
            if len(signals) >= self.min_samples:
                wins = len([s for s in signals if self._is_win(s)])
                win_rate = wins / len(signals)
                if win_rate < worst_win_rate:
                    worst_win_rate = win_rate
                    worst_setup = setup
        
        return worst_setup or "insufficient_data"
    
    def generate_weight_adjustments(self) -> Dict[str, Any]:
        """
        Auto-adjust weights based on performance.
        Boost good patterns (>60% win rate), disable bad patterns (<40% win rate).
        """
        analysis = self.analyze_all_setups()
        
        if not analysis or 'setup_metrics' not in analysis:
            return {}
        
        adjustments = {
            'boost_setups': [],
            'reduce_setups': [],
            'disable_setups': [],
            'weight_changes': {},
            'generated_at': datetime.now().isoformat()
        }
        
        for setup, metrics in analysis['setup_metrics'].items():
            if metrics.get('sample_size', 0) < self.min_samples:
                continue
            
            win_rate = metrics.get('win_rate', 50)
            
            if win_rate > 60:
                adjustments['boost_setups'].append({
                    'setup': setup,
                    'win_rate': win_rate,
                    'boost_factor': 1.2
                })
            elif win_rate < 40:
                adjustments['disable_setups'].append({
                    'setup': setup,
                    'win_rate': win_rate,
                    'reason': 'poor_win_rate'
                })
            elif win_rate < 45:
                adjustments['reduce_setups'].append({
                    'setup': setup,
                    'win_rate': win_rate,
                    'reduce_factor': 0.8
                })
        
        return adjustments


class PositionManager:
    """
    Manages open positions with trailing SL, partial exits, 
    and close on opposite signal.
    """
    
    def __init__(self, history_manager):
        self.hm = history_manager
        self.positions: Dict[str, PositionState] = {}
        self.trailing_atr_multiplier = 2.0
        self.partial_exit_levels = [0.5, 0.75]  # Exit 50% at T1, 75% at T2
    
    def open_position(self, signal_data: Dict[str, Any]) -> str:
        """Open a new position from a signal."""
        signal_id = signal_data.get('signal_id', '')
        
        position = PositionState(
            signal_id=signal_id or f"pos_{datetime.now().timestamp()}",
            entry_price=signal_data.get('entry_price', 0.0),
            current_price=signal_data.get('entry_price', 0.0),
            quantity=signal_data.get('quantity', 1),
            stop_loss=signal_data.get('stop_loss', 0.0),
            target_1=signal_data.get('target_1', 0.0),
            target_2=signal_data.get('target_2', 0.0),
            initial_risk=abs(signal_data.get('entry_price', 0.0) - signal_data.get('stop_loss', 0.0)),
            last_updated=datetime.now().isoformat()
        )
        
        self.positions[position.signal_id] = position
        logger.info(f"Position opened: {signal_id} at {position.entry_price}")
        
        return signal_id
    
    def update_position(self, signal_id: str, current_price: float) -> Dict[str, Any]:
        """Update position with current price and check for exits."""
        if signal_id not in self.positions:
            return {}
        
        position = self.positions[signal_id]
        position.current_price = current_price
        position.last_updated = datetime.now().isoformat()
        
        actions = self._check_exit_conditions(position)
        
        if actions:
            self.hm.update_active_signal(signal_id, {
                'position_updates': actions,
                'last_checked': datetime.now().isoformat()
            })
        
        return actions
    
    def _check_exit_conditions(self, position: PositionState) -> Dict[str, Any]:
        """Check all exit conditions and return actions."""
        actions = {}
        entry = position.entry_price
        current = position.current_price
        sl = position.stop_loss
        t1 = position.target_1
        t2 = position.target_2
        
        direction = 1 if current > entry else -1
        
        # Check stop loss
        if (direction == 1 and current < sl) or (direction == -1 and current > sl):
            actions['exit'] = 'STOP_LOSS'
            actions['exit_price'] = sl
            return actions
        
        # Check target 1 - partial exit
        if direction == 1 and current >= t1:
            if not any(p.get('at_target_1') for p in position.partial_exits):
                actions['partial_exit'] = {
                    'level': 1,
                    'quantity': int(position.quantity * 0.5),
                    'price': current,
                    'profit_pct': ((current - entry) / entry) * 100
                }
                position.partial_exits.append({'at_target_1': True, 'qty': int(position.quantity * 0.5)})
        
        # Check target 2 - final exit
        if direction == 1 and current >= t2:
            if not any(p.get('at_target_2') for p in position.partial_exits):
                actions['exit'] = 'TARGET_2'
                actions['exit_price'] = current
                actions['profit_pct'] = ((current - entry) / entry) * 100
                return actions
        
        # Check trailing stop
        new_trailing = self._calculate_trailing_stop(position)
        if new_trailing and position.trailing_sl:
            if (direction == 1 and new_trailing > position.trailing_sl) or \
               (direction == -1 and new_trailing < position.trailing_sl):
                position.trailing_sl = new_trailing
                actions['trailing_sl_updated'] = new_trailing
        elif new_trailing:
            position.trailing_sl = new_trailing
            actions['trailing_sl_set'] = new_trailing
        
        # Check if trailing SL hit
        if position.trailing_sl:
            if (direction == 1 and current < position.trailing_sl) or \
               (direction == -1 and current > position.trailing_sl):
                actions['exit'] = 'TRAILING_STOP'
                actions['exit_price'] = position.trailing_sl
                actions['profit_pct'] = ((position.trailing_sl - entry) / entry) * 100
        
        return actions
    
    def _calculate_trailing_stop(self, position: PositionState) -> Optional[float]:
        """Calculate trailing stop based on ATR or percentage."""
        entry = position.entry_price
        current = position.current_price
        direction = 1 if current > entry else -1
        
        # Simple 1% trailing for now
        trail_pct = 0.01
        
        if direction == 1:
            return entry * (1 + trail_pct)
        else:
            return entry * (1 - trail_pct)
    
    def close_on_opposite_signal(self, signal_id: str, opposite_signal: Dict[str, Any]) -> Dict[str, Any]:
        """Close position when opposite signal is generated."""
        if signal_id not in self.positions:
            return {}
        
        position = self.positions[signal_id]
        
        action = {
            'exit': 'OPPOSITE_SIGNAL',
            'exit_price': opposite_signal.get('entry_price', position.current_price),
            'reason': f"Opposite signal for {opposite_signal.get('stock_symbol')}",
            'profit_pct': ((opposite_signal.get('entry_price', position.current_price) - position.entry_price) 
                          / position.entry_price) * 100
        }
        
        del self.positions[signal_id]
        
        return action
    
    def get_position(self, signal_id: str) -> Optional[PositionState]:
        """Get position by signal ID."""
        return self.positions.get(signal_id)
    
    def get_all_positions(self) -> List[PositionState]:
        """Get all open positions."""
        return list(self.positions.values())


class MultiTimeframeValidator:
    """
    Validates signals across multiple timeframes.
    Daily for trend, 1H for structure, 15m for entry.
    """
    
    def __init__(self):
        self.timeframe_priority = {
            'daily': 1,    # Trend filter (highest priority)
            '1h': 2,       # Structure
            '15m': 3       # Entry (lowest priority)
        }
    
    def validate_signal(self, signal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate signal across timeframes.
        
        Returns:
            Dict with 'valid', 'confidence', 'filters_triggered'
        """
        result = {
            'valid': True,
            'confidence': 1.0,
            'filters_triggered': [],
            'recommendation': 'APPROVE'
        }
        
        # Get timeframe data from context
        daily = context.get('daily', {})
        h1 = context.get('1h', {})
        m15 = context.get('15m', {})
        
        # Validate trend direction (Daily)
        if daily:
            trend = daily.get('trend', 'UNKNOWN')
            signal_direction = signal.get('direction', '')
            
            if trend == 'BEARISH' and signal_direction == 'BUY':
                result['filters_triggered'].append('daily_trend_opposite')
                result['valid'] = False
                result['confidence'] = 0.0
                result['recommendation'] = 'REJECT'
                return result
            
            if trend == 'BULLISH' and signal_direction == 'SELL':
                result['filters_triggered'].append('daily_trend_opposite')
                result['valid'] = False
                result['confidence'] = 0.0
                result['recommendation'] = 'REJECT'
                return result
            
            # Same direction boosts confidence
            if trend == signal_direction:
                result['confidence'] *= 1.2
        
        # Validate structure (1H)
        if h1:
            structure = h1.get('structure', 'UNKNOWN')
            
            if structure == 'RANGE_BOUND':
                result['filters_triggered'].append('1h_range_bound')
                result['confidence'] *= 0.7
                result['recommendation'] = 'CAUTION'
            
            elif structure == 'TRENDING':
                result['confidence'] *= 1.1
        
        # Entry timing (15m)
        if m15:
            volatility = m15.get('volatility', 'NORMAL')
            
            if volatility == 'EXTREME':
                result['filters_triggered'].append('15m_extreme_volatility')
                result['confidence'] *= 0.8
                result['recommendation'] = 'CAUTION'
        
        # Cap confidence at 1.0
        result['confidence'] = min(result['confidence'], 1.0)
        
        return result


class HistoryManager:
    """
    Manages signal data persistence with learning capabilities.
    Handles active signals, historical records, and performance analytics.
    """
    
    ACTIVE_SIGNALS_FILE = 'signals_active.json'
    HISTORY_FILE = 'signals_history.json'
    PERFORMANCE_FILE = 'performance_metrics.json'
    WEIGHTS_FILE = 'weight_config.json'
    
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self._ensure_data_dir()
        
        self._lock = threading.Lock()
        
        self.active_signals = self._load_active_signals()
        self.history = self._load_history()
        
        # Initialize modules
        self.performance_analyzer = PerformanceAnalyzer(self)
        self.position_manager = PositionManager(self)
        self.mtf_validator = MultiTimeframeValidator()
        
        logger.info(f"HistoryManager initialized. Active: {len(self.active_signals)}, History: {len(self.history.get('signals', []))}")
    
    def _ensure_data_dir(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _load_active_signals(self) -> Dict[str, Any]:
        filepath = os.path.join(self.data_dir, self.ACTIVE_SIGNALS_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return data.get('signals', {})
            except Exception as e:
                logger.error(f"Error loading active signals: {e}")
                return {}
        return {}
    
    def _save_active_signals(self) -> None:
        filepath = os.path.join(self.data_dir, self.ACTIVE_SIGNALS_FILE)
        data = {
            'version': '2.0',
            'last_updated': datetime.now().isoformat(),
            'signals': self.active_signals
        }
        try:
            with self._lock:
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving active signals: {e}")
    
    def _load_history(self) -> Dict[str, Any]:
        filepath = os.path.join(self.data_dir, self.HISTORY_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading history: {e}")
                return {'version': '2.0', 'signals': []}
        return {'version': '2.0', 'signals': []}
    
    def _save_history(self) -> None:
        filepath = os.path.join(self.data_dir, self.HISTORY_FILE)
        self.history['last_updated'] = datetime.now().isoformat()
        try:
            with self._lock:
                with open(filepath, 'w') as f:
                    json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    # ==================== Signal with Trade Setup ====================
    
    def add_signal_with_setup(self, signal_data: Dict[str, Any]) -> str:
        """
        Add a new signal with complete trade setup (entry, SL, targets).
        Every signal MUST include entry_price, stop_loss, target_1, target_2.
        """
        signal_id = signal_data.get('signal_id', '')
        
        # Validate required fields
        required = ['entry_price', 'stop_loss', 'target_1', 'target_2', 'atr']
        missing = [f for f in required if f not in signal_data]
        
        if missing:
            logger.error(f"Signal {signal_id} missing required fields: {missing}")
            raise ValueError(f"Missing required fields: {missing}")
        
        # Calculate risk/reward
        entry = signal_data['entry_price']
        sl = signal_data['stop_loss']
        t1 = signal_data['target_1']
        t2 = signal_data['target_2']
        
        risk = abs(entry - sl)
        signal_data['risk'] = risk
        signal_data['risk_reward_1'] = round(abs(t1 - entry) / risk, 2) if risk > 0 else 0
        signal_data['risk_reward_2'] = round(abs(t2 - entry) / risk, 2) if risk > 0 else 0
        
        # Add to active signals
        with self._lock:
            signal_key = signal_id or f"sig_{datetime.now().timestamp()}"
            self.active_signals[signal_key] = {
                **signal_data,
                'status': 'ACTIVE',
                'added_at': datetime.now().isoformat(),
                'last_checked': datetime.now().isoformat(),
                'has_trade_setup': True
            }
            
            self._save_active_signals()
        
        # Open position in position manager
        self.position_manager.open_position(signal_data)
        
        logger.info(f"Added signal with setup: {signal_data.get('stock_symbol')} ({signal_key})")
        
        return signal_key
    
    def validate_mtf(self, signal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate signal across multiple timeframes."""
        return self.mtf_validator.validate_signal(signal, context)
    
    # ==================== Active Signal Management ====================
    
    def add_active_signal(self, signal_data: Dict[str, Any]) -> str:
        signal_id = signal_data.get('signal_id', '')
        
        with self._lock:
            self.active_signals[signal_id] = {
                **signal_data,
                'status': 'ACTIVE',
                'added_at': datetime.now().isoformat(),
                'last_checked': datetime.now().isoformat()
            }
            
            self._save_active_signals()
        
        logger.info(f"Added active signal: {signal_data.get('stock_symbol')} ({signal_id})")
        
        return signal_id
    
    def update_active_signal(self, signal_id: str, updates: Dict[str, Any]) -> bool:
        if signal_id not in self.active_signals:
            logger.warning(f"Signal not found for update: {signal_id}")
            return False
        
        self.active_signals[signal_id].update(updates)
        self.active_signals[signal_id]['last_checked'] = datetime.now().isoformat()
        
        self._save_active_signals()
        
        return True
    
    def remove_active_signal(self, signal_id: str, outcome: Optional[str] = None, return_pct: Optional[float] = None) -> bool:
        """Remove active signal and move to history."""
        if signal_id not in self.active_signals:
            logger.warning(f"Signal not found for removal: {signal_id}")
            return False
        
        signal_data = self.active_signals[signal_id].copy()
        
        # Add outcome data
        if outcome:
            signal_data['outcome'] = outcome
        if return_pct is not None:
            signal_data['return_pct'] = return_pct
        
        # Close position
        if signal_id in self.position_manager.positions:
            del self.position_manager.positions[signal_id]
        
        self.add_to_history(signal_data)
        
        del self.active_signals[signal_id]
        self._save_active_signals()
        
        logger.info(f"Removed active signal: {signal_id} - {outcome}")
        
        return True
    
    def get_active_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self.active_signals.get(signal_id)
    
    def get_active_signals_for_stock(self, stock_symbol: str) -> List[Dict[str, Any]]:
        return [s for s in self.active_signals.values() if s.get('stock_symbol') == stock_symbol]
    
    def get_all_active_signals(self) -> List[Dict[str, Any]]:
        return list(self.active_signals.values())
    
    def get_active_count(self) -> int:
        return len(self.active_signals)
    
    # ==================== History Management ====================
    
    def add_to_history(self, signal_data: Dict[str, Any]) -> None:
        if 'signals' not in self.history:
            self.history['signals'] = []
        
        signal_data['completed_at'] = datetime.now().isoformat()
        
        self.history['signals'].append(signal_data)
        
        if len(self.history['signals']) > 1000:
            self.history['signals'] = self.history['signals'][-1000:]
        
        self._save_history()
        
        logger.info(f"Added to history: {signal_data.get('stock_symbol')} - {signal_data.get('outcome')}")
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        signals = self.history.get('signals', [])
        return signals[-limit:] if limit > 0 else signals
    
    def get_history_for_stock(self, stock_symbol: str) -> List[Dict[str, Any]]:
        return [s for s in self.history.get('signals', []) if s.get('stock_symbol') == stock_symbol]
    
    def get_completed_signals(self) -> List[Dict[str, Any]]:
        return [s for s in self.history.get('signals', []) if s.get('status') == 'COMPLETED']
    
    # ==================== Cleanup & Maintenance ====================
    
    def cleanup_expired_signals(self, expiry_days: int = 30) -> List[Dict[str, Any]]:
        expired = []
        cutoff = datetime.now() - timedelta(days=expiry_days)
        
        for signal_id, signal in list(self.active_signals.items()):
            try:
                added_at = datetime.fromisoformat(signal.get('added_at', ''))
                if added_at < cutoff:
                    signal['status'] = 'EXPIRED'
                    signal['outcome'] = 'TIMEOUT'
                    self.add_to_history(signal)
                    del self.active_signals[signal_id]
                    expired.append(signal)
                    logger.info(f"Expired signal: {signal.get('stock_symbol')} ({signal_id})")
            except Exception as e:
                logger.error(f"Error checking signal expiry: {e}")
        
        if expired:
            self._save_active_signals()
        
        return expired
    
    def get_stats(self) -> Dict[str, Any]:
        total_active = len(self.active_signals)
        total_history = len(self.history.get('signals', []))
        
        completed = self.get_completed_signals()
        
        return {
            'active_signals': total_active,
            'historical_signals': total_history,
            'completed_signals': len(completed),
            'open_positions': len(self.position_manager.positions)
        }
    
    # ==================== Performance Analytics ====================
    
    def analyze_performance(self) -> Dict[str, Any]:
        """Get complete performance analysis."""
        return self.performance_analyzer.analyze_all_setups()
    
    def get_weight_adjustments(self) -> Dict[str, Any]:
        """Get auto-generated weight adjustments."""
        return self.performance_analyzer.generate_weight_adjustments()
    
    def get_performance_data(self) -> Dict[str, Any]:
        return self._load_performance_file()
    
    def save_performance_data(self, data: Dict[str, Any]) -> None:
        filepath = os.path.join(self.data_dir, self.PERFORMANCE_FILE)
        data['last_updated'] = datetime.now().isoformat()
        
        try:
            with self._lock:
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving performance data: {e}")
    
    def _load_performance_file(self) -> Dict[str, Any]:
        filepath = os.path.join(self.data_dir, self.PERFORMANCE_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading performance data: {e}")
                return {}
        return {}
    
    # ==================== Weight Configuration ====================
    
    def get_weights_config(self) -> Dict[str, Any]:
        filepath = os.path.join(self.data_dir, self.WEIGHTS_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading weights config: {e}")
        return {}
    
    def save_weights_config(self, weights: Dict[str, Any]) -> None:
        filepath = os.path.join(self.data_dir, self.WEIGHTS_FILE)
        
        try:
            with self._lock:
                with open(filepath, 'w') as f:
                    json.dump(weights, f, indent=2)
            logger.info("Saved weights configuration")
        except Exception as e:
            logger.error(f"Error saving weights config: {e}")
    
    # ==================== Export ====================
    
    def export_history_csv(self, filepath: str) -> bool:
        try:
            import csv
            
            signals = self.history.get('signals', [])
            
            if not signals:
                logger.warning("No history to export")
                return False
            
            keys = set()
            for s in signals:
                keys.update(s.keys())
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(list(keys)))
                writer.writeheader()
                writer.writerows(signals)
            
            logger.info(f"Exported {len(signals)} signals to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False


def create_history_manager(data_dir: str = DATA_DIR) -> HistoryManager:
    return HistoryManager(data_dir)