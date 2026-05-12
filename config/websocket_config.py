"""
WebSocket Streaming Configuration for the Momentum Scanner.

Provides environment-variable-driven configuration for websocket connections,
reconnection behavior, exchange enable flags, alert cooldown, and journal retention.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class WebSocketStreamConfig:
    """WebSocket streaming configuration with env-var-driven defaults.

    Covers exchange URLs, enable flags, reconnect settings, max coins,
    alert cooldown, and journal retention.

    Requirements:
        1.1 - Binance websocket connection within 10 seconds
        1.2 - Secondary Bybit websocket connection
        1.3 - Tertiary OKX websocket connection
        15.2 - Configurable cooldown (default 4h, range 1-48h)
        17.7 - 90-day journal retention
        20.4 - Support up to 300 coin pairs concurrently
    """

    # --- Exchange WebSocket URLs ---
    binance_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "BINANCE_WS_URL", "wss://stream.binance.com:9443/ws"
        )
    )
    bybit_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "BYBIT_WS_URL", "wss://stream.bybit.com/v5/public/linear"
        )
    )
    okx_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "OKX_WS_URL", "wss://ws.okx.com:8443/ws/v5/public"
        )
    )

    # --- Exchange Enable Flags ---
    enable_binance: bool = field(
        default_factory=lambda: os.getenv("WS_ENABLE_BINANCE", "false").lower() == "true"
    )
    enable_bybit: bool = field(
        default_factory=lambda: os.getenv("WS_ENABLE_BYBIT", "true").lower() == "true"
    )
    enable_okx: bool = field(
        default_factory=lambda: os.getenv("WS_ENABLE_OKX", "false").lower() == "true"
    )

    # --- Reconnection Settings ---
    reconnect_max_attempts: int = field(
        default_factory=lambda: int(os.getenv("WS_RECONNECT_MAX_ATTEMPTS", "5"))
    )
    reconnect_initial_delay: float = field(
        default_factory=lambda: float(os.getenv("WS_RECONNECT_INITIAL_DELAY", "1.0"))
    )
    reconnect_max_delay: float = field(
        default_factory=lambda: float(os.getenv("WS_RECONNECT_MAX_DELAY", "60.0"))
    )
    connection_timeout: float = field(
        default_factory=lambda: float(os.getenv("WS_CONNECTION_TIMEOUT", "10.0"))
    )
    stale_data_threshold: float = field(
        default_factory=lambda: float(os.getenv("WS_STALE_DATA_THRESHOLD", "5.0"))
    )

    # --- Streaming Timeframes ---
    timeframes: List[str] = field(
        default_factory=lambda: os.getenv("WS_TIMEFRAMES", "4h,1h,15m").split(",")
    )

    # --- Coin Universe ---
    max_coins: int = field(
        default_factory=lambda: int(os.getenv("WS_MAX_COINS", "300"))
    )

    # --- Alert Cooldown (Requirement 15.2) ---
    alert_cooldown_hours: float = field(
        default_factory=lambda: float(os.getenv("WS_ALERT_COOLDOWN_HOURS", "4.0"))
    )
    alert_cooldown_min_hours: float = field(
        default_factory=lambda: float(os.getenv("WS_ALERT_COOLDOWN_MIN_HOURS", "1.0"))
    )
    alert_cooldown_max_hours: float = field(
        default_factory=lambda: float(os.getenv("WS_ALERT_COOLDOWN_MAX_HOURS", "48.0"))
    )

    # --- Journal Retention (Requirement 17.7) ---
    journal_retention_days: int = field(
        default_factory=lambda: int(os.getenv("WS_JOURNAL_RETENTION_DAYS", "90"))
    )

    # --- Event Processing ---
    event_queue_max_size: int = field(
        default_factory=lambda: int(os.getenv("WS_EVENT_QUEUE_MAX_SIZE", "10000"))
    )
    max_concurrent_coin_updates: int = field(
        default_factory=lambda: int(os.getenv("WS_MAX_CONCURRENT_UPDATES", "50"))
    )

    # --- Universe Management (Requirement 2.1) ---
    universe_refresh_minutes: int = field(
        default_factory=lambda: int(os.getenv("UNIVERSE_REFRESH_MINUTES", "60"))
    )
    universe_min_volume_usd: float = field(
        default_factory=lambda: float(os.getenv("UNIVERSE_MIN_VOLUME_USD", "50000000"))
    )
    universe_min_price: float = field(
        default_factory=lambda: float(os.getenv("UNIVERSE_MIN_PRICE", "0.10"))
    )

    # --- Volatility Gate (Requirement 5.1) ---
    volatility_min_pct: float = field(
        default_factory=lambda: float(os.getenv("VOLATILITY_MIN_PCT", "1.5"))
    )
    volatility_max_pct: float = field(
        default_factory=lambda: float(os.getenv("VOLATILITY_MAX_PCT", "8.0"))
    )

    # --- BTC Crash Detection (Requirement 1.1) ---
    btc_crash_threshold_pct: float = field(
        default_factory=lambda: float(os.getenv("BTC_CRASH_THRESHOLD_PCT", "3.0"))
    )
    btc_crash_candle_count: int = field(
        default_factory=lambda: int(os.getenv("BTC_CRASH_CANDLE_COUNT", "4"))
    )

    def __post_init__(self):
        """Validate configuration values after initialization."""
        # Clamp cooldown to permitted range (Requirement 15.2)
        self.alert_cooldown_hours = max(
            self.alert_cooldown_min_hours,
            min(self.alert_cooldown_hours, self.alert_cooldown_max_hours),
        )

        # Ensure at least one exchange is enabled
        if not any([self.enable_binance, self.enable_bybit, self.enable_okx]):
            self.enable_bybit = True

        # Validate positive numeric values
        if self.reconnect_max_attempts < 1:
            self.reconnect_max_attempts = 5
        if self.reconnect_initial_delay <= 0:
            self.reconnect_initial_delay = 1.0
        if self.connection_timeout <= 0:
            self.connection_timeout = 10.0
        if self.max_coins < 1:
            self.max_coins = 300
        if self.journal_retention_days < 1:
            self.journal_retention_days = 90

        # Validate universe management settings
        if self.universe_refresh_minutes < 1:
            self.universe_refresh_minutes = 60
        if self.universe_min_volume_usd < 0:
            self.universe_min_volume_usd = 50_000_000
        if self.universe_min_price < 0:
            self.universe_min_price = 0.10

        # Validate volatility gate settings
        if self.volatility_min_pct < 0:
            self.volatility_min_pct = 1.5
        if self.volatility_max_pct <= self.volatility_min_pct:
            self.volatility_max_pct = 8.0

        # Validate BTC crash detection settings
        if self.btc_crash_threshold_pct <= 0:
            self.btc_crash_threshold_pct = 3.0
        if self.btc_crash_candle_count < 1:
            self.btc_crash_candle_count = 4

    @property
    def enabled_exchanges(self) -> List[str]:
        """Return list of enabled exchange names."""
        exchanges = []
        if self.enable_binance:
            exchanges.append("binance")
        if self.enable_bybit:
            exchanges.append("bybit")
        if self.enable_okx:
            exchanges.append("okx")
        return exchanges

    def get_exchange_url(self, exchange: str) -> str:
        """Get the WebSocket URL for a given exchange name.

        Args:
            exchange: Exchange name ('binance', 'bybit', or 'okx')

        Returns:
            The WebSocket URL for the exchange.

        Raises:
            ValueError: If the exchange name is not recognized.
        """
        url_map = {
            "binance": self.binance_ws_url,
            "bybit": self.bybit_ws_url,
            "okx": self.okx_ws_url,
        }
        if exchange not in url_map:
            raise ValueError(
                f"Unknown exchange: '{exchange}'. Must be one of: {list(url_map.keys())}"
            )
        return url_map[exchange]
