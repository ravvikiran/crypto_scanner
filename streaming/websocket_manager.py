"""
WebSocket Manager for the Crypto Momentum Scanner.

Provides the ExchangeConnection class for managing individual exchange
websocket connections with automatic reconnection and drop detection.

Requirements:
    1.1 - Binance websocket connection within 10 seconds
    1.5 - Reconnection with exponential backoff (initial 1s, max 5 attempts)
    1.8 - Connection timeout handling on startup
    1.9 - Emit ConnectionFailureEvent when all attempts exhausted
    20.3 - Exchange failover support
"""

import asyncio
import logging
import time
from typing import Callable, Optional, Awaitable

import websockets
from websockets.client import WebSocketClientProtocol

from streaming.models import ConnectionFailureEvent, WebSocketConfig

logger = logging.getLogger(__name__)


class ExchangeConnection:
    """Manages a single websocket connection to a crypto exchange.

    Handles connection establishment with configurable timeout, graceful
    disconnection, automatic reconnection with exponential backoff, and
    connection drop detection via message timeout.

    Requirements:
        1.1 - Connect within 10 seconds (configurable timeout)
        1.5 - Exponential backoff reconnection (initial 1s, max 5 attempts)
        1.8 - Log error on connection failure, retry with backoff
        1.9 - Emit ConnectionFailureEvent when all attempts exhausted
    """

    def __init__(
        self,
        config: WebSocketConfig,
        on_message: Optional[Callable[[dict], Awaitable[None]]] = None,
        on_failure: Optional[Callable[[ConnectionFailureEvent], Awaitable[None]]] = None,
        on_reconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """Initialize ExchangeConnection.

        Args:
            config: WebSocket configuration for this exchange connection.
            on_message: Async callback invoked with each received message.
            on_failure: Async callback invoked when all reconnection attempts
                        are exhausted (emits ConnectionFailureEvent).
            on_reconnect: Async callback invoked after successful reconnection
                          to re-subscribe to streams.
        """
        self._config = config
        self._on_message = on_message
        self._on_failure = on_failure
        self._on_reconnect = on_reconnect

        self._ws: Optional[WebSocketClientProtocol] = None
        self._connected: bool = False
        self._running: bool = False
        self._reconnect_attempts: int = 0
        self._last_message_time: float = 0.0
        self._listen_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None

        # Drop detection: if no message received within this many seconds,
        # consider the connection dropped. Default to 3x the stale threshold
        # or 30 seconds if not configured.
        self._message_timeout: float = 120.0

    @property
    def is_connected(self) -> bool:
        """Whether the websocket connection is currently active."""
        if not self._connected or self._ws is None:
            return False
        # Support both old websockets (<13: .open) and new (>=13: .state)
        try:
            return self._ws.open
        except AttributeError:
            # websockets v13+: check state instead
            try:
                from websockets.protocol import State
                return self._ws.state == State.OPEN
            except (ImportError, AttributeError):
                # Fallback: if we have a ws object and _connected is True, assume open
                return True

    @property
    def exchange(self) -> str:
        """The exchange name for this connection."""
        return self._config.exchange

    async def connect(self) -> bool:
        """Establish websocket connection with configurable timeout.

        Attempts to connect to the exchange websocket URL within the
        configured timeout (default 10 seconds). On success, starts
        the message listener and drop monitor tasks.

        Returns:
            True if connection was established successfully, False otherwise.

        Requirements:
            1.1 - Connection within 10 seconds
            1.8 - Log error on failure
        """
        timeout = self._config.connection_timeout
        try:
            logger.info(
                "Connecting to %s at %s (timeout: %.1fs)",
                self._config.exchange,
                self._config.url,
                timeout,
            )
            self._ws = await asyncio.wait_for(
                websockets.connect(self._config.url),
                timeout=timeout,
            )
            self._connected = True
            self._running = True
            self._reconnect_attempts = 0
            self._last_message_time = time.monotonic()

            # Start background tasks for listening and drop monitoring
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._monitor_task = asyncio.create_task(self._monitor_connection())

            logger.info(
                "Successfully connected to %s", self._config.exchange
            )
            return True

        except asyncio.TimeoutError:
            logger.error(
                "Connection to %s timed out after %.1f seconds",
                self._config.exchange,
                timeout,
            )
            self._connected = False
            return False

        except Exception as e:
            logger.error(
                "Failed to connect to %s: %s", self._config.exchange, str(e)
            )
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Gracefully shut down the websocket connection.

        Cancels background tasks and closes the websocket connection.
        Safe to call multiple times.
        """
        self._running = False
        self._connected = False

        # Cancel background tasks
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        # Close websocket
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(
                    "Error closing websocket for %s: %s",
                    self._config.exchange,
                    str(e),
                )
            self._ws = None

        logger.info("Disconnected from %s", self._config.exchange)

    async def _reconnect_with_backoff(self) -> bool:
        """Attempt reconnection with exponential backoff.

        Uses exponential backoff starting at the configured initial delay
        (default 1 second), doubling each attempt, up to the configured
        maximum number of attempts (default 5).

        Returns:
            True if reconnection succeeded, False if all attempts exhausted.

        Requirements:
            1.5 - Exponential backoff (initial 1s, max 5 attempts)
            1.9 - Emit ConnectionFailureEvent when exhausted
        """
        max_attempts = self._config.max_reconnect_attempts
        initial_delay = self._config.initial_reconnect_delay

        self._connected = False

        for attempt in range(1, max_attempts + 1):
            self._reconnect_attempts = attempt
            delay = initial_delay * (2 ** (attempt - 1))

            logger.info(
                "Reconnecting to %s (attempt %d/%d, delay: %.1fs)",
                self._config.exchange,
                attempt,
                max_attempts,
                delay,
            )

            await asyncio.sleep(delay)

            if not self._running:
                # Shutdown was requested during backoff
                return False

            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(self._config.url),
                    timeout=self._config.connection_timeout,
                )
                self._connected = True
                self._last_message_time = time.monotonic()
                logger.info(
                    "Reconnected to %s on attempt %d",
                    self._config.exchange,
                    attempt,
                )
                # Re-subscribe to streams after reconnection
                if self._on_reconnect:
                    try:
                        await self._on_reconnect()
                    except Exception as re_err:
                        logger.warning(
                            "Re-subscribe after reconnect failed for %s: %s",
                            self._config.exchange,
                            str(re_err),
                        )
                return True

            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(
                    "Reconnection attempt %d/%d to %s failed: %s",
                    attempt,
                    max_attempts,
                    self._config.exchange,
                    str(e),
                )

        # All attempts exhausted — emit failure event
        logger.error(
            "All %d reconnection attempts to %s exhausted",
            max_attempts,
            self._config.exchange,
        )
        await self._emit_failure_event(
            reason=f"All {max_attempts} reconnection attempts exhausted"
        )
        return False

    async def _listen_loop(self) -> None:
        """Background task that listens for incoming websocket messages.

        Processes messages and triggers reconnection on connection drops.
        """
        while self._running:
            try:
                if self._ws is None or not self.is_connected:
                    # Connection lost, attempt reconnection
                    success = await self._reconnect_with_backoff()
                    if not success:
                        self._running = False
                        return
                    continue

                message = await self._ws.recv()
                self._last_message_time = time.monotonic()

                if self._on_message is not None:
                    # Parse JSON if string, pass raw dict if already parsed
                    import json

                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Received malformed JSON from %s",
                                self._config.exchange,
                            )
                            continue
                    else:
                        data = message

                    await self._on_message(data)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(
                    "Connection to %s closed: code=%s reason=%s",
                    self._config.exchange,
                    e.code,
                    e.reason,
                )
                self._connected = False
                if self._running:
                    success = await self._reconnect_with_backoff()
                    if not success:
                        self._running = False
                        return

            except asyncio.CancelledError:
                return

            except Exception as e:
                logger.error(
                    "Unexpected error in listen loop for %s: %s",
                    self._config.exchange,
                    str(e),
                )
                self._connected = False
                if self._running:
                    success = await self._reconnect_with_backoff()
                    if not success:
                        self._running = False
                        return

    async def _monitor_connection(self) -> None:
        """Background task that detects connection drops via message timeout.

        If no message is received within the configured timeout period,
        the connection is considered dropped and reconnection is triggered.
        """
        while self._running:
            try:
                await asyncio.sleep(5.0)  # Check every 5 seconds

                if not self._running or not self._connected:
                    continue

                elapsed = time.monotonic() - self._last_message_time
                if elapsed > self._message_timeout:
                    logger.warning(
                        "No message from %s for %.1fs, connection may be dropped",
                        self._config.exchange,
                        elapsed,
                    )
                    # Close the stale connection to trigger reconnection in listen loop
                    if self._ws is not None and self.is_connected:
                        await self._ws.close()
                    self._connected = False

            except asyncio.CancelledError:
                return

            except Exception as e:
                logger.debug(
                    "Monitor error for %s: %s", self._config.exchange, str(e)
                )

    async def _emit_failure_event(self, reason: str) -> None:
        """Emit a ConnectionFailureEvent when all reconnection attempts fail.

        Args:
            reason: Description of why the connection failed.

        Requirements:
            1.9 - Emit ConnectionFailureEvent when exhausted
        """
        event = ConnectionFailureEvent(
            exchange=self._config.exchange,
            reason=reason,
            attempts_made=self._reconnect_attempts,
        )

        if self._on_failure is not None:
            try:
                await self._on_failure(event)
            except Exception as e:
                logger.error(
                    "Error in failure callback for %s: %s",
                    self._config.exchange,
                    str(e),
                )

        logger.error(
            "ConnectionFailureEvent emitted for %s: %s",
            self._config.exchange,
            reason,
        )


# ─── WebSocket Manager ────────────────────────────────────────────────────────


import json
from datetime import datetime, timezone
from typing import Dict, List

from config.websocket_config import WebSocketStreamConfig
from streaming.event_bus import EventBus
from streaming.models import CandleCloseEvent, WebSocketConfig

from streaming.models import OHLCV


class WebSocketManager:
    """Orchestrates websocket connections to multiple crypto exchanges.

    Manages ExchangeConnection instances for each enabled exchange,
    subscribes to kline streams for configured symbols and timeframes,
    parses exchange-specific message formats, validates data integrity,
    and emits CandleCloseEvent instances to the EventBus.

    Supported exchanges:
        - Binance (primary): kline stream format
        - Bybit (secondary): kline topic format
        - OKX (tertiary): candle channel format

    Requirements:
        1.1 - Binance websocket connection within 10 seconds
        1.2 - Secondary Bybit websocket connection
        1.3 - Tertiary OKX websocket connection
        1.4 - Validate live OHLCV data, discard zero volume/malformed
        1.6 - Stream data for 4H, 1H, and 15m timeframes
        1.7 - Emit event to downstream within 50ms
        20.3 - Exchange failover support
        20.6 - Graceful shutdown
    """

    # Timeframe mappings per exchange for subscription messages
    _BINANCE_TIMEFRAME_MAP: Dict[str, str] = {
        "4h": "4h",
        "1h": "1h",
        "15m": "15m",
    }

    _BYBIT_TIMEFRAME_MAP: Dict[str, str] = {
        "4h": "240",
        "1h": "60",
        "15m": "15",
    }

    _OKX_TIMEFRAME_MAP: Dict[str, str] = {
        "4h": "4H",
        "1h": "1H",
        "15m": "15m",
    }

    # Reverse maps for parsing incoming messages back to canonical timeframes
    _BINANCE_INTERVAL_TO_TF: Dict[str, str] = {
        "4h": "4h",
        "1h": "1h",
        "15m": "15m",
    }

    _BYBIT_INTERVAL_TO_TF: Dict[str, str] = {
        "240": "4h",
        "60": "1h",
        "15": "15m",
    }

    _OKX_CHANNEL_TO_TF: Dict[str, str] = {
        "candle4H": "4h",
        "candle1H": "1h",
        "candle15m": "15m",
    }

    def __init__(
        self,
        config: WebSocketStreamConfig,
        event_bus: EventBus,
        symbols: Optional[List[str]] = None,
    ) -> None:
        """Initialize WebSocketManager.

        Args:
            config: WebSocket streaming configuration with exchange URLs,
                    enable flags, and reconnect settings.
            event_bus: The EventBus instance to emit CandleCloseEvent to.
            symbols: List of trading symbols to subscribe to. If None,
                     defaults to an empty list (symbols should be set
                     before calling start()).
        """
        self._config = config
        self._event_bus = event_bus
        self._symbols = symbols or []
        self._connections: Dict[str, ExchangeConnection] = {}
        self._running: bool = False
        self._external_failure_callback: Optional[
            Callable[[ConnectionFailureEvent], Awaitable[None]]
        ] = None

    def set_failure_callback(
        self,
        callback: Callable[[ConnectionFailureEvent], Awaitable[None]],
    ) -> None:
        """Register an external callback for connection failure events.

        The MomentumScanner uses this to receive failure notifications
        and trigger exchange failover logic.

        Args:
            callback: Async callable that receives a ConnectionFailureEvent
                      when all reconnection attempts for an exchange are
                      exhausted.
        """
        self._external_failure_callback = callback

    @property
    def is_running(self) -> bool:
        """Whether the manager is currently running."""
        return self._running

    @property
    def connections(self) -> Dict[str, ExchangeConnection]:
        """Active exchange connections keyed by exchange name."""
        return self._connections

    @property
    def connected_exchanges(self) -> List[str]:
        """List of exchange names that are currently connected."""
        return [
            name
            for name, conn in self._connections.items()
            if conn.is_connected
        ]

    async def start(self) -> None:
        """Establish connections to all configured/enabled exchanges.

        Creates ExchangeConnection instances for each enabled exchange,
        connects them, and subscribes to kline streams for all configured
        symbols and timeframes.

        Requirements:
            1.1 - Binance connection within 10 seconds
            1.2 - Bybit secondary connection
            1.3 - OKX tertiary connection
        """
        if self._running:
            logger.warning("WebSocketManager is already running")
            return

        self._running = True
        logger.info(
            "Starting WebSocketManager for exchanges: %s, symbols: %d, timeframes: %s",
            self._config.enabled_exchanges,
            len(self._symbols),
            self._config.timeframes,
        )

        for exchange in self._config.enabled_exchanges:
            ws_config = WebSocketConfig(
                exchange=exchange,
                url=self._config.get_exchange_url(exchange),
                symbols=self._symbols,
                timeframes=self._config.timeframes,
                max_reconnect_attempts=self._config.reconnect_max_attempts,
                initial_reconnect_delay=self._config.reconnect_initial_delay,
                connection_timeout=self._config.connection_timeout,
            )

            connection = ExchangeConnection(
                config=ws_config,
                on_message=self._make_message_handler(exchange),
                on_failure=self._handle_connection_failure,
                on_reconnect=self._make_resubscribe_handler(exchange),
            )

            self._connections[exchange] = connection

            success = await connection.connect()
            if success:
                logger.info("Connected to %s, subscribing to streams", exchange)
                await self._subscribe_streams(exchange)
            else:
                logger.error(
                    "Failed to connect to %s on startup", exchange
                )

    async def stop(self) -> None:
        """Gracefully shut down all exchange connections.

        Disconnects all active connections and clears internal state.

        Requirements:
            20.6 - Graceful shutdown
        """
        if not self._running:
            return

        self._running = False
        logger.info("Stopping WebSocketManager, disconnecting all exchanges")

        disconnect_tasks = []
        for exchange, connection in self._connections.items():
            logger.info("Disconnecting from %s", exchange)
            disconnect_tasks.append(connection.disconnect())

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        self._connections.clear()
        logger.info("WebSocketManager stopped")

    async def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to WebSocket streams for newly added symbols.

        Adds the given symbols to the internal symbol list and sends
        subscription messages to all connected exchanges for the new symbols.

        Args:
            symbols: List of symbol strings to subscribe to (e.g. ["ETHUSDT", "SOLUSDT"]).

        Requirements:
            2.6 - Subscribe to WebSocket streams for newly added symbols within 30 seconds
        """
        if not symbols:
            return

        # Add new symbols to internal list (avoid duplicates)
        for symbol in symbols:
            if symbol not in self._symbols:
                self._symbols.append(symbol)

        logger.info("Subscribing to %d new symbols: %s", len(symbols), symbols[:5])

        # Send subscription messages to all connected exchanges
        for exchange, connection in self._connections.items():
            if not connection.is_connected:
                continue

            try:
                if exchange == "binance":
                    await self._subscribe_binance_symbols(connection, symbols)
                elif exchange == "bybit":
                    await self._subscribe_bybit_symbols(connection, symbols)
                elif exchange == "okx":
                    await self._subscribe_okx_symbols(connection, symbols)
            except Exception as e:
                logger.error(
                    "Failed to subscribe new symbols on %s: %s", exchange, str(e)
                )

    async def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from WebSocket streams for removed symbols.

        Removes the given symbols from the internal symbol list and sends
        unsubscription messages to all connected exchanges.

        Args:
            symbols: List of symbol strings to unsubscribe from (e.g. ["XRPUSDT"]).

        Requirements:
            2.7 - Unsubscribe from WebSocket streams for removed symbols within 30 seconds
        """
        if not symbols:
            return

        # Remove symbols from internal list
        self._symbols = [s for s in self._symbols if s not in symbols]

        logger.info("Unsubscribing from %d symbols: %s", len(symbols), symbols[:5])

        # Send unsubscription messages to all connected exchanges
        for exchange, connection in self._connections.items():
            if not connection.is_connected:
                continue

            try:
                if exchange == "binance":
                    await self._unsubscribe_binance_symbols(connection, symbols)
                elif exchange == "bybit":
                    await self._unsubscribe_bybit_symbols(connection, symbols)
                elif exchange == "okx":
                    await self._unsubscribe_okx_symbols(connection, symbols)
            except Exception as e:
                logger.error(
                    "Failed to unsubscribe symbols on %s: %s", exchange, str(e)
                )

    async def _subscribe_binance_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send Binance subscription for specific symbols."""
        params = []
        for symbol in symbols:
            symbol_lower = symbol.lower().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                binance_tf = self._BINANCE_TIMEFRAME_MAP.get(tf, tf)
                params.append(f"{symbol_lower}@kline_{binance_tf}")

        if params and connection._ws is not None:
            subscribe_msg = json.dumps({
                "method": "SUBSCRIBE",
                "params": params,
                "id": 2,
            })
            await connection._ws.send(subscribe_msg)
            logger.debug("Binance: subscribed to %d new streams", len(params))

    async def _unsubscribe_binance_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send Binance unsubscription for specific symbols."""
        params = []
        for symbol in symbols:
            symbol_lower = symbol.lower().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                binance_tf = self._BINANCE_TIMEFRAME_MAP.get(tf, tf)
                params.append(f"{symbol_lower}@kline_{binance_tf}")

        if params and connection._ws is not None:
            unsubscribe_msg = json.dumps({
                "method": "UNSUBSCRIBE",
                "params": params,
                "id": 3,
            })
            await connection._ws.send(unsubscribe_msg)
            logger.debug("Binance: unsubscribed from %d streams", len(params))

    async def _subscribe_bybit_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send Bybit subscription for specific symbols."""
        args = []
        for symbol in symbols:
            symbol_upper = symbol.upper().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                bybit_tf = self._BYBIT_TIMEFRAME_MAP.get(tf, tf)
                args.append(f"kline.{bybit_tf}.{symbol_upper}")

        if args and connection._ws is not None:
            subscribe_msg = json.dumps({
                "op": "subscribe",
                "args": args,
            })
            await connection._ws.send(subscribe_msg)
            logger.debug("Bybit: subscribed to %d new streams", len(args))

    async def _unsubscribe_bybit_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send Bybit unsubscription for specific symbols."""
        args = []
        for symbol in symbols:
            symbol_upper = symbol.upper().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                bybit_tf = self._BYBIT_TIMEFRAME_MAP.get(tf, tf)
                args.append(f"kline.{bybit_tf}.{symbol_upper}")

        if args and connection._ws is not None:
            unsubscribe_msg = json.dumps({
                "op": "unsubscribe",
                "args": args,
            })
            await connection._ws.send(unsubscribe_msg)
            logger.debug("Bybit: unsubscribed from %d streams", len(args))

    async def _subscribe_okx_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send OKX subscription for specific symbols."""
        args = []
        for symbol in symbols:
            inst_id = symbol.upper()
            if "-" not in inst_id:
                if inst_id.endswith("USDT"):
                    inst_id = f"{inst_id[:-4]}-USDT"
                elif inst_id.endswith("USD"):
                    inst_id = f"{inst_id[:-3]}-USD"

            for tf in self._config.timeframes:
                okx_tf = self._OKX_TIMEFRAME_MAP.get(tf, tf)
                args.append({
                    "channel": f"candle{okx_tf}",
                    "instId": inst_id,
                })

        if args and connection._ws is not None:
            subscribe_msg = json.dumps({
                "op": "subscribe",
                "args": args,
            })
            await connection._ws.send(subscribe_msg)
            logger.debug("OKX: subscribed to %d new streams", len(args))

    async def _unsubscribe_okx_symbols(
        self, connection: ExchangeConnection, symbols: List[str]
    ) -> None:
        """Send OKX unsubscription for specific symbols."""
        args = []
        for symbol in symbols:
            inst_id = symbol.upper()
            if "-" not in inst_id:
                if inst_id.endswith("USDT"):
                    inst_id = f"{inst_id[:-4]}-USDT"
                elif inst_id.endswith("USD"):
                    inst_id = f"{inst_id[:-3]}-USD"

            for tf in self._config.timeframes:
                okx_tf = self._OKX_TIMEFRAME_MAP.get(tf, tf)
                args.append({
                    "channel": f"candle{okx_tf}",
                    "instId": inst_id,
                })

        if args and connection._ws is not None:
            unsubscribe_msg = json.dumps({
                "op": "unsubscribe",
                "args": args,
            })
            await connection._ws.send(unsubscribe_msg)
            logger.debug("OKX: unsubscribed from %d streams", len(args))

    async def _subscribe_streams(self, exchange: str) -> None:
        """Subscribe to kline streams for all symbols and timeframes.

        Sends exchange-specific subscription messages for each
        symbol/timeframe combination.

        Args:
            exchange: The exchange name to subscribe streams for.

        Requirements:
            1.6 - Stream data for 4H, 1H, and 15m timeframes
        """
        connection = self._connections.get(exchange)
        if connection is None or not connection.is_connected:
            logger.warning(
                "Cannot subscribe streams for %s: not connected", exchange
            )
            return

        if not self._symbols:
            logger.warning("No symbols configured for subscription")
            return

        if exchange == "binance":
            await self._subscribe_binance(connection)
        elif exchange == "bybit":
            await self._subscribe_bybit(connection)
        elif exchange == "okx":
            await self._subscribe_okx(connection)
        else:
            logger.warning("Unknown exchange for subscription: %s", exchange)

    async def _subscribe_binance(self, connection: ExchangeConnection) -> None:
        """Send Binance kline subscription message.

        Binance uses a combined stream subscription format:
        {"method": "SUBSCRIBE", "params": ["btcusdt@kline_1h", ...], "id": 1}
        """
        params = []
        for symbol in self._symbols:
            symbol_lower = symbol.lower().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                binance_tf = self._BINANCE_TIMEFRAME_MAP.get(tf, tf)
                params.append(f"{symbol_lower}@kline_{binance_tf}")

        if params and connection._ws is not None:
            subscribe_msg = json.dumps({
                "method": "SUBSCRIBE",
                "params": params,
                "id": 1,
            })
            try:
                await connection._ws.send(subscribe_msg)
                logger.info(
                    "Binance: subscribed to %d streams", len(params)
                )
            except Exception as e:
                logger.error("Binance subscription failed: %s", str(e))

    async def _subscribe_bybit(self, connection: ExchangeConnection) -> None:
        """Send Bybit kline subscription message.

        Bybit uses topic-based subscription:
        {"op": "subscribe", "args": ["kline.60.BTCUSDT", ...]}
        """
        args = []
        for symbol in self._symbols:
            symbol_upper = symbol.upper().replace("-", "").replace("/", "")
            for tf in self._config.timeframes:
                bybit_tf = self._BYBIT_TIMEFRAME_MAP.get(tf, tf)
                args.append(f"kline.{bybit_tf}.{symbol_upper}")

        if args and connection._ws is not None:
            subscribe_msg = json.dumps({
                "op": "subscribe",
                "args": args,
            })
            try:
                await connection._ws.send(subscribe_msg)
                logger.info(
                    "Bybit: subscribed to %d streams", len(args)
                )
            except Exception as e:
                logger.error("Bybit subscription failed: %s", str(e))

    async def _subscribe_okx(self, connection: ExchangeConnection) -> None:
        """Send OKX kline subscription message.

        OKX uses channel-based subscription:
        {"op": "subscribe", "args": [{"channel": "candle1H", "instId": "BTC-USDT"}, ...]}
        """
        args = []
        for symbol in self._symbols:
            # OKX uses dash-separated format like BTC-USDT
            inst_id = symbol.upper()
            if "-" not in inst_id:
                # Convert BTCUSDT to BTC-USDT format
                # Assume last 4 chars are quote currency for USDT pairs
                if inst_id.endswith("USDT"):
                    inst_id = f"{inst_id[:-4]}-USDT"
                elif inst_id.endswith("USD"):
                    inst_id = f"{inst_id[:-3]}-USD"

            for tf in self._config.timeframes:
                okx_tf = self._OKX_TIMEFRAME_MAP.get(tf, tf)
                args.append({
                    "channel": f"candle{okx_tf}",
                    "instId": inst_id,
                })

        if args and connection._ws is not None:
            subscribe_msg = json.dumps({
                "op": "subscribe",
                "args": args,
            })
            try:
                await connection._ws.send(subscribe_msg)
                logger.info(
                    "OKX: subscribed to %d streams", len(args)
                )
            except Exception as e:
                logger.error("OKX subscription failed: %s", str(e))

    def _make_message_handler(
        self, exchange: str
    ) -> Callable[[dict], Awaitable[None]]:
        """Create an exchange-specific message handler closure.

        Args:
            exchange: The exchange name for routing message parsing.

        Returns:
            An async callable that handles raw messages from the exchange.
        """

        async def handler(data: dict) -> None:
            await self._handle_message(exchange, data)

        return handler

    def _make_resubscribe_handler(
        self, exchange: str
    ) -> Callable[[], Awaitable[None]]:
        """Create an exchange-specific re-subscribe handler for reconnection.

        After a WebSocket reconnects, it needs to re-send subscription
        messages to resume receiving kline data.

        Args:
            exchange: The exchange name to re-subscribe streams for.

        Returns:
            An async callable that re-subscribes to all streams.
        """

        async def handler() -> None:
            logger.info("Re-subscribing to %s streams after reconnection", exchange)
            await self._subscribe_streams(exchange)

        return handler

    async def _handle_message(self, exchange: str, data: dict) -> None:
        """Parse raw messages, validate, and emit to event bus.

        Routes to exchange-specific parsers, validates the resulting
        candle data, and emits a CandleCloseEvent if valid.

        Args:
            exchange: The source exchange name.
            data: The raw parsed JSON message from the websocket.

        Requirements:
            1.4 - Validate data, discard zero volume/malformed
            1.7 - Emit event within 50ms
        """
        try:
            event = self._parse_message(exchange, data)
            if event is None:
                return

            if not self._validate_message(event):
                return

            await self._event_bus.emit(event)

        except Exception as e:
            logger.debug(
                "Error handling message from %s: %s", exchange, str(e)
            )

    def _parse_message(
        self, exchange: str, data: dict
    ) -> Optional[CandleCloseEvent]:
        """Parse exchange-specific message format into CandleCloseEvent.

        Only processes confirmed/closed candles:
        - Binance: x=true in kline data
        - Bybit: confirm=true in data array
        - OKX: confirm="1" in data array

        Args:
            exchange: The source exchange name.
            data: The raw parsed JSON message.

        Returns:
            A CandleCloseEvent if the message represents a closed candle,
            None otherwise (non-kline messages, unclosed candles, etc.).
        """
        if exchange == "binance":
            return self._parse_binance_message(data)
        elif exchange == "bybit":
            return self._parse_bybit_message(data)
        elif exchange == "okx":
            return self._parse_okx_message(data)
        else:
            logger.debug("Unknown exchange in message: %s", exchange)
            return None

    def _parse_binance_message(self, data: dict) -> Optional[CandleCloseEvent]:
        """Parse Binance kline message format.

        Expected format:
        {
            "e": "kline",
            "k": {
                "t": 1672531200000,  # kline start time (ms)
                "s": "BTCUSDT",      # symbol
                "i": "1h",           # interval
                "o": "16500.00",     # open
                "h": "16600.00",     # high
                "l": "16400.00",     # low
                "c": "16550.00",     # close
                "v": "1234.56",      # volume
                "x": true            # is candle closed
            }
        }
        """
        # Only process kline events
        if data.get("e") != "kline":
            return None

        kline = data.get("k")
        if not isinstance(kline, dict):
            return None

        # Only process closed candles
        if not kline.get("x", False):
            return None

        try:
            interval = kline.get("i", "")
            timeframe = self._BINANCE_INTERVAL_TO_TF.get(interval)
            if timeframe is None:
                return None

            symbol = kline.get("s", "").upper()
            timestamp_ms = kline.get("t", 0)

            candle = OHLCV(
                timestamp=datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                ),
                open=float(kline["o"]),
                high=float(kline["h"]),
                low=float(kline["l"]),
                close=float(kline["c"]),
                volume=float(kline["v"]),
            )

            return CandleCloseEvent(
                symbol=symbol,
                timeframe=timeframe,
                candle=candle,
                exchange="binance",
                received_at=datetime.now(tz=timezone.utc),
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.debug("Binance parse error: %s", str(e))
            return None

    def _parse_bybit_message(self, data: dict) -> Optional[CandleCloseEvent]:
        """Parse Bybit kline message format.

        Expected format:
        {
            "topic": "kline.60.BTCUSDT",
            "data": [{
                "start": 1672531200000,
                "open": "16500.00",
                "high": "16600.00",
                "low": "16400.00",
                "close": "16550.00",
                "volume": "1234.56",
                "confirm": true
            }]
        }
        """
        topic = data.get("topic", "")
        if not topic.startswith("kline."):
            return None

        kline_data = data.get("data")
        if not isinstance(kline_data, list) or len(kline_data) == 0:
            return None

        candle_data = kline_data[0]
        if not isinstance(candle_data, dict):
            return None

        # Only process confirmed/closed candles
        if not candle_data.get("confirm", False):
            return None

        try:
            # Parse topic: "kline.{interval}.{symbol}"
            parts = topic.split(".")
            if len(parts) < 3:
                return None

            interval = parts[1]
            symbol = parts[2].upper()

            timeframe = self._BYBIT_INTERVAL_TO_TF.get(interval)
            if timeframe is None:
                return None

            timestamp_ms = candle_data.get("start", 0)

            candle = OHLCV(
                timestamp=datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                ),
                open=float(candle_data["open"]),
                high=float(candle_data["high"]),
                low=float(candle_data["low"]),
                close=float(candle_data["close"]),
                volume=float(candle_data["volume"]),
            )

            return CandleCloseEvent(
                symbol=symbol,
                timeframe=timeframe,
                candle=candle,
                exchange="bybit",
                received_at=datetime.now(tz=timezone.utc),
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.debug("Bybit parse error: %s", str(e))
            return None

    def _parse_okx_message(self, data: dict) -> Optional[CandleCloseEvent]:
        """Parse OKX kline message format.

        Expected format:
        {
            "arg": {
                "channel": "candle1H",
                "instId": "BTC-USDT"
            },
            "data": [
                ["1672531200000", "16500.00", "16600.00", "16400.00",
                 "16550.00", "1234.56", "volCcy", "volCcyQuote", "1"]
            ]
        }

        Data array indices:
            0: timestamp (ms)
            1: open
            2: high
            3: low
            4: close
            5: volume (in base currency)
            6: volCcy
            7: volCcyQuote
            8: confirm ("0" = not closed, "1" = closed)
        """
        arg = data.get("arg")
        if not isinstance(arg, dict):
            return None

        channel = arg.get("channel", "")
        if not channel.startswith("candle"):
            return None

        candle_data = data.get("data")
        if not isinstance(candle_data, list) or len(candle_data) == 0:
            return None

        row = candle_data[0]
        if not isinstance(row, list) or len(row) < 9:
            return None

        # Only process confirmed/closed candles (index 8 == "1")
        if str(row[8]) != "1":
            return None

        try:
            timeframe = self._OKX_CHANNEL_TO_TF.get(channel)
            if timeframe is None:
                return None

            inst_id = arg.get("instId", "")
            # Normalize OKX instId (BTC-USDT) to symbol format (BTCUSDT)
            symbol = inst_id.upper().replace("-", "")

            timestamp_ms = int(row[0])

            candle = OHLCV(
                timestamp=datetime.fromtimestamp(
                    timestamp_ms / 1000, tz=timezone.utc
                ),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )

            return CandleCloseEvent(
                symbol=symbol,
                timeframe=timeframe,
                candle=candle,
                exchange="okx",
                received_at=datetime.now(tz=timezone.utc),
            )

        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.debug("OKX parse error: %s", str(e))
            return None

    def _validate_message(self, event: CandleCloseEvent) -> bool:
        """Validate a parsed CandleCloseEvent for data integrity.

        Checks:
        - Volume is not zero or negative
        - OHLCV values are positive and finite
        - High >= Low
        - High >= Open and High >= Close
        - Low <= Open and Low <= Close
        - Symbol is not empty
        - Timeframe is valid

        Args:
            event: The parsed CandleCloseEvent to validate.

        Returns:
            True if the event passes all validation checks, False otherwise.

        Requirements:
            1.4 - Discard zero volume or malformed fields
        """
        candle = event.candle

        # Check for zero or negative volume
        if candle.volume <= 0:
            logger.debug(
                "Discarding %s/%s: zero/negative volume (%.6f)",
                event.symbol,
                event.timeframe,
                candle.volume,
            )
            return False

        # Check for non-positive OHLC values
        if any(
            v <= 0
            for v in [candle.open, candle.high, candle.low, candle.close]
        ):
            logger.debug(
                "Discarding %s/%s: non-positive OHLC values",
                event.symbol,
                event.timeframe,
            )
            return False

        # Check OHLC consistency: high >= low
        if candle.high < candle.low:
            logger.debug(
                "Discarding %s/%s: high (%.6f) < low (%.6f)",
                event.symbol,
                event.timeframe,
                candle.high,
                candle.low,
            )
            return False

        # Check high is >= open and close
        if candle.high < candle.open or candle.high < candle.close:
            logger.debug(
                "Discarding %s/%s: high not >= open/close",
                event.symbol,
                event.timeframe,
            )
            return False

        # Check low is <= open and close
        if candle.low > candle.open or candle.low > candle.close:
            logger.debug(
                "Discarding %s/%s: low not <= open/close",
                event.symbol,
                event.timeframe,
            )
            return False

        # Check symbol is not empty
        if not event.symbol:
            logger.debug("Discarding event: empty symbol")
            return False

        # Check timeframe is valid
        valid_timeframes = {"4h", "1h", "15m"}
        if event.timeframe not in valid_timeframes:
            logger.debug(
                "Discarding %s: invalid timeframe '%s'",
                event.symbol,
                event.timeframe,
            )
            return False

        return True

    async def _handle_connection_failure(
        self, event: ConnectionFailureEvent
    ) -> None:
        """Handle connection failure from an ExchangeConnection.

        Logs the failure and forwards to the external failure callback
        (if registered) for failover logic.

        Args:
            event: The ConnectionFailureEvent from the failed connection.
        """
        logger.error(
            "Connection failure for %s: %s (attempts: %d)",
            event.exchange,
            event.reason,
            event.attempts_made,
        )

        # Forward to external callback (e.g., MomentumScanner failover handler)
        if self._external_failure_callback is not None:
            try:
                await self._external_failure_callback(event)
            except Exception as e:
                logger.error(
                    "Error in external failure callback for %s: %s",
                    event.exchange,
                    str(e),
                )
