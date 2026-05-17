"""
State Manager for the Crypto Momentum Scanner.

Maintains per-coin stateful tracking across 4H, 1H, and 15m timeframes.
Supports up to 300 concurrent coin states with rolling candle buffers.
Provides crash recovery via JSON persistence.

Requirements: 2.2, 2.5, 20.4, 20.5
"""

import json
import logging
import os
from dataclasses import asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from streaming.models import OHLCV
from streaming.models import (
    ActiveSetup,
    CoinState,
    CompressionZone,
    PendingTrigger,
    SetupState,
    SetupType,
    SignalDirection,
    TrendStatus,
)

logger = logging.getLogger(__name__)

# Rolling candle buffer sizes per timeframe
BUFFER_SIZES: Dict[str, int] = {
    "4h": 200,
    "1h": 100,
    "15m": 50,
}

# Maximum concurrent coin states
MAX_COINS = 300

# Default persistence path
DEFAULT_STATE_PATH = "data/state/scanner_state.json"


class StateManager:
    """
    Maintains stateful tracking for each monitored coin.

    Stores CoinState objects in a dict keyed by symbol. Supports rolling
    candle buffers, trend status tracking, active setup lifecycle management,
    and crash recovery via JSON file persistence.
    """

    def __init__(self, state_file_path: Optional[str] = None, max_coins: int = MAX_COINS):
        """
        Initialize the StateManager.

        Args:
            state_file_path: Path to the JSON state file for persistence.
                             Defaults to data/state/scanner_state.json.
            max_coins: Maximum number of concurrent coin states to track.
        """
        self._states: Dict[str, CoinState] = {}
        self._max_coins = max_coins
        self._state_file_path = Path(state_file_path or DEFAULT_STATE_PATH)

    # ─── Core State Access ────────────────────────────────────────────────────

    def get_state(self, symbol: str) -> CoinState:
        """
        Get or create state for a coin.

        If the coin doesn't exist in the state dict, a new CoinState is created
        with default values. Respects the max_coins limit by rejecting new coins
        when at capacity.

        Args:
            symbol: The trading pair symbol (e.g., "BTCUSDT").

        Returns:
            The CoinState for the given symbol.

        Raises:
            ValueError: If max_coins limit is reached and symbol is new.
        """
        if symbol in self._states:
            return self._states[symbol]

        if len(self._states) >= self._max_coins:
            raise ValueError(
                f"Maximum coin state limit ({self._max_coins}) reached. "
                f"Cannot add new symbol: {symbol}"
            )

        state = CoinState(symbol=symbol)
        self._states[symbol] = state
        return state

    def get_all_states(self) -> Dict[str, CoinState]:
        """
        Return all tracked coin states.

        Returns:
            Dictionary of symbol -> CoinState for all tracked coins.
        """
        return dict(self._states)

    # ─── Candle Buffer Management ─────────────────────────────────────────────

    def update_candle(self, symbol: str, timeframe: str, candle: OHLCV) -> None:
        """
        Append a candle to the rolling buffer for a coin/timeframe.

        Maintains a fixed-size rolling buffer per timeframe:
        - 4H: 200 candles
        - 1H: 100 candles
        - 15m: 50 candles

        Args:
            symbol: The trading pair symbol.
            timeframe: The candle timeframe ("4h", "1h", "15m").
            candle: The OHLCV candle data to append.
        """
        state = self.get_state(symbol)

        if timeframe not in state.candle_buffers:
            state.candle_buffers[timeframe] = []

        buffer = state.candle_buffers[timeframe]
        buffer.append(candle)

        # Enforce rolling buffer size limit
        max_size = BUFFER_SIZES.get(timeframe, 100)
        if len(buffer) > max_size:
            state.candle_buffers[timeframe] = buffer[-max_size:]

        state.last_updated = datetime.utcnow()

    # ─── Trend Status Management ──────────────────────────────────────────────

    def set_trend_status(self, symbol: str, status: TrendStatus) -> None:
        """
        Update the trend status for a coin.

        Args:
            symbol: The trading pair symbol.
            status: The new TrendStatus value.
        """
        state = self.get_state(symbol)
        state.trend_status = status
        state.last_updated = datetime.utcnow()

    # ─── Active Setup Lifecycle ───────────────────────────────────────────────

    def add_active_setup(self, symbol: str, setup: ActiveSetup) -> None:
        """
        Set the active setup for a coin.

        Only one active setup per coin is supported. Setting a new setup
        replaces any existing one.

        Args:
            symbol: The trading pair symbol.
            setup: The ActiveSetup to track.
        """
        state = self.get_state(symbol)
        state.active_setup = setup
        state.last_updated = datetime.utcnow()

    def expire_setup(self, symbol: str, reason: str = "expired") -> Optional[ActiveSetup]:
        """
        Expire and remove the active setup for a coin.

        Marks the setup state as EXPIRED and clears it from the coin state.
        Also clears any pending trigger associated with the setup.

        Args:
            symbol: The trading pair symbol.
            reason: The reason for expiry (for logging).

        Returns:
            The expired ActiveSetup, or None if no setup was active.
        """
        state = self.get_state(symbol)
        expired_setup = state.active_setup

        if expired_setup is not None:
            expired_setup.state = SetupState.EXPIRED
            state.active_setup = None
            state.pending_trigger = None
            state.last_updated = datetime.utcnow()
            logger.info(
                f"Setup expired for {symbol}: {expired_setup.setup_type.value} - {reason}"
            )

        return expired_setup

    # ─── Persistence: Save State ──────────────────────────────────────────────

    def save_state(self) -> bool:
        """
        Persist all coin states to a JSON file for crash recovery.

        Saves to the configured state file path. Creates parent directories
        if they don't exist.

        Returns:
            True if save was successful, False otherwise.
        """
        try:
            # Ensure directory exists
            self._state_file_path.parent.mkdir(parents=True, exist_ok=True)

            serialized = self._serialize_states()

            # Write atomically using a temp file
            temp_path = self._state_file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, default=str)

            # Atomic rename (on most OS)
            temp_path.replace(self._state_file_path)

            logger.info(
                f"State saved successfully: {len(self._states)} coins "
                f"to {self._state_file_path}"
            )
            return True

        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to save state: {e}")
            return False

    # ─── Persistence: Restore State ───────────────────────────────────────────

    def restore_state(self) -> bool:
        """
        Restore coin states from the JSON persistence file on startup.

        Handles missing or corrupt files gracefully by starting with
        an empty state.

        Returns:
            True if state was restored successfully, False if starting fresh.
        """
        if not self._state_file_path.exists():
            logger.info(
                f"No state file found at {self._state_file_path}. "
                "Starting with empty state."
            )
            return False

        try:
            with open(self._state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._deserialize_states(data)
            logger.info(
                f"State restored successfully: {len(self._states)} coins "
                f"from {self._state_file_path}"
            )
            return True

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"Failed to restore state from {self._state_file_path}: {e}. "
                "Starting with empty state."
            )
            self._states = {}
            return False
        except OSError as e:
            logger.warning(
                f"Cannot read state file {self._state_file_path}: {e}. "
                "Starting with empty state."
            )
            self._states = {}
            return False

    # ─── Serialization Helpers ────────────────────────────────────────────────

    def _serialize_states(self) -> dict:
        """Serialize all coin states to a JSON-compatible dict."""
        result = {
            "version": 1,
            "saved_at": datetime.utcnow().isoformat(),
            "coin_count": len(self._states),
            "states": {},
        }

        for symbol, state in self._states.items():
            result["states"][symbol] = self._serialize_coin_state(state)

        return result

    def _serialize_coin_state(self, state: CoinState) -> dict:
        """Serialize a single CoinState to a dict."""
        data = {
            "symbol": state.symbol,
            "trend_status": state.trend_status.value,
            "last_signal_score": state.last_signal_score,
            "last_updated": state.last_updated.isoformat(),
            "candle_buffers": {},
            "active_setup": None,
            "pending_trigger": None,
        }

        # Serialize candle buffers
        for timeframe, candles in state.candle_buffers.items():
            data["candle_buffers"][timeframe] = [
                self._serialize_candle(c) for c in candles
            ]

        # Serialize active setup
        if state.active_setup is not None:
            data["active_setup"] = self._serialize_active_setup(state.active_setup)

        # Serialize pending trigger
        if state.pending_trigger is not None:
            data["pending_trigger"] = self._serialize_pending_trigger(
                state.pending_trigger
            )

        return data

    def _serialize_candle(self, candle: OHLCV) -> dict:
        """Serialize an OHLCV candle to a dict."""
        return {
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }

    def _serialize_active_setup(self, setup: ActiveSetup) -> dict:
        """Serialize an ActiveSetup to a dict."""
        data = {
            "symbol": setup.symbol,
            "setup_type": setup.setup_type.value,
            "state": setup.state.value,
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "target_1": setup.target_1,
            "target_2": setup.target_2,
            "risk_reward": setup.risk_reward,
            "timeframe": setup.timeframe,
            "trigger_timeframe": setup.trigger_timeframe,
            "direction": setup.direction.value if setup.direction else None,
            "detected_at": setup.detected_at.isoformat(),
            "confirmed_at": (
                setup.confirmed_at.isoformat() if setup.confirmed_at else None
            ),
        }

        # Serialize compression zone if present
        if setup.compression_zone is not None:
            data["compression_zone"] = {
                "high": setup.compression_zone.high,
                "low": setup.compression_zone.low,
                "candle_count": setup.compression_zone.candle_count,
                "start_atr14": setup.compression_zone.start_atr14,
                "created_at": setup.compression_zone.created_at.isoformat(),
                "expired": setup.compression_zone.expired,
            }
        else:
            data["compression_zone"] = None

        return data

    def _serialize_pending_trigger(self, trigger: PendingTrigger) -> dict:
        """Serialize a PendingTrigger to a dict."""
        return {
            "symbol": trigger.symbol,
            "setup_type": trigger.setup_type.value,
            "entry_price": trigger.entry_price,
            "stop_loss": trigger.stop_loss,
            "target_1": trigger.target_1,
            "target_2": trigger.target_2,
            "candles_remaining": trigger.candles_remaining,
            "created_at": trigger.created_at.isoformat(),
        }

    # ─── Deserialization Helpers ──────────────────────────────────────────────

    def _deserialize_states(self, data: dict) -> None:
        """Deserialize all coin states from a JSON dict."""
        self._states = {}
        states_data = data.get("states", {})

        for symbol, state_data in states_data.items():
            try:
                coin_state = self._deserialize_coin_state(state_data)
                self._states[symbol] = coin_state
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(
                    f"Skipping corrupt state for {symbol}: {e}"
                )
                continue

    def _deserialize_coin_state(self, data: dict) -> CoinState:
        """Deserialize a single CoinState from a dict."""
        state = CoinState(
            symbol=data["symbol"],
            trend_status=TrendStatus(data["trend_status"]),
            last_signal_score=data.get("last_signal_score", 0.0),
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )

        # Deserialize candle buffers
        for timeframe, candles_data in data.get("candle_buffers", {}).items():
            state.candle_buffers[timeframe] = [
                self._deserialize_candle(c) for c in candles_data
            ]

        # Deserialize active setup
        if data.get("active_setup") is not None:
            state.active_setup = self._deserialize_active_setup(data["active_setup"])

        # Deserialize pending trigger
        if data.get("pending_trigger") is not None:
            state.pending_trigger = self._deserialize_pending_trigger(
                data["pending_trigger"]
            )

        return state

    def _deserialize_candle(self, data: dict) -> OHLCV:
        """Deserialize an OHLCV candle from a dict."""
        return OHLCV(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
        )

    def _deserialize_active_setup(self, data: dict) -> ActiveSetup:
        """Deserialize an ActiveSetup from a dict."""
        _dir_raw = data.get("direction")
        _direction = (
            SignalDirection(_dir_raw) if _dir_raw else None
        )

        setup = ActiveSetup(
            symbol=data["symbol"],
            setup_type=SetupType(data["setup_type"]),
            state=SetupState(data["state"]),
            entry_price=float(data["entry_price"]),
            stop_loss=float(data["stop_loss"]),
            target_1=float(data["target_1"]),
            target_2=float(data["target_2"]) if data.get("target_2") else None,
            risk_reward=float(data["risk_reward"]),
            direction=_direction,
            timeframe=data.get("timeframe", "1h"),
            trigger_timeframe=data.get("trigger_timeframe", "15m"),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            confirmed_at=(
                datetime.fromisoformat(data["confirmed_at"])
                if data.get("confirmed_at")
                else None
            ),
        )

        # Deserialize compression zone if present
        if data.get("compression_zone") is not None:
            zone_data = data["compression_zone"]
            setup.compression_zone = CompressionZone(
                high=float(zone_data["high"]),
                low=float(zone_data["low"]),
                candle_count=int(zone_data["candle_count"]),
                start_atr14=float(zone_data["start_atr14"]),
                created_at=datetime.fromisoformat(zone_data["created_at"]),
                expired=zone_data.get("expired", False),
            )

        return setup

    def _deserialize_pending_trigger(self, data: dict) -> PendingTrigger:
        """Deserialize a PendingTrigger from a dict."""
        return PendingTrigger(
            symbol=data["symbol"],
            setup_type=SetupType(data["setup_type"]),
            entry_price=float(data["entry_price"]),
            stop_loss=float(data["stop_loss"]),
            target_1=float(data["target_1"]),
            target_2=float(data["target_2"]) if data.get("target_2") else None,
            candles_remaining=int(data["candles_remaining"]),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
