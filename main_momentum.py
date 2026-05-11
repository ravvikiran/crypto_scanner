"""
Momentum Scanner Entry Point.

Starts the event-driven momentum scanning engine with WebSocket streaming.
Handles graceful shutdown via SIGINT/SIGTERM and logs a configuration
summary on startup. Graceful shutdown completes within 10 seconds.

Requirements: 20.5 - Crash recovery via state persistence on shutdown/restart.
Requirements: 9.5, 9.6 - Health check endpoint and SIGTERM graceful shutdown.

Usage:
    python main_momentum.py
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Try to import yaml for config loading
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from config.websocket_config import WebSocketStreamConfig
from core.momentum_scanner import MomentumScanner

logger = logging.getLogger("momentum_scanner")


def setup_logging() -> None:
    """Configure logging for the momentum scanner."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/momentum_scanner.log"),
        ],
    )


def load_symbols() -> list:
    """Load symbols to monitor from config.yaml or environment variable.

    Priority:
        1. MOMENTUM_SYMBOLS env var (comma-separated)
        2. config.yaml momentum_scanner.symbols section
        3. Default top crypto pairs
    """
    # Check environment variable first
    env_symbols = os.getenv("MOMENTUM_SYMBOLS")
    if env_symbols:
        symbols = [s.strip().upper() for s in env_symbols.split(",") if s.strip()]
        if symbols:
            return symbols

    # Try loading from config.yaml
    if YAML_AVAILABLE:
        config_path = Path("config.yaml")
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f) or {}
                momentum_config = config.get("momentum_scanner", {})
                yaml_symbols = momentum_config.get("symbols", [])
                if yaml_symbols:
                    return [s.strip().upper() for s in yaml_symbols if s.strip()]
            except Exception as e:
                logger.warning("Failed to load symbols from config.yaml: %s", e)

    # Default symbols - top crypto pairs by volume
    return [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "AVAXUSDT",
        "DOTUSDT",
        "MATICUSDT",
        "LINKUSDT",
        "UNIUSDT",
        "ATOMUSDT",
        "LTCUSDT",
        "ETCUSDT",
        "APTUSDT",
        "ARBUSDT",
        "OPUSDT",
        "NEARUSDT",
        "FILUSDT",
    ]


def log_startup_summary(config: WebSocketStreamConfig, symbols: list) -> None:
    """Log a configuration summary on startup."""
    logger.info("=" * 60)
    logger.info("MOMENTUM SCANNER - Starting Up")
    logger.info("=" * 60)
    logger.info("Configuration Summary:")
    logger.info("  Exchanges enabled: %s", ", ".join(config.enabled_exchanges))
    logger.info("  Symbols count: %d", len(symbols))
    logger.info("  Timeframes: %s", ", ".join(config.timeframes))
    logger.info("  Alert cooldown: %.1f hours", config.alert_cooldown_hours)
    logger.info("  Max coins: %d", config.max_coins)
    logger.info("  Reconnect attempts: %d", config.reconnect_max_attempts)
    logger.info("  Connection timeout: %.1fs", config.connection_timeout)
    logger.info("  Stale data threshold: %.1fs", config.stale_data_threshold)
    logger.info("  Journal retention: %d days", config.journal_retention_days)
    logger.info("  Event queue max size: %d", config.event_queue_max_size)
    logger.info("  Max concurrent updates: %d", config.max_concurrent_coin_updates)
    logger.info("=" * 60)


async def run_scanner() -> None:
    """Main async entry point for the momentum scanner.

    Creates the scanner, registers signal handlers for graceful shutdown,
    and starts the event processing loop. The scanner internally manages
    the health check server (starts if PORT is set). Graceful shutdown
    completes within 10 seconds.

    Requirements: 9.5, 9.6, 20.5
    """
    # Load configuration from environment variables
    config = WebSocketStreamConfig()

    # Load symbols to monitor
    symbols = load_symbols()

    # Log startup summary
    log_startup_summary(config, symbols)

    # Create the scanner
    scanner = MomentumScanner(config=config, symbols=symbols)

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %s, initiating graceful shutdown...", sig.name)
        shutdown_event.set()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_shutdown, sig)
        except NotImplementedError:
            # Windows does not support add_signal_handler for SIGTERM
            # Fall back to signal.signal for Windows compatibility
            pass

    # Start the scanner (includes health check server if PORT is set)
    try:
        await scanner.start()
        logger.info("Momentum scanner is running. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except asyncio.CancelledError:
        logger.info("Scanner task cancelled")
    finally:
        # Graceful shutdown within 10 seconds (Requirement 9.6)
        logger.info("Shutting down momentum scanner (10s budget)...")
        try:
            await asyncio.wait_for(
                _graceful_shutdown(scanner),
                timeout=10.0,
            )
            logger.info("Momentum scanner stopped successfully.")
        except asyncio.TimeoutError:
            logger.warning(
                "Graceful shutdown exceeded 10-second budget. "
                "Some resources may not have been cleaned up."
            )


async def _graceful_shutdown(scanner: MomentumScanner) -> None:
    """Execute the graceful shutdown sequence within 10 seconds.

    The scanner.stop() method handles the full shutdown sequence:
    1. Set _running=False to stop event processing
    2. Cancel universe refresh timer
    3. Cancel status reporter scheduled tasks (idle check, daily summary)
    4. Save state via StateManager (includes TrailingStopMonitor positions)
    5. Close WebSocket connections
    6. Close universe manager resources (ccxt exchange connection)
    7. Stop health check server

    Requirements: 9.6, 20.5
    """
    # Log trailing stop positions being saved
    if hasattr(scanner, '_trailing_stop_monitor'):
        positions = scanner._trailing_stop_monitor.get_monitored_positions()
        if positions:
            logger.info(
                "Persisting %d monitored position(s) before shutdown",
                len(positions),
            )

    # Stop the scanner (handles all shutdown steps)
    await scanner.stop()


def main() -> None:
    """Entry point for the momentum scanner."""
    setup_logging()

    logger.info("Initializing momentum scanner...")

    try:
        asyncio.run(run_scanner())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting.")
    except Exception as e:
        logger.critical("Fatal error in momentum scanner: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
