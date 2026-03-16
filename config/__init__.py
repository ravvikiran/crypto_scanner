"""
Crypto Scanner Configuration Module
Loads and manages all configuration settings from environment variables.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")


@dataclass
class APIConfig:
    """API Configuration"""
    coingecko_api_key: str = os.getenv("COINGECKO_API_KEY", "")
    cmc_api_key: str = os.getenv("CMC_API_KEY", "")
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_secret_key: str = os.getenv("BINANCE_SECRET_KEY", "")


@dataclass
class AlertConfig:
    """Alert System Configuration"""
    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Discord
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    
    # Email
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")


@dataclass
class ScannerConfig:
    """Scanner Configuration"""
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))
    max_coins_to_scan: int = int(os.getenv("MAX_COINS_TO_SCAN", "500"))
    min_market_cap_millions: float = float(os.getenv("MIN_MARKET_CAP_MILLIONS", "10"))
    min_volume_24h_millions: float = float(os.getenv("MIN_VOLUME_24H_MILLIONS", "1"))
    min_signal_score: float = float(os.getenv("MIN_SIGNAL_SCORE", "7.0"))
    timeframes: List[str] = field(default_factory=lambda: os.getenv("TIMEFRAMES", "4h,daily").split(","))


@dataclass
class StrategyConfig:
    """Strategy Parameters"""
    # EMA Periods
    ema_short: int = int(os.getenv("EMA_SHORT", "20"))
    ema_medium: int = int(os.getenv("EMA_MEDIUM", "50"))
    ema_long: int = int(os.getenv("EMA_LONG", "100"))
    ema_very_long: int = int(os.getenv("EMA_VERY_LONG", "200"))
    
    # RSI
    rsi_period: int = int(os.getenv("RSI_PERIOD", "14"))
    rsi_oversold: float = float(os.getenv("RSI_OVERSOLD", "30"))
    rsi_overbought: float = float(os.getenv("RSI_OVERBOUGHT", "70"))
    rsi_momentum_low: float = float(os.getenv("RSI_MOMENTUM_LOW", "55"))
    rsi_momentum_high: float = float(os.getenv("RSI_MOMENTUM_HIGH", "70"))
    
    # Volume
    volume_ma_period: int = int(os.getenv("VOLUME_MA_PERIOD", "30"))
    
    # Volatility
    atr_period: int = int(os.getenv("ATR_PERIOD", "14"))
    bollinger_period: int = int(os.getenv("BOLLINGER_PERIOD", "20"))
    bollinger_std: float = float(os.getenv("BOLLINGER_STD", "2"))
    volatility_lookback: int = int(os.getenv("VOLATILITY_LOOKBACK", "20"))


@dataclass
class TradingConfig:
    """Trading Pairs Configuration"""
    primary_asset: str = os.getenv("PRIMARY_ASSET", "BTC")
    quote_asset: str = os.getenv("QUOTE_ASSET", "USDT")


@dataclass
class LoggingConfig:
    """Logging Configuration"""
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/scanner.log")


@dataclass
class Config:
    """Main Configuration Container"""
    api: APIConfig = field(default_factory=APIConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Reload configuration from environment"""
    global _config
    _config = Config()
    return _config
