"""
Event Bus for the Crypto Momentum Scanner.

Provides an async event dispatcher that maintains per-coin+timeframe
latest-event semantics, discarding stale intermediate events when a
newer event arrives for the same key.

Requirements: 2.1, 2.4, 2.7, 20.7
"""

import asyncio
import logging
from typing import AsyncIterator, Dict, Optional, Tuple

from streaming.models import CandleCloseEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Async event dispatcher with per-coin+timeframe deduplication.

    Maintains an asyncio.Queue for event flow and a dictionary keyed by
    (symbol, timeframe) to track the latest event for each key. When a
    new event arrives for an existing key, the stale event is replaced
    so consumers always process the most recent data.

    When the queue is full (backpressure), the oldest event is dropped
    to make room for the incoming event.
    """

    def __init__(self, max_size: int = 10000) -> None:
        """Initialize the EventBus.

        Args:
            max_size: Maximum number of events the queue can hold.
                      Defaults to 10000.
        """
        self._max_size = max_size
        self._queue: asyncio.Queue[CandleCloseEvent] = asyncio.Queue(
            maxsize=max_size
        )
        # Tracks the latest event per (symbol, timeframe) key
        self._latest_events: Dict[Tuple[str, str], CandleCloseEvent] = {}
        self._dropped_count: int = 0
        self._total_emitted: int = 0
        self._stopped: bool = False

    async def emit(self, event: CandleCloseEvent) -> None:
        """Emit a candle close event to the bus.

        Implements per-coin+timeframe latest-event semantics: if an event
        already exists in the tracking dict for the same (symbol, timeframe)
        key, it is replaced with the newer event. Only the latest event
        per key will be yielded by consume().

        When the queue is full, the oldest event is dropped to handle
        backpressure.

        Args:
            event: The CandleCloseEvent to emit.
        """
        key = (event.symbol, event.timeframe)

        # Update the latest event for this key (replaces stale)
        self._latest_events[key] = event

        # Handle backpressure: if queue is full, drop the oldest event
        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()
                self._dropped_count += 1
                logger.warning(
                    "EventBus backpressure: dropped stale event for %s/%s "
                    "(queue full at %d)",
                    dropped.symbol,
                    dropped.timeframe,
                    self._max_size,
                )
            except asyncio.QueueEmpty:
                pass

        # Put the new event on the queue
        try:
            self._queue.put_nowait(event)
            self._total_emitted += 1
        except asyncio.QueueFull:
            # Should not happen after dropping, but handle defensively
            self._dropped_count += 1
            logger.error(
                "EventBus: failed to enqueue event for %s/%s after drop",
                event.symbol,
                event.timeframe,
            )

    async def consume(self) -> AsyncIterator[CandleCloseEvent]:
        """Async iterator that yields the most recent event per coin+timeframe.

        When an event is dequeued, this method checks the latest_events dict
        to ensure only the most recent event for each key is yielded. If the
        dequeued event is stale (a newer one exists for the same key), it is
        silently discarded.

        Yields:
            The most recent CandleCloseEvent for each (symbol, timeframe) key.
        """
        while not self._stopped:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            key = (event.symbol, event.timeframe)

            # Only yield if this event is still the latest for its key
            latest = self._latest_events.get(key)
            if latest is not None and latest is not event:
                # A newer event has replaced this one; discard stale
                continue

            # Clear the tracking entry since we're yielding it
            self._latest_events.pop(key, None)
            yield event

    def get_queue_depth(self) -> int:
        """Return the current number of events in the queue.

        Returns:
            Current queue size for monitoring purposes.
        """
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        """Total number of events dropped due to backpressure."""
        return self._dropped_count

    @property
    def total_emitted(self) -> int:
        """Total number of events successfully emitted."""
        return self._total_emitted

    @property
    def max_size(self) -> int:
        """Maximum queue capacity."""
        return self._max_size

    def stop(self) -> None:
        """Signal the consume loop to stop."""
        self._stopped = True

    def reset(self) -> None:
        """Reset the event bus state. Useful for testing."""
        self._latest_events.clear()
        self._dropped_count = 0
        self._total_emitted = 0
        self._stopped = False
        # Drain the queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
