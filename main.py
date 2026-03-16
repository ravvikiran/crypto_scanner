"""
Crypto Scanner CLI
Command-line interface for the crypto scanner.
"""

import asyncio
import argparse
import sys
from scanner import CryptoScanner
from storage import PerformanceTracker
from dashboard import Dashboard
from alerts import AlertManager


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
        """
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
