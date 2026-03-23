"""
Signal Tracker Module
Tracks active trading signals until resolution and persists state.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from loguru import logger

from models import TradingSignal, SignalOutcome, SignalResolution, StrategyType, SignalDirection
from config import get_config


class SignalTracker:
    """
    Tracks active trading signals until resolution.
    
    Manages the lifecycle of signals from generation to resolution,
    storing them persistently in a JSON file.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize the SignalTracker.
        
        Args:
            config: Optional config object. If not provided, uses get_config()
        """
        self._config = config or get_config()
        self._storage_file = Path(self._config.learning.history_file)
        
        # Ensure data directory exists
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing active signals
        self._active_signals: Dict[str, Dict[str, Any]] = {}
        self._load_state()
        
        logger.info(f"SignalTracker initialized with {len(self._active_signals)} active signals")
    
    def _load_state(self) -> None:
        """Load active signals from storage file."""
        if not self._storage_file.exists():
            logger.info("No existing active signals file found, starting fresh")
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._active_signals = data.get('active_signals', {})
            logger.info(f"Loaded {len(self._active_signals)} active signals from storage")
        except Exception as e:
            logger.error(f"Failed to load active signals: {e}")
            self._active_signals = {}
    
    def save_state(self) -> None:
        """Persist active signals to storage file, preserving other data."""
        try:
            # Load existing data to preserve structure (outcomes, insights, etc.)
            existing_data = {}
            if self._storage_file.exists():
                try:
                    with open(self._storage_file, 'r') as f:
                        existing_data = json.load(f)
                except Exception:
                    pass
            
            # Update with active signals data
            existing_data['last_updated'] = datetime.now().isoformat()
            existing_data['active_signals'] = self._active_signals
            
            with open(self._storage_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            
            logger.debug(f"Saved {len(self._active_signals)} active signals to storage")
        except Exception as e:
            logger.error(f"Failed to save active signals: {e}")
    
    def add_signal(self, signal: TradingSignal) -> None:
        """
        Add a signal to active tracking.
        
        Args:
            signal: TradingSignal to track
        """
        # Check for duplicate signal
        if signal.id in self._active_signals:
            logger.warning(f"Signal {signal.id} ({signal.symbol}) already exists - updating")
        
        signal_dict = {
            'signal_id': signal.id,
            'timestamp': signal.timestamp.isoformat(),
            'symbol': signal.symbol,
            'name': signal.name,
            'direction': signal.direction.value,
            'strategy_type': signal.strategy_type.value,
            'timeframe': signal.timeframe,
            'entry_zone_min': signal.entry_zone_min,
            'entry_zone_max': signal.entry_zone_max,
            'stop_loss': signal.stop_loss,
            'target_1': signal.target_1,
            'target_2': signal.target_2,
            'confidence_score': signal.confidence_score,
            'reasoning': signal.reasoning,
            'current_price': signal.current_price
        }
        
        self._active_signals[signal.id] = signal_dict
        logger.info(f"Added signal {signal.id} ({signal.symbol}) to active tracking")
        self.save_state()
    
    def get_active_signals(self) -> List[TradingSignal]:
        """
        Get all active signals as TradingSignal objects.
        
        Returns:
            List of active TradingSignal objects
        """
        signals = []
        
        for signal_id, signal_data in self._active_signals.items():
            try:
                signal = TradingSignal(
                    id=signal_data['signal_id'],
                    timestamp=datetime.fromisoformat(signal_data['timestamp']),
                    symbol=signal_data['symbol'],
                    name=signal_data['name'],
                    direction=SignalDirection(signal_data['direction']),
                    strategy_type=StrategyType(signal_data['strategy_type']),
                    timeframe=signal_data['timeframe'],
                    entry_zone_min=signal_data['entry_zone_min'],
                    entry_zone_max=signal_data['entry_zone_max'],
                    stop_loss=signal_data['stop_loss'],
                    target_1=signal_data['target_1'],
                    target_2=signal_data['target_2'],
                    confidence_score=signal_data['confidence_score'],
                    reasoning=signal_data['reasoning'],
                    current_price=signal_data['current_price']
                )
                signals.append(signal)
            except Exception as e:
                logger.error(f"Failed to reconstruct signal {signal_id}: {e}")
        
        return signals
    
    def remove_signal(self, signal_id: str) -> bool:
        """
        Remove a resolved signal from active tracking.
        
        Args:
            signal_id: ID of the signal to remove
            
        Returns:
            True if signal was removed, False if not found
        """
        if signal_id in self._active_signals:
            del self._active_signals[signal_id]
            logger.info(f"Removed signal {signal_id} from active tracking")
            self.save_state()
            return True
        
        logger.warning(f"Signal {signal_id} not found in active tracking")
        return False
    
    def get_signal_by_id(self, signal_id: str) -> Optional[TradingSignal]:
        """
        Get a specific signal by ID.
        
        Args:
            signal_id: ID of the signal to retrieve
            
        Returns:
            TradingSignal if found, None otherwise
        """
        signal_data = self._active_signals.get(signal_id)
        
        if not signal_data:
            return None
        
        try:
            signal = TradingSignal(
                id=signal_data['signal_id'],
                timestamp=datetime.fromisoformat(signal_data['timestamp']),
                symbol=signal_data['symbol'],
                name=signal_data['name'],
                direction=SignalDirection(signal_data['direction']),
                strategy_type=StrategyType(signal_data['strategy_type']),
                timeframe=signal_data['timeframe'],
                entry_zone_min=signal_data['entry_zone_min'],
                entry_zone_max=signal_data['entry_zone_max'],
                stop_loss=signal_data['stop_loss'],
                target_1=signal_data['target_1'],
                target_2=signal_data['target_2'],
                confidence_score=signal_data['confidence_score'],
                reasoning=signal_data['reasoning'],
                current_price=signal_data['current_price']
            )
            return signal
        except Exception as e:
            logger.error(f"Failed to reconstruct signal {signal_id}: {e}")
            return None
    
    def get_count(self) -> int:
        """Get the count of active signals."""
        return len(self._active_signals)
    
    def get_signals_by_symbol(self, symbol: str) -> List[TradingSignal]:
        """
        Get all active signals for a specific symbol.
        
        Args:
            symbol: Symbol to filter by
            
        Returns:
            List of active signals for the symbol
        """
        signals = []
        
        for signal_id, signal_data in self._active_signals.items():
            if signal_data['symbol'] == symbol:
                try:
                    signal = TradingSignal(
                        id=signal_data['signal_id'],
                        timestamp=datetime.fromisoformat(signal_data['timestamp']),
                        symbol=signal_data['symbol'],
                        name=signal_data['name'],
                        direction=SignalDirection(signal_data['direction']),
                        strategy_type=StrategyType(signal_data['strategy_type']),
                        timeframe=signal_data['timeframe'],
                        entry_zone_min=signal_data['entry_zone_min'],
                        entry_zone_max=signal_data['entry_zone_max'],
                        stop_loss=signal_data['stop_loss'],
                        target_1=signal_data['target_1'],
                        target_2=signal_data['target_2'],
                        confidence_score=signal_data['confidence_score'],
                        reasoning=signal_data['reasoning'],
                        current_price=signal_data['current_price']
                    )
                    signals.append(signal)
                except Exception as e:
                    logger.error(f"Failed to reconstruct signal {signal_id}: {e}")
        
        return signals