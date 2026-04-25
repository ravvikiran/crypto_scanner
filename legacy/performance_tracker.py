"""
LEGACY PERFORMANCE TRACKER - NSE Stock Scanner (Deprecated)
This file is kept for reference only. DO NOT USE for crypto scanner.
Crypto uses storage.performance_tracker.PerformanceTracker instead.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import json
import math

logger = logging.getLogger(__name__)


class MarketRegime:
    """Market regime detection and classification."""
    
    HIGH_VOLATILE = 'HIGH_VOLATILE'
    NORMAL = 'NORMAL'
    LOW_VOLATILE = 'LOW_VOLATILE'
    TRENDING = 'TRENDING'
    SIDEWAYS = 'SIDEWAYS'
    
    ATR_THRESHOLD_HIGH = 3.0
    ATR_THRESHOLD_LOW = 1.5
    
    @classmethod
    def detect_regime(cls, atr_percent: float, ema_20: float, ema_50: float) -> str:
        """Detect current market regime."""
        if atr_percent > cls.ATR_THRESHOLD_HIGH:
            volatility = cls.HIGH_VOLATILE
        elif atr_percent < cls.ATR_THRESHOLD_LOW:
            volatility = cls.LOW_VOLATILE
        else:
            volatility = cls.NORMAL
        
        if ema_20 > ema_50:
            trend = cls.TRENDING
        elif ema_20 < ema_50:
            trend = cls.SIDEWAYS
        else:
            trend = cls.SIDEWAYS
        
        return f"{volatility}_{trend}"
    
    @classmethod
    def get_regime_settings(cls, regime: str) -> Dict[str, Any]:
        """Get strategy settings for a regime."""
        settings = {
            'HIGH_VOLATILE_TRENDING': {
                'min_confidence': 75,
                'max_position_size': 0.6,
                'min_volume_ratio': 2.0,
                'prefer_signals': ['BREAKOUT']
            },
            'HIGH_VOLATILE_SIDEWAYS': {
                'min_confidence': 80,
                'max_position_size': 0.4,
                'min_volume_ratio': 2.5,
                'prefer_signals': ['REVERSAL']
            },
            'NORMAL_TRENDING': {
                'min_confidence': 65,
                'max_position_size': 0.8,
                'min_volume_ratio': 1.5,
                'prefer_signals': ['BREAKOUT', 'PULLBACK']
            },
            'NORMAL_SIDEWAYS': {
                'min_confidence': 70,
                'max_position_size': 0.6,
                'min_volume_ratio': 1.5,
                'prefer_signals': ['REVERSAL']
            },
            'LOW_VOLATILE_TRENDING': {
                'min_confidence': 60,
                'max_position_size': 1.0,
                'min_volume_ratio': 1.2,
                'prefer_signals': ['BREAKOUT', 'PULLBACK']
            },
            'LOW_VOLATILE_SIDEWAYS': {
                'min_confidence': 65,
                'max_position_size': 0.7,
                'min_volume_ratio': 1.5,
                'prefer_signals': ['RANGE_BOUND']
            }
        }
        return settings.get(regime, settings.get('NORMAL_TRENDING'))


class PerformanceTracker:
    """
    Tracks and calculates signal performance metrics.
    Implements SIQ (Signal Intelligence Quotient) scoring.
    """
    
    # Default weights for SIQ calculation
    DEFAULT_WEIGHTS = {
        'win_rate': 0.25,
        'avg_return': 0.20,
        'consistency': 0.15,
        'risk_reward': 0.15,
        'signal_quality': 0.15,
        'timing': 0.10
    }
    
    DEDUP_FILE = 'smart_dedup.json'
    FACTOR_WEIGHTS_KEY = 'factor_weights'
    
    DEFAULT_FACTOR_WEIGHTS = {
        'ema_alignment': 0.15,
        'volume_confirmation': 0.15,
        'rsi_position': 0.10,
        'atr_volatility': 0.10,
        'verc_score': 0.20,
        'rsi_divergence': 0.10,
        'market_context': 0.10,
        'price_momentum': 0.10
    }
    
    POSITION_SIZING = {
        80: 1.0,
        70: 0.7,
        60: 0.4,
        0: 0.2
    }
    
    AI_ACCURACY_FILE = 'ai_accuracy.json'
    CONFIDENCE_CALIBRATION_FILE = 'confidence_calibration.json'
    ADAPTIVE_WEIGHTS_FILE = 'adaptive_weights.json'
    DEFAULT_AI_WEIGHT = 1.0
    
    def __init__(self, history_manager):
        """
        Initialize performance tracker.
        
        Args:
            history_manager: History manager for data access
        """
        self.history_manager = history_manager
        self.weights = self.DEFAULT_WEIGHTS.copy()
        self.factor_weights = self.DEFAULT_FACTOR_WEIGHTS.copy()
        self.dedup_cache = self._load_dedup_cache()
        self.ai_accuracy = self._load_ai_accuracy()
        self.confidence_calibration = self._load_confidence_calibration()
        self.adaptive_weights = self._load_adaptive_weights()
        
        logger.info("PerformanceTracker initialized")
    
    def _load_dedup_cache(self) -> Dict[str, Any]:
        """Load smart dedup cache."""
        filepath = os.path.join('data', self.DEDUP_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading dedup cache: {e}")
        return {'signals': {}, 'failed_signals': {}}
    
    def _save_dedup_cache(self) -> None:
        """Save smart dedup cache."""
        filepath = os.path.join('data', self.DEDUP_FILE)
        try:
            os.makedirs('data', exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(self.dedup_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving dedup cache: {e}")
    
    def _load_ai_accuracy(self) -> Dict[str, Any]:
        """Load AI accuracy tracking data."""
        filepath = os.path.join('data', self.AI_ACCURACY_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading AI accuracy: {e}")
        return {'predictions': [], 'total_predictions': 0, 'correct_predictions': 0}
    
    def _save_ai_accuracy(self) -> None:
        """Save AI accuracy data."""
        filepath = os.path.join('data', self.AI_ACCURACY_FILE)
        try:
            os.makedirs('data', exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(self.ai_accuracy, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving AI accuracy: {e}")
    
    def record_ai_prediction(self, prediction: str, actual_outcome: str, confidence: int) -> None:
        """
        Record AI prediction for accuracy tracking.
        
        Args:
            prediction: AI prediction (BUY/SELL/HOLD)
            actual_outcome: Actual outcome (TARGET_HIT/SL_HIT/etc)
            confidence: AI confidence at time of prediction
        """
        self.ai_accuracy.setdefault('predictions', [])
        self.ai_accuracy['predictions'].append({
            'prediction': prediction,
            'actual_outcome': actual_outcome,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        })
        self.ai_accuracy['total_predictions'] = self.ai_accuracy.get('total_predictions', 0) + 1
        
        predicted_correct = (
            (prediction in ('BUY', 'STRONG_BUY') and actual_outcome == 'TARGET_HIT') or
            (prediction in ('SELL', 'STRONG_SELL') and actual_outcome == 'SL_HIT') or
            (prediction == 'HOLD' and actual_outcome in ('TIMEOUT', 'CANCELLED'))
        )
        if predicted_correct:
            self.ai_accuracy['correct_predictions'] = self.ai_accuracy.get('correct_predictions', 0) + 1
        
        self._save_ai_accuracy()
    
    def get_ai_weight(self, default_weight: float = 1.0) -> float:
        """
        Get dynamic AI weight based on past accuracy.
        
        Args:
            default_weight: Default weight if no history
            
        Returns:
            Adaptive weight (0.5 to 1.5 based on accuracy)
        """
        total = self.ai_accuracy.get('total_predictions', 0)
        if total < 10:
            return default_weight
        
        correct = self.ai_accuracy.get('correct_predictions', 0)
        accuracy = correct / total
        
        if accuracy >= 0.7:
            return min(1.5, default_weight + 0.2)
        elif accuracy >= 0.5:
            return default_weight
        else:
            return max(0.5, default_weight - 0.3)
    
    def _load_confidence_calibration(self) -> Dict[str, Any]:
        """Load confidence calibration data."""
        filepath = os.path.join('data', self.CONFIDENCE_CALIBRATION_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading confidence calibration: {e}")
        return {'calibrations': [], 'bias_adjustment': 0.0}
    
    def _save_confidence_calibration(self) -> None:
        """Save confidence calibration data."""
        filepath = os.path.join('data', self.CONFIDENCE_CALIBRATION_FILE)
        try:
            os.makedirs('data', exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(self.confidence_calibration, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving confidence calibration: {e}")
    
    def record_signal_outcome(self, signal_confidence: int, actual_outcome: str, pnl_percent: float = 0.0) -> None:
        """
        Record signal confidence vs actual outcome for calibration.
        
        Args:
            signal_confidence: Predicted confidence (0-100)
            actual_outcome: Actual outcome (TARGET_HIT, SL_HIT, TIMEOUT)
            pnl_percent: Profit/loss percentage
        """
        self.confidence_calibration.setdefault('calibrations', [])
        self.confidence_calibration['calibrations'].append({
            'predicted_confidence': signal_confidence,
            'actual_outcome': actual_outcome,
            'pnl_percent': pnl_percent,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(self.confidence_calibration['calibrations']) > 500:
            self.confidence_calibration['calibrations'] = self.confidence_calibration['calibrations'][-500:]
        
        self._calculate_confidence_bias()
        self._save_confidence_calibration()
    
    def _calculate_confidence_bias(self) -> float:
        """Calculate bias between predicted confidence and actual win rate."""
        calibrations = self.confidence_calibration.get('calibrations', [])
        if len(calibrations) < 10:
            return 0.0
        
        total_predicted_win_rate = 0.0
        total_actual_win_rate = 0.0
        count = 0
        
        for cal in calibrations[-100:]:
            predicted = cal['predicted_confidence'] / 100.0
            actual_win = cal['actual_outcome'] == 'TARGET_HIT'
            
            total_predicted_win_rate += predicted
            total_actual_win_rate += 1.0 if actual_win else 0.0
            count += 1
        
        if count > 0:
            avg_predicted = total_predicted_win_rate / count
            avg_actual = total_actual_win_rate / count
            bias = avg_actual - avg_predicted
            self.confidence_calibration['bias_adjustment'] = round(bias, 3)
            return bias
        return 0.0
    
    def get_calibrated_confidence(self, raw_confidence: int) -> int:
        """
        Get calibrated confidence by removing known bias.
        
        Args:
            raw_confidence: Raw confidence score
            
        Returns:
            Calibrated confidence score
        """
        bias = self.confidence_calibration.get('bias_adjustment', 0.0)
        calibrated = raw_confidence + int(bias * 100)
        return max(0, min(100, calibrated))
    
    def _load_adaptive_weights(self) -> Dict[str, Any]:
        """Load adaptive weights data."""
        filepath = os.path.join('data', self.ADAPTIVE_WEIGHTS_FILE)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return data.get('factor_weights', {})
            except Exception as e:
                logger.error(f"Error loading adaptive weights: {e}")
        return {}
    
    def _save_adaptive_weights(self) -> None:
        """Save adaptive weights data."""
        filepath = os.path.join('data', self.ADAPTIVE_WEIGHTS_FILE)
        try:
            os.makedirs('data', exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump({
                    'factor_weights': self.factor_weights,
                    'last_adjusted': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving adaptive weights: {e}")
    
    def get_adaptive_factor_weight(self, factor_name: str) -> float:
        """
        Get adaptive weight for a factor based on recent performance.
        
        Args:
            factor_name: Name of the factor
            
        Returns:
            Adaptive weight multiplier (0.5 to 1.5)
        """
        if not self.adaptive_weights:
            return 1.0
        
        base_weight = self.factor_weights.get(factor_name, 0.15)
        adaptive = self.adaptive_weights.get(factor_name, 1.0)
        return base_weight * adaptive
    
    def evolve_adaptive_weights(self, lookback_days: int = 30) -> Dict[str, float]:
        """
        Evolve adaptive weights based on recent factor performance.
        This is the key feedback loop for the adaptive weight engine.
        
        Args:
            lookback_days: Days to analyze
            
        Returns:
            Updated adaptive weights
        """
        factor_stats = self._analyze_factor_performance(lookback_days)
        
        if not factor_stats or len(factor_stats) < 2:
            logger.info("Not enough data for adaptive weight evolution")
            return self.adaptive_weights
        
        new_adaptive = {}
        for factor, stats in factor_stats.items():
            win_rate = stats.get('win_rate', 0.5)
            total = stats.get('total', 0)
            
            if total < 5:
                new_adaptive[factor] = 1.0
                continue
            
            if win_rate >= 0.7:
                new_adaptive[factor] = min(1.5, (self.adaptive_weights.get(factor, 1.0) + 0.1))
            elif win_rate >= 0.5:
                new_adaptive[factor] = self.adaptive_weights.get(factor, 1.0)
            else:
                new_adaptive[factor] = max(0.5, (self.adaptive_weights.get(factor, 1.0) - 0.15))
        
        self.adaptive_weights = new_adaptive
        self._save_adaptive_weights()
        
        logger.info(f"Evolved adaptive weights: {self.adaptive_weights}")
        return self.adaptive_weights
    
    def _analyze_factor_performance(self, lookback_days: int) -> Dict[str, Any]:
        """Analyze performance by factor."""
        signals = self.history_manager.get_completed_signals()
        cutoff = datetime.now() - timedelta(days=lookback_days)
        
        recent_signals = []
        for s in signals:
            try:
                if s.get('completed_at'):
                    completed = datetime.fromisoformat(s['completed_at'])
                    if completed >= cutoff:
                        recent_signals.append(s)
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing signal timestamp: {e}")
                pass
        
        if len(recent_signals) < 5:
            return {}
        
        factor_stats = defaultdict(lambda: {'wins': 0, 'total': 0})
        
        for s in recent_signals:
            is_win = s.get('outcome') == 'TARGET_HIT'
            
            if s.get('ema_aligned'):
                factor_stats['ema_alignment']['total'] += 1
                if is_win:
                    factor_stats['ema_alignment']['wins'] += 1
            
            if s.get('volume_ratio', 0) >= 1.5:
                factor_stats['volume_confirmation']['total'] += 1
                if is_win:
                    factor_stats['volume_confirmation']['wins'] += 1
            
            rsi = s.get('rsi', 50)
            if rsi < 40:
                factor_stats['rsi_oversold']['total'] += 1
                if is_win:
                    factor_stats['rsi_oversold']['wins'] += 1
            elif rsi > 65:
                factor_stats['rsi_overbought']['total'] += 1
                if is_win:
                    factor_stats['rsi_overbought']['wins'] += 1
            
            if s.get('signal_type') == 'BREAKOUT':
                factor_stats['breakout']['total'] += 1
                if is_win:
                    factor_stats['breakout']['wins'] += 1
            
            trend_strength = s.get('trend_strength', 0)
            if trend_strength >= 7:
                factor_stats['trend_strength']['total'] += 1
                if is_win:
                    factor_stats['trend_strength']['wins'] += 1
        
        result = {}
        for factor, stats in factor_stats.items():
            if stats['total'] >= 3:
                result[factor] = {
                    'win_rate': stats['wins'] / stats['total'],
                    'total': stats['total']
                }
        
        return result
    
    def get_mtf_alignment_boost(
        self,
        trend_1d: str,
        structure_1h: str,
        breakout_15m: bool
    ) -> float:
        """
        Get confidence boost based on multi-timeframe alignment.
        
        Args:
            trend_1d: Daily trend (BULLISH/BEARISH)
            structure_1h: Hourly structure (HIGHER_HIGHS/LOWER_LOWS/SIDEWAYS)
            breakout_15m: 15m breakout confirmed
            
        Returns:
            Boost multiplier (1.0 to 1.5)
        """
        boost = 1.0
        
        if trend_1d == "BULLISH" and structure_1h == "HIGHER_HIGHS":
            boost += 0.2
        elif trend_1d == "BEARISH" and structure_1h == "LOWER_LOWS":
            boost += 0.2
        
        if breakout_15m:
            boost += 0.1
        
        return min(1.5, boost)
    
    def smart_dedup_check(self, stock_symbol: str, signal_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Smart dedup check - context-based instead of time-based.
        
        Args:
            stock_symbol: Stock to check
            signal_data: Signal data with factors
            
        Returns:
            (should_block, reason)
        """
        signals = self.dedup_cache.get('signals', {})
        failed_signals = self.dedup_cache.get('failed_signals', {})
        
        now = datetime.now()
        
        if stock_symbol in signals:
            last_signal = signals[stock_symbol]
            last_time = datetime.fromisoformat(last_signal.get('timestamp', now.isoformat()))
            days_since = (now - last_time).days
            
            is_new_breakout = signal_data.get('breakout_strength', 0) > 0.05
            is_stronger = signal_data.get('signal_score', 0) > last_signal.get('signal_score', 0)
            
            if is_new_breakout and is_stronger:
                return False, "stronger_breakout_allowed"
            
            if days_since < 3:
                return True, "recent_signal_active"
            
            if days_since < 7:
                last_outcome = last_signal.get('outcome')
                if last_outcome == 'SL_HIT' or last_outcome == 'TIMEOUT':
                    return True, f"recent_failure_{days_since}d"
        
        if stock_symbol in failed_signals:
            last_failed = failed_signals[stock_symbol]
            fail_time = datetime.fromisoformat(last_failed.get('timestamp', now.isoformat()))
            days_since_fail = (now - fail_time).days
            
            if days_since_fail < 3:
                return True, "recent_failure_wait"
        
        return False, ""
    
    def get_portfolio_status(self, active_signals: List[Dict[str, Any]], sector_mapping: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Get current portfolio status including exposure and limits.
        
        Args:
            active_signals: List of active signals
            sector_mapping: Optional mapping of stock to sector
            
        Returns:
            Portfolio status dict
        """
        max_active = 10
        max_per_sector = 0.3
        
        sector_exposure = defaultdict(float)
        correlations = []
        
        for sig in active_signals:
            position_pct = sig.get('position_size', 0) / 100000
            sector = (sector_mapping or {}).get(sig.get('stock_symbol', ''), 'Unknown')
            sector_exposure[sector] += position_pct
        
        total_exposure = sum(sector_exposure.values())
        
        return {
            'active_signals': len(active_signals),
            'max_active': max_active,
            'slots_available': max(0, max_active - len(active_signals)),
            'sector_exposure': dict(sector_exposure),
            'total_exposure_pct': round(total_exposure * 100, 1),
            'sector_limit': max_per_sector * 100,
            'at_sector_limit': any(v > max_per_sector for v in sector_exposure.values()),
            'correlation_warnings': len(correlations)
        }
    
    def check_signal_allowed(self, active_signals: List[Dict[str, Any]], new_signal_sector: str = None) -> Tuple[bool, str]:
        """
        Check if new signal is allowed based on portfolio limits.
        
        Args:
            active_signals: Current active signals
            new_signal_sector: Sector of new signal
            
        Returns:
            (allowed, reason)
        """
        portfolio = self.get_portfolio_status(active_signals)
        
        if portfolio['active_signals'] >= portfolio['max_active']:
            return False, f"max_active_reached ({portfolio['max_active']})"
        
        if new_signal_sector:
            current_sector_exposure = portfolio['sector_exposure'].get(new_signal_sector, 0)
            if current_sector_exposure >= portfolio['sector_limit']:
                return False, f"sector_limit_reached ({new_signal_sector})"
        
        return True, ""
    
    def record_signal_for_dedup(self, stock_symbol: str, signal_data: Dict[str, Any], outcome: str = None) -> None:
        """Record signal for smart dedup tracking."""
        signals = self.dedup_cache.setdefault('signals', {})
        failed_signals = self.dedup_cache.setdefault('failed_signals', {})
        
        now = datetime.now().isoformat()
        
        if outcome in ['SL_HIT', 'TIMEOUT']:
            failed_signals[stock_symbol] = {
                'timestamp': now,
                'outcome': outcome,
                'signal_score': signal_data.get('signal_score', 0)
            }
        else:
            signals[stock_symbol] = {
                'timestamp': now,
                'outcome': outcome,
                'signal_score': signal_data.get('signal_score', 0),
                'breakout_strength': signal_data.get('breakout_strength', 0)
            }
            if stock_symbol in failed_signals:
                del failed_signals[stock_symbol]
        
        self._save_dedup_cache()
    
    def calculate_position_size(self, final_score: float, regime: str = None) -> float:
        """
        Calculate position size based on confidence and regime.
        
        Args:
            final_score: Signal confidence score (0-100)
            regime: Current market regime
            
        Returns:
            Position size multiplier (0.2-1.0)
        """
        base_size = 0.2
        for threshold, size in self.POSITION_SIZING.items():
            if final_score >= threshold:
                base_size = size
                break
        
        if regime:
            regime_settings = MarketRegime.get_regime_settings(regime)
            regime_size = regime_settings.get('max_position_size', 1.0)
            base_size = min(base_size, regime_size)
        
        return base_size
    
    def detect_market_regime(self, stock_data: Dict[str, Any]) -> str:
        """
        Detect market regime from stock data.
        
        Args:
            stock_data: Stock technical data
            
        Returns:
            Market regime string
        """
        atr_percent = stock_data.get('atr_percent', 0)
        ema_20 = stock_data.get('ema_20', 0)
        ema_50 = stock_data.get('ema_50', 0)
        
        return MarketRegime.detect_regime(atr_percent, ema_20, ema_50)
    
    def get_factor_win_rates(self, lookback_days: int = 30) -> Dict[str, Any]:
        """Get win rates by factor from completed signals."""
        signals = self.history_manager.get_completed_signals()
        
        cutoff = datetime.now() - timedelta(days=lookback_days)
        recent_signals = []
        
        for s in signals:
            try:
                if s.get('completed_at'):
                    completed = datetime.fromisoformat(s['completed_at'])
                    if completed >= cutoff:
                        recent_signals.append(s)
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing signal timestamp in factor analysis: {e}")
                pass
        
        if len(recent_signals) < 5:
            return {}
        
        factor_stats = defaultdict(lambda: {'wins': 0, 'total': 0})
        
        for s in recent_signals:
            is_win = s.get('outcome') in ['TARGET_HIT', 'PARTIAL']
            
            if s.get('ema_aligned'):
                key = 'ema_alignment'
                factor_stats[key]['total'] += 1
                if is_win:
                    factor_stats[key]['wins'] += 1
            
            if s.get('volume_ratio', 0) >= 1.5:
                key = 'volume_confirmation'
                factor_stats[key]['total'] += 1
                if is_win:
                    factor_stats[key]['wins'] += 1
            
            if s.get('rsi', 0) < 50:
                key = 'rsi_oversold'
                factor_stats[key]['total'] += 1
                if is_win:
                    factor_stats[key]['wins'] += 1
            elif s.get('rsi', 0) > 60:
                key = 'rsi_overbought'
                factor_stats[key]['total'] += 1
                if is_win:
                    factor_stats[key]['wins'] += 1
            
            if s.get('signal_type') == 'BREAKOUT':
                key = 'breakout_signal'
                factor_stats[key]['total'] += 1
                if is_win:
                    factor_stats[key]['wins'] += 1
        
        result = {}
        for factor, stats in factor_stats.items():
            if stats['total'] >= 3:
                result[factor] = {
                    'win_rate': stats['wins'] / stats['total'],
                    'total': stats['total']
                }
        
        return result
    
    def auto_adjust_weights(self, lookback_days: int = 30, min_samples: int = 5) -> Dict[str, float]:
        """
        Auto-adjust factor weights based on historical performance.
        This is the KEY feedback loop.
        
        Args:
            lookback_days: Days to analyze
            min_samples: Minimum samples needed to adjust
            
        Returns:
            Updated weights
        """
        factor_win_rates = self.get_factor_win_rates(lookback_days)
        
        if not factor_win_rates or len(factor_win_rates) < 2:
            logger.info("Not enough data for auto-weight adjustment")
            return self.factor_weights
        
        factor_to_weight = {
            'ema_alignment': 'ema_alignment',
            'volume_confirmation': 'volume_confirmation',
            'rsi_oversold': 'rsi_position',
            'rsi_overbought': 'rsi_position',
            'breakout_signal': 'verc_score'
        }
        
        win_rate_buckets = [
            (0.7, 1.0, +0.05),
            (0.5, 0.7, +0.02),
            (0.0, 0.5, -0.03)
        ]
        
        adjustments = defaultdict(float)
        
        for factor, data in factor_win_rates.items():
            wr = data['win_rate']
            total = data['total']
            
            if total < min_samples:
                continue
            
            for min_wr, max_wr, adj in win_rate_buckets:
                if min_wr <= wr < max_wr:
                    adjustments[factor] = adj
                    break
        
        new_weights = self.factor_weights.copy()
        
        for factor, adjustment in adjustments.items():
            weight_key = factor_to_weight.get(factor, factor)
            if weight_key in new_weights:
                new_weights[weight_key] = max(0.05, min(0.30, new_weights[weight_key] + adjustment))
        
        total = sum(new_weights.values())
        if total > 0:
            for key in new_weights:
                new_weights[key] /= total
        
        self.factor_weights = new_weights
        self._save_auto_weights()
        
        logger.info(f"Auto-adjusted weights: {self.factor_weights}")
        
        return self.factor_weights
    
    def _save_auto_weights(self) -> None:
        """Save auto-adjusted weights."""
        filepath = os.path.join('data', 'auto_weights.json')
        try:
            os.makedirs('data', exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump({
                    'factor_weights': self.factor_weights,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving auto weights: {e}")
    
    def get_optimized_threshold(self, regime: str) -> Dict[str, Any]:
        """Get optimized thresholds based on regime."""
        settings = MarketRegime.get_regime_settings(regime)
        
        return {
            'min_confidence': settings.get('min_confidence', 65),
            'max_position_size': settings.get('max_position_size', 0.8),
            'min_volume_ratio': settings.get('min_volume_ratio', 1.5)
        }
    
    def should_block_signal(self, stock_symbol: str, signal_data: Dict[str, Any], stock_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Complete signal blocking logic with all factors.
        
        Args:
            stock_symbol: Stock to check
            signal_data: Signal data
            stock_data: Market data for regime detection
            
        Returns:
            (should_block, reason)
        """
        block, reason = self.smart_dedup_check(stock_symbol, signal_data)
        if block:
            return True, reason
        
        regime = self.detect_market_regime(stock_data)
        regime_settings = MarketRegime.get_regime_settings(regime)
        
        prefer_signals = regime_settings.get('prefer_signals', ['BREAKOUT'])
        signal_type = signal_data.get('signal_type', 'BREAKOUT')
        
        if signal_type not in prefer_signals and len(prefer_signals) < 3:
            confidence = signal_data.get('signal_score', signal_data.get('confidence', 50))
            if confidence < regime_settings.get('min_confidence', 70) + 10:
                return True, f"signal_type_not_preferred_for_{regime}"
        
        return False, ""
    
    def get_performance_feedback(self) -> Dict[str, Any]:
        """Get comprehensive performance feedback for the feedback loop."""
        siq_7 = self.calculate_siq(lookback_days=7)
        siq_30 = self.calculate_siq(lookback_days=30)
        
        return {
            'siq_score': siq_7.get('siq_score', 0),
            'siq_7_day': siq_7,
            'siq_30_day': siq_30,
            'ai_accuracy': {
                'total_predictions': self.ai_accuracy.get('total_predictions', 0),
                'correct_predictions': self.ai_accuracy.get('correct_predictions', 0),
                'accuracy_rate': (
                    self.ai_accuracy.get('correct_predictions', 0) / 
                    max(1, self.ai_accuracy.get('total_predictions', 1))
                )
            },
            'factor_weights': self.factor_weights,
            'auto_weights_applied': os.path.exists(os.path.join('data', 'auto_weights.json')),
            'dedup_cache_size': len(self.dedup_cache.get('signals', {})),
            'optimization_recommendations': self.get_recommendations()
        }
    
    def calculate_siq(self, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Calculate Signal Intelligence Quotient.
        
        Args:
            lookback_days: Days to analyze
            
        Returns:
            SIQ score and breakdown
        """
        # Get completed signals
        signals = self.history_manager.get_completed_signals()
        
        # Filter by date
        cutoff = datetime.now() - timedelta(days=lookback_days)
        recent_signals = []
        
        for s in signals:
            try:
                if s.get('completed_at'):
                    completed = datetime.fromisoformat(s['completed_at'])
                    if completed >= cutoff:
                        recent_signals.append(s)
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Error parsing SIQ signal timestamp: {e}")
                pass
        
        if not recent_signals:
            return {
                'siq_score': 0,
                'signal_count': 0,
                'lookback_days': lookback_days,
                'message': 'No completed signals in the lookback period'
            }
        
        # Calculate individual metrics
        metrics = {
            'win_rate': self._calculate_win_rate(recent_signals),
            'avg_return': self._calculate_avg_return(recent_signals),
            'consistency': self._calculate_consistency(recent_signals),
            'risk_reward': self._calculate_risk_reward(recent_signals),
            'signal_quality': self._calculate_signal_quality(recent_signals),
            'timing': self._calculate_timing_score(recent_signals)
        }
        
        # Calculate weighted SIQ
        siq_score = sum(
            metrics[key] * self.weights.get(key, 0)
            for key in metrics
        )
        
        # Normalize to 0-100
        siq_score = max(0, min(100, siq_score * 100))
        
        return {
            'siq_score': round(siq_score, 2),
            'signal_count': len(recent_signals),
            'lookback_days': lookback_days,
            'metrics': metrics,
            'weights': self.weights,
            'calculated_at': datetime.now().isoformat()
        }
    
    def _calculate_win_rate(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate win rate (0-1)."""
        if not signals:
            return 0
        
        wins = len([s for s in signals if s.get('outcome') == 'TARGET_HIT'])
        return wins / len(signals)
    
    def _calculate_avg_return(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate average return (0-1 normalized)."""
        if not signals:
            return 0
        
        returns = [s.get('pnl_percent', 0) for s in signals if s.get('pnl_percent') is not None]
        
        if not returns:
            return 0
        
        avg = sum(returns) / len(returns)
        
        # Normalize: 10% avg return = 1.0, 0% = 0.5, -10% = 0
        normalized = (avg + 10) / 20
        return max(0, min(1, normalized))
    
    def _calculate_consistency(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate consistency score based on variance (0-1)."""
        if not signals:
            return 0
        
        returns = [s.get('pnl_percent', 0) for s in signals if s.get('pnl_percent') is not None]
        
        if len(returns) < 2:
            return 0.5
        
        # Calculate standard deviation
        mean = sum(returns) / len(returns)
        variance = sum((x - mean) ** 2 for x in returns) / len(returns)
        std_dev = math.sqrt(variance)
        
        # Lower variance = higher consistency
        # Normalize: 0% std dev = 1.0, 20%+ std dev = 0
        consistency = 1 - (std_dev / 20)
        
        return max(0, min(1, consistency))
    
    def _calculate_risk_reward(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate average risk-reward ratio (0-1)."""
        if not signals:
            return 0
        
        ratios = []
        
        for s in signals:
            entry = s.get('entry_price', 0)
            target = s.get('target_price', 0)
            sl = s.get('sl_price', 0)
            
            if entry and target and sl:
                reward = abs(target - entry)
                risk = abs(entry - sl)
                
                if risk > 0:
                    ratios.append(reward / risk)
        
        if not ratios:
            return 0
        
        avg_rr = sum(ratios) / len(ratios)
        
        # Normalize: 3:1 = 1.0, 1:1 = 0.5, <1:1 = 0
        normalized = (avg_rr - 1) / 2
        return max(0, min(1, normalized))
    
    def _calculate_signal_quality(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate average signal quality based on confidence scores (0-1)."""
        if not signals:
            return 0
        
        # Look at original confidence if available
        scores = [s.get('confidence_score', s.get('signal_score', 50)) for s in signals]
        
        if not scores:
            return 0.5
        
        # Normalize to 0-1
        avg_score = sum(scores) / len(scores)
        return avg_score / 100
    
    def _calculate_timing_score(self, signals: List[Dict[str, Any]]) -> float:
        """Calculate how quickly signals hit targets (0-1)."""
        if not signals:
            return 0
        
        days_to_resolution = []
        
        for s in signals:
            added = s.get('added_at')
            completed = s.get('completed_at')
            
            if added and completed:
                try:
                    start = datetime.fromisoformat(added)
                    end = datetime.fromisoformat(completed)
                    days = (end - start).days
                    
                    if days >= 0:
                        days_to_resolution.append(days)
                except (ValueError, TypeError) as e:
                    logger.debug(f"Error calculating days to resolution: {e}")
                    pass
        
        if not days_to_resolution:
            return 0.5
        
        avg_days = sum(days_to_resolution) / len(days_to_resolution)
        
        # Normalize: 0-3 days = 1.0, 30+ days = 0
        timing = 1 - (avg_days / 30)
        return max(0, min(1, timing))
    
    def get_accuracy_by_signal_type(self) -> Dict[str, Any]:
        """Get accuracy breakdown by signal type."""
        history = self.history_manager.get_completed_signals()
        
        by_type = defaultdict(lambda: {'total': 0, 'wins': 0, 'returns': []})
        
        for s in history:
            signal_type = s.get('signal_type', 'UNKNOWN')
            by_type[signal_type]['total'] += 1
            
            if s.get('outcome') == 'TARGET_HIT':
                by_type[signal_type]['wins'] += 1
            
            if s.get('pnl_percent'):
                by_type[signal_type]['returns'].append(s['pnl_percent'])
        
        result = {}
        for signal_type, data in by_type.items():
            win_rate = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0
            avg_return = sum(data['returns']) / len(data['returns']) if data['returns'] else 0
            
            result[signal_type] = {
                'total_signals': data['total'],
                'wins': data['wins'],
                'win_rate': round(win_rate, 2),
                'avg_return': round(avg_return, 2)
            }
        
        return result
    
    def get_accuracy_by_stock(self, min_signals: int = 3) -> Dict[str, Any]:
        """Get accuracy breakdown by stock symbol."""
        history = self.history_manager.get_completed_signals()
        
        by_stock = defaultdict(lambda: {'total': 0, 'wins': 0, 'returns': []})
        
        for s in history:
            stock = s.get('stock_symbol', 'UNKNOWN')
            by_stock[stock]['total'] += 1
            
            if s.get('outcome') == 'TARGET_HIT':
                by_stock[stock]['wins'] += 1
            
            if s.get('pnl_percent'):
                by_stock[stock]['returns'].append(s['pnl_percent'])
        
        # Filter stocks with minimum signals
        filtered = {
            stock: data for stock, data in by_stock.items()
            if data['total'] >= min_signals
        }
        
        result = {}
        for stock, data in filtered.items():
            win_rate = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0
            avg_return = sum(data['returns']) / len(data['returns']) if data['returns'] else 0
            
            result[stock] = {
                'total_signals': data['total'],
                'wins': data['wins'],
                'win_rate': round(win_rate, 2),
                'avg_return': round(avg_return, 2)
            }
        
        return result
    
    def get_performance_trend(self, periods: int = 4, period_days: int = 7) -> List[Dict[str, Any]]:
        """Get performance trend over time periods."""
        history = self.history_manager.get_completed_signals()
        
        trends = []
        
        for i in range(periods):
            end_date = datetime.now() - timedelta(days=i * period_days)
            start_date = end_date - timedelta(days=period_days)
            
            period_signals = []
            
            for s in history:
                try:
                    completed = datetime.fromisoformat(s.get('completed_at', ''))
                    if start_date <= completed < end_date:
                        period_signals.append(s)
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(f"Error filtering signals by period: {e}")
                    pass
            
            if period_signals:
                wins = len([s for s in period_signals if s.get('outcome') == 'TARGET_HIT'])
                returns = [s.get('pnl_percent', 0) for s in period_signals if s.get('pnl_percent')]
                avg_return = sum(returns) / len(returns) if returns else 0
                
                trends.append({
                    'period': f"Week {periods - i}",
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'signals': len(period_signals),
                    'wins': wins,
                    'win_rate': round((wins / len(period_signals)) * 100, 2),
                    'avg_return': round(avg_return, 2)
                })
        
        return trends
    
    def update_weights(self, new_weights: Dict[str, float]) -> bool:
        """
        Update SIQ calculation weights.
        
        Args:
            new_weights: Dictionary of metric weights
            
        Returns:
            True if successful
        """
        # Validate weights sum to 1.0
        total = sum(new_weights.values())
        
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights don't sum to 1.0: {total}")
            return False
        
        # Update weights
        self.weights.update(new_weights)
        
        # Save to history manager
        self.history_manager.save_weights_config({
            'weights': self.weights,
            'updated_at': datetime.now().isoformat()
        })
        
        logger.info(f"Updated SIQ weights: {self.weights}")
        
        return True
    
    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on performance analysis."""
        siq = self.calculate_siq()
        recommendations = []
        
        if siq['signal_count'] < 5:
            recommendations.append("Need more signal data for meaningful recommendations")
            return recommendations
        
        metrics = siq.get('metrics', {})
        
        # Win rate recommendations
        win_rate = metrics.get('win_rate', 0)
        if win_rate < 0.4:
            recommendations.append("Low win rate - consider stricter entry criteria")
        elif win_rate > 0.7:
            recommendations.append("Excellent win rate - consider reducing position size for better risk management")
        
        # Return recommendations
        avg_return = metrics.get('avg_return', 0)
        if avg_return < 0.3:
            recommendations.append("Low average returns - review target levels")
        
        # Consistency recommendations
        consistency = metrics.get('consistency', 0)
        if consistency < 0.3:
            recommendations.append("Inconsistent results - signals may need more filtering")
        
        # Risk-reward recommendations
        rr = metrics.get('risk_reward', 0)
        if rr < 0.3:
            recommendations.append("Poor risk-reward ratio - review stop-loss and target settings")
        
        # Timing recommendations
        timing = metrics.get('timing', 0)
        if timing < 0.3:
            recommendations.append("Slow signal resolution - signals may be too early or targets too aggressive")
        
        return recommendations
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        siq_30 = self.calculate_siq(lookback_days=30)
        siq_7 = self.calculate_siq(lookback_days=7)
        
        return {
            'generated_at': datetime.now().isoformat(),
            'siq_30_day': siq_30,
            'siq_7_day': siq_7,
            'accuracy_by_type': self.get_accuracy_by_signal_type(),
            'accuracy_by_stock': self.get_accuracy_by_stock(),
            'performance_trend': self.get_performance_trend(),
            'recommendations': self.get_recommendations()
        }


def create_performance_tracker(history_manager) -> PerformanceTracker:
    """Factory function to create performance tracker."""
    return PerformanceTracker(history_manager)