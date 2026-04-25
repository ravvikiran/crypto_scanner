"""
LEGACY SIGNAL TRACKER - NSE Stock Scanner (Deprecated)
This is the NSE version. For crypto, use learning.signal_tracker.SignalTracker
which integrates with the learning system and 24/7 market operation.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json

try:
    from data_fetcher import DataFetcher
except ImportError:
    from data_fetcher import DataFetcher

try:
    from history_manager import HistoryManager
except ImportError:
    from history_manager import HistoryManager

logger = logging.getLogger(__name__)


class SignalTracker:
    """
    Tracks active signals and monitors them until completion.
    Checks prices against SL and target levels.
    """
    
    OUTCOME_TARGET_HIT = 'TARGET_HIT'
    OUTCOME_SL_HIT = 'SL_HIT'
    OUTCOME_TIMEOUT = 'TIMEOUT'
    OUTCOME_PARTIAL = 'PARTIAL'
    OUTCOME_ACTIVE = 'ACTIVE'
    
    DEFAULT_TIMEOUT_DAYS = 15
    EXECUTION_BUFFER_PERCENT = 0.2
    
    def __init__(self, history_manager: HistoryManager, data_fetcher: DataFetcher = None, trade_journal=None):
        """
        Initialize signal tracker.
        
        Args:
            history_manager: History manager for persistence
            data_fetcher: Data fetcher for current prices
            trade_journal: Trade journal for recording outcomes
        """
        self.history_manager = history_manager
        self.data_fetcher = data_fetcher or DataFetcher()
        self.trade_journal = trade_journal
        
        logger.info("SignalTracker initialized with trade_journal=%s", trade_journal is not None)
    
    def check_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if a signal has hit target or SL.
        
        Args:
            signal: Signal data with levels
            
        Returns:
            Updated signal with status and outcome
        """
        stock_symbol = signal.get('stock_symbol')
        entry_price = signal.get('entry_price', 0)
        sl_price = signal.get('sl_price', 0)
        signal_type = signal.get('signal_type', 'BUY')
        quantity = signal.get('quantity', 0)
        
        targets = signal.get('targets', [])
        if not targets:
            targets = [signal.get('target_price', 0)]
        
        signal.setdefault('targets_hit', [])
        
        if not entry_price or not sl_price:
            logger.warning(f"Invalid signal levels for {stock_symbol}")
            return signal
        
        try:
            current_price = self._get_current_price(stock_symbol)
            
            if current_price is None:
                logger.warning(f"Could not fetch current price for {stock_symbol}")
                signal['current_price'] = None
                signal['status'] = self.OUTCOME_ACTIVE
                return signal
            
            signal['current_price'] = current_price
            signal['last_checked'] = datetime.now().isoformat()
            
            self._check_timeout(signal, current_price)
            
            if signal.get('status') == 'COMPLETED':
                return signal
            
            self._check_multi_targets(signal, current_price, signal_type)
            
            self._apply_trailing_sl(signal, current_price, signal_type)
            
            self._calculate_pnl(signal, current_price, signal_type, quantity)
            
            self._check_sl_hit(signal, current_price, sl_price, signal_type)
            
            if signal.get('status') != 'COMPLETED':
                signal['status'] = self.OUTCOME_ACTIVE
                logger.debug(f"Active: {stock_symbol} @ {current_price}, P&L: {signal.get('pnl_percent', 0):.2f}%")
            
            return signal
            
        except Exception as e:
            logger.error(f"Error checking signal {stock_symbol}: {e}")
            signal['error'] = str(e)
            return signal
    
    def _check_timeout(self, signal: Dict[str, Any], current_price: float) -> None:
        """Check if signal has expired (timeout)."""
        added_at = signal.get('added_at')
        if not added_at:
            return
        
        try:
            added_time = datetime.fromisoformat(added_at)
            days_active = (datetime.now() - added_time).days
            
            timeout_days = signal.get('timeout_days', self.DEFAULT_TIMEOUT_DAYS)
            
            if days_active > timeout_days:
                signal['outcome'] = self.OUTCOME_TIMEOUT
                signal['status'] = 'COMPLETED'
                signal['days_active'] = days_active
                signal['closed_at'] = datetime.now().isoformat()
                
                self._update_trade_journal(signal, current_price)
                
                logger.info(f"TIMEOUT: {signal.get('stock_symbol')} after {days_active} days")
        except Exception as e:
            logger.error(f"Error checking timeout: {e}")
    
    def _check_multi_targets(self, signal: Dict[str, Any], current_price: float, signal_type: str) -> None:
        """Check if multiple targets (T1, T2, T3) have been hit."""
        targets = signal.get('targets', [])
        if not targets:
            return
        
        targets_hit = signal.get('targets_hit', [])
        execution_buffer = self.EXECUTION_BUFFER_PERCENT
        
        for i, target in enumerate(targets):
            if not target or (i + 1) in targets_hit:
                continue
            
            if signal_type == 'BUY':
                trigger_price = target * (1 - execution_buffer / 100)
                if current_price >= trigger_price:
                    targets_hit.append(i + 1)
                    logger.info(f"Target T{i+1} HIT: {signal.get('stock_symbol')} @ {current_price} (target: {target})")
            else:
                trigger_price = target * (1 + execution_buffer / 100)
                if current_price <= trigger_price:
                    targets_hit.append(i + 1)
                    logger.info(f"Target T{i+1} HIT (SELL): {signal.get('stock_symbol')} @ {current_price} (target: {target})")
        
        signal['targets_hit'] = targets_hit
        
        if targets_hit and signal.get('status') != 'COMPLETED':
            signal['outcome'] = self.OUTCOME_PARTIAL
            signal['partial_targets'] = len(targets_hit)
    
    def _apply_trailing_sl(self, signal: Dict[str, Any], current_price: float, signal_type: str) -> None:
        """Apply trailing stop loss after targets are hit."""
        targets_hit = signal.get('targets_hit', [])
        entry_price = signal.get('entry_price', 0)
        original_sl = signal.get('original_sl_price', signal.get('sl_price', 0))
        
        if not targets_hit or not entry_price:
            return
        
        current_sl = signal.get('sl_price', original_sl)
        
        if 1 in targets_hit:
            current_sl = entry_price
        
        if 2 in targets_hit:
            if signal_type == 'BUY':
                current_sl = max(current_sl, current_price * 0.97)
            else:
                current_sl = min(current_sl, current_price * 1.03)
        
        if 3 in targets_hit:
            if signal_type == 'BUY':
                current_sl = max(current_sl, current_price * 0.95)
            else:
                current_sl = min(current_sl, current_price * 1.05)
        
        signal['sl_price'] = current_sl
        signal['original_sl_price'] = original_sl
    
    def _calculate_pnl(self, signal: Dict[str, Any], current_price: float, signal_type: str, quantity: int) -> None:
        """Calculate P&L percentage and amount."""
        entry_price = signal.get('entry_price', 0)
        
        if not entry_price or entry_price == 0:
            signal['pnl_percent'] = 0
            signal['pnl_amount'] = 0
            return
        
        if signal_type == 'BUY':
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_percent = ((entry_price - current_price) / entry_price) * 100
        
        signal['pnl_percent'] = pnl_percent
        
        if quantity and quantity > 0:
            if signal_type == 'BUY':
                pnl_amount = (current_price - entry_price) * quantity
            else:
                pnl_amount = (entry_price - current_price) * quantity
            signal['pnl_amount'] = pnl_amount
    
    def _check_sl_hit(self, signal: Dict[str, Any], current_price: float, sl_price: float, signal_type: str) -> None:
        """Check if stop loss has been hit."""
        if signal.get('status') == 'COMPLETED':
            return
        
        execution_buffer = self.EXECUTION_BUFFER_PERCENT
        
        if signal_type == 'BUY':
            trigger_price = sl_price * (1 + execution_buffer / 100)
            if current_price <= trigger_price:
                signal['outcome'] = self.OUTCOME_SL_HIT
                signal['status'] = 'COMPLETED'
                signal['closed_at'] = datetime.now().isoformat()
                logger.info(f"SL HIT: {signal.get('stock_symbol')} @ {current_price} (sl: {sl_price})")
        else:
            trigger_price = sl_price * (1 - execution_buffer / 100)
            if current_price >= trigger_price:
                signal['outcome'] = self.OUTCOME_SL_HIT
                signal['status'] = 'COMPLETED'
                signal['closed_at'] = datetime.now().isoformat()
                logger.info(f"SL HIT (SELL): {signal.get('stock_symbol')} @ {current_price} (sl: {sl_price})")
        
        if signal.get('status') == 'COMPLETED':
            self._update_trade_journal(signal, current_price)
    
    def _check_all_targets_hit(self, signal: Dict[str, Any], current_price: float, signal_type: str) -> None:
        """Check if all targets hit (full target hit)."""
        if signal.get('status') == 'COMPLETED':
            return
        
        targets = signal.get('targets', [])
        targets_hit = signal.get('targets_hit', [])
        
        if len(targets_hit) >= len(targets) and targets:
            signal['outcome'] = self.OUTCOME_TARGET_HIT
            signal['status'] = 'COMPLETED'
            signal['closed_at'] = datetime.now().isoformat()
            logger.info(f"ALL TARGETS HIT: {signal.get('stock_symbol')} @ {current_price}")
            
            self._update_trade_journal(signal, current_price)
    
    def _update_trade_journal(self, signal: Dict[str, Any], current_price: float) -> None:
        """Update trade journal with completed trade."""
        if not self.trade_journal:
            return
        
        try:
            trade_id = signal.get('trade_id')
            if not trade_id:
                trade_id = signal.get('signal_id')
            
            outcome = 'WIN' if signal.get('outcome') in [self.OUTCOME_TARGET_HIT, self.OUTCOME_PARTIAL] else 'LOSS'
            
            self.trade_journal.update_trade(
                trade_id=trade_id,
                outcome=outcome,
                exit_price=current_price,
                pnl_percent=signal.get('pnl_percent', 0),
                pnl_amount=signal.get('pnl_amount', 0),
                notes=f"Target hit: {signal.get('targets_hit', [])}, Outcome: {signal.get('outcome')}"
            )
            
            logger.info(f"Trade journal updated: {trade_id} -> {outcome}")
            
        except Exception as e:
            logger.error(f"Error updating trade journal: {e}")
    
    def calculate_priority(self, signal: Dict[str, Any]) -> float:
        """
        Calculate priority score for a signal.
        
        Args:
            signal: Signal data
            
        Returns:
            Priority score (higher = more important)
        """
        confidence = signal.get('confidence', 5)
        volume_ratio = signal.get('volume_ratio', 1)
        trend_score = signal.get('trend_score', 0)
        
        priority = (
            confidence * 0.5 +
            volume_ratio * 0.3 +
            trend_score * 0.2
        )
        
        return priority
    
    def _get_current_price(self, stock_symbol: str) -> Optional[float]:
        """Get current price for a stock with retry logic."""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                stock_data = self.data_fetcher.fetch_stock_data(stock_symbol, interval='15m', days=2)
                
                if stock_data is not None and len(stock_data) > 0:
                    latest = stock_data.iloc[-1]
                    return float(latest.get('close', latest.get('Close', 0)))
                
                if attempt < max_retries - 1:
                    logger.warning(f"No data for {stock_symbol}, retrying ({attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    continue
                
                return None
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error fetching price for {stock_symbol}: {e}, retrying ({attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Error fetching price for {stock_symbol} after {max_retries} attempts: {e}")
                    return None
        
        return None
    
    def check_all_active_signals(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Check all active signals and return status.
        
        Returns:
            Dict with 'completed', 'still_active' lists
        """
        active_signals = self.history_manager.get_all_active_signals()
        
        completed = []
        still_active = []
        
        for signal in active_signals:
            updated = self.check_signal(signal)
            
            if updated.get('status') == 'COMPLETED':
                signal_id = updated.get('signal_id')
                self.history_manager.update_active_signal(signal_id, updated)
                completed.append(updated)
            else:
                still_active.append(updated)
        
        logger.info(f"Checked {len(active_signals)} signals. Completed: {len(completed)}, Active: {len(still_active)}")
        
        return {
            'completed': completed,
            'still_active': still_active
        }
    
    def get_signals_needing_check(self, check_interval_hours: int = 4) -> List[Dict[str, Any]]:
        """
        Get signals that need to be checked based on interval and priority.
        
        Args:
            check_interval_hours: Hours between checks
            
        Returns:
            List of signals to check (sorted by priority)
        """
        signals = self.history_manager.get_all_active_signals()
        now = datetime.now()
        to_check = []
        
        for signal in signals:
            last_checked = signal.get('last_checked')
            
            if not last_checked:
                to_check.append(signal)
                continue
            
            try:
                last_time = datetime.fromisoformat(last_checked)
                if (now - last_time).total_seconds() >= check_interval_hours * 3600:
                    to_check.append(signal)
            except (ValueError, TypeError) as e:
                logger.debug(f"Error checking signal timestamp: {e}")
                to_check.append(signal)
        
        to_check.sort(key=lambda s: self.calculate_priority(s), reverse=True)
        
        return to_check
    
    def get_pending_signals_report(self) -> Dict[str, Any]:
        """
        Generate a report of all pending signals.
        
        Returns:
            Report dict with signal summaries
        """
        active_signals = self.history_manager.get_all_active_signals()
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_active': len(active_signals),
            'signals': []
        }
        
        for signal in active_signals:
            current = self.check_signal(signal.copy())
            
            targets = signal.get('targets', [])
            targets_hit = signal.get('targets_hit', [])
            
            report['signals'].append({
                'signal_id': signal.get('signal_id'),
                'trade_id': signal.get('trade_id'),
                'stock_symbol': signal.get('stock_symbol'),
                'signal_type': signal.get('signal_type'),
                'entry_price': signal.get('entry_price'),
                'targets': targets,
                'targets_hit': targets_hit,
                'sl_price': signal.get('sl_price'),
                'current_price': current.get('current_price'),
                'pnl_percent': current.get('pnl_percent', 0),
                'pnl_amount': current.get('pnl_amount', 0),
                'quantity': signal.get('quantity', 0),
                'added_at': signal.get('added_at'),
                'days_active': (datetime.now() - datetime.fromisoformat(signal.get('added_at', datetime.now().isoformat()))).days,
                'priority': self.calculate_priority(signal)
            })
        
        return report
    
    def force_close_signal(self, signal_id: str, outcome: str, current_price: float) -> bool:
        """
        Manually close a signal.
        
        Args:
            signal_id: Signal to close
            outcome: Outcome reason
            current_price: Current market price
            
        Returns:
            True if successful
        """
        signal = self.history_manager.get_active_signal(signal_id)
        
        if not signal:
            logger.warning(f"Signal not found: {signal_id}")
            return False
        
        signal['outcome'] = outcome
        signal['status'] = 'COMPLETED'
        signal['closed_at'] = datetime.now().isoformat()
        signal['current_price'] = current_price
        
        entry = signal.get('entry_price', 0)
        quantity = signal.get('quantity', 0)
        if entry and current_price:
            signal_type = signal.get('signal_type', 'BUY')
            if signal_type == 'BUY':
                signal['pnl_percent'] = ((current_price - entry) / entry) * 100
                signal['pnl_amount'] = (current_price - entry) * quantity if quantity else 0
            else:
                signal['pnl_percent'] = ((entry - current_price) / entry) * 100
                signal['pnl_amount'] = (entry - current_price) * quantity if quantity else 0
        
        self._update_trade_journal(signal, current_price)
        
        self.history_manager.remove_active_signal(signal_id)
        
        logger.info(f"Force closed signal {signal_id}: {outcome}")
        
        return True
    
    def get_signals_summary(self) -> Dict[str, Any]:
        """Get a summary of all tracked signals."""
        active = self.history_manager.get_all_active_signals()
        
        history = self.history_manager.get_history(limit=100)
        completed = [s for s in history if s.get('status') == 'COMPLETED']
        
        if completed:
            wins = len([s for s in completed if s.get('outcome') in [self.OUTCOME_TARGET_HIT, self.OUTCOME_PARTIAL]])
            total = len(completed)
            win_rate = (wins / total) * 100 if total > 0 else 0
        else:
            win_rate = 0
        
        total_pnl = sum(s.get('pnl_amount', 0) for s in completed)
        
        return {
            'active_count': len(active),
            'completed_count': len(completed),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'recent_signals': completed[-10:] if completed else []
        }


def create_signal_tracker(history_manager: HistoryManager = None, data_fetcher: DataFetcher = None, trade_journal=None) -> SignalTracker:
    """Factory function to create signal tracker."""
    if not history_manager:
        history_manager = HistoryManager()
    return SignalTracker(history_manager, data_fetcher, trade_journal)
