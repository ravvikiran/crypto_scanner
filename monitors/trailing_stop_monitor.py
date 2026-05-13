"""
Trailing Stop Monitor

Tracks open positions and adjusts stop-loss based on price progression
toward targets. Uses 15-minute candle closes to update trailing stops.

Logic:
- T1 hit → move stop to entry (breakeven)
- T2 hit → begin trailing at 1% below highest close since T2
- Trailing stop never decreases
- Exit when 15m close < trailing stop or when T3 is reached

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 8.5
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from loguru import logger

from streaming.models import MonitoredPosition, OHLCV, SetupSignal, SignalDirection, SignalOutcomeType


class TrailingStopMonitor:
    """
    Tracks open positions and adjusts stop-loss based on price progression.

    Monitors 15m candle closes for each tracked position and applies
    trailing stop logic:
    - When price reaches T1: move stop to entry (breakeven)
    - When price reaches T2: trail at 1% below highest close since T2
    - Trailing stop never decreases
    - Exit when close < trailing stop or T3 reached
    """

    # Maximum time without data before logging a warning (30 minutes)
    NO_DATA_WARNING_MINUTES: int = 30

    def __init__(self, alert_manager, journal) -> None:
        """
        Initialize the TrailingStopMonitor.

        Args:
            alert_manager: MomentumAlertManager instance for sending Telegram messages.
            journal: JournalStore instance for recording outcomes.
        """
        self._alert_manager = alert_manager
        self._journal = journal
        self._positions: Dict[str, MonitoredPosition] = {}

    def start_monitoring(self, signal: SetupSignal, signal_id: str) -> None:
        """
        Begin monitoring a new position.

        Creates a MonitoredPosition from the signal and starts tracking
        price progression on 15m candle closes.

        Args:
            signal: The SetupSignal containing entry, stop, and target levels.
            signal_id: The unique journal signal ID for outcome recording.

        Requirements: 6.1
        """
        if signal.target_2 is None or signal.target_3 is None:
            logger.warning(
                f"Cannot monitor {signal.symbol}: missing T2 or T3 targets"
            )
            return

        position = MonitoredPosition(
            symbol=signal.symbol,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            current_stop=signal.stop_loss,
            target_1=signal.target_1,
            target_2=signal.target_2,
            target_3=signal.target_3,
            signal_id=signal_id,
            started_at=datetime.now(timezone.utc),
            highest_since_t2=None,
            lowest_since_t2=None,
            t1_hit=False,
            t2_hit=False,
            t3_hit=False,
            last_data_at=datetime.now(timezone.utc),
            direction=getattr(signal, 'direction', SignalDirection.LONG),
        )

        self._positions[signal.symbol] = position
        logger.info(
            f"Started monitoring {signal.symbol}: "
            f"entry={signal.entry_price:.6f}, stop={signal.stop_loss:.6f}, "
            f"T1={signal.target_1:.6f}, T2={signal.target_2:.6f}, "
            f"T3={signal.target_3:.6f}"
        )

    async def on_15m_candle(self, symbol: str, candle: OHLCV) -> None:
        """
        Process a 15m candle close for a monitored position.

        Applies trailing stop logic:
        1. Check for no-data warning (30 min gap)
        2. Check if T3 reached → exit as win
        3. Check if trailing stop hit → exit
        4. Update trailing stop levels based on T1/T2 progression

        Args:
            symbol: The trading pair symbol.
            candle: The closed 15m OHLCV candle.

        Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 8.5
        """
        if symbol not in self._positions:
            return

        position = self._positions[symbol]
        close_price = candle.close
        now = candle.timestamp

        # Check for data gap warning (Requirement 6.8)
        self._check_data_gap(position, now)

        # Update last data timestamp
        position.last_data_at = now

        # Direction-aware target and stop checks
        if position.direction == SignalDirection.SHORT:
            # SHORT: T3 hit when close <= target_3 (price going down)
            if close_price <= position.target_3:
                await self._exit_position(
                    position,
                    exit_price=close_price,
                    reason="T3 reached",
                )
                return

            # SHORT: Stop hit when close > current_stop (price going up)
            if close_price > position.current_stop:
                await self._exit_position(
                    position,
                    exit_price=close_price,
                    reason="trailing stop hit",
                )
                return
        else:
            # LONG: T3 hit when close >= target_3
            if close_price >= position.target_3:
                await self._exit_position(
                    position,
                    exit_price=close_price,
                    reason="T3 reached",
                )
                return

            # LONG: Stop hit when close < current_stop
            if close_price < position.current_stop:
                await self._exit_position(
                    position,
                    exit_price=close_price,
                    reason="trailing stop hit",
                )
                return

        # Update trailing stop levels
        await self._update_trailing_stop(position, close_price)

    def get_monitored_positions(self) -> List[MonitoredPosition]:
        """Return all currently monitored positions."""
        return list(self._positions.values())

    def _check_data_gap(self, position: MonitoredPosition, now: datetime) -> None:
        """
        Log warning if no data received for 30+ minutes.

        Requirements: 6.8
        """
        if position.last_data_at is None:
            return

        # Ensure both datetimes are comparable
        last_data = position.last_data_at
        if last_data.tzinfo is None:
            last_data = last_data.replace(tzinfo=timezone.utc)
        current = now
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        elapsed = current - last_data
        if elapsed > timedelta(minutes=self.NO_DATA_WARNING_MINUTES):
            logger.warning(
                f"No data for {position.symbol} for "
                f"{elapsed.total_seconds() / 60:.1f} minutes. "
                f"Continuing on next candle."
            )

    async def _update_trailing_stop(
        self, position: MonitoredPosition, close_price: float
    ) -> None:
        """
        Update trailing stop based on price progression.

        Logic for LONG:
        - If price >= T1 and T1 not yet hit: move stop to entry (breakeven)
        - If price >= T2 and T2 not yet hit: mark T2 hit, start tracking highest
        - If T2 hit: trail at 1% below highest close since T2

        Logic for SHORT:
        - If price <= T1 and T1 not yet hit: move stop to entry (breakeven)
        - If price <= T2 and T2 not yet hit: mark T2 hit, start tracking lowest
        - If T2 hit: trail at 1% above lowest close since T2

        The trailing stop never moves against the position.

        Requirements: 6.2, 6.3, 6.4, 6.5
        """
        old_stop = position.current_stop

        if position.direction == SignalDirection.SHORT:
            # SHORT direction trailing logic
            # Check T1 hit → move to breakeven (stop moves DOWN to entry)
            if not position.t1_hit and close_price <= position.target_1:
                position.t1_hit = True
                new_stop = position.entry_price
                if new_stop < position.current_stop:
                    position.current_stop = new_stop
                    logger.info(
                        f"{position.symbol}: T1 hit at {close_price:.6f}, "
                        f"stop moved to breakeven ({position.entry_price:.6f})"
                    )

            # Check T2 hit → begin trailing
            if not position.t2_hit and close_price <= position.target_2:
                position.t2_hit = True
                position.lowest_since_t2 = close_price
                # Calculate initial trailing stop: 1% above current close
                new_stop = close_price * 1.01
                if new_stop < position.current_stop:
                    position.current_stop = new_stop
                    logger.info(
                        f"{position.symbol}: T2 hit at {close_price:.6f}, "
                        f"trailing stop set to {new_stop:.6f}"
                    )

            # If T2 already hit, update trailing stop
            if position.t2_hit:
                # Update lowest close since T2
                if (
                    position.lowest_since_t2 is None
                    or close_price < position.lowest_since_t2
                ):
                    position.lowest_since_t2 = close_price

                # Trail at 1% above lowest close since T2
                new_stop = position.lowest_since_t2 * 1.01

                # Trailing stop never increases for shorts (moves down only)
                if new_stop < position.current_stop:
                    position.current_stop = new_stop
                    logger.debug(
                        f"{position.symbol}: trailing stop updated to "
                        f"{new_stop:.6f} (lowest={position.lowest_since_t2:.6f})"
                    )
        else:
            # LONG direction trailing logic (existing)
            # Check T1 hit → move to breakeven (Requirement 6.2)
            if not position.t1_hit and close_price >= position.target_1:
                position.t1_hit = True
                new_stop = position.entry_price
                if new_stop > position.current_stop:
                    position.current_stop = new_stop
                    logger.info(
                        f"{position.symbol}: T1 hit at {close_price:.6f}, "
                        f"stop moved to breakeven ({position.entry_price:.6f})"
                    )

            # Check T2 hit → begin trailing (Requirement 6.3)
            if not position.t2_hit and close_price >= position.target_2:
                position.t2_hit = True
                position.highest_since_t2 = close_price
                # Calculate initial trailing stop: 1% below current close
                new_stop = close_price * 0.99
                if new_stop > position.current_stop:
                    position.current_stop = new_stop
                    logger.info(
                        f"{position.symbol}: T2 hit at {close_price:.6f}, "
                        f"trailing stop set to {new_stop:.6f}"
                    )

            # If T2 already hit, update trailing stop (Requirement 6.4)
            if position.t2_hit:
                # Update highest close since T2
                if (
                    position.highest_since_t2 is None
                    or close_price > position.highest_since_t2
                ):
                    position.highest_since_t2 = close_price

                # Trail at 1% below highest close since T2
                new_stop = position.highest_since_t2 * 0.99

                # Trailing stop never decreases (Requirement 6.4)
                if new_stop > position.current_stop:
                    position.current_stop = new_stop
                    logger.debug(
                        f"{position.symbol}: trailing stop updated to "
                        f"{new_stop:.6f} (highest={position.highest_since_t2:.6f})"
                    )

        # Send Telegram notification if stop level changed (Requirement 6.5)
        if position.current_stop != old_stop:
            await self._notify_stop_change(position, old_stop)

    async def _exit_position(
        self, position: MonitoredPosition, exit_price: float, reason: str
    ) -> None:
        """
        Record position exit and update journal.

        Calculates actual risk-reward and duration, updates the journal,
        and removes the position from monitoring.

        Requirements: 6.6, 6.7, 8.5
        """
        # Calculate actual RR based on direction
        if position.direction == SignalDirection.SHORT:
            # SHORT: risk = stop_loss - entry_price, profit = entry - exit
            risk = position.stop_loss - position.entry_price
            if risk > 0:
                actual_rr = (position.entry_price - exit_price) / risk
            else:
                actual_rr = 0.0
        else:
            # LONG: risk = entry_price - stop_loss, profit = exit - entry
            risk = position.entry_price - position.stop_loss
            if risk > 0:
                actual_rr = (exit_price - position.entry_price) / risk
            else:
                actual_rr = 0.0

        # Calculate duration in minutes
        now = datetime.now(timezone.utc)
        started = position.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        duration_minutes = (now - started).total_seconds() / 60.0

        # Determine outcome
        if reason == "T3 reached":
            outcome = SignalOutcomeType.WIN
            position.t3_hit = True
        elif actual_rr >= 0:
            outcome = SignalOutcomeType.WIN
        else:
            outcome = SignalOutcomeType.LOSS

        logger.info(
            f"{position.symbol}: EXIT ({reason}) at {exit_price:.6f}, "
            f"actual RR={actual_rr:.2f}, duration={duration_minutes:.1f}min, "
            f"outcome={outcome.value}"
        )

        # Update JournalStore (Requirement 6.7)
        try:
            self._journal.record_outcome(
                signal_id=position.signal_id,
                outcome=outcome,
                actual_rr=round(actual_rr, 4),
                duration_minutes=round(duration_minutes, 2),
                exit_price=exit_price,
            )
        except Exception as e:
            logger.error(
                f"Failed to record outcome for {position.symbol}: {e}"
            )

        # Send exit notification via Telegram
        await self._notify_exit(position, exit_price, actual_rr, reason)

        # Remove from monitoring
        del self._positions[position.symbol]

    async def _notify_stop_change(
        self, position: MonitoredPosition, old_stop: float
    ) -> None:
        """
        Send Telegram message when stop level changes.

        Requirements: 6.5
        """
        message = (
            f"🔄 Stop Update: {position.symbol}\n"
            f"Old stop: {old_stop:.6f}\n"
            f"New stop: {position.current_stop:.6f}\n"
        )

        if position.t2_hit:
            message += f"Mode: Trailing (highest={position.highest_since_t2:.6f})\n"
        elif position.t1_hit:
            message += "Mode: Breakeven\n"

        await self._send_telegram(message)

    async def _notify_exit(
        self,
        position: MonitoredPosition,
        exit_price: float,
        actual_rr: float,
        reason: str,
    ) -> None:
        """Send Telegram message on position exit."""
        emoji = "✅" if actual_rr >= 0 else "❌"
        message = (
            f"{emoji} Exit: {position.symbol}\n"
            f"Reason: {reason}\n"
            f"Entry: {position.entry_price:.6f}\n"
            f"Exit: {exit_price:.6f}\n"
            f"Actual RR: {actual_rr:.2f}\n"
        )
        await self._send_telegram(message)

    async def _send_telegram(self, message: str) -> None:
        """
        Send a Telegram message via the AlertManager.

        Uses the AlertManager's retry logic for delivery.
        """
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if not bot_token or not chat_id:
            logger.debug("Telegram not configured, skipping notification")
            return

        try:
            await self._alert_manager._send_with_retry(
                message=message,
                chat_id=chat_id,
                bot_token=bot_token,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
