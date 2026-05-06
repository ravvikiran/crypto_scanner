"""
Trade Journal Module
Tracks user-executed trades and their outcomes for self-adaptive learning.
Works alongside automated signal tracking.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from loguru import logger

from models import TradingSignal, SignalOutcome, SignalResolution, SignalDirection, StrategyType
from config import get_config


class TradeType(Enum):
    """Type of trade execution"""
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


class TradeExitReason(Enum):
    """Reason for exiting a trade"""
    MANUAL = "MANUAL"
    TARGET_1_HIT = "TARGET_1_HIT"
    TARGET_2_HIT = "TARGET_2_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TIME_BASED = "TIME_BASED"


class TradeJournal:
    """
    Tracks user-executed trades for self-adaptive learning.
    
    Manually journals trades when:
    - User enters a trade (from signal or manually)
    - User exits a trade (manually, stop loss, or target hit)
    
    Then uses this data for self-adaptation.
    """
    
    def __init__(self, config: Optional[Any] = None):
        self._config = config or get_config()
        self._storage_file = Path(self._config.learning.history_file)
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._trades: Dict[str, Dict[str, Any]] = {}
        self._outcomes: List[Dict[str, Any]] = []
        self._load_state()
        
        logger.info(f"TradeJournal initialized with {len(self._trades)} open trades")
    
    def _load_state(self) -> None:
        """Load journal state from storage."""
        if not self._storage_file.exists():
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._trades = data.get('journal_trades', {})
            self._outcomes = data.get('outcomes', [])
            logger.info(f"Loaded {len(self._trades)} open trades and {len(self._outcomes)} outcomes")
        except Exception as e:
            logger.error(f"Failed to load journal state: {e}")
            self._trades = {}
            self._outcomes = []
    
    def _save_state(self) -> None:
        """Persist journal state to storage atomically."""
        try:
            existing_data = {}
            if self._storage_file.exists():
                try:
                    with open(self._storage_file, 'r') as f:
                        existing_data = json.load(f)
                except Exception:
                    pass
            
            existing_data['journal_trades'] = self._trades
            existing_data['outcomes'] = self._outcomes
            existing_data['last_updated'] = datetime.now().isoformat()
            
            # Atomic write: write to temp file then rename
            tmp_file = self._storage_file.with_suffix('.tmp')
            with open(tmp_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            tmp_file.replace(self._storage_file)
            
            logger.debug(f"Saved {len(self._trades)} open trades")
        except Exception as e:
            logger.error(f"Failed to save journal state: {e}")
    
    def journal_entry(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        target_1: Optional[float] = None,
        target_2: Optional[float] = None,
        strategy_type: str = "Manual",
        timeframe: str = "1h",
        notes: str = ""
    ) -> str:
        """
        Journal a new trade entry.
        
        Args:
            symbol: Trading symbol (e.g., BTC, ETH)
            direction: LONG or SHORT
            entry_price: Entry price
            quantity: Quantity/amount
            stop_loss: Optional stop loss price
            target_1: Optional first target
            target_2: Optional second target
            strategy_type: Strategy used
            timeframe: Timeframe
            notes: Optional notes
            
        Returns:
            Trade ID
        """
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"
        
        trade = {
            'trade_id': trade_id,
            'symbol': symbol.upper(),
            'direction': direction.upper(),
            'entry_price': entry_price,
            'quantity': quantity,
            'entry_time': datetime.now().isoformat(),
            'stop_loss': stop_loss,
            'target_1': target_1,
            'target_2': target_2,
            'strategy_type': strategy_type,
            'timeframe': timeframe,
            'notes': notes,
            'status': 'OPEN'
        }
        
        self._trades[trade_id] = trade
        self._save_state()
        
        logger.info(f"Journaled {direction} entry for {symbol} at ${entry_price}")
        return trade_id
    
    def journal_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        notes: str = ""
    ) -> Optional[SignalOutcome]:
        """
        Journal a trade exit and record outcome.
        
        Args:
            trade_id: Trade ID to close
            exit_price: Exit price
            exit_reason: MANUAL, TARGET_1_HIT, TARGET_2_HIT, STOP_LOSS_HIT, TIME_BASED
            notes: Optional notes
            
        Returns:
            SignalOutcome if successful, None if trade not found
        """
        if trade_id not in self._trades:
            logger.warning(f"Trade {trade_id} not found")
            return None
        
        trade = self._trades[trade_id]
        
        if trade['status'] == 'CLOSED':
            logger.warning(f"Trade {trade_id} already closed")
            return None
        
        direction = trade['direction']
        entry_price = trade['entry_price']
        
        pnl_percent = 0
        if direction == 'LONG':
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        duration_hours = (
            datetime.now() - datetime.fromisoformat(trade['entry_time'])
        ).total_seconds() / 3600
        
        outcome = {
            'trade_id': trade_id,
            'symbol': trade['symbol'],
            'strategy_type': trade['strategy_type'],
            'timeframe': trade['timeframe'],
            'direction': direction,
            'resolution': exit_reason,
            'pnl_percent': pnl_percent,
            'duration_hours': duration_hours,
            'entry_price': entry_price,
            'stop_loss': trade.get('stop_loss'),
            'target_1': trade.get('target_1'),
            'target_2': trade.get('target_2'),
            'price_at_resolution': exit_price,
            'timestamp': trade['entry_time'],
            'exit_time': datetime.now().isoformat(),
            'notes': notes
        }
        
        self._outcomes.append(outcome)
        
        trade['status'] = 'CLOSED'
        trade['exit_price'] = exit_price
        trade['exit_reason'] = exit_reason
        trade['pnl_percent'] = pnl_percent
        trade['exit_time'] = datetime.now().isoformat()
        
        self._save_state()
        
        logger.info(
            f"Closed {trade_id} ({trade['symbol']}): {exit_reason} "
            f"@ ${exit_price:.2f} ({pnl_percent:+.2f}%)"
        )
        
        outcome_obj = SignalOutcome(
            signal_id=trade_id,
            symbol=trade['symbol'],
            strategy_type=StrategyType(trade['strategy_type']),
            timeframe=trade['timeframe'],
            direction=SignalDirection(direction),
            resolution=SignalResolution(exit_reason),
            pnl_percent=pnl_percent,
            duration_hours=duration_hours,
            entry_price=entry_price,
            stop_loss=trade.get('stop_loss') or 0,
            target_1=trade.get('target_1') or 0,
            target_2=trade.get('target_2') or 0,
            price_at_resolution=exit_price,
            timestamp=datetime.fromisoformat(trade['entry_time']),
            confidence_score=7.0
        )
        
        return outcome_obj
    
    def close_trade_by_symbol(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        notes: str = ""
    ) -> Optional[SignalOutcome]:
        """
        Close the earliest open trade for a symbol.
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            exit_reason: Exit reason
            notes: Optional notes
            
        Returns:
            SignalOutcome if closed, None if no open trade
        """
        open_trades = [
            (tid, t) for tid, t in self._trades.items()
            if t['symbol'] == symbol.upper() and t['status'] == 'OPEN'
        ]
        
        if not open_trades:
            return None
        
        trade_id = open_trades[0][0]
        return self.journal_exit(trade_id, exit_price, exit_reason, notes)
    
    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all currently open trades."""
        trades = []
        for t in self._trades.values():
            if t['status'] == 'OPEN':
                # Convert LONG/SHORT to BUY/SELL for API compatibility
                direction = 'BUY' if t.get('direction', 'LONG').upper() in ['LONG', 'BUY'] else 'SELL'
                trades.append({
                    'trade_id': t.get('trade_id'),
                    'symbol': t.get('symbol'),
                    'strategy_type': t.get('strategy_type'),
                    'timeframe': t.get('timeframe'),
                    'direction': direction,
                    'entry': t.get('entry_price'),
                    'stop_loss': t.get('stop_loss'),
                    'target_1': t.get('target_1'),
                    'target_2': t.get('target_2'),
                    'targets': [t.get('target_1'), t.get('target_2')] if t.get('target_1') and t.get('target_2') else [],
                    'quantity': t.get('quantity', 1),
                    'status': t.get('status', 'OPEN'),
                    'outcome': t.get('exit_reason', 'OPEN'),
                    'exit_price': t.get('exit_price'),
                    'pnl_percent': t.get('pnl_percent'),
                    'timestamp': t.get('entry_time'),
                    'exit_time': t.get('exit_time'),
                    'notes': t.get('notes', '')
                })
        return trades
    
    def get_all_trades(self) -> List[Dict[str, Any]]:
        """Get all trades (open + closed)."""
        all_trades = []
        # Add open trades
        for trade in self._trades.values():
            direction = 'BUY' if trade.get('direction', 'LONG').upper() in ['LONG', 'BUY'] else 'SELL'
            all_trades.append({
                'trade_id': trade.get('trade_id'),
                'symbol': trade.get('symbol'),
                'strategy_type': trade.get('strategy_type'),
                'timeframe': trade.get('timeframe'),
                'direction': direction,
                'entry': trade.get('entry_price'),
                'stop_loss': trade.get('stop_loss'),
                'target_1': trade.get('target_1'),
                'target_2': trade.get('target_2'),
                'targets': [trade.get('target_1'), trade.get('target_2')] if trade.get('target_1') and trade.get('target_2') else [],
                'quantity': trade.get('quantity', 1),
                'status': trade.get('status', 'OPEN'),
                'outcome': trade.get('exit_reason', 'OPEN'),
                'exit_price': trade.get('exit_price'),
                'pnl_percent': trade.get('pnl_percent'),
                'timestamp': trade.get('entry_time'),
                'exit_time': trade.get('exit_time'),
                'notes': trade.get('notes', '')
            })
        # Add closed outcomes as trades
        for outcome in self._outcomes:
            direction = 'BUY' if outcome.get('direction', 'LONG').upper() in ['LONG', 'BUY'] else 'SELL'
            trade_data = {
                'trade_id': outcome.get('trade_id'),
                'symbol': outcome.get('symbol'),
                'strategy_type': outcome.get('strategy_type'),
                'timeframe': outcome.get('timeframe'),
                'direction': direction,
                'entry': outcome.get('entry_price'),
                'stop_loss': outcome.get('stop_loss'),
                'target_1': outcome.get('target_1'),
                'target_2': outcome.get('target_2'),
                'targets': [outcome.get('target_1'), outcome.get('target_2')] if outcome.get('target_1') and outcome.get('target_2') else [],
                'quantity': outcome.get('quantity', 1),
                'status': 'CLOSED',
                'outcome': outcome.get('resolution'),
                'exit_price': outcome.get('price_at_resolution'),
                'pnl_percent': outcome.get('pnl_percent'),
                'timestamp': outcome.get('timestamp'),
                'exit_time': outcome.get('exit_time'),
                'notes': outcome.get('notes', '')
            }
            all_trades.append(trade_data)
        # Sort by timestamp descending
        all_trades.sort(key=lambda t: t.get('timestamp', ''), reverse=True)
        return all_trades
    
    def get_trade_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific trade by ID."""
        return self._trades.get(trade_id)
    
    def get_outcomes(self) -> List[Dict[str, Any]]:
        """Get all recorded outcomes."""
        return self._outcomes
    
    def get_outcomes_count(self) -> int:
        """Get count of recorded outcomes."""
        return len(self._outcomes)
    
    def calculate_win_rate(self) -> float:
        """Calculate overall win rate."""
        if not self._outcomes:
            return 0.0
        
        wins = sum(
            1 for o in self._outcomes
            if o['resolution'] in ['TARGET_1_HIT', 'TARGET_2_HIT']
        )
        return (wins / len(self._outcomes)) * 100
    
    def get_stats(self) -> Dict[str, Any]:
        """Get journal statistics."""
        open_trades = self.get_open_trades()
        
        return {
            'open_trades': len(open_trades),
            'closed_trades': len([t for t in self._trades.values() if t['status'] == 'CLOSED']),
            'total_outcomes': len(self._outcomes),
            'win_rate': self.calculate_win_rate(),
            'total_pnl': sum(o['pnl_percent'] for o in self._outcomes)
        }

    def add_signal(self, signal_dict: Dict[str, Any]) -> str:
        """
        Add a signal from automated scanner as a tracked trade.
        
        This is called by the scanner when a signal is generated.
        The signal is tracked until it hits a target or stop loss.
        
        Args:
            signal_dict: Dictionary with signal details (from TradingSignal.to_dict())
            
        Returns:
            Trade ID
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        direction_raw = signal_dict.get('direction', 'LONG')
        if direction_raw.upper() not in ['LONG', 'SHORT', 'BUY', 'SELL']:
            direction_raw = 'LONG'  # Default
        
        # Convert BUY/SELL to LONG/SHORT
        if direction_raw.upper() == 'BUY':
            direction = 'LONG'
        elif direction_raw.upper() == 'SELL':
            direction = 'SHORT'
        else:
            direction = direction_raw.upper()
        
        symbol = signal_dict.get('symbol', 'UNKNOWN').upper()
        
        signal_id = signal_dict.get('signal_id', signal_dict.get('id', f'{symbol}_{direction}_{timestamp_str}'))
        trade_id = f"auto_{signal_id}"
        
        # Extract entry price from various possible keys
        entry = signal_dict.get('entry', signal_dict.get('entry_zone_min', signal_dict.get('current_price', signal_dict.get('stop_loss', 0) * 0.98)))
        
        # Build trade record
        trade = {
            'trade_id': trade_id,
            'signal_id': signal_id,
            'symbol': symbol,
            'direction': direction,
            'entry_price': entry,
            'quantity': signal_dict.get('quantity', 1),
            'entry_time': datetime.now().isoformat(),
            'stop_loss': signal_dict.get('stop_loss', 0),
            'target_1': signal_dict.get('target_1', signal_dict.get('targets', [0, 0])[0] if signal_dict.get('targets', []) else 0),
            'target_2': signal_dict.get('target_2', signal_dict.get('targets', [0, 0])[1] if signal_dict.get('targets', []) and len(signal_dict.get('targets', [])) > 1 else 0),
            'strategy_type': signal_dict.get('strategy', signal_dict.get('strategy_type', signal_dict.get('signal_type', 'Auto'))),
            'timeframe': signal_dict.get('timeframe', '1h'),
            'notes': signal_dict.get('reasoning', signal_dict.get('notes', '')),
            'status': 'OPEN',
            'entry_source': 'signal',
            'current_price': signal_dict.get('current_price', entry),
            'last_check': datetime.now().isoformat()
        }
        
        self._trades[trade_id] = trade
        self._save_state()
        
        logger.info(f"Added signal as tracked trade {trade_id} for {trade['symbol']}: {direction} @ ${trade['entry_price']:.2f}")
        return trade_id

    def check_signal_crossings(self, current_prices: Dict[str, float] = None) -> List[SignalOutcome]:
        """
        Check all open trades for target or stop loss crossings.
        Auto-closes trades when targets/stop losses are hit.
        
        This enables the learning system to track automated signal outcomes.
        
        Args:
            current_prices: Dictionary of symbol -> current price
                          If not provided, trades won't be checked against live prices
                          
        Returns:
            List of SignalOutcome objects for closed trades
        """
        outcomes = []
        
        if not current_prices:
            logger.debug("No current prices provided, skipping signal crossing check")
            return outcomes
        
        for trade_id, trade in list(self._trades.items()):
            if trade['status'] != 'OPEN':
                continue
            
            symbol = trade['symbol']
            if symbol not in current_prices:
                continue
            
            current_price = current_prices[symbol]
            trade['current_price'] = current_price
            direction = trade['direction']
            
            exit_reason = None
            exit_price = None
            
            if direction == 'LONG':
                if current_price <= trade['stop_loss']:
                    exit_reason = 'STOP_LOSS_HIT'
                    exit_price = trade['stop_loss']
                elif trade['target_2'] and current_price >= trade['target_2']:
                    exit_reason = 'TARGET_2_HIT'
                    exit_price = trade['target_2']
                elif trade['target_1'] and current_price >= trade['target_1']:
                    exit_reason = 'TARGET_1_HIT'
                    exit_price = trade['target_1']
            elif direction == 'SHORT':
                if current_price >= trade['stop_loss']:
                    exit_reason = 'STOP_LOSS_HIT'
                    exit_price = trade['stop_loss']
                elif trade['target_2'] and current_price <= trade['target_2']:
                    exit_reason = 'TARGET_2_HIT'
                    exit_price = trade['target_2']
                elif trade['target_1'] and current_price <= trade['target_1']:
                    exit_reason = 'TARGET_1_HIT'
                    exit_price = trade['target_1']
            
            if exit_reason:
                outcome = self.journal_exit(trade_id, exit_price, exit_reason, 
                                           notes="Auto-closed: signal target/stop loss crossed")
                if outcome:
                    outcomes.append(outcome)
        
        if outcomes:
            logger.info(f"Auto-closed {len(outcomes)} trades due to target/stop loss crossings")
        
        return outcomes

    def update_trade_price(self, symbol: str, current_price: float) -> None:
        """
        Update the current price for open trades of a given symbol.
        Useful for tracking price movements without closing trades.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
        """
        for trade in self._trades.values():
            if trade['symbol'] == symbol.upper() and trade['status'] == 'OPEN':
                trade['current_price'] = current_price
                trade['last_check'] = datetime.now().isoformat()

    def get_closed_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get closed trades (trades with CLOSED status).
        
        Args:
            limit: Maximum number of trades to return
            
        Returns:
            List of closed trade dictionaries, sorted by exit time descending
        """
        closed = []
        for trade in self._trades.values():
            if trade['status'] == 'CLOSED':
                direction = 'BUY' if trade.get('direction', 'LONG').upper() in ['LONG', 'BUY'] else 'SELL'
                closed.append({
                    'trade_id': trade.get('trade_id'),
                    'symbol': trade.get('symbol'),
                    'strategy_type': trade.get('strategy_type'),
                    'timeframe': trade.get('timeframe'),
                    'direction': direction,
                    'entry': trade.get('entry_price'),
                    'stop_loss': trade.get('stop_loss'),
                    'target_1': trade.get('target_1'),
                    'target_2': trade.get('target_2'),
                    'targets': [trade.get('target_1'), trade.get('target_2')] if trade.get('target_1') and trade.get('target_2') else [],
                    'quantity': trade.get('quantity', 1),
                    'status': trade.get('status'),
                    'outcome': trade.get('exit_reason', 'UNKNOWN'),
                    'exit_price': trade.get('exit_price'),
                    'pnl_percent': trade.get('pnl_percent'),
                    'timestamp': trade.get('entry_time'),
                    'exit_time': trade.get('exit_time'),
                    'notes': trade.get('notes', ''),
                    'market_context': trade.get('market_context', '')
                })
        
        # Also add outcome records that may not be in _trades anymore
        for outcome in self._outcomes:
            direction = 'BUY' if outcome.get('direction', 'LONG').upper() in ['LONG', 'BUY'] else 'SELL'
            closed.append({
                'trade_id': outcome.get('trade_id'),
                'symbol': outcome.get('symbol'),
                'strategy_type': outcome.get('strategy_type'),
                'timeframe': outcome.get('timeframe'),
                'direction': direction,
                'entry': outcome.get('entry_price'),
                'stop_loss': outcome.get('stop_loss'),
                'target_1': outcome.get('target_1'),
                'target_2': outcome.get('target_2'),
                'targets': [outcome.get('target_1'), outcome.get('target_2')] if outcome.get('target_1') and outcome.get('target_2') else [],
                'quantity': outcome.get('quantity', 1),
                'status': 'CLOSED',
                'outcome': outcome.get('resolution', ''),
                'exit_price': outcome.get('price_at_resolution'),
                'pnl_percent': outcome.get('pnl_percent'),
                'timestamp': outcome.get('timestamp'),
                'exit_time': outcome.get('exit_time'),
                'notes': outcome.get('notes', ''),
                'market_context': outcome.get('market_context', '')
            })
        
        # Remove duplicates by trade_id, keeping most recent
        seen = set()
        unique = []
        for trade in sorted(closed, key=lambda t: t.get('exit_time', ''), reverse=True):
            tid = trade.get('trade_id')
            if tid not in seen:
                seen.add(tid)
                unique.append(trade)
        
        return unique[:limit]