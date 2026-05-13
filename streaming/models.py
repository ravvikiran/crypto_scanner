"""
Data Models for the Streaming Momentum Scanner.

Defines all enums and dataclasses used across the event-driven
momentum scanning pipeline.

Requirements: 2.2, 6.1, 7.1, 8.1, 9.1, 11.1, 12.1, 17.1
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


# ─── Core Data Models ────────────────────────────────────────────────────────


@dataclass
class OHLCV:
    """OHLCV Candle Data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class CoinData:
    """Coin market data with indicators"""
    symbol: str
    name: str
    current_price: float
    market_cap: float
    volume_24h: float
    price_change_24h: float
    price_change_percent_24h: float


# ─── Enums ───────────────────────────────────────────────────────────────────


class SignalDirection(Enum):
    """Direction of a trading signal."""

    LONG = "long"
    SHORT = "short"


class TrendStatus(Enum):
    """Status of a coin's 4H trend assessment."""

    BULLISH = "bullish"
    NOT_BULLISH = "not_bullish"
    INSUFFICIENT_DATA = "insufficient_data"


class SetupType(Enum):
    """Types of momentum setups detected by the scanner."""

    COMPRESSION_BREAKOUT = "compression_breakout"
    PULLBACK_CONTINUATION = "pullback_continuation"
    MOMENTUM_BREAKOUT = "momentum_breakout"


class SetupState(Enum):
    """Lifecycle state of a detected setup."""

    DETECTED = "detected"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class SignalOutcomeType(Enum):
    """Outcome of a resolved signal."""

    WIN = "win"
    LOSS = "loss"
    EXPIRY = "expiry"


# ─── WebSocket & Event Dataclasses ───────────────────────────────────────────


@dataclass
class WebSocketConfig:
    """Configuration for a single exchange websocket connection."""

    exchange: str  # "binance", "bybit", "okx"
    url: str
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=lambda: ["4h", "1h", "15m"])
    max_reconnect_attempts: int = 5
    initial_reconnect_delay: float = 1.0
    connection_timeout: float = 10.0


@dataclass
class CandleCloseEvent:
    """Emitted when a candle closes on any timeframe."""

    symbol: str
    timeframe: str  # "4h", "1h", "15m"
    candle: OHLCV
    exchange: str
    received_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConnectionFailureEvent:
    """Emitted when all reconnection attempts are exhausted for an exchange."""

    exchange: str
    reason: str
    attempts_made: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ─── Setup Detection Dataclasses ─────────────────────────────────────────────


@dataclass
class CompressionZone:
    """A detected compression zone on the 1H timeframe."""

    high: float
    low: float
    candle_count: int
    start_atr14: float
    candles: List[OHLCV] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expired: bool = False


@dataclass
class ActiveSetup:
    """A setup that has been detected and is being tracked."""

    symbol: str
    setup_type: SetupType
    state: SetupState = SetupState.DETECTED
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: Optional[float] = None
    risk_reward: float = 0.0
    timeframe: str = "1h"
    trigger_timeframe: str = "15m"
    target_3: Optional[float] = None
    compression_zone: Optional[CompressionZone] = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None
    direction: "SignalDirection" = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.direction is None:
            self.direction = SignalDirection.LONG


@dataclass
class PendingTrigger:
    """A 15m entry trigger awaiting confirmation."""

    symbol: str
    setup_type: SetupType
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    candles_remaining: int = 4  # 4 x 15m = 1 hour confirmation window
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SetupSignal:
    """A fully formed setup signal ready for scoring."""

    symbol: str
    setup_type: SetupType
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    risk_reward: float = 0.0
    timeframe: str = "1h"
    trigger_timeframe: str = "15m"
    pending_confirmation: bool = True
    confirmation_deadline: int = 4  # 15m candles
    detected_at: datetime = field(default_factory=datetime.utcnow)
    direction: "SignalDirection" = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.direction is None:
            self.direction = SignalDirection.LONG


# ─── Scoring Dataclasses ─────────────────────────────────────────────────────


@dataclass
class RelativeStrength:
    """Relative strength metrics for a coin vs BTC."""

    rs_4h: float = 0.0  # 4H rolling RS vs BTC
    rs_24h: float = 0.0  # 24H rolling RS vs BTC
    acceleration: float = 0.0  # Current 4H RS - Previous 4H RS
    percentile: float = 0.0  # 0-100 normalized rank
    is_stale: bool = False


@dataclass
class OIFundingData:
    """Open interest and funding rate context for a coin."""

    oi_change_4h_pct: float = 0.0  # % change over 4 hours
    funding_rate: float = 0.0  # per 8 hours
    is_overcrowded: bool = False  # funding > 0.1% or < -0.1%
    weak_oi_participation: bool = False  # OI down >5% while price up >1%
    data_available: bool = True  # False if data unavailable
    score_adjustment: float = 0.0  # -0.20, -0.15, or 0.0


@dataclass
class BreakoutQualityScore:
    """Breakout quality assessment from 5 sub-scores (0-100 total)."""

    body_ratio_score: int = 0  # 0-20
    close_position_score: int = 0  # 0-20
    range_expansion_score: int = 0  # 0-20
    momentum_acceleration_score: int = 0  # 0-20
    relative_volume_score: int = 0  # 0-20

    @property
    def total(self) -> int:
        """Sum of all 5 sub-scores (0-100)."""
        return (
            self.body_ratio_score
            + self.close_position_score
            + self.range_expansion_score
            + self.momentum_acceleration_score
            + self.relative_volume_score
        )


@dataclass
class ScoreInputs:
    """Normalized inputs for the composite scoring formula."""

    relative_strength: float = 0.0  # 0-100 (30% weight)
    relative_volume: float = 0.0  # 0-100 (25% weight)
    breakout_quality: float = 0.0  # 0-100 (20% weight)
    trend_quality: float = 0.0  # 0-100 (15% weight)
    market_alignment: float = 0.0  # 0-100 (10% weight)


@dataclass
class ScoredSetup:
    """A scored and ranked setup ready for alerting."""

    signal: SetupSignal
    composite_score: float = 0.0  # 0-100, rounded to 2 decimal places
    inputs: ScoreInputs = field(default_factory=ScoreInputs)
    oi_adjustment: float = 0.0  # -0.20, -0.15, or 0.0
    labels: List[str] = field(default_factory=list)  # e.g. ["overcrowded"]


# ─── State & Persistence Dataclasses ─────────────────────────────────────────


@dataclass
class CoinState:
    """Stateful tracking for a single monitored coin."""

    symbol: str
    trend_status: TrendStatus = TrendStatus.INSUFFICIENT_DATA
    active_setup: Optional[ActiveSetup] = None
    pending_trigger: Optional[PendingTrigger] = None
    last_signal_score: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    candle_buffers: Dict[str, List[OHLCV]] = field(default_factory=dict)


@dataclass
class JournalEntry:
    """A persisted signal record in the journal store."""

    symbol: str
    setup_type: SetupType
    entry_price: float
    stop_loss: float
    composite_score: float = 0.0
    relative_strength: float = 0.0
    relative_volume: float = 0.0
    oi_change_pct: float = 0.0
    funding_rate: float = 0.0
    ema20: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    atr14: float = 0.0
    btc_regime: str = "unknown"
    target_3: Optional[float] = None
    outcome: Optional[SignalOutcomeType] = None
    actual_rr: Optional[float] = None
    duration_minutes: Optional[float] = None
    exit_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AlertCacheEntry:
    """A cached alert entry for deduplication."""

    symbol: str
    setup_type: SetupType
    sent_at: datetime = field(default_factory=datetime.utcnow)
    volume_ratio_at_send: float = 0.0
    score_at_send: float = 0.0


# ─── Trailing Stop & Monitoring Dataclasses ──────────────────────────────────


@dataclass
class MonitoredPosition:
    """A position being tracked by the Trailing Stop Monitor."""

    symbol: str
    entry_price: float
    stop_loss: float  # Original stop-loss
    current_stop: float  # Current trailing stop level
    target_1: float
    target_2: float
    target_3: float
    signal_id: str
    started_at: datetime
    highest_since_t2: Optional[float] = None
    lowest_since_t2: Optional[float] = None
    t1_hit: bool = False
    t2_hit: bool = False
    t3_hit: bool = False
    last_data_at: Optional[datetime] = None
    direction: "SignalDirection" = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.direction is None:
            self.direction = SignalDirection.LONG


# ─── Universe Management Dataclasses ─────────────────────────────────────────


@dataclass
class UniversePair:
    """A trading pair in the dynamic universe."""

    symbol: str
    volume_24h_usd: float
    current_price: float
    last_updated: datetime


# ─── Health Check Dataclasses ────────────────────────────────────────────────


@dataclass
class HealthStatus:
    """Health check response for Railway deployment."""

    status: str  # "healthy"
    uptime_seconds: float
    monitored_symbols: int
    active_positions: int
