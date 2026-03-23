"""
Accuracy Scorer Module
Calculates accuracy metrics and tracks signal outcomes for learning.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from loguru import logger

from models import TradingSignal, SignalOutcome, SignalResolution, StrategyType, SignalDirection
from config import get_config


class AccuracyScorer:
    """
    Tracks signal outcomes and calculates accuracy metrics.
    
    Manages the learning history, calculates win rates by strategy and timeframe,
    and computes quality scores for signal generation.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize the AccuracyScorer.
        
        Args:
            config: Optional config object. If not provided, uses get_config()
        """
        self._config = config or get_config()
        self._storage_file = Path(self._config.learning.history_file)
        
        # Ensure data directory exists
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing outcomes
        self._outcomes: List[Dict[str, Any]] = []
        self._load_history()
        
        logger.info(f"AccuracyScorer initialized with {len(self._outcomes)} recorded outcomes")
    
    def _load_history(self) -> None:
        """Load outcome history from storage file."""
        if not self._storage_file.exists():
            logger.info("No existing learning history found, starting fresh")
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._outcomes = data.get('outcomes', [])
            logger.info(f"Loaded {len(self._outcomes)} outcomes from history")
        except Exception as e:
            logger.error(f"Failed to load learning history: {e}")
            self._outcomes = []
    
    def save_history(self) -> None:
        """Persist outcomes to storage file, preserving other data."""
        try:
            # Load existing data to preserve structure (insights, active_signals, etc.)
            existing_data = {}
            if self._storage_file.exists():
                try:
                    with open(self._storage_file, 'r') as f:
                        existing_data = json.load(f)
                except Exception:
                    pass
            
            # Update with outcomes data
            existing_data['last_updated'] = datetime.now().isoformat()
            existing_data['outcomes'] = self._outcomes
            
            with open(self._storage_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            
            logger.debug(f"Saved {len(self._outcomes)} outcomes to history")
        except Exception as e:
            logger.error(f"Failed to save learning history: {e}")
    
    def calculate_outcome(self, signal: TradingSignal, current_price: float) -> Optional[SignalOutcome]:
        """
        Detect if a signal has resolved based on current price.
        
        Args:
            signal: The trading signal to check
            current_price: Current price of the asset
            
        Returns:
            SignalOutcome if resolved, None if still active
        """
        resolution: Optional[SignalResolution] = None
        exit_price = current_price
        
        if signal.direction == SignalDirection.LONG:
            # For LONG signals
            if current_price <= signal.stop_loss:
                resolution = SignalResolution.STOP_LOSS_HIT
                exit_price = signal.stop_loss
            elif current_price >= signal.target_2:
                resolution = SignalResolution.TARGET_2_HIT
                exit_price = signal.target_2
            elif current_price >= signal.target_1:
                resolution = SignalResolution.TARGET_1_HIT
                exit_price = signal.target_1
                
        elif signal.direction == SignalDirection.SHORT:
            # For SHORT signals
            if current_price >= signal.stop_loss:
                resolution = SignalResolution.STOP_LOSS_HIT
                exit_price = signal.stop_loss
            elif current_price <= signal.target_2:
                resolution = SignalResolution.TARGET_2_HIT
                exit_price = signal.target_2
            elif current_price <= signal.target_1:
                resolution = SignalResolution.TARGET_1_HIT
                exit_price = signal.target_1
        
        if resolution is None:
            return None
        
        # Calculate PnL
        pnl_percent = 0
        if signal.direction == SignalDirection.LONG:
            if resolution == SignalResolution.STOP_LOSS_HIT:
                # Loss: (entry - exit) / entry
                entry_price = signal.entry_zone_min
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            else:
                # Win: (exit - entry) / entry
                entry_price = signal.entry_zone_min
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        elif signal.direction == SignalDirection.SHORT:
            if resolution == SignalResolution.STOP_LOSS_HIT:
                # Loss: (exit - entry) / entry
                entry_price = signal.entry_zone_max
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
            else:
                # Win: (entry - exit) / entry
                entry_price = signal.entry_zone_max
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        # Calculate duration in hours
        duration_hours = (datetime.now() - signal.timestamp).total_seconds() / 3600
        
        # Determine if this was a "correct" prediction (win)
        is_win = resolution in [SignalResolution.TARGET_1_HIT, SignalResolution.TARGET_2_HIT]
        
        outcome = SignalOutcome(
            signal_id=signal.id,
            symbol=signal.symbol,
            strategy_type=signal.strategy_type,
            timeframe=signal.timeframe,
            direction=signal.direction,
            resolution=resolution,
            pnl_percent=pnl_percent,
            duration_hours=duration_hours,
            entry_price=signal.entry_zone_min if signal.direction == SignalDirection.LONG else signal.entry_zone_max,
            stop_loss=signal.stop_loss,
            target_1=signal.target_1,
            target_2=signal.target_2,
            price_at_resolution=exit_price,
            timestamp=signal.timestamp,
            confidence_score=signal.confidence_score
        )
        
        return outcome
    
    def record_outcome(self, outcome: SignalOutcome) -> None:
        """
        Record a resolved signal outcome.
        
        Args:
            outcome: SignalOutcome to record
        """
        outcome_dict = outcome.to_dict()
        outcome_dict['resolved_at'] = datetime.now().isoformat()
        
        self._outcomes.append(outcome_dict)
        logger.info(f"Recorded outcome for {outcome.symbol}: {outcome.resolution.value} (PnL: {outcome.pnl_percent:.2f}%)")
        self.save_history()
    
    def calculate_accuracy_by_strategy(self) -> Dict[str, float]:
        """
        Calculate win rate by strategy type.
        
        Returns:
            Dictionary mapping strategy type to win rate (0-100)
        """
        strategy_stats: Dict[str, Dict[str, int]] = {}
        
        for outcome in self._outcomes:
            strategy = outcome.get('strategy_type', 'None')
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'wins': 0, 'total': 0}
            
            strategy_stats[strategy]['total'] += 1
            
            # Win if target was hit
            resolution = outcome.get('resolution', '')
            if resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']:
                strategy_stats[strategy]['wins'] += 1
        
        # Calculate win rates
        win_rates = {}
        for strategy, stats in strategy_stats.items():
            if stats['total'] > 0:
                win_rates[strategy] = (stats['wins'] / stats['total']) * 100
            else:
                win_rates[strategy] = 0.0
        
        return win_rates
    
    def calculate_accuracy_by_timeframe(self) -> Dict[str, float]:
        """
        Calculate win rate by timeframe.
        
        Returns:
            Dictionary mapping timeframe to win rate (0-100)
        """
        timeframe_stats: Dict[str, Dict[str, int]] = {}
        
        for outcome in self._outcomes:
            timeframe = outcome.get('timeframe', 'unknown')
            if timeframe not in timeframe_stats:
                timeframe_stats[timeframe] = {'wins': 0, 'total': 0}
            
            timeframe_stats[timeframe]['total'] += 1
            
            # Win if target was hit
            resolution = outcome.get('resolution', '')
            if resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']:
                timeframe_stats[timeframe]['wins'] += 1
        
        # Calculate win rates
        win_rates = {}
        for timeframe, stats in timeframe_stats.items():
            if stats['total'] > 0:
                win_rates[timeframe] = (stats['wins'] / stats['total']) * 100
            else:
                win_rates[timeframe] = 0.0
        
        return win_rates
    
    def calculate_overall_accuracy(self) -> float:
        """
        Calculate overall win rate across all signals.
        
        Returns:
            Overall win rate (0-100)
        """
        if not self._outcomes:
            return 0.0
        
        total = len(self._outcomes)
        wins = sum(1 for o in self._outcomes 
                   if o.get('resolution') in ['TARGET_1_HIT', 'TARGET_2_HIT'])
        
        return (wins / total) * 100 if total > 0 else 0.0
    
    def calculate_quality_score(self) -> float:
        """
        Calculate overall quality score.
        
        Quality = (WinRate*0.4) + (AvgR/R*0.3) + (AvgConfidence*0.3)
        
        Returns:
            Quality score (0-10)
        """
        if not self._outcomes:
            return 0.0
        
        # Win rate component (0-10)
        win_rate = self.calculate_overall_accuracy()
        win_rate_score = (win_rate / 100) * 10
        
        # Average R/R component
        avg_rr = self._calculate_avg_risk_reward()
        rr_score = min(avg_rr / 3.0, 1.0) * 10  # Cap at 3:1 for max score
        
        # Average confidence component
        avg_confidence = self._calculate_avg_confidence()
        confidence_score = avg_confidence
        
        # Weighted quality score
        quality = (win_rate_score * 0.4) + (rr_score * 0.3) + (confidence_score * 0.3)
        
        return round(quality, 2)
    
    def _calculate_avg_risk_reward(self) -> float:
        """Calculate average risk/reward ratio of resolved signals."""
        wins = [o for o in self._outcomes 
                if o.get('resolution') in ['TARGET_1_HIT', 'TARGET_2_HIT']]
        
        if not wins:
            return 0.0
        
        total_rr = 0
        for outcome in wins:
            entry = outcome.get('entry_price', 0)
            target = outcome.get('target_1', 0)
            stop = outcome.get('stop_loss', 0)
            
            if entry > 0 and stop > 0:
                risk = abs(entry - stop) / entry
                reward = abs(target - entry) / entry
                rr = reward / risk if risk > 0 else 0
                total_rr += rr
        
        return total_rr / len(wins) if wins else 0.0
    
    def _calculate_avg_confidence(self) -> float:
        """Calculate average confidence score of resolved signals."""
        if not self._outcomes:
            return 0.0
        
        total_confidence = sum(o.get('confidence_score', 0) for o in self._outcomes)
        return total_confidence / len(self._outcomes)
    
    def get_outcomes_count(self) -> int:
        """Get the count of recorded outcomes."""
        return len(self._outcomes)
    
    def get_recent_outcomes(self, limit: int = 10) -> List[SignalOutcome]:
        """
        Get the most recent outcomes.
        
        Args:
            limit: Maximum number of outcomes to return
            
        Returns:
            List of recent SignalOutcome objects
        """
        outcomes = sorted(self._outcomes, 
                         key=lambda x: x.get('timestamp', ''), 
                         reverse=True)[:limit]
        
        result = []
        for o in outcomes:
            try:
                outcome = SignalOutcome(
                    signal_id=o.get('signal_id', ''),
                    symbol=o.get('symbol', ''),
                    strategy_type=StrategyType(o.get('strategy_type', 'None')),
                    timeframe=o.get('timeframe', ''),
                    direction=SignalDirection(o.get('direction', 'NEUTRAL')),
                    resolution=SignalResolution(o.get('resolution', 'EXPIRED')),
                    pnl_percent=o.get('pnl_percent', 0),
                    duration_hours=o.get('duration_hours', 0),
                    entry_price=o.get('entry_price', 0),
                    stop_loss=o.get('stop_loss', 0),
                    target_1=o.get('target_1', 0),
                    target_2=o.get('target_2', 0),
                    price_at_resolution=o.get('price_at_resolution', 0),
                    timestamp=datetime.fromisoformat(o.get('timestamp', datetime.now().isoformat())),
                    confidence_score=o.get('confidence_score', 0)
                )
                result.append(outcome)
            except Exception as e:
                logger.error(f"Failed to reconstruct outcome: {e}")
        
        return result
