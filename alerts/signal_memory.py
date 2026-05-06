"""
Signal Memory - Tracks signals, prevents duplicates, and provides update mechanism.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class SignalMemory:
    """
    Tracks signals sent and determines if a new signal should be sent as UPDATE or NEW.
    """

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True, parents=True)
        self.all_signals_file = self.data_dir / 'memory_all_signals.json'
        self.active_signals_file = self.data_dir / 'signals_active.json'

        self.all_signals: List[Dict] = self._load_json(self.all_signals_file, [])
        self.active_signals: Dict[str, Dict] = self._load_json(self.active_signals_file, {})
        
        # Auto-cleanup old signals on initialization
        self.cleanup_old_signals(days=30)

    def _load_json(self, path: Path, default):
        """Load JSON file or return default."""
        if path.exists():
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {path}: {e}")
        return default

    def _save_json(self, path: Path, data):
        """Save JSON atomically."""
        tmp = path.with_suffix('.tmp')
        try:
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            tmp.replace(path)
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")

    def get_signals_sent_today(self) -> List[Dict]:
        """Get all signals sent today (midnight UTC)."""
        today_utc = datetime.utcnow().date()
        today_signals = []

        for sig in self.all_signals:
            try:
                sent_time = datetime.fromisoformat(sig.get('generated_at', ''))
                if sent_time.date() == today_utc:
                    today_signals.append(sig)
            except:
                continue

        return today_signals

    def get_signal_status(self, symbol: str, signal_type: str) -> Optional[Dict]:
        """
        Find latest signal for symbol+type and return its current status.
        """
        matching = [
            s for s in reversed(self.all_signals)
            if s.get('symbol') == symbol and s.get('signal_type', '').upper() == signal_type.upper()
        ]

        if not matching:
            return None

        latest = matching[0]

        return {
            'symbol': symbol,
            'signal_type': signal_type,
            'entry': latest.get('entry', 0),
            'stop_loss': latest.get('stop_loss', 0),
            'targets': latest.get('targets', []),
            'status': latest.get('outcome', 'OPEN'),
            'current_price': latest.get('current_price', 0),
            'highest_target_hit': latest.get('highest_target_hit', 0),
            'generated_at': latest.get('generated_at', ''),
            'rank': latest.get('rank', 0),
            'score': latest.get('score', 0)
        }

    def should_send_update(self, new_signal: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Check if new_signal was already sent today (i.e., exists in active signals).

        Returns:
            (should_send_update, previous_signal_status or None)
            If signal exists and is still active → (True, previous_data)
            If signal is new → (False, None)
        """
        symbol = new_signal['symbol']
        signal_type = new_signal.get('signal_type', new_signal.get('strategy', 'UNKNOWN'))

        previous = self.get_signal_status(symbol, signal_type)

        if previous:
            # Signal was already sent. Check if it's still active (not closed)
            # For now, consider all previous signals as candidates for update
            return True, previous

        return False, None

    def add_signal(self, signal: Dict):
        """Add new signal to memory."""
        signal_with_meta = {
            **signal,
            'generated_at': datetime.utcnow().isoformat(),
            'signal_id': f"{signal['symbol']}_{signal.get('signal_type', 'UNK')}_{signal.get('rank', 0)}",
            'status': 'ACTIVE'
        }

        self.all_signals.append(signal_with_meta)

        # Also add to active signals dict for quick lookup
        key = f"{signal['symbol']}_{signal.get('signal_type', 'UNK')}"
        self.active_signals[key] = signal_with_meta

        self._save_json(self.all_signals_file, self.all_signals)
        self._save_json(self.active_signals_file, self.active_signals)

        logger.debug(f"Signal stored in memory: {signal['symbol']}")

    def mark_signal_resolved(self, symbol: str, signal_type: str, outcome: str, exit_price: float = None):
        """Mark a signal as resolved (no longer active)."""
        key = f"{symbol}_{signal_type}"

        if key in self.active_signals:
            signal = self.active_signals[key]
            signal['status'] = outcome
            signal['exit_price'] = exit_price
            signal['resolved_at'] = datetime.utcnow().isoformat()

            # Update in all_signals too
            for s in reversed(self.all_signals):
                if s.get('signal_id') == signal.get('signal_id'):
                    s.update(signal)
                    break

            self._save_json(self.all_signals_file, self.all_signals)
            self._save_json(self.active_signals_file, self.active_signals)
            logger.info(f"Signal marked resolved: {symbol} - {outcome}")

    def cleanup_old_signals(self, days: int = 30):
        """Remove signals older than N days from all_signals (keep active)."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        self.all_signals = [
            s for s in self.all_signals
            if datetime.fromisoformat(s.get('generated_at', '')) > cutoff
            or s.get('status') == 'ACTIVE'
        ]

        self._save_json(self.all_signals_file, self.all_signals)
        logger.info(f"Cleaned up signals older than {days} days")
