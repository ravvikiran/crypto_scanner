"""
Status Reporter for the Crypto Momentum Scanner.

Sends periodic status and summary messages via Telegram:
- Startup message with symbol count
- Daily summary at 00:00 UTC with signals, win rate, best symbol
- Idle status message if no signals for 4+ hours (rate-limited)

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger


class StatusReporter:
    """
    Sends periodic status and summary messages via Telegram.

    Independent of the signal processing pipeline — reads state from
    the scanner and journal but doesn't participate in signal processing.
    Runs on its own timer.

    Rate limiting: at most one "no setups" message per 4-hour window.
    Retry: up to 2 retries (3 total attempts) with 5-second intervals on failure.
    """

    # Rate limit window for "no setups" messages
    IDLE_WINDOW_HOURS: float = 4.0

    # Retry configuration for Telegram delivery
    MAX_RETRIES: int = 2
    RETRY_DELAY_SECONDS: float = 5.0

    def __init__(
        self,
        alert_manager,
        journal_store,
        regime_filter=None,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        """
        Initialize the StatusReporter.

        Args:
            alert_manager: MomentumAlertManager instance (used for Telegram delivery).
            journal_store: JournalStore instance (used for daily summary data).
            regime_filter: MarketRegimeFilter instance (used for BTC regime status).
            bot_token: Telegram bot token. Defaults to TELEGRAM_BOT_TOKEN env var.
            chat_id: Telegram chat ID. Defaults to TELEGRAM_CHAT_ID env var.
        """
        self._alert_manager = alert_manager
        self._journal_store = journal_store
        self._regime_filter = regime_filter

        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

        # Track when the last "no setups" message was sent for rate limiting
        self._last_idle_message_time: Optional[datetime] = None

    async def send_startup_message(self, symbol_count: int) -> None:
        """
        Send scanner started message via Telegram.

        Message format: "🟢 Scanner started — monitoring {N} symbols"

        Args:
            symbol_count: Number of symbols being monitored.

        Requirements: 7.1
        """
        message = f"🟢 Scanner started — monitoring {symbol_count} symbols"
        success = await self._send_with_retry(message)
        if success:
            logger.info(f"Startup message sent: {symbol_count} symbols")
        else:
            logger.error("Failed to send startup message after retries")

    async def send_daily_summary(self) -> None:
        """
        Send daily summary at 00:00 UTC.

        Includes: total signals emitted today, win rate %, best performing symbol.
        Uses JournalStore to gather today's data.

        Requirements: 7.2
        """
        today = datetime.utcnow()
        signals = self._journal_store.get_signals_for_date(today)

        total_signals = len(signals)

        # Calculate win rate from resolved signals
        resolved = [s for s in signals if s.get("outcome") is not None]
        wins = sum(1 for s in resolved if s.get("outcome") == "win")
        win_rate = (wins / len(resolved) * 100.0) if resolved else 0.0

        # Find best performing symbol (highest actual_rr among wins)
        best_symbol = self._find_best_symbol(signals)

        # Build summary message
        lines = [
            "📊 Daily Summary",
            f"Total signals: {total_signals}",
            f"Win rate: {win_rate:.1f}%",
            f"Best symbol: {best_symbol or 'N/A'}",
        ]
        message = "\n".join(lines)

        success = await self._send_with_retry(message)
        if success:
            logger.info(
                f"Daily summary sent: {total_signals} signals, "
                f"{win_rate:.1f}% win rate, best={best_symbol}"
            )
        else:
            logger.error("Failed to send daily summary after retries")

    async def check_idle_status(self, last_signal_time: Optional[datetime]) -> None:
        """
        Send idle status message if no signals for 4+ hours.

        Rate limited: at most one "no setups" message per 4-hour window.
        Includes BTC regime status if regime_filter is available.

        Args:
            last_signal_time: UTC timestamp of the most recent signal emitted,
                or None if no signals have been emitted.

        Requirements: 7.3, 7.4
        """
        now = datetime.utcnow()

        # Determine if we're idle (no signals for 4+ hours)
        if last_signal_time is not None:
            elapsed = now - last_signal_time
            if elapsed < timedelta(hours=self.IDLE_WINDOW_HOURS):
                # Not idle yet
                return
        # If last_signal_time is None, scanner has never emitted a signal — treat as idle

        # Rate limit: check if we already sent a "no setups" message in this window
        if self._last_idle_message_time is not None:
            since_last_idle = now - self._last_idle_message_time
            if since_last_idle < timedelta(hours=self.IDLE_WINDOW_HOURS):
                logger.debug(
                    f"Idle message rate-limited: last sent "
                    f"{since_last_idle.total_seconds() / 3600:.1f}h ago"
                )
                return

        # Build idle message with BTC regime status
        btc_status = self._get_btc_regime_status()
        message = f"✅ Scanner active. No setups found.\nBTC regime: {btc_status}"

        success = await self._send_with_retry(message)
        if success:
            self._last_idle_message_time = now
            logger.info(f"Idle status message sent. BTC regime: {btc_status}")
        else:
            logger.error("Failed to send idle status message after retries")

    def _get_btc_regime_status(self) -> str:
        """
        Get the current BTC regime status string.

        Returns a human-readable status from the regime filter,
        or "unknown" if no filter is available.
        """
        if self._regime_filter is None:
            return "unknown"

        try:
            result = self._regime_filter.last_result
            score = self._regime_filter.get_alignment_score()
            is_crashing = self._regime_filter.is_crashing(
                self._regime_filter._btc_candles_1h
            )

            if is_crashing:
                return "🔴 Crashing"
            elif result.status == "bullish":
                return f"🟢 Bullish (alignment: {score:.0f}/100)"
            elif result.status == "not_bullish":
                return f"🟡 Not bullish (alignment: {score:.0f}/100)"
            else:
                return "⚪ Indeterminate"
        except Exception as e:
            logger.warning(f"Failed to get BTC regime status: {e}")
            return "unknown"

    def _find_best_symbol(self, signals: list) -> Optional[str]:
        """
        Find the best performing symbol from today's signals.

        Best = highest actual_rr among resolved wins.
        Falls back to the symbol with the highest composite score if no wins.

        Args:
            signals: List of signal records for today.

        Returns:
            Symbol string of the best performer, or None if no signals.
        """
        if not signals:
            return None

        # Try to find best by actual RR among wins
        wins = [
            s for s in signals
            if s.get("outcome") == "win" and s.get("actual_rr") is not None
        ]
        if wins:
            best = max(wins, key=lambda s: s.get("actual_rr", 0.0))
            return best.get("symbol")

        # Fallback: highest composite score
        scored = [s for s in signals if s.get("composite_score") is not None]
        if scored:
            best = max(scored, key=lambda s: s.get("composite_score", 0.0))
            return best.get("symbol")

        # Last resort: first signal's symbol
        return signals[0].get("symbol") if signals else None

    async def _send_with_retry(self, message: str) -> bool:
        """
        Send a Telegram message with retry logic.

        Makes up to 3 total attempts (1 initial + 2 retries) with 5-second
        intervals between retries.

        Args:
            message: The message text to send.

        Returns:
            True if the message was sent successfully, False if all attempts failed.

        Requirements: 7.5
        """
        if not self._bot_token or not self._chat_id:
            logger.warning(
                "StatusReporter: Telegram credentials not configured, "
                "skipping message delivery"
            )
            return False

        # Delegate to AlertManager's retry method if available
        try:
            return await self._alert_manager._send_with_retry(
                message, self._chat_id, self._bot_token
            )
        except AttributeError:
            # Fallback: implement retry locally if AlertManager doesn't have the method
            pass

        # Local retry implementation as fallback
        import aiohttp

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        timeout = aiohttp.ClientTimeout(total=10.0)
        max_attempts = 1 + self.MAX_RETRIES  # 3 total

        for attempt in range(1, max_attempts + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as response:
                        if response.status == 200:
                            logger.debug(
                                f"Status message sent on attempt {attempt}"
                            )
                            return True
                        logger.warning(
                            f"Telegram API returned status {response.status} "
                            f"on attempt {attempt}/{max_attempts}"
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Status message attempt {attempt}/{max_attempts} failed: {e}"
                )

            # Wait before retrying (skip wait after last attempt)
            if attempt < max_attempts:
                await asyncio.sleep(self.RETRY_DELAY_SECONDS)

        logger.error(
            f"Status message delivery failed after {max_attempts} attempts"
        )
        return False
