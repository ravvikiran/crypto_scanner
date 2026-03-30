"""
Crypto Scanner CLI
Command-line interface for the crypto scanner.
"""

import asyncio
import argparse
import sys
import os
import logging
from pathlib import Path
from scanner import CryptoScanner
from storage import PerformanceTracker
from dashboard import Dashboard
from alerts import AlertManager

# Try to import yaml for config loading
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Global config storage
_config = {}


def load_yaml_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    if not YAML_AVAILABLE:
        return {}
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def setup_logging(config: dict = None):
    """Setup logging configuration"""
    if config is None:
        config = {}
    
    log_config = config.get('logging', {})
    
    level_str = log_config.get('level', 'INFO')
    level = getattr(logging, level_str.upper())
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create logs directory if it doesn't exist
    log_file = log_config.get('file', 'logs/scanner.log')
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    
    return logging.getLogger(__name__)


def run_scheduled(config: dict, logger):
    """
    Run the scanner with scheduler and Telegram bot (both running together)
    """
    logger.info("Initializing scheduler and Telegram bot...")
    
    # Create scheduler
    from src.scheduler import ScannerScheduler
    scheduler = ScannerScheduler(config)
    
    # Add the scan job
    def scan_job():
        """Run scan in a thread-safe manner using a new event loop"""
        import asyncio
        logger.info("Running scheduled scan...")
        
        # Create a new event loop for this thread to avoid conflicts
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            scanner = CryptoScanner()
            signals = loop.run_until_complete(scanner.run_scan())
            if signals:
                scanner.send_alerts(signals)
            logger.info(f"Scheduled scan complete. {len(signals)} signals generated.")
        finally:
            loop.close()
    
    scheduler.add_job(scan_job)
    
    # Add signal monitoring job if SIE is enabled
    sie_config = config.get('signal_intelligence', {})
    if sie_config.get('enabled', True):
        def monitor_job():
            logger.info("Running signal monitoring check...")
            # Use existing ResolutionChecker for signal checking
            from config import get_config
            
            try:
                cfg = get_config()
                if cfg.learning.enable_learning:
                    from learning import ResolutionChecker
                    resolution_checker = ResolutionChecker(cfg)
                    resolution_checker.run_check_sync()
                    logger.info("Signal monitoring check complete.")
            except Exception as e:
                logger.error(f"Error in monitor job: {e}")
        
        scheduler.add_monitor_job(monitor_job)
    
    # Start scheduler
    scheduler.start()
    
    logger.info(f"Scheduler running. Next scan: {scheduler.get_next_run()}")
    
    # Check if Telegram is configured for alerts
    from config import get_config
    cfg = get_config()
    if cfg.alerts.telegram_bot_token and cfg.alerts.telegram_chat_id:
        logger.info("Telegram bot is configured - ready to send alerts")
    else:
        logger.warning("Telegram bot not configured - alerts will not be sent")
    
    logger.info("System running. Scanner at 3 PM Mon-Fri.")
    logger.info("Press Ctrl+C to stop")
    
    try:
        import time
        while True:
            time.sleep(60)
            logger.debug(f"Next scan: {scheduler.get_next_run()}")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.stop()


async def run_scan(args):
    """Run a single scan"""
    scanner = CryptoScanner()
    
    signals = await scanner.run_scan()
    
    if args.display:
        scanner.display_results(signals)
    
    if args.alerts and signals:
        scanner.send_alerts(signals)
    
    return len(signals)


async def run_continuous(args):
    """Run continuous scanner"""
    scanner = CryptoScanner()
    
    if args.display:
        scanner.display_results([])
    
    await scanner.run_continuous()


def show_stats(args):
    """Show performance statistics"""
    tracker = PerformanceTracker()
    stats = tracker.get_statistics()
    
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE STATISTICS")
    print("=" * 60)
    
    print(f"""
Signals Generated:
  Total:     {stats.get('total_signals', 0)}
  Long:      {stats.get('long_signals', 0)}
  Short:     {stats.get('short_signals', 0)}
  Avg Conf:  {stats.get('avg_confidence', 0):.1f}/10

Trades:
  Closed:    {stats.get('closed_trades', 0)}
  Wins:      {stats.get('winning_trades', 0)}
  Losses:    {stats.get('losing_trades', 0)}
  Win Rate:  {stats.get('win_rate', 0):.1f}%

Avg Win:    {stats.get('avg_win', 0):.2f}%
Avg Loss:   {stats.get('avg_loss', 0):.2f}%

Scans (7d): {stats.get('scans_last_7_days', 0)}
""")
    
    if args.export:
        tracker.export_signals_csv(args.export)
        print(f"Exported to: {args.export}")


def test_alerts(args):
    """Test alert configuration"""
    alert_mgr = AlertManager()
    success = alert_mgr.send_test_alert()
    
    if success:
        print("✅ Test alert sent successfully!")
    else:
        print("❌ Test alert failed. Check configuration.")


def main():
    """Main CLI entry point"""
    # Load YAML config if available
    yaml_config = load_yaml_config()
    
    parser = argparse.ArgumentParser(
        description="Crypto Momentum & Reversal AI Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py scan                    Run a single scan
  python main.py scan --alerts           Run scan and send alerts
  python main.py continuous              Run continuous scanner
  python main.py stats                   Show performance statistics
  python main.py test                    Test alert configuration
  python main.py --schedule              Run with scheduler (daily at 3 PM Mon-Fri)
        """
    )
    
    # Add --schedule flag
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Run with scheduler (daily at 3 PM Mon-Fri)'
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Run a single market scan")
    scan_parser.add_argument("--display", "-d", action="store_true", help="Display results")
    scan_parser.add_argument("--alerts", "-a", action="store_true", help="Send alerts")
    
    # Continuous command
    cont_parser = subparsers.add_parser("continuous", help="Run scanner continuously")
    cont_parser.add_argument("--display", "-d", action="store_true", help="Display results")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show performance statistics")
    stats_parser.add_argument("--export", "-e", type=str, help="Export to CSV file")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test alert configuration")
    
    args = parser.parse_args()
    
    # Handle --schedule mode (runs without subcommand)
    if args.schedule:
        logger = setup_logging(yaml_config)
        run_scheduled(yaml_config, logger)
        return
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute command
    if args.command == "scan":
        count = asyncio.run(run_scan(args))
        print(f"\n✅ Scan complete. {count} signals generated.")
        
    elif args.command == "continuous":
        print("🔄 Starting continuous scanner... Press Ctrl+C to stop.")
        asyncio.run(run_continuous(args))
        
    elif args.command == "stats":
        show_stats(args)
        
    elif args.command == "test":
        test_alerts(args)


if __name__ == "__main__":
    main()
