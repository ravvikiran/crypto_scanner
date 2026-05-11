"""
Momentum Alert Manager

Stateful alert deduplication with cooldown enforcement, volume-based override,
score threshold override, and cache invalidation logic.

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6
"""

import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
from loguru import logger

from streaming.models import AlertCacheEntry, OIFundingData, ScoredSetup, SetupType


class MomentumAlertManager:
    """
    Manages alert deduplication for the momentum scanner pipeline.

    Maintains a state cache keyed by symbol+setup_type with LRU eviction
    at max capacity. Enforces configurable cooldown with volume and score
    threshold overrides.
    """

    # Score threshold for the score-crossing override (Requirement 15.4)
    SCORE_THRESHOLD: float = 80.0

    def __init__(
        self,
        cooldown_hours: float = 4.0,
        max_entries: int = 500,
    ) -> None:
        """
        Initialize the MomentumAlertManager.

        Args:
            cooldown_hours: Hours between duplicate alerts for same symbol+setup_type.
                            Must be between 1.0 and 48.0. Defaults to 4.0.
            max_entries: Maximum cache entries before LRU eviction. Defaults to 500.
        """
        # Clamp cooldown to valid range (Requirement 15.2)
        self._cooldown_hours = max(1.0, min(48.0, cooldown_hours))
        self._max_entries = max_entries

        # OrderedDict for LRU eviction - most recently accessed at end
        self._cache: OrderedDict[str, AlertCacheEntry] = OrderedDict()

        logger.info(
            f"MomentumAlertManager initialized: cooldown={self._cooldown_hours}h, "
            f"max_entries={self._max_entries}"
        )

    @property
    def cooldown_hours(self) -> float:
        """Current cooldown period in hours."""
        return self._cooldown_hours

    @property
    def cache_size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._cache)

    def _make_key(self, symbol: str, setup_type: SetupType) -> str:
        """Generate cache key from symbol and setup type."""
        return f"{symbol}_{setup_type.value}"

    def should_send(
        self,
        symbol: str,
        setup_type: SetupType,
        current_rvol: float,
        current_score: float,
        trend_score: float,
        stop_loss_breached: bool = False,
    ) -> bool:
        """
        Determine whether an alert should be sent for the given setup.

        Checks cooldown, volume override, score threshold override, and
        cache invalidation conditions.

        Args:
            symbol: The coin symbol (e.g., "BTCUSDT").
            setup_type: The type of setup detected.
            current_rvol: Current relative volume ratio.
            current_score: Current composite score (0-100).
            trend_score: Current trend score component (0-100).
            stop_loss_breached: Whether the stop-loss has been breached.

        Returns:
            True if the alert should be sent, False otherwise.
        """
        key = self._make_key(symbol, setup_type)

        # Cache invalidation: remove entry on stop-loss breach or trend < 40
        # (Requirement 15.5)
        if stop_loss_breached or trend_score < 40:
            self._invalidate(key)
            # After invalidation, this is treated as a fresh alert
            return True

        # If no previous alert exists, allow sending
        if key not in self._cache:
            return True

        entry = self._cache[key]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        elapsed = now - entry.sent_at
        cooldown_delta = timedelta(hours=self._cooldown_hours)

        # If cooldown has expired, allow sending
        if elapsed >= cooldown_delta:
            return True

        # Volume override: send if current RVOL exceeds previous by 50+ pp
        # (Requirement 15.3)
        rvol_diff = current_rvol - entry.volume_ratio_at_send
        if rvol_diff >= 50.0:
            logger.debug(
                f"Volume override for {key}: current_rvol={current_rvol:.1f}, "
                f"previous={entry.volume_ratio_at_send:.1f}, diff={rvol_diff:.1f}pp"
            )
            return True

        # Score threshold override: send when score crosses 80.0 threshold
        # (Requirement 15.4)
        if entry.score_at_send < self.SCORE_THRESHOLD <= current_score:
            logger.debug(
                f"Score threshold override for {key}: "
                f"previous_score={entry.score_at_send:.2f}, "
                f"current_score={current_score:.2f}"
            )
            return True

        # Still in cooldown, no override conditions met
        return False

    def mark_sent(
        self,
        symbol: str,
        setup_type: SetupType,
        volume_ratio: float,
        score: float,
    ) -> None:
        """
        Record that an alert was sent, updating the cache.

        Args:
            symbol: The coin symbol.
            setup_type: The type of setup.
            volume_ratio: The RVOL at the time of sending.
            score: The composite score at the time of sending.
        """
        key = self._make_key(symbol, setup_type)

        entry = AlertCacheEntry(
            symbol=symbol,
            setup_type=setup_type,
            sent_at=datetime.now(timezone.utc).replace(tzinfo=None),
            volume_ratio_at_send=volume_ratio,
            score_at_send=score,
        )

        # If key exists, move to end (most recent); otherwise add
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = entry

        # LRU eviction if over capacity (Requirement 15.1 - max 500 entries)
        while len(self._cache) > self._max_entries:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Cache evicted LRU entry: {evicted_key}")

    def invalidate(self, symbol: str, setup_type: SetupType) -> None:
        """
        Remove a cache entry when setup is invalidated.

        Called externally when stop-loss is breached or trend score drops
        below 40. (Requirement 15.5)

        Args:
            symbol: The coin symbol.
            setup_type: The type of setup.
        """
        key = self._make_key(symbol, setup_type)
        self._invalidate(key)

    def _invalidate(self, key: str) -> None:
        """Remove a cache entry by key if it exists."""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache entry invalidated: {key}")

    def reset_cache(self) -> None:
        """
        Initialize an empty cache.

        Used on corrupt state detection at startup. (Requirement 15.6)
        """
        self._cache.clear()
        logger.warning("Alert cache was reset (empty cache initialized)")

    def get_entry(self, symbol: str, setup_type: SetupType) -> Optional[AlertCacheEntry]:
        """
        Get the cache entry for a symbol+setup_type if it exists.

        Args:
            symbol: The coin symbol.
            setup_type: The type of setup.

        Returns:
            The AlertCacheEntry if found, None otherwise.
        """
        key = self._make_key(symbol, setup_type)
        return self._cache.get(key)

    async def _send_with_retry(
        self, message: str, chat_id: str, bot_token: str
    ) -> bool:
        """
        Send a Telegram message with retry logic.

        Makes up to 3 total attempts (1 initial + 2 retries) with 5-second
        intervals between retries. Each attempt has a 10-second HTTP timeout.

        Args:
            message: The formatted message text to send.
            chat_id: The Telegram chat ID to send to.
            bot_token: The Telegram bot API token.

        Returns:
            True if the message was sent successfully, False if all attempts failed.

        Requirements: 16.6
        """
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        timeout = aiohttp.ClientTimeout(total=10.0)
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as response:
                        if response.status == 200:
                            logger.debug(
                                f"Telegram message sent successfully on attempt {attempt}"
                            )
                            return True
                        logger.warning(
                            f"Telegram API returned status {response.status} "
                            f"on attempt {attempt}/{max_attempts}"
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Telegram send attempt {attempt}/{max_attempts} failed: {e}"
                )

            # Wait before retrying (skip wait after last attempt)
            if attempt < max_attempts:
                await asyncio.sleep(5.0)

        logger.error(
            f"Telegram delivery failed after {max_attempts} attempts. "
            f"chat_id={chat_id}, message_length={len(message)}"
        )
        return False

    def _format_telegram_message(
        self,
        scored_setup: ScoredSetup,
        risk_levels: dict,
        oi_data: OIFundingData,
        trend_score: float,
    ) -> str:
        """
        Format a Telegram alert message with labeled sections.

        Produces a structured message with Signal, Entry/Exit, Market Context,
        Scoring, and Exit Strategy sections. Enforces 4096 character limit.
        Displays "N/A" for unavailable fields.

        Requirements: 16.1, 16.2, 16.3, 16.5, 16.7, 16.8, 10.3, 10.4

        Args:
            scored_setup: The scored setup containing signal, composite score, and inputs.
            risk_levels: Dict with keys: entry, stop_loss, risk_pct, target_1, target_2.
            oi_data: Open interest and funding rate data.
            trend_score: The trend score component (0-100).

        Returns:
            Formatted Telegram message string, truncated to 4096 chars if needed.
        """
        MAX_CHARS = 4096

        signal = scored_setup.signal
        symbol = signal.symbol
        setup_type_display = signal.setup_type.value.replace("_", " ").title()

        # Directional emoji - currently only LONG setups supported
        direction_emoji = "\U0001f7e2"  # 🟢
        direction_label = "LONG"

        # Extract risk levels with N/A fallback
        entry = risk_levels.get("entry")
        stop_loss = risk_levels.get("stop_loss")
        risk_pct = risk_levels.get("risk_pct")
        target_1 = risk_levels.get("target_1")
        target_2 = risk_levels.get("target_2")

        # Format numeric values with appropriate precision
        def _fmt_price(val: Optional[float]) -> str:
            if val is None:
                return "N/A"
            # Use 2 decimals for large prices, up to 6 for small ones
            if val >= 100:
                return f"{val:.2f}"
            elif val >= 1:
                return f"{val:.4f}"
            else:
                return f"{val:.6f}"

        def _fmt_pct(val: Optional[float]) -> str:
            if val is None:
                return "N/A"
            return f"{val:.2f}%"

        def _fmt_score(val: Optional[float]) -> str:
            if val is None:
                return "N/A"
            return f"{val:.2f}"

        # Market context fields with N/A for unavailable data
        rs_display = _fmt_score(scored_setup.inputs.relative_strength) if scored_setup.inputs else "N/A"
        rvol_display = _fmt_score(scored_setup.inputs.relative_volume) if scored_setup.inputs else "N/A"

        if oi_data and oi_data.data_available:
            oi_change_display = _fmt_pct(oi_data.oi_change_4h_pct)
            funding_display = f"{oi_data.funding_rate:.4f}%" if oi_data.funding_rate is not None else "N/A"
        else:
            oi_change_display = "N/A"
            funding_display = "N/A"

        # UTC timestamp in ISO-8601
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build message sections
        lines = []

        # ── Signal Section ──
        lines.append(f"{direction_emoji} {direction_label} SIGNAL")
        lines.append(f"Symbol: {symbol}")
        lines.append(f"Setup: {setup_type_display}")
        lines.append("")

        # Extract T3 from signal (5R target)
        target_3 = signal.target_3

        # ── Entry/Exit Section ──
        lines.append("\U0001f4cd Entry/Exit")
        lines.append(f"Entry: {_fmt_price(entry)}")
        lines.append(f"Stop-Loss: {_fmt_price(stop_loss)}")
        lines.append(f"Risk: {_fmt_pct(risk_pct)}")
        lines.append(f"Target1 (1R): {_fmt_price(target_1)}")
        lines.append(f"Target2 (2R): {_fmt_price(target_2)}")
        lines.append(f"Target3 (5R): {_fmt_price(target_3)}")
        lines.append("")

        # ── Market Context Section ──
        lines.append("\U0001f30d Market Context")
        lines.append(f"RS vs BTC: {rs_display}")
        lines.append(f"RVOL: {rvol_display}")
        lines.append(f"OI Change (4H): {oi_change_display}")
        lines.append(f"Funding Rate: {funding_display}")
        lines.append("")

        # ── Scoring Section ──
        lines.append("\U0001f4ca Scoring")
        lines.append(f"Trend Score: {_fmt_score(trend_score)}")
        lines.append(f"Composite Score: {_fmt_score(scored_setup.composite_score)}")
        lines.append("")

        # ── Exit Strategy Section ──
        lines.append("\U0001f6aa Exit Strategy")
        lines.append("Take 40% at T1, 40% at T2, let 20% run to T3")
        lines.append("")

        # ── Timestamp ──
        lines.append(f"\U0001f552 {timestamp}")

        message = "\n".join(lines)

        # Enforce 4096 character limit (Requirement 16.8)
        if len(message) > MAX_CHARS:
            message = message[: MAX_CHARS - 3] + "..."

        return message
