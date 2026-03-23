"""
Learning Engine Module
Analyzes signal outcomes and generates actionable insights for the learning system.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum

from loguru import logger

from models import TradingSignal, SignalOutcome, SignalResolution, StrategyType, SignalDirection, TrendDirection
from config import get_config
from learning.accuracy_scorer import AccuracyScorer


class InsightType(Enum):
    """Types of insights that can be generated"""
    STRATEGY_PERFORMANCE = "STRATEGY_PERFORMANCE"
    TIMEFRAME_PERFORMANCE = "TIMEFRAME_PERFORMANCE"
    MARKET_CONDITION = "MARKET_CONDITION"
    RECOMMENDATION = "RECOMMENDATION"


class LearningEngine:
    """
    Analyzes signal outcomes and generates actionable insights.
    
    This is the core engine of the learning system that:
    - Analyzes performance patterns across strategies and timeframes
    - Identifies market condition dependencies
    - Generates recommendations for improvement
    - Persists insights for future reference
    """
    
    def __init__(
        self,
        config: Optional[Any] = None,
        accuracy_scorer: Optional[AccuracyScorer] = None
    ):
        """
        Initialize the LearningEngine.
        
        Args:
            config: Optional config object. If not provided, uses get_config()
            accuracy_scorer: Optional AccuracyScorer instance for tracking outcomes
        """
        self._config = config or get_config()
        self._accuracy_scorer = accuracy_scorer or AccuracyScorer(self._config)
        self._storage_file = Path(self._config.learning.history_file)
        
        # Ensure data directory exists
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing insights
        self._insights: List[Dict[str, Any]] = []
        self._load_insights()
        
        logger.info(f"LearningEngine initialized with {len(self._insights)} existing insights")
    
    def _load_insights(self) -> None:
        """Load existing insights from storage file."""
        if not self._storage_file.exists():
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._insights = data.get('insights', [])
            logger.debug(f"Loaded {len(self._insights)} insights from storage")
        except Exception as e:
            logger.error(f"Failed to load insights: {e}")
            self._insights = []
    
    def _save_insights(self) -> None:
        """Persist insights to storage file."""
        try:
            # Load existing data to preserve structure
            existing_data = {}
            if self._storage_file.exists():
                try:
                    with open(self._storage_file, 'r') as f:
                        existing_data = json.load(f)
                except Exception:
                    pass
            
            # Update with new insights
            existing_data['insights'] = self._insights
            existing_data['last_updated'] = datetime.now().isoformat()
            
            # Update total resolved signals count
            total_outcomes = self._accuracy_scorer.get_outcomes_count()
            existing_data['resolved_signals'] = total_outcomes
            
            # Calculate and save accuracy scores
            overall_acc = self._accuracy_scorer.calculate_overall_accuracy()
            by_strategy = self._accuracy_scorer.calculate_accuracy_by_strategy()
            by_timeframe = self._accuracy_scorer.calculate_accuracy_by_timeframe()
            
            existing_data['win_rate'] = overall_acc
            existing_data['accuracy_scores'] = {
                'overall': overall_acc,
                'by_strategy': by_strategy,
                'by_timeframe': by_timeframe
            }
            
            with open(self._storage_file, 'w') as f:
                json.dump(existing_data, f, indent=2)
            
            logger.debug(f"Saved {len(self._insights)} insights to storage")
        except Exception as e:
            logger.error(f"Failed to save insights: {e}")
    
    def should_generate_insights(self) -> bool:
        """
        Check if enough signals have been tracked to generate meaningful insights.
        
        Returns:
            True if min_signals_for_insights threshold is met
        """
        outcome_count = self._accuracy_scorer.get_outcomes_count()
        threshold = self._config.learning.min_signals_for_insights
        
        ready = outcome_count >= threshold
        logger.debug(
            f"Insight generation check: {outcome_count}/{threshold} signals "
            f"({'ready' if ready else 'not ready'})"
        )
        
        return ready
    
    def _load_all_outcomes(self) -> List[Dict[str, Any]]:
        """Load all resolved outcomes from the accuracy scorer."""
        # Get from storage file directly
        if not self._storage_file.exists():
            return []
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            # Try different possible keys
            return data.get('outcomes') or data.get('recent_outcomes') or []
        except Exception as e:
            logger.error(f"Failed to load outcomes: {e}")
            return []
    
    def _analyze_strategy_performance(self) -> Dict[str, Any]:
        """Analyze performance by strategy type."""
        outcomes = self._load_all_outcomes()
        
        if not outcomes:
            return {}
        
        strategy_stats: Dict[str, Dict[str, Any]] = {}
        
        for outcome in outcomes:
            strategy = outcome.get('strategy_type', 'Unknown')
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {
                    'wins': 0,
                    'losses': 0,
                    'total': 0,
                    'avg_pnl': 0,
                    'total_pnl': 0
                }
            
            strategy_stats[strategy]['total'] += 1
            
            resolution = outcome.get('resolution', '')
            is_win = resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']
            
            if is_win:
                strategy_stats[strategy]['wins'] += 1
            else:
                strategy_stats[strategy]['losses'] += 1
            
            pnl = outcome.get('pnl_percent', 0)
            strategy_stats[strategy]['total_pnl'] += pnl
        
        # Calculate metrics
        results = {}
        for strategy, stats in strategy_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
            
            results[strategy] = {
                'win_rate': round(win_rate, 1),
                'total_signals': stats['total'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'avg_pnl': round(avg_pnl, 2)
            }
        
        return results
    
    def _analyze_timeframe_performance(self) -> Dict[str, Any]:
        """Analyze performance by timeframe."""
        outcomes = self._load_all_outcomes()
        
        if not outcomes:
            return {}
        
        timeframe_stats: Dict[str, Dict[str, Any]] = {}
        
        for outcome in outcomes:
            timeframe = outcome.get('timeframe', 'Unknown')
            if timeframe not in timeframe_stats:
                timeframe_stats[timeframe] = {
                    'wins': 0,
                    'losses': 0,
                    'total': 0,
                    'avg_pnl': 0,
                    'total_pnl': 0
                }
            
            timeframe_stats[timeframe]['total'] += 1
            
            resolution = outcome.get('resolution', '')
            is_win = resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']
            
            if is_win:
                timeframe_stats[timeframe]['wins'] += 1
            else:
                timeframe_stats[timeframe]['losses'] += 1
            
            pnl = outcome.get('pnl_percent', 0)
            timeframe_stats[timeframe]['total_pnl'] += pnl
        
        # Calculate metrics
        results = {}
        for timeframe, stats in timeframe_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
            
            results[timeframe] = {
                'win_rate': round(win_rate, 1),
                'total_signals': stats['total'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'avg_pnl': round(avg_pnl, 2)
            }
        
        return results
    
    def _analyze_market_conditions(self) -> Dict[str, Any]:
        """Analyze how BTC trend affects signal performance."""
        # Note: This requires BTC trend data to be stored with outcomes
        # For now, we'll analyze by direction (LONG vs SHORT) as proxy
        outcomes = self._load_all_outcomes()
        
        if not outcomes:
            return {}
        
        direction_stats: Dict[str, Dict[str, Any]] = {}
        
        for outcome in outcomes:
            direction = outcome.get('direction', 'NEUTRAL')
            if direction not in direction_stats:
                direction_stats[direction] = {
                    'wins': 0,
                    'losses': 0,
                    'total': 0,
                    'avg_pnl': 0,
                    'total_pnl': 0
                }
            
            direction_stats[direction]['total'] += 1
            
            resolution = outcome.get('resolution', '')
            is_win = resolution in ['TARGET_1_HIT', 'TARGET_2_HIT']
            
            if is_win:
                direction_stats[direction]['wins'] += 1
            else:
                direction_stats[direction]['losses'] += 1
            
            pnl = outcome.get('pnl_percent', 0)
            direction_stats[direction]['total_pnl'] += pnl
        
        # Calculate metrics
        results = {}
        for direction, stats in direction_stats.items():
            win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            avg_pnl = stats['total_pnl'] / stats['total'] if stats['total'] > 0 else 0
            
            results[direction] = {
                'win_rate': round(win_rate, 1),
                'total_signals': stats['total'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'avg_pnl': round(avg_pnl, 2)
            }
        
        return results
    
    def _generate_recommendations(
        self,
        strategy_perf: Dict[str, Any],
        timeframe_perf: Dict[str, Any],
        market_perf: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Strategy recommendations
        if strategy_perf:
            # Find best and worst strategies
            sorted_strategies = sorted(
                strategy_perf.items(),
                key=lambda x: x[1]['win_rate'],
                reverse=True
            )
            
            if sorted_strategies:
                best = sorted_strategies[0]
                if best[1]['total_signals'] >= 3:  # Only if enough data
                    recommendations.append(
                        f"Prioritize {best[0]} strategy (win rate: {best[1]['win_rate']}%)"
                    )
                
                worst = sorted_strategies[-1]
                if worst[1]['win_rate'] < 40 and worst[1]['total_signals'] >= 3:
                    recommendations.append(
                        f"Review or reduce {worst[0]} strategy (low win rate: {worst[1]['win_rate']}%)"
                    )
        
        # Timeframe recommendations
        if timeframe_perf:
            sorted_timeframes = sorted(
                timeframe_perf.items(),
                key=lambda x: x[1]['win_rate'],
                reverse=True
            )
            
            if sorted_timeframes:
                best_tf = sorted_timeframes[0]
                if best_tf[1]['total_signals'] >= 3:
                    recommendations.append(
                        f"Focus on {best_tf[0]} timeframe (win rate: {best_tf[1]['win_rate']}%)"
                    )
        
        # Market condition recommendations
        if market_perf:
            long_perf = market_perf.get('LONG', {})
            short_perf = market_perf.get('SHORT', {})
            
            if long_perf.get('total', 0) >= 3 and short_perf.get('total', 0) >= 3:
                if long_perf.get('win_rate', 0) > short_perf.get('win_rate', 0) + 15:
                    recommendations.append(
                        "LONG signals performing significantly better - consider directional bias"
                    )
                elif short_perf.get('win_rate', 0) > long_perf.get('win_rate', 0) + 15:
                    recommendations.append(
                        "SHORT signals performing significantly better - consider directional bias"
                    )
        
        return recommendations
    
    def generate_insights(self) -> List[Dict[str, Any]]:
        """
        Analyze outcomes and generate comprehensive insights.
        
        This method:
        - Analyzes performance by strategy type
        - Analyzes performance by timeframe
        - Analyzes market condition impacts
        - Generates actionable recommendations
        - Saves insights to storage
        
        Returns:
            List of generated insight dictionaries
        """
        if not self.should_generate_insights():
            logger.info(
                f"Not enough data for insights yet "
                f"({self._accuracy_scorer.get_outcomes_count()}/{self._config.learning.min_signals_for_insights})"
            )
            return []
        
        logger.info("Generating learning insights...")
        
        # Run analyses
        strategy_perf = self._analyze_strategy_performance()
        timeframe_perf = self._analyze_timeframe_performance()
        market_perf = self._analyze_market_conditions()
        
        new_insights = []
        timestamp = datetime.now().isoformat()
        
        # Strategy Performance Insight
        if strategy_perf:
            best_strategy = max(strategy_perf.items(), key=lambda x: x[1]['win_rate'])
            insight = {
                'type': InsightType.STRATEGY_PERFORMANCE.value,
                'timestamp': timestamp,
                'data': strategy_perf,
                'summary': f"Best: {best_strategy[0]} ({best_strategy[1]['win_rate']}%)",
                'recommendation': f"Focus on {best_strategy[0]} strategy"
            }
            new_insights.append(insight)
        
        # Timeframe Performance Insight
        if timeframe_perf:
            best_timeframe = max(timeframe_perf.items(), key=lambda x: x[1]['win_rate'])
            insight = {
                'type': InsightType.TIMEFRAME_PERFORMANCE.value,
                'timestamp': timestamp,
                'data': timeframe_perf,
                'summary': f"Best: {best_timeframe[0]} ({best_timeframe[1]['win_rate']}%)",
                'recommendation': f"Use {best_timeframe[0]} timeframe for higher win rate"
            }
            new_insights.append(insight)
        
        # Market Condition Insight
        if market_perf:
            insight = {
                'type': InsightType.MARKET_CONDITION.value,
                'timestamp': timestamp,
                'data': market_perf,
                'summary': f"LONG: {market_perf.get('LONG', {}).get('win_rate', 0)}%, SHORT: {market_perf.get('SHORT', {}).get('win_rate', 0)}%",
                'recommendation': "Track performance in different market conditions"
            }
            new_insights.append(insight)
        
        # Generate Recommendations
        recommendations = self._generate_recommendations(
            strategy_perf, timeframe_perf, market_perf
        )
        
        if recommendations:
            insight = {
                'type': InsightType.RECOMMENDATION.value,
                'timestamp': timestamp,
                'data': {},
                'recommendations': recommendations,
                'summary': f"{len(recommendations)} recommendations generated"
            }
            new_insights.append(insight)
        
        # Add to stored insights
        self._insights.extend(new_insights)
        
        # Save to storage
        self._save_insights()
        
        logger.info(f"Generated {len(new_insights)} new insights")
        
        return new_insights
    
    def get_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent insights.
        
        Args:
            limit: Maximum number of insights to return
            
        Returns:
            List of recent insight dictionaries
        """
        return self._insights[-limit:] if self._insights else []
    
    def get_latest_insight_by_type(self, insight_type: InsightType) -> Optional[Dict[str, Any]]:
        """
        Get the most recent insight of a specific type.
        
        Args:
            insight_type: Type of insight to retrieve
            
        Returns:
            Latest insight of the specified type, or None
        """
        for insight in reversed(self._insights):
            if insight.get('type') == insight_type.value:
                return insight
        return None
    
    def get_accuracy_stats(self) -> Dict[str, Any]:
        """
        Get current accuracy statistics.
        
        Returns:
            Dictionary with accuracy metrics
        """
        return {
            'overall': self._accuracy_scorer.calculate_overall_accuracy(),
            'by_strategy': self._accuracy_scorer.calculate_accuracy_by_strategy(),
            'by_timeframe': self._accuracy_scorer.calculate_accuracy_by_timeframe(),
            'total_resolved': self._accuracy_scorer.get_outcomes_count(),
            'quality_score': self._accuracy_scorer.calculate_quality_score()
        }