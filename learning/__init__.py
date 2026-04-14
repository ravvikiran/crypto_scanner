"""
Learning Module for Hybrid Reasoning + Learning System
Tracks signals and learns from outcomes to improve AI reasoning.
Includes self-adaptation capabilities.
"""

from learning.signal_tracker import SignalTracker
from learning.accuracy_scorer import AccuracyScorer
from learning.resolution_checker import ResolutionChecker
from learning.learning_engine import LearningEngine
from learning.notifier import send_resolution_alert
from learning.trade_journal import TradeJournal
from learning.self_adaptation import SelfAdaptationEngine

__all__ = [
    "SignalTracker",
    "AccuracyScorer", 
    "ResolutionChecker",
    "LearningEngine",
    "send_resolution_alert",
    "TradeJournal",
    "SelfAdaptationEngine"
]