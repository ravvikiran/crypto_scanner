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
from alerts.signal_publisher import get_signal_publisher

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
    
    signal_publisher = get_signal_publisher()
    
    logger.info(f"Signal Publisher initialized: {signal_publisher.get_status()}")
    
    from src.scheduler import ScannerScheduler
    scheduler = ScannerScheduler(config)
    scheduler.set_signal_publisher(signal_publisher)
    
    def scan_job():
        """Run scan in a thread-safe manner using a new event loop"""
        import asyncio
        logger.info("Running scheduled scan...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            scanner = CryptoScanner()
            signals = loop.run_until_complete(scanner.run_scan())
            
            if signals:
                publisher = get_signal_publisher()
                
                published_count = 0
                for signal in signals:
                    if publisher.can_publish():
                        if publisher.publish_signal(signal):
                            published_count += 1
                            logger.info(f"Published signal: {signal.symbol} ({signal.direction.value})")
                    else:
                        logger.info(f"Daily limit reached, skipping: {signal.symbol}")
                
                logger.info(f"Published {published_count} signals this scan")
            
            logger.info(f"Scheduled scan complete. {len(signals)} signals generated.")
        finally:
            loop.close()
    
    scheduler.add_job(scan_job)
    
    scheduler.start()
    
    if scheduler.run_mode == 'continuous':
        logger.info(f"Scheduler running in CONTINUOUS mode. Scanning every {config.get('scheduler', {}).get('continuous_interval_minutes', 15)} minutes.")
    else:
        logger.info(f"Scheduler running. Next scan: {scheduler.get_next_run()}")
    
    from config import get_config
    cfg = get_config()
    if cfg.alerts.telegram_bot_token and cfg.alerts.telegram_chat_id:
        logger.info("Telegram bot is configured - ready to send alerts")
        alert_mgr = AlertManager()
        alert_mgr.send_startup_alert()
    else:
        logger.warning("Telegram bot not configured - alerts will not be sent")
    
    logger.info("Signal monitoring active - checking SL/TP every 15 minutes")
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


def handle_trade(args):
    """Handle trade-related commands"""
    from config import get_config
    cfg = get_config()
    
    if not cfg.learning.enable_learning:
        print("Learning system is disabled. Enable in config.")
        return
    
    from learning import TradeJournal, SelfAdaptationEngine, AccuracyScorer
    
    journal = TradeJournal(cfg)
    adaptation = SelfAdaptationEngine(cfg)
    
    if args.trade_action == "journal":
        trade_id = journal.journal_entry(
            symbol=args.symbol,
            direction=args.direction,
            entry_price=float(args.entry),
            quantity=float(args.quantity),
            stop_loss=float(args.sl) if args.sl else None,
            target_1=float(args.t1) if args.t1 else None,
            target_2=float(args.t2) if args.t2 else None,
            strategy_type=args.strategy if args.strategy else "Manual",
            timeframe=args.timeframe if args.timeframe else "1h",
            notes=args.notes if args.notes else ""
        )
        print(f"✅ Trade journaled: {trade_id}")
        print(f"   Symbol: {args.symbol}")
        print(f"   Direction: {args.direction}")
        print(f"   Entry: ${args.entry}")
        print(f"   Quantity: {args.quantity}")
    
    elif args.trade_action == "exit":
        if args.trade_id:
            outcome = journal.journal_exit(
                trade_id=args.trade_id,
                exit_price=float(args.exit_price),
                exit_reason=args.reason,
                notes=args.notes if args.notes else ""
            )
            if outcome:
                pnl = outcome.pnl_percent
                emoji = "✅" if pnl > 0 else "❌"
                print(f"✅ Trade closed: {args.trade_id}")
                print(f"   {emoji} Exit: ${args.exit_price}")
                print(f"   PnL: {pnl:+.2f}%")
                
                adaptation.generate_adaptations(journal.get_outcomes())
            else:
                print("❌ Trade not found")
        else:
            outcome = journal.close_trade_by_symbol(
                symbol=args.symbol,
                exit_price=float(args.exit_price),
                exit_reason=args.reason,
                notes=args.notes if args.notes else ""
            )
            if outcome:
                pnl = outcome.pnl_percent
                emoji = "✅" if pnl > 0 else "❌"
                print(f"✅ Trade closed: {args.symbol}")
                print(f"   {emoji} Exit: ${args.exit_price}")
                print(f"   PnL: {pnl:+.2f}%")
                
                adaptation.generate_adaptations(journal.get_outcomes())
            else:
                print("❌ No open trade found for symbol")
    
    elif args.trade_action == "list":
        open_trades = journal.get_open_trades()
        if open_trades:
            print("\n📓 Open Trades:")
            for t in open_trades:
                print(f"  {t['trade_id']}: {t['symbol']} {t['direction']} @ ${t['entry_price']}")
        else:
            print("No open trades")
        
        stats = journal.get_stats()
        print(f"\nStats: {stats['closed_trades']} closed, {stats['win_rate']:.1f}% win rate")
    
    elif args.trade_action == "stats":
        stats = journal.get_stats()
        print(f"\n📊 Trade Journal Stats:")
        print(f"   Open: {stats['open_trades']}")
        print(f"   Closed: {stats['closed_trades']}")
        print(f"   Win Rate: {stats['win_rate']:.1f}%")
        print(f"   Total PnL: {stats['total_pnl']:+.2f}%")


def handle_learning(args):
    """Handle learning-related commands"""
    from config import get_config
    cfg = get_config()
    
    if not cfg.learning.enable_learning:
        print("Learning system is disabled. Enable in config.")
        return
    
    from learning import TradeJournal, SelfAdaptationEngine, AccuracyScorer, LearningEngine
    
    journal = TradeJournal(cfg)
    adaptation = SelfAdaptationEngine(cfg)
    accuracy = AccuracyScorer(cfg)
    learning_engine = LearningEngine(cfg, accuracy)
    
    if args.learning_action == "stats":
        stats = learning_engine.get_accuracy_stats()
        print("\n📊 Learning System Stats:")
        print(f"   Total Resolved: {stats.get('total_resolved', 0)}")
        print(f"   Win Rate: {stats.get('overall', 0):.1f}%")
        print(f"   Quality Score: {stats.get('quality_score', 0):.1f}/10")
        
        if stats.get('by_strategy'):
            print(f"   By Strategy:")
            for strat, wr in stats['by_strategy'].items():
                print(f"     {strat}: {wr:.1f}%")
        
        if stats.get('by_timeframe'):
            print(f"   By Timeframe:")
            for tf, wr in stats['by_timeframe'].items():
                print(f"     {tf}: {wr:.1f}%")
        
        jstats = journal.get_stats()
        print(f"\n📓 Journal Trades:")
        print(f"   Open: {jstats['open_trades']}, Closed: {jstats['closed_trades']}")
    
    elif args.learning_action == "adapt":
        all_outcomes = journal.get_outcomes()
        if accuracy.get_outcomes_count() > 0:
            all_outcomes.extend(accuracy._outcomes)
        
        adaptations = adaptation.generate_adaptations(all_outcomes)
        if adaptations:
            print("✅ Adaptation applied")
            
            recs = adaptation.get_recommendations()
            if recs:
                print("\n📋 Recommendations:")
                for r in recs:
                    print(f"   - {r}")
        else:
            print("❌ Not enough data for adaptation (need 5+ outcomes)")
    
    elif args.learning_action == "show":
        adaps = adaptation.get_all_adaptations()
        
        print("\n⚙️ Current Adaptations:")
        print("Strategy Weights:")
        for s, w in adaps.get('strategy_weights', {}).items():
            print(f"  {s}: {w:.2f}")
        
        print("Timeframe Weights:")
        for t, w in adaps.get('timeframe_weights', {}).items():
            print(f"  {t}: {w:.2f}")
        
        print("Direction Bias:")
        for d, w in adaps.get('direction_bias', {}).items():
            print(f"  {d}: {w:.2f}")
    
    elif args.learning_action == "reset":
        confirm = input("Reset all adaptations? (y/n): ")
        if confirm.lower() == 'y':
            adaptation.reset_adaptations()
            print("✅ Adaptations reset to defaults")


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
  python main.py --schedule              Run with scheduler (continuous 24x7, every 15 min)
        """
    )
    
    # Add --schedule flag
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Run with scheduler (continuous 24x7 every 15 minutes)'
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
    
    # Trade command
    trade_parser = subparsers.add_parser("trade", help="Trade journal commands")
    trade_subparsers = trade_parser.add_subparsers(dest="trade_action", help="Trade actions")
    
    journal_parser = trade_subparsers.add_parser("journal", help="Journal a new trade entry")
    journal_parser.add_argument("symbol", help="Trading symbol (e.g., BTC)")
    journal_parser.add_argument("direction", help="LONG or SHORT")
    journal_parser.add_argument("entry", help="Entry price")
    journal_parser.add_argument("quantity", help="Quantity/amount")
    journal_parser.add_argument("--sl", help="Stop loss price")
    journal_parser.add_argument("--t1", help="Target 1 price")
    journal_parser.add_argument("--t2", help="Target 2 price")
    journal_parser.add_argument("--strategy", help="Strategy type")
    journal_parser.add_argument("--timeframe", help="Timeframe")
    journal_parser.add_argument("--notes", help="Notes")
    
    exit_parser = trade_subparsers.add_parser("exit", help="Close a trade")
    exit_parser.add_argument("--trade-id", help="Trade ID to close")
    exit_parser.add_argument("--symbol", help="Symbol to close (closes earliest)")
    exit_parser.add_argument("exit_price", help="Exit price")
    exit_parser.add_argument("reason", help="Exit reason: MANUAL, TARGET_1_HIT, TARGET_2_HIT, STOP_LOSS_HIT")
    exit_parser.add_argument("--notes", help="Notes")
    
    list_parser = trade_subparsers.add_parser("list", help="List open trades")
    
    trade_stats_parser = trade_subparsers.add_parser("stats", help="Show trade journal stats")
    
    # Learning command
    learning_parser = subparsers.add_parser("learning", help="Learning system commands")
    learning_subparsers = learning_parser.add_subparsers(dest="learning_action", help="Learning actions")
    
    learning_stats_parser = learning_subparsers.add_parser("stats", help="Show learning statistics")
    
    adapt_parser = learning_subparsers.add_parser("adapt", help="Run self-adaptation analysis")
    
    show_adapt_parser = learning_subparsers.add_parser("show", help="Show current adaptations")
    
    reset_adapt_parser = learning_subparsers.add_parser("reset", help="Reset adaptations to defaults")
    
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
    
    elif args.command == "trade":
        handle_trade(args)
        
    elif args.command == "learning":
        handle_learning(args)


if __name__ == "__main__":
    main()
