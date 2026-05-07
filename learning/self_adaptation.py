"""
Self Adaptation Engine
Learns from trade outcomes and adapts signal generation parameters.
Works with both automated signals and manual journal trades.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
from loguru import logger

from config import get_config


class AdaptationType(Enum):
    STRATEGY_WEIGHT = "STRATEGY_WEIGHT"
    TIMEFRAME_WEIGHT = "TIMEFRAME_WEIGHT"
    PARAMETER_ADJUSTMENT = "PARAMETER_ADJUSTMENT"
    CONFIDENCE_THRESHOLD = "CONFIDENCE_THRESHOLD"
    DIRECTION_BIAS = "DIRECTION_BIAS"


class SelfAdaptationEngine:
    def __init__(self, config: Optional[Any] = None):
        self._config = config or get_config()
        self._storage_file = Path(self._config.learning.history_file)
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._adaptations: Dict[str, Any] = {}
        self._load_adaptations()
        
        self._min_samples_for_adaptation = 5
        
        logger.info("SelfAdaptationEngine initialized")
    
    def _load_adaptations(self) -> None:
        if not self._storage_file.exists():
            self._init_default_adaptations()
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._adaptations = data.get('adaptations', {})
            if not self._adaptations:
                self._init_default_adaptations()
            
            logger.info(f"Loaded adaptations: {list(self._adaptations.keys())}")
        except Exception as e:
            logger.error(f"Failed to load adaptations: {e}")
            self._init_default_adaptations()
    
    def _init_default_adaptations(self) -> None:
        self._adaptations = {
            'strategy_weights': {
                'Breakout': 1.0,
                'Pullback': 1.0,
                'MTF': 1.0,
                'Reversal': 1.0,
                'Momentum': 1.0,
                'Manual': 1.0
            },
            'timeframe_weights': {
                '4h': 1.0,
                'daily': 1.0,
                '1h': 1.0,
                '15m': 1.0
            },
            'direction_bias': {
                'LONG': 1.0,
                'SHORT': 1.0
            },
            'min_confidence_adjustment': 0,
            'last_updated': datetime.now().isoformat()
        }
    
    def _save_adaptations(self) -> None:
        try:
            existing_data = {}
            if self._storage_file.exists():
                try:
                    with open(self._storage_file, 'r') as f:
                        existing_data = json.load(f)
                except Exception:
                    pass
            
            existing_data['adaptations'] = self._adaptations
            existing_data['last_adaptation_update'] = datetime.now().isoformat()
            
            with open(self._storage_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            
            logger.debug("Saved adaptations")
        except Exception as e:
            logger.error(f"Failed to save adaptations: {e}")
    
    def analyze_outcomes(self, outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(outcomes) < self._min_samples_for_adaptation:
            return {'ready': False, 'reason': f'Not enough samples'}
        
        strategy_stats: Dict[str, Dict[str, Any]] = {}
        timeframe_stats: Dict[str, Dict[str, Any]] = {}
        direction_stats: Dict[str, Dict[str, Any]] = {}
        
        for outcome in outcomes:
            strategy = outcome.get('strategy_type', 'Unknown')
            timeframe = outcome.get('timeframe', 'Unknown')
            direction = outcome.get('direction', 'NEUTRAL')
            resolution = outcome.get('resolution', '')
            
            is_win = resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']
            pnl = outcome.get('pnl_percent', 0)
            
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {'wins': 0, 'total': 0, 'avg_pnl': 0}
            strategy_stats[strategy]['total'] += 1
            if is_win:
                strategy_stats[strategy]['wins'] += 1
            strategy_stats[strategy]['avg_pnl'] += pnl
            
            if timeframe not in timeframe_stats:
                timeframe_stats[timeframe] = {'wins': 0, 'total': 0, 'avg_pnl': 0}
            timeframe_stats[timeframe]['total'] += 1
            if is_win:
                timeframe_stats[timeframe]['wins'] += 1
            timeframe_stats[timeframe]['avg_pnl'] += pnl
            
            if direction not in direction_stats:
                direction_stats[direction] = {'wins': 0, 'total': 0, 'avg_pnl': 0}
            direction_stats[direction]['total'] += 1
            if is_win:
                direction_stats[direction]['wins'] += 1
            direction_stats[direction]['avg_pnl'] += pnl
        
        results = {
            'strategy': {},
            'timeframe': {},
            'direction': {}
        }
        
        for strategy, stats in strategy_stats.items():
            if stats['total'] >= 2:
                win_rate = (stats['wins'] / stats['total']) * 100
                avg_pnl = stats['avg_pnl'] / stats['total']
                results['strategy'][strategy] = {
                    'win_rate': win_rate,
                    'avg_pnl': avg_pnl,
                    'total': stats['total']
                }
        
        for timeframe, stats in timeframe_stats.items():
            if stats['total'] >= 2:
                win_rate = (stats['wins'] / stats['total']) * 100
                avg_pnl = stats['avg_pnl'] / stats['total']
                results['timeframe'][timeframe] = {
                    'win_rate': win_rate,
                    'avg_pnl': avg_pnl,
                    'total': stats['total']
                }
        
        for direction, stats in direction_stats.items():
            if stats['total'] >= 2:
                win_rate = (stats['wins'] / stats['total']) * 100
                avg_pnl = stats['avg_pnl'] / stats['total']
                results['direction'][direction] = {
                    'win_rate': win_rate,
                    'avg_pnl': avg_pnl,
                    'total': stats['total']
                }
        
        return results
    
    def generate_adaptations(self, outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
        analysis = self.analyze_outcomes(outcomes)
        
        if not analysis.get('strategy'):
            return {'ready': False}
        
        new_adaptations = {}
        
        strategy_weights = self._adaptations.get('strategy_weights', {})
        for strategy, data in analysis['strategy'].items():
            win_rate = data['win_rate']
            base_w = strategy_weights.get(strategy, 1.0)
            
            if win_rate >= 60:
                new_w = base_w * 1.15
            elif win_rate >= 50:
                new_w = base_w
            elif win_rate >= 40:
                new_w = base_w * 0.85
            else:
                new_w = base_w * 0.7
            
            new_w = max(0.5, min(1.5, new_w))
            strategy_weights[strategy] = new_w
        
        new_adaptations['strategy_weights'] = strategy_weights
        
        timeframe_weights = self._adaptations.get('timeframe_weights', {})
        for timeframe, data in analysis['timeframe'].items():
            win_rate = data['win_rate']
            base_w = timeframe_weights.get(timeframe, 1.0)
            
            if win_rate >= 60:
                new_w = base_w * 1.15
            elif win_rate >= 50:
                new_w = base_w
            elif win_rate >= 40:
                new_w = base_w * 0.85
            else:
                new_w = base_w * 0.7
            
            new_w = max(0.5, min(1.5, new_w))
            timeframe_weights[timeframe] = new_w
        
        new_adaptations['timeframe_weights'] = timeframe_weights
        
        direction_bias = self._adaptations.get('direction_bias', {})
        long_perf = analysis['direction'].get('LONG', {})
        short_perf = analysis['direction'].get('SHORT', {})
        
        if long_perf.get('total', 0) >= 2 and short_perf.get('total', 0) >= 2:
            long_wr = long_perf.get('win_rate', 0)
            short_wr = short_perf.get('win_rate', 0)
            
            if long_wr > short_wr + 10:
                direction_bias['LONG'] = 1.2
                direction_bias['SHORT'] = 0.8
            elif short_wr > long_wr + 10:
                direction_bias['LONG'] = 0.8
                direction_bias['SHORT'] = 1.2
            else:
                direction_bias['LONG'] = 1.0
                direction_bias['SHORT'] = 1.0
        
        new_adaptations['direction_bias'] = direction_bias
        new_adaptations['last_updated'] = datetime.now().isoformat()
        
        self._adaptations.update(new_adaptations)
        self._save_adaptations()
        
        logger.info(f"Generated adaptations: {list(new_adaptations.keys())}")
        
        return new_adaptations
    
    def get_strategy_weight(self, strategy: str) -> float:
        return self._adaptations.get('strategy_weights', {}).get(strategy, 1.0)
    
    def get_timeframe_weight(self, timeframe: str) -> float:
        return self._adaptations.get('timeframe_weights', {}).get(timeframe, 1.0)
    
    def get_direction_bias(self, direction: str) -> float:
        return self._adaptations.get('direction_bias', {}).get(direction, 1.0)
    
    def apply_adaptations(self, signal_confidence: float, strategy: str, timeframe: str, direction: str) -> float:
        strategy_weight = self.get_strategy_weight(strategy)
        timeframe_weight = self.get_timeframe_weight(timeframe)
        direction_bias = self.get_direction_bias(direction)
        
        # Use averaged weight instead of multiplicative (prevents cascading reduction)
        # Average the weights, then apply as a single multiplier
        avg_weight = (strategy_weight + timeframe_weight + direction_bias) / 3.0
        
        # Clamp the adjustment to prevent extreme reductions (min 0.7x, max 1.3x)
        avg_weight = max(0.7, min(1.3, avg_weight))
        
        adjusted = signal_confidence * avg_weight
        
        return max(0, min(10, adjusted))
    
    def get_all_adaptations(self) -> Dict[str, Any]:
        return self._adaptations.copy()
    
    def reset_adaptations(self) -> None:
        self._init_default_adaptations()
        self._save_adaptations()
        logger.info("Adaptations reset to defaults")
    
    def get_recommendations(self) -> List[str]:
        recommendations = []
        
        strategy_weights = self._adaptations.get('strategy_weights', {})
        for strategy, weight in strategy_weights.items():
            if weight > 1.2:
                recommendations.append(f"Boost {strategy} signals (win rate high: {weight:.0%})")
            elif weight < 0.8:
                recommendations.append(f"Reduce {strategy} signals (win rate low: {weight:.0%})")
        
        direction_bias = self._adaptations.get('direction_bias', {})
        if direction_bias.get('LONG', 1.0) > 1.1:
            recommendations.append("Focus on LONG signals (better historical performance)")
        elif direction_bias.get('SHORT', 1.0) > 1.1:
            recommendations.append("Focus on SHORT signals (better historical performance)")
        
        return recommendations