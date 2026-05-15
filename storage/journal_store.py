"""
Journal Store for the Crypto Momentum Scanner.

Persists all signals, rejections, and outcomes using JSON file storage.
One file per day: data/journal/signals_YYYY-MM-DD.json

Requirements: 17.1, 17.2, 17.3, 17.4, 17.7
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from streaming.models import JournalEntry, SignalOutcomeType

logger = logging.getLogger(__name__)

# Default journal directory
DEFAULT_JOURNAL_DIR = "data/journal"
RETENTION_DAYS = 90


class JournalStore:
    """
    Persists all signals, rejections, and outcomes. 90-day retention.

    Uses JSON file persistence with one file per day:
        data/journal/signals_YYYY-MM-DD.json

    Each file contains:
        {
            "signals": [...],
            "rejections": [...]
        }
    """

    def __init__(self, journal_dir: Optional[str] = None):
        """
        Initialize the JournalStore.

        Args:
            journal_dir: Path to the journal directory. Defaults to 'data/journal/'.
        """
        self._journal_dir = Path(journal_dir or DEFAULT_JOURNAL_DIR)
        self._journal_dir.mkdir(parents=True, exist_ok=True)
        self._enforce_retention()

    def _get_file_path(self, date: Optional[datetime] = None) -> Path:
        """Get the journal file path for a given date (defaults to today)."""
        if date is None:
            date = datetime.utcnow()
        filename = f"signals_{date.strftime('%Y-%m-%d')}.json"
        return self._journal_dir / filename

    def _load_file(self, file_path: Path) -> Dict[str, List]:
        """Load a journal file, returning empty structure if not found."""
        if not file_path.exists():
            return {"signals": [], "rejections": []}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure both keys exist
            if "signals" not in data:
                data["signals"] = []
            if "rejections" not in data:
                data["rejections"] = []
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load journal file {file_path}: {e}")
            return {"signals": [], "rejections": []}

    def _save_file(self, file_path: Path, data: Dict[str, List]) -> None:
        """Save data to a journal file."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Failed to save journal file {file_path}: {e}")

    def log_signal(self, entry: JournalEntry) -> str:
        """
        Persist a signal entry to today's journal file.

        Logs all required fields: symbol, setup type, entry price, stop-loss,
        composite score, RS, RVOL, OI, funding, EMAs, ATR, BTC regime, timestamp.

        Args:
            entry: A JournalEntry dataclass with all signal data.

        Returns:
            A unique signal_id for later outcome recording.

        Requirements: 17.1
        """
        signal_id = str(uuid.uuid4())
        timestamp = entry.timestamp if entry.timestamp else datetime.utcnow()

        risk = entry.entry_price - entry.stop_loss
        signal_record = {
            "signal_id": signal_id,
            "symbol": entry.symbol,
            "setup_type": entry.setup_type.value if hasattr(entry.setup_type, "value") else str(entry.setup_type),
            "direction": entry.direction.value if entry.direction and hasattr(entry.direction, "value") else "long",
            "entry_price": entry.entry_price,
            "stop_loss": entry.stop_loss,
            "composite_score": entry.composite_score,
            "relative_strength": entry.relative_strength,
            "relative_volume": entry.relative_volume,
            "oi_change_pct": entry.oi_change_pct,
            "funding_rate": entry.funding_rate,
            "ema20": entry.ema20,
            "ema50": entry.ema50,
            "ema200": entry.ema200,
            "atr14": entry.atr14,
            "btc_regime": entry.btc_regime,
            "timestamp": timestamp.isoformat(),
            # Target1 is entry + 1R (where 1R = entry - stop_loss)
            "target_1": entry.entry_price + risk,
            # Target2 is entry + 2R
            "target_2": entry.entry_price + 2 * risk,
            # Target3 is entry + 5R (from JournalEntry field, or calculated)
            "target_3": entry.target_3 if entry.target_3 is not None else entry.entry_price + 5 * risk,
            # Outcome fields (populated later)
            "outcome": None,
            "actual_rr": None,
            "duration_minutes": None,
            "exit_price": None,
        }

        file_path = self._get_file_path(timestamp)
        data = self._load_file(file_path)
        data["signals"].append(signal_record)
        self._save_file(file_path, data)

        logger.info(f"Logged signal {signal_id} for {entry.symbol} ({entry.setup_type})")
        return signal_id

    def log_rejection(
        self,
        symbol: str,
        reason: str,
        stage: str,
        indicator_values: Dict[str, float],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Persist a rejection entry to today's journal file.

        Args:
            symbol: The coin symbol that was rejected.
            reason: Human-readable rejection reason.
            stage: Pipeline stage where rejection occurred
                   (Market_Regime_Filter, Trend_Filter, Setup_Detector, Scoring_Engine).
            indicator_values: Dict of indicator names to their values at rejection time.
            timestamp: UTC timestamp of rejection. Defaults to now.

        Requirements: 17.2
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        rejection_record = {
            "symbol": symbol,
            "reason": reason,
            "stage": stage,
            "indicator_values": indicator_values,
            "timestamp": timestamp.isoformat(),
        }

        file_path = self._get_file_path(timestamp)
        data = self._load_file(file_path)
        data["rejections"].append(rejection_record)
        self._save_file(file_path, data)

        logger.debug(f"Logged rejection for {symbol} at {stage}: {reason}")

    def record_outcome(
        self,
        signal_id: str,
        outcome: SignalOutcomeType,
        actual_rr: float,
        duration_minutes: float,
        exit_price: float,
    ) -> bool:
        """
        Update an existing signal entry with outcome data.

        Searches through journal files to find the signal by ID and updates
        its outcome fields.

        Args:
            signal_id: The unique signal ID returned by log_signal().
            outcome: The outcome type (WIN, LOSS, EXPIRY).
            actual_rr: The actual risk-reward achieved.
            duration_minutes: Time from signal to outcome in minutes.
            exit_price: The price at which the outcome was determined.

        Returns:
            True if the signal was found and updated, False otherwise.

        Requirements: 17.4
        """
        # Search through recent files (within retention window) for the signal
        for days_back in range(RETENTION_DAYS):
            date = datetime.utcnow() - timedelta(days=days_back)
            file_path = self._get_file_path(date)

            if not file_path.exists():
                continue

            data = self._load_file(file_path)
            for signal in data["signals"]:
                if signal.get("signal_id") == signal_id:
                    signal["outcome"] = outcome.value if hasattr(outcome, "value") else str(outcome)
                    signal["actual_rr"] = actual_rr
                    signal["duration_minutes"] = duration_minutes
                    signal["exit_price"] = exit_price
                    self._save_file(file_path, data)
                    logger.info(
                        f"Recorded outcome for signal {signal_id}: "
                        f"{outcome.value} at RR={actual_rr:.2f}"
                    )
                    return True

        logger.warning(f"Signal {signal_id} not found for outcome recording")
        return False

    def check_outcome(
        self,
        entry_price: float,
        stop_loss: float,
        target_1: float,
        signal_timestamp: datetime,
        current_price: float,
        direction: str = "long",
    ) -> Optional[SignalOutcomeType]:
        """
        Determine if a signal has hit stop-loss, target1, or expired.

        Monitors price vs stop-loss and Target1:
        - WIN: price reaches Target1 (1R)
        - LOSS: price hits stop-loss
        - EXPIRY: neither level reached within 7 days

        Supports both LONG and SHORT directions.

        Args:
            entry_price: The signal's entry price.
            stop_loss: The signal's stop-loss level.
            target_1: The signal's Target1 level (entry + 1R).
            signal_timestamp: When the signal was generated.
            current_price: The current market price.
            direction: "long" or "short" (default "long").

        Returns:
            SignalOutcomeType if outcome is determined, None if still active.

        Requirements: 17.3
        """
        if direction == "short":
            # SHORT: loss when price goes above stop, win when price goes below target
            if current_price >= stop_loss:
                return SignalOutcomeType.LOSS
            if current_price <= target_1:
                return SignalOutcomeType.WIN
        else:
            # LONG: loss when price goes below stop, win when price goes above target
            if current_price <= stop_loss:
                return SignalOutcomeType.LOSS
            if current_price >= target_1:
                return SignalOutcomeType.WIN

        # Check for expiry (7 days elapsed)
        elapsed = datetime.utcnow() - signal_timestamp
        if elapsed >= timedelta(days=7):
            return SignalOutcomeType.EXPIRY

        # Still active, no outcome yet
        return None

    def _enforce_retention(self) -> None:
        """
        Delete journal files older than 90 days.

        Called on startup to enforce the retention policy.

        Requirements: 17.7
        """
        if not self._journal_dir.exists():
            return

        cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        deleted_count = 0

        for file_path in self._journal_dir.glob("signals_*.json"):
            try:
                # Extract date from filename: signals_YYYY-MM-DD.json
                date_str = file_path.stem.replace("signals_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    file_path.unlink()
                    deleted_count += 1
            except (ValueError, OSError) as e:
                logger.warning(f"Could not process journal file {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Retention cleanup: deleted {deleted_count} journal files older than {RETENTION_DAYS} days")

    def get_signals_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve all signals for a specific date.

        Args:
            date: The date to retrieve signals for.

        Returns:
            List of signal records for that date.
        """
        file_path = self._get_file_path(date)
        data = self._load_file(file_path)
        return data["signals"]

    def get_rejections_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve all rejections for a specific date.

        Args:
            date: The date to retrieve rejections for.

        Returns:
            List of rejection records for that date.
        """
        file_path = self._get_file_path(date)
        data = self._load_file(file_path)
        return data["rejections"]

    def get_open_signals(self) -> List[Dict[str, Any]]:
        """
        Retrieve all signals that have no outcome recorded yet.

        Searches through recent files to find signals without outcomes.

        Returns:
            List of signal records with no outcome.
        """
        open_signals = []
        # Only look back 7 days (max expiry window)
        for days_back in range(8):
            date = datetime.utcnow() - timedelta(days=days_back)
            file_path = self._get_file_path(date)

            if not file_path.exists():
                continue

            data = self._load_file(file_path)
            for signal in data["signals"]:
                if signal.get("outcome") is None:
                    open_signals.append(signal)

        return open_signals

    def generate_daily_analytics(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate end-of-day analytics for a given date.

        Calculates: total_signals, wins, losses, expiries, win_rate, avg_rr,
        best_setup_type (highest win rate), best_btc_regime, best_hour_utc.

        Zero-signal days return all zeros/empty values.

        Saves analytics to data/journal/analytics_YYYY-MM-DD.json with 90-day retention.

        Args:
            date: The date to generate analytics for. Defaults to today (UTC).

        Returns:
            Dict with analytics data.

        Requirements: 17.5, 17.6, 18.5
        """
        if date is None:
            date = datetime.utcnow()

        # Gather all resolved signals for the given date
        signals = self.get_signals_for_date(date)
        resolved = [s for s in signals if s.get("outcome") is not None]

        # Zero-signal day handling (Requirement 17.6)
        if not resolved:
            analytics = {
                "date": date.strftime("%Y-%m-%d"),
                "total_signals": 0,
                "wins": 0,
                "losses": 0,
                "expiries": 0,
                "win_rate": 0.0,
                "avg_rr": 0.0,
                "best_setup_type": "",
                "best_btc_regime": "",
                "best_hour_utc": -1,
            }
            self._save_analytics(date, analytics)
            return analytics

        # Count outcomes
        wins = sum(1 for s in resolved if s.get("outcome") == "win")
        losses = sum(1 for s in resolved if s.get("outcome") == "loss")
        expiries = sum(1 for s in resolved if s.get("outcome") == "expiry")
        total = len(resolved)

        # Win rate
        win_rate = round((wins / total) * 100, 2) if total > 0 else 0.0

        # Average RR achieved
        rr_values = [s.get("actual_rr", 0.0) for s in resolved if s.get("actual_rr") is not None]
        avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else 0.0

        # Best setup type (highest win rate)
        best_setup_type = self._find_best_by_win_rate(resolved, "setup_type")

        # Best BTC regime (highest win rate)
        best_btc_regime = self._find_best_by_win_rate(resolved, "btc_regime")

        # Best hour UTC (highest win rate)
        best_hour_utc = self._find_best_hour(resolved)

        analytics = {
            "date": date.strftime("%Y-%m-%d"),
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "expiries": expiries,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "best_setup_type": best_setup_type,
            "best_btc_regime": best_btc_regime,
            "best_hour_utc": best_hour_utc,
        }

        self._save_analytics(date, analytics)
        return analytics

    def get_rolling_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Calculate rolling performance statistics by setup type over the last N days.

        Groups resolved signals by setup_type and calculates:
        - win_rate: percentage of wins
        - avg_rr: average risk-reward achieved
        - total_trades: number of resolved trades
        - insufficient_data: True if <5 trades for that setup type

        Args:
            days: Number of days to look back. Defaults to 30.

        Returns:
            Dict keyed by setup_type with performance stats.

        Requirements: 18.1, 18.2, 18.3, 18.4, 18.6
        """
        # Gather all resolved signals over the rolling window
        all_resolved: List[Dict[str, Any]] = []
        for days_back in range(days):
            date = datetime.utcnow() - timedelta(days=days_back)
            signals = self.get_signals_for_date(date)
            resolved = [s for s in signals if s.get("outcome") is not None]
            all_resolved.extend(resolved)

        # Group by setup_type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for signal in all_resolved:
            setup_type = signal.get("setup_type", "unknown")
            if setup_type not in by_type:
                by_type[setup_type] = []
            by_type[setup_type].append(signal)

        # Calculate stats per setup type
        stats: Dict[str, Any] = {}
        for setup_type, type_signals in by_type.items():
            total_trades = len(type_signals)
            wins = sum(1 for s in type_signals if s.get("outcome") == "win")
            rr_values = [
                s.get("actual_rr", 0.0)
                for s in type_signals
                if s.get("actual_rr") is not None
            ]

            win_rate = round((wins / total_trades) * 100, 2) if total_trades > 0 else 0.0
            avg_rr = round(sum(rr_values) / len(rr_values), 2) if rr_values else 0.0

            # Mark as insufficient data if <5 trades (Requirement 18.6)
            insufficient_data = total_trades < 5

            stats[setup_type] = {
                "win_rate": win_rate,
                "avg_rr": avg_rr,
                "total_trades": total_trades,
                "insufficient_data": insufficient_data,
            }

        # Also find best BTC regime and best hour across all resolved signals
        best_btc_regime = self._find_best_by_win_rate(all_resolved, "btc_regime")
        best_hour_utc = self._find_best_hour(all_resolved)

        return {
            "days": days,
            "total_signals": len(all_resolved),
            "by_setup_type": stats,
            "best_btc_regime": best_btc_regime,
            "best_hour_utc": best_hour_utc,
        }

    def _find_best_by_win_rate(self, signals: List[Dict[str, Any]], field: str) -> str:
        """
        Find the value of `field` with the highest win rate among resolved signals.

        Args:
            signals: List of resolved signal records.
            field: The field to group by (e.g., 'setup_type', 'btc_regime').

        Returns:
            The field value with the highest win rate, or empty string if none.
        """
        if not signals:
            return ""

        # Group by field value
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for s in signals:
            value = s.get(field, "")
            if value not in groups:
                groups[value] = []
            groups[value].append(s)

        # Find highest win rate
        best_value = ""
        best_win_rate = -1.0
        for value, group_signals in groups.items():
            total = len(group_signals)
            wins = sum(1 for s in group_signals if s.get("outcome") == "win")
            wr = wins / total if total > 0 else 0.0
            if wr > best_win_rate:
                best_win_rate = wr
                best_value = value

        return best_value

    def _find_best_hour(self, signals: List[Dict[str, Any]]) -> int:
        """
        Find the UTC hour (0-23) with the highest win rate among resolved signals.

        Args:
            signals: List of resolved signal records.

        Returns:
            The hour (0-23) with the highest win rate, or -1 if no signals.
        """
        if not signals:
            return -1

        # Group by hour
        hours: Dict[int, List[Dict[str, Any]]] = {}
        for s in signals:
            ts = s.get("timestamp", "")
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    dt = ts
                hour = dt.hour
            except (ValueError, AttributeError):
                continue
            if hour not in hours:
                hours[hour] = []
            hours[hour].append(s)

        if not hours:
            return -1

        # Find hour with highest win rate
        best_hour = -1
        best_win_rate = -1.0
        for hour, hour_signals in hours.items():
            total = len(hour_signals)
            wins = sum(1 for s in hour_signals if s.get("outcome") == "win")
            wr = wins / total if total > 0 else 0.0
            if wr > best_win_rate:
                best_win_rate = wr
                best_hour = hour

        return best_hour

    def _save_analytics(self, date: datetime, analytics: Dict[str, Any]) -> None:
        """
        Save analytics report to data/journal/analytics_YYYY-MM-DD.json.

        Also enforces 90-day retention on analytics files.

        Args:
            date: The date of the analytics report.
            analytics: The analytics data to persist.

        Requirements: 18.5, 18.7
        """
        filename = f"analytics_{date.strftime('%Y-%m-%d')}.json"
        file_path = self._journal_dir / filename
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(analytics, f, indent=2, default=str)
            logger.info(f"Saved daily analytics for {date.strftime('%Y-%m-%d')}")
        except IOError as e:
            logger.error(f"Failed to save analytics file {file_path}: {e}")

        # Enforce 90-day retention on analytics files
        self._enforce_analytics_retention()

    def _enforce_analytics_retention(self) -> None:
        """
        Delete analytics files older than 90 days.

        Requirements: 18.7
        """
        if not self._journal_dir.exists():
            return

        cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        deleted_count = 0

        for file_path in self._journal_dir.glob("analytics_*.json"):
            try:
                date_str = file_path.stem.replace("analytics_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    file_path.unlink()
                    deleted_count += 1
            except (ValueError, OSError) as e:
                logger.warning(f"Could not process analytics file {file_path}: {e}")

        if deleted_count > 0:
            logger.info(
                f"Analytics retention cleanup: deleted {deleted_count} files older than {RETENTION_DAYS} days"
            )
