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
        """Persist journal state to storage."""
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
            
            with open(self._storage_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            
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
        """Get all open trades."""
        return [t for t in self._trades.values() if t['status'] == 'OPEN']
    
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