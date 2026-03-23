"""
Dashboard
Displays trading signals and market information in a formatted table.
"""

from typing import List, Optional
from datetime import datetime
from tabulate import tabulate

from models import TradingSignal, MarketSummary, TrendDirection
from config import get_config


class Dashboard:
    """Display dashboard for trading signals"""
    
    def __init__(self):
        self.config = get_config()
    
    def print_signals(self, signals: List[TradingSignal], title: str = "Trading Signals"):
        """Print signals in a formatted table"""
        
        if not signals:
            print("\n" + "=" * 60)
            print(f"📊 {title}")
            print("=" * 60)
            print("No signals generated.")
            print()
            return
        
        # Prepare table data
        table_data = []
        
        for i, signal in enumerate(signals, 1):
            direction_emoji = "🟢" if signal.direction.value == "LONG" else "🔴"
            
            table_data.append([
                i,
                f"{direction_emoji} {signal.symbol}",
                signal.strategy_type.value[:15],
                signal.timeframe,
                f"${signal.entry_zone_min:.2f}-{signal.entry_zone_max:.2f}",
                f"${signal.stop_loss:.2f}",
                f"${signal.target_1:.2f}",
                f"1:{signal.risk_reward:.1f}",
                f"{signal.confidence_score:.1f}/10"
            ])
        
        # Print header
        print("\n" + "=" * 100)
        print(f"📊 {title} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        
        # Create table
        headers = ["#", "Coin", "Strategy", "TF", "Entry Zone", "Stop", "Target", "R:R", "Conf."]
        
        print(tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            colalign=("center", "left", "left", "center", "center", "center", "center", "center", "center")
        ))
        
        print()
    
    def print_signal_details(self, signal: TradingSignal):
        """Print detailed signal information"""
        
        print("\n" + "=" * 60)
        print("📈 SIGNAL DETAILS")
        print("=" * 60)
        
        direction = "🟢 LONG" if signal.direction.value == "LONG" else "🔴 SHORT"
        
        print(f"""
Coin:         {signal.symbol} ({signal.name})
Strategy:     {signal.strategy_type.value}
Direction:    {direction}
Timeframe:     {signal.timeframe}
Confidence:   {signal.confidence_score:.1f}/10

📊 Entry Zone
  Min: ${signal.entry_zone_min:.2f}
  Max: ${signal.entry_zone_max:.2f}

🛡️ Stop Loss
  ${signal.stop_loss:.2f}

🎯 Targets
  T1: ${signal.target_1:.2f}
  T2: ${signal.target_2:.2f}

📈 Risk/Reward
  1:{signal.risk_reward:.1f}

Reasoning: {signal.reasoning}

Score Breakdown:
""")
        
        if signal.score_breakdown:
            for factor, score in signal.score_breakdown.items():
                print(f"  - {factor}: +{score:.1f}")
        
        print()
    
    def print_market_summary(self, summary: MarketSummary):
        """Print market summary"""
        
        btc_emoji = "🟢" if summary.btc_trend == TrendDirection.BULLISH else "🔴" if summary.btc_trend == TrendDirection.BEARISH else "⚪"
        
        print("\n" + "=" * 60)
        print("🌍 MARKET SUMMARY")
        print("=" * 60)
        
        print(f"""
Bitcoin:      {btc_emoji} {summary.btc_trend.value}
BTC Price:    ${summary.btc_price:,.0f}
BTC RSI:      {summary.btc_rsi:.1f}

Market Regime: {summary.market_regime}

Total Signals: {summary.total_signals}
  🟢 Longs:    {summary.long_signals}
  🔴 Shorts:   {summary.short_signals}

Scan Duration: {summary.scan_duration_seconds:.1f}s

Top Bullish:   {', '.join(summary.top_coins_bullish[:5]) if summary.top_coins_bullish else 'N/A'}
Top Bearish:   {', '.join(summary.top_coins_bearish[:5]) if summary.top_coins_bearish else 'N/A'}
""")
    
    def print_learning_stats(self, stats: dict):
        """
        Print learning system statistics.
        
        Args:
            stats: Dictionary with learning metrics from scanner.get_learning_stats()
        """
        if not stats.get('enabled', False):
            return
        
        print("\n" + "=" * 60)
        print("🧠 LEARNING SYSTEM STATS")
        print("=" * 60)
        
        print(f"""
📊 Accuracy Metrics
  Active Signals:    {stats.get('active_signals', 0)}
  Resolved Signals:  {stats.get('total_resolved', 0)}
  Overall Win Rate:   {stats.get('overall_win_rate', 0)}%
  Quality Score:     {stats.get('quality_score', 0):.1f}/10

📈 Win Rate by Strategy:""")
        
        by_strategy = stats.get('win_rate_by_strategy', {})
        if by_strategy:
            for strategy, win_rate in sorted(by_strategy.items(), key=lambda x: x[1], reverse=True):
                print(f"    {strategy}: {win_rate:.1f}%")
        else:
            print("    No data yet")
        
        print("\n⏱️ Win Rate by Timeframe:")
        
        by_timeframe = stats.get('win_rate_by_timeframe', {})
        if by_timeframe:
            for timeframe, win_rate in sorted(by_timeframe.items(), key=lambda x: x[1], reverse=True):
                print(f"    {timeframe}: {win_rate:.1f}%")
        else:
            print("    No data yet")
        
        print(f"""
💡 Insights: {stats.get('recent_insights_count', 0)} stored
   Ready to generate: {'Yes' if stats.get('insights_ready', False) else 'No (need more data)'}
""")
    
    def print_scanner_status(self, is_running: bool, last_scan: Optional[datetime] = None):
        """Print scanner status"""
        
        status = "✅ RUNNING" if is_running else "❌ STOPPED"
        last = last_scan.strftime('%Y-%m-%d %H:%M:%S') if last_scan else "Never"
        
        print("\n" + "=" * 60)
        print("🤖 SCANNER STATUS")
        print("=" * 60)
        print(f"Status:     {status}")
        print(f"Interval:   {self.config.scanner.scan_interval_minutes} minutes")
        print(f"Min Score:  {self.config.scanner.min_signal_score}")
        print(f"Last Scan:  {last}")
        print(f"Max Coins:  {self.config.scanner.max_coins_to_scan}")
        print(f"Timeframes: {', '.join(self.config.scanner.timeframes)}")
        print()
    
    def create_table_string(self, signals: List[TradingSignal]) -> str:
        """Create a simple table string for export"""
        
        if not signals:
            return "No signals"
        
        lines = []
        
        for signal in signals:
            lines.append(
                f"{signal.symbol} | {signal.direction.value} | "
                f"Entry: {signal.entry_zone_min:.2f}-{signal.entry_zone_max:.2f} | "
                f"SL: {signal.stop_loss:.2f} | "
                f"TP: {signal.target_1:.2f} | "
                f"Conf: {signal.confidence_score:.1f}"
            )
        
        return "\n".join(lines)
