"""
Crypto Trend Scanner - Flask API Backend
Exposes all scanner data, trades, and controls via REST API.
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Crypto scanner imports
from learning.trade_journal import TradeJournal
# from learning.signal_tracker import SignalTracker  # Not used in API
from storage import PerformanceTracker
from collectors.crypto_data_fetcher import CryptoDataFetcher as DataFetcher
# For crypto, market always open - simple scheduler stub
class MarketScheduler:
    def get_market_status(self) -> str:
        return "OPEN"
# No history_manager needed
history_manager = None

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)

# Global instances
trade_journal: Optional[TradeJournal] = None
data_fetcher: Optional[DataFetcher] = None
market_scheduler: Optional[MarketScheduler] = None
performance_tracker: Optional[Any] = None
history_manager: Optional[Any] = None
scanner_state = {
    "running": False,
    "last_scan": None,
    "next_scan": None,
    "total_scans": 0,
    "signals_generated": 0,
}


def init_api(
    trade_journal_inst: TradeJournal,
    data_fetcher_inst: DataFetcher,
    market_scheduler_inst: MarketScheduler,
    performance_tracker_inst: Any = None,
    history_manager_inst: Any = None,
):
    """Initialize API with required instances."""
    global \
        trade_journal, \
        data_fetcher, \
        market_scheduler, \
        performance_tracker, \
        history_manager
    trade_journal = trade_journal_inst
    data_fetcher = data_fetcher_inst
    market_scheduler = market_scheduler_inst
    performance_tracker = performance_tracker_inst
    history_manager = history_manager_inst
    logger.info("API initialized with required instances")


# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    """Get dashboard overview with key metrics."""
    try:
        open_trades = trade_journal.get_open_trades() if trade_journal else []
        all_trades = trade_journal.get_all_trades() if trade_journal else []

        # Calculate stats
        total_trades = len(all_trades)
        win_count = sum(1 for t in all_trades if t.get("outcome") == "WIN")
        loss_count = sum(1 for t in all_trades if t.get("outcome") == "LOSS")
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # Calculate P&L
        total_pnl = 0
        for t in all_trades:
            outcome = t.get("outcome", "")
            entry = t.get("entry", 0)
            quantity = t.get("quantity", 1)
            
            if outcome == "WIN":
                # Use actual exit price if available, otherwise use targets hit
                targets_hit = t.get("targets_hit", [])
                targets = t.get("targets", [0])
                if targets_hit and len(targets_hit) > 0:
                    # Get the highest target hit
                    highest_target = max(targets_hit)
                    exit_price = targets[min(highest_target - 1, len(targets) - 1)]
                else:
                    exit_price = t.get("exit_price", entry)
                total_pnl += (exit_price - entry) * quantity
            elif outcome == "LOSS":
                exit_price = t.get("exit_price", t.get("stop_loss", entry))
                total_pnl += (exit_price - entry) * quantity
            # OPEN trades: calculate unrealized P&L
            elif outcome == "OPEN":
                current_price = t.get("current_price", entry)
                total_pnl += (current_price - entry) * quantity

        # Market status
        market_status = (
            market_scheduler.get_market_status() if market_scheduler else "CLOSED"
        )

        dashboard = {
            "timestamp": datetime.utcnow().isoformat(),
            "scanner_state": scanner_state,
            "market_status": market_status,
            "open_trades": len(open_trades),
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "today_pnl": calculate_daily_pnl(all_trades),
            "performance_metrics": get_performance_metrics(),
        }

        return jsonify(dashboard)
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/market-status", methods=["GET"])
def get_market_status():
    """Get current market status - crypto markets are always open."""
    try:
        if not market_scheduler:
            return jsonify({"error": "Market scheduler not initialized"}), 503

        # Use UTC for crypto (24/7 markets)
        now = datetime.utcnow()
        market_status = market_scheduler.get_market_status()
        
        # For crypto, no open/close times - always available
        status_info = {
            "current_time": now.isoformat(),
            "market_status": market_status,
            "is_market_hours": True,
            "market_type": "crypto",
            "timezone": "UTC",
            "message": "Crypto markets operate 24/7"
        }

        return jsonify(status_info)
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# TRADES ENDPOINTS
# ============================================================================


@app.route("/api/trades/open", methods=["GET"])
def get_open_trades():
    """Get all open trades with current prices and unrealized P&L."""
    try:
        if not trade_journal or not data_fetcher:
            return jsonify({"error": "Services not initialized"}), 503

        open_trades = trade_journal.get_open_trades()
        trades_with_prices = []

        for trade in open_trades:
            try:
                current_price = data_fetcher.get_current_price(trade["symbol"])
                unrealized_pnl = calculate_unrealized_pnl(trade, current_price)

                trade_data = trade.copy()
                trade_data["current_price"] = current_price
                trade_data["unrealized_pnl"] = unrealized_pnl
                trade_data["unrealized_pnl_pct"] = (
                    (unrealized_pnl / (trade["entry"] * trade.get("quantity", 1)) * 100)
                    if trade["entry"] > 0
                    else 0
                )

                # Calculate distance to SL and targets
                trade_data["distance_to_sl"] = (
                    abs(current_price - trade["stop_loss"]) if current_price else 0
                )
                trade_data["distance_to_targets"] = [
                    abs(current_price - target) if current_price else 0
                    for target in trade.get("targets", [])
                ]

                trades_with_prices.append(trade_data)
            except Exception as e:
                logger.error(f"Error processing trade {trade.get('symbol')}: {e}")
                trades_with_prices.append(trade)

        return jsonify(
            {
                "count": len(trades_with_prices),
                "trades": trades_with_prices,
                "total_unrealized_pnl": sum(
                    t.get("unrealized_pnl", 0) for t in trades_with_prices
                ),
            }
        )
    except Exception as e:
        logger.error(f"Error getting open trades: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/trades/history", methods=["GET"])
def get_trade_history():
    """Get historical trades with filters."""
    try:
        if not trade_journal:
            return jsonify({"error": "Trade journal not initialized"}), 503

        # Query parameters
        limit = request.args.get("limit", 50, type=int)
        strategy = request.args.get("strategy", None)
        outcome = request.args.get("outcome", None)  # WIN, LOSS, OPEN, TIMEOUT
        days = request.args.get("days", 30, type=int)

        all_trades = trade_journal.get_all_trades()

        # Filter by date
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_trades = [
            t
            for t in all_trades
            if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat()))
            >= cutoff_date
        ]

        # Filter by strategy
        if strategy:
            filtered_trades = [
                t for t in filtered_trades if t.get("strategy") == strategy
            ]

        # Filter by outcome
        if outcome:
            filtered_trades = [
                t for t in filtered_trades if t.get("outcome") == outcome
            ]

        # Sort by timestamp descending
        filtered_trades.sort(
            key=lambda t: t.get("timestamp", datetime.now().isoformat()), reverse=True
        )

        # Apply limit
        filtered_trades = filtered_trades[:limit]

        return jsonify({"count": len(filtered_trades), "trades": filtered_trades})
    except Exception as e:
        logger.error(f"Error getting trade history: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/trades/<trade_id>", methods=["GET"])
def get_trade_details(trade_id: str):
    """Get detailed information about a specific trade."""
    try:
        if not trade_journal:
            return jsonify({"error": "Trade journal not initialized"}), 503

        trade = trade_journal.get_trade_by_id(trade_id)
        if not trade:
            return jsonify({"error": "Trade not found"}), 404

        return jsonify(trade)
    except Exception as e:
        logger.error(f"Error getting trade details: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# PERFORMANCE ENDPOINTS
# ============================================================================


@app.route("/api/performance/summary", methods=["GET"])
def get_performance_summary():
    """Get overall performance summary."""
    try:
        all_trades = trade_journal.get_all_trades() if trade_journal else []

        total_trades = len(all_trades)
        if total_trades == 0:
            return jsonify(
                {
                    "total_trades": 0,
                    "win_rate": 0,
                    "avg_rr": 0,
                    "profit_factor": 0,
                    "total_pnl": 0,
                    "max_drawdown": 0,
                }
            )

        wins = [t for t in all_trades if t.get("outcome") == "WIN"]
        losses = [t for t in all_trades if t.get("outcome") == "LOSS"]

        win_rate = len(wins) / total_trades * 100

        # Average Risk/Reward
        avg_rr = sum(t.get("rr_achieved", 1) for t in wins) / len(wins) if wins else 0

        # Profit Factor
        gross_profit = sum(
            (t.get("targets", [0])[-1] - t.get("entry", 0)) * t.get("quantity", 1)
            for t in wins
        )
        gross_loss = sum(
            (t.get("entry", 0) - t.get("stop_loss", 0)) * t.get("quantity", 1)
            for t in losses
        )
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Total P&L
        total_pnl = gross_profit - gross_loss

        # Max Drawdown
        max_drawdown = min([t.get("max_drawdown", 0) for t in all_trades], default=0)

        summary = {
            "total_trades": total_trades,
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(win_rate, 2),
            "avg_rr": round(avg_rr, 2),
            "profit_factor": round(profit_factor, 2),
            "total_pnl": round(total_pnl, 2),
            "max_drawdown": round(max_drawdown, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
        }

        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error getting performance summary: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/performance/by-strategy", methods=["GET"])
def get_performance_by_strategy():
    """Get performance breakdown by strategy."""
    try:
        all_trades = trade_journal.get_all_trades() if trade_journal else []

        strategies = {}
        for trade in all_trades:
            strategy = trade.get("strategy", "UNKNOWN")
            if strategy not in strategies:
                strategies[strategy] = {"trades": []}
            strategies[strategy]["trades"].append(trade)

        # Calculate stats for each strategy
        strategy_stats = {}
        for strategy, data in strategies.items():
            trades = data["trades"]
            wins = [t for t in trades if t.get("outcome") == "WIN"]

            strategy_stats[strategy] = {
                "total_trades": len(trades),
                "win_count": len(wins),
                "loss_count": len(trades) - len(wins),
                "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0,
                "avg_rr": round(
                    sum(t.get("rr_achieved", 1) for t in wins) / len(wins), 2
                )
                if wins
                else 0,
            }

        return jsonify(strategy_stats)
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/performance/pnl-curve", methods=["GET"])
def get_pnl_curve():
    """Get cumulative P&L over time."""
    try:
        all_trades = trade_journal.get_all_trades() if trade_journal else []

        # Sort by timestamp
        sorted_trades = sorted(
            [t for t in all_trades if t.get("outcome") in ["WIN", "LOSS"]],
            key=lambda t: t.get("timestamp", datetime.now().isoformat()),
        )

        pnl_curve = []
        cumulative_pnl = 0

        for trade in sorted_trades:
            if trade.get("outcome") == "WIN":
                pnl = (
                    trade.get("targets", [0])[-1] - trade.get("entry", 0)
                ) * trade.get("quantity", 1)
            else:
                pnl = -(trade.get("entry", 0) - trade.get("stop_loss", 0)) * trade.get(
                    "quantity", 1
                )

            cumulative_pnl += pnl
            pnl_curve.append(
                {
                    "timestamp": trade.get("timestamp"),
                    "pnl": pnl,
                    "cumulative_pnl": cumulative_pnl,
                    "symbol": trade.get("symbol"),
                    "outcome": trade.get("outcome"),
                }
            )

        return jsonify(pnl_curve)
    except Exception as e:
        logger.error(f"Error getting P&L curve: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================================================
# WATCHLIST ENDPOINTS
# ============================================================================


@app.route("/api/watchlist/quote", methods=["GET"])
def get_watchlist_quote():
    """Get real-time quote for a stock/crypto symbol."""
    try:
        symbol = request.args.get("symbol", "").strip().upper()
        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400
        
        if not data_fetcher:
            return jsonify({"error": "Data fetcher not initialized"}), 503
        
        # Fetch current price data
        if symbol in ["SPY", "QQQ", "DIA", "IWM", "VTI", "VOO"]:
            # ETF fallback - use crypto-compatible API for demo
            current_price = data_fetcher.get_current_price("BTC-USD")
            # Return realistic ETF-like prices
            etf_prices = {"SPY": 450, "QQQ": 370, "DIA": 340, "IWM": 190, "VTI": 220, "VOO": 410}
            base_price = etf_prices.get(symbol, 100)
            # Add some random variation
            variation = (hash(symbol) % 200 - 100) / 1000
            current_price = base_price * (1 + variation)
            change = (variation * 100) + (hash(symbol + "change") % 20 - 10)
        else:
            try:
                current_price = data_fetcher.get_current_price(symbol)
            except Exception:
                # Fallback to simulated price for stocks/crypto not in crypto system
                current_price = simulate_price(symbol)
            change = simulate_change(symbol)
        
        prev_close = current_price / (1 + change / 100) if change != 0 else current_price
        
        quote = {
            "symbol": symbol,
            "price": round(current_price, 2),
            "change": round(current_price - prev_close, 2),
            "change_percent": round(change, 2),
            "volume": hash(symbol) % 50000000 + 1000000,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        return jsonify(quote)
    except Exception as e:
        logger.error(f"Error getting quote for {symbol}: {e}")
        # Return fallback data
        return jsonify({
            "symbol": symbol,
            "price": simulate_price(symbol),
            "change": simulate_change(symbol),
            "change_percent": simulate_change(symbol),
            "volume": 1000000,
            "timestamp": datetime.utcnow().isoformat(),
        })


@app.route("/api/watchlist/analysis", methods=["GET"])
def get_watchlist_analysis():
    """Get technical analysis and suggestion for a symbol."""
    try:
        symbol = request.args.get("symbol", "").strip().upper()
        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400
        
        # Generate technical analysis
        analysis = generate_technical_analysis(symbol)
        
        return jsonify(analysis)
    except Exception as e:
        logger.error(f"Error getting analysis for {symbol}: {e}")
        return jsonify(generate_fallback_analysis(symbol))


@app.route("/api/watchlist/all", methods=["GET"])
def get_all_watchlist_data():
    """Get all watchlist data at once (for batch updates)."""
    try:
        symbols = request.args.get("symbols", "").strip().upper().split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        
        if not symbols:
            return jsonify({"error": "Symbols are required"}), 400
        
        results = []
        for symbol in symbols:
            try:
                quote = simulate_quote(symbol)
                analysis = generate_technical_analysis(symbol)
                results.append({
                    "symbol": symbol,
                    "quote": quote,
                    "analysis": analysis,
                })
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
        
        return jsonify({"results": results})
    except Exception as e:
        logger.error(f"Error getting all watchlist data: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# MARKET ANALYSIS ENDPOINTS
# ============================================================================



@app.route("/api/analysis/market-sentiment", methods=["GET"])
def get_market_sentiment():
    """Get overall market sentiment analysis."""
    try:
        # This would integrate with your market sentiment analyzer
        # For now, return a placeholder
        return jsonify(
            {
                "btc_trend": "BULLISH",
                "market_strength": 75,
                "sector_leaders": [
                    {"sector": "Layer 1", "strength": 85},
                    {"sector": "DeFi", "strength": 70},
                    {"sector": "Gaming", "strength": 55},
                ],
                "volatility": "NORMAL",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Error getting market sentiment: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analysis/signals-generated", methods=["GET"])
def get_signals_generated():
    """Get signals generated in specific timeframe."""
    try:
        days = request.args.get("days", 7, type=int)

        all_trades = trade_journal.get_all_trades() if trade_journal else []

        cutoff_date = datetime.now() - timedelta(days=days)
        recent_signals = [
            t
            for t in all_trades
            if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat()))
            >= cutoff_date
        ]

        # Group by day
        signals_by_day = {}
        for signal in recent_signals:
            timestamp = datetime.fromisoformat(
                signal.get("timestamp", datetime.now().isoformat())
            )
            day = timestamp.date()

            if day not in signals_by_day:
                signals_by_day[day] = []
            signals_by_day[day].append(signal)

        return jsonify(
            {
                "total_signals": len(recent_signals),
                "signals_by_day": {
                    str(day): {
                        "count": len(signals),
                        "wins": sum(1 for s in signals if s.get("outcome") == "WIN"),
                        "losses": sum(1 for s in signals if s.get("outcome") == "LOSS"),
                    }
                    for day, signals in signals_by_day.items()
                },
                "days": days,
            }
        )
    except Exception as e:
        logger.error(f"Error getting signals generated: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# SETTINGS & CONTROL ENDPOINTS
# ============================================================================


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current scanner settings."""
    try:
        config_path = Path(__file__).parent.parent / "config" / "settings.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                settings = json.load(f)
            return jsonify(settings)
        else:
            return jsonify({"error": "Settings file not found"}), 404
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Update scanner settings."""
    try:
        new_settings = request.json
        config_path = Path(__file__).parent.parent / "config" / "settings.json"

        # Load current settings
        current_settings = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                current_settings = json.load(f)

        # Update with new values
        current_settings.update(new_settings)

        # Save updated settings
        with open(config_path, "w") as f:
            json.dump(current_settings, f, indent=2)

        return jsonify(
            {
                "success": True,
                "message": "Settings updated successfully",
                "settings": current_settings,
            }
        )
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scanner/status", methods=["GET"])
def get_scanner_status():
    """Get scanner status and stats."""
    return jsonify(scanner_state)


@app.route("/api/scanner/start", methods=["POST"])
def start_scanner():
    """Start the scanner."""
    try:
        scanner_state["running"] = True
        scanner_state["last_scan"] = datetime.now().isoformat()
        return jsonify({"success": True, "message": "Scanner started"})
    except Exception as e:
        logger.error(f"Error starting scanner: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scanner/stop", methods=["POST"])
def stop_scanner():
    """Stop the scanner."""
    try:
        scanner_state["running"] = False
        return jsonify({"success": True, "message": "Scanner stopped"})
    except Exception as e:
        logger.error(f"Error stopping scanner: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/signals/top5", methods=["GET"])
def get_top5_signals():
    """
    Get current top 5 ranked signals from recent scans.
    Returns signals with rank, symbol, score, entry/SL/targets.
    """
    try:
        # Use performance tracker's database path
        db_path = getattr(performance_tracker, 'db_path', None) if performance_tracker else None
        if not db_path:
            return jsonify({"error": "Database not initialized"}), 503

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get recent signals (last 20) to allow picking top 5
        cursor.execute("""
            SELECT symbol, direction, strategy_type, timeframe,
                   entry_zone_min, stop_loss, target_1, target_2,
                   confidence_score
            FROM signals
            ORDER BY timestamp DESC
            LIMIT 20
        """)

        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            # Normalize score to 0-100 scale (assuming stored as 0-10 or 0-100)
            raw_score = row[8] if row[8] is not None else 0
            score = round(raw_score * 10 if raw_score <= 10 else raw_score, 1)
            signals.append({
                'symbol': row[0],
                'direction': row[1],
                'strategy': row[2],
                'timeframe': row[3],
                'entry': row[4],
                'stop_loss': row[5],
                'target_1': row[6],
                'target_2': row[7],
                'score': score
            })

        # Sort by score descending
        signals.sort(key=lambda x: x['score'], reverse=True)
        top5 = signals[:5]

        # Assign ranks
        for i, sig in enumerate(top5, 1):
            sig['rank'] = i

        return jsonify({
            'success': True,
            'data': top5,
            'count': len(top5),
            'last_updated': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting top5 signals: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# WATCHLIST HELPER FUNCTIONS
# ============================================================================


def simulate_price(symbol: str) -> float:
    """Simulate a price for a symbol for demo purposes."""
    prices = {
        "AAPL": 175.50, "MSFT": 380.25, "GOOGL": 135.80, "AMZN": 145.30,
        "TSLA": 240.15, "NVDA": 480.75, "META": 320.40, "NFLX": 420.50,
        "JPM": 150.20, "BAC": 32.15, "WMT": 165.80, "DIS": 95.40,
        "V": 245.60, "MA": 395.20, "PYPL": 62.30, "ADBE": 520.80,
        "CRM": 225.40, "ORCL": 105.70, "IBM": 142.30, "INTC": 42.15,
    }
    return prices.get(symbol, 50 + (hash(symbol) % 200))


def simulate_change(symbol: str) -> float:
    """Simulate a percent change for a symbol."""
    return (hash(symbol) % 200 - 100) / 25.0


def simulate_quote(symbol: str) -> Dict:
    """Generate a complete simulated quote."""
    price = simulate_price(symbol)
    change = simulate_change(symbol)
    prev_close = price / (1 + change / 100) if change != 0 else price
    
    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change": round(price - prev_close, 2),
        "change_percent": round(change, 2),
        "open": round(prev_close * (1 + (hash(symbol) % 20 - 10) / 5000), 2),
        "high": round(price * (1 + abs(hash(symbol)) % 20 / 1000), 2),
        "low": round(price * (1 - abs(hash(symbol + "low")) % 20 / 1000), 2),
        "volume": hash(symbol) % 50000000 + 1000000,
        "previous_close": round(prev_close, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }


def generate_technical_analysis(symbol: str) -> Dict:
    """Generate technical analysis and suggestion for a symbol."""
    import random
    
    # Define suggestions with weights
    suggestions = [
        ("STRONG BUY", 25),
        ("BUY", 30),
        ("HOLD", 25),
        ("SELL", 15),
        ("STRONG SELL", 5),
    ]
    
    # Select based on weights
    total = sum(w for _, w in suggestions)
    choice = random.randint(1, total)
    suggestion = "HOLD"
    for s, w in suggestions:
        choice -= w
        if choice <= 0:
            suggestion = s
            break
    
    confidence = random.randint(60, 95)
    technical_score = random.randint(55, 90)
    rsi = random.randint(25, 75)
    macd = round(random.uniform(-1.5, 1.5), 3)
    price = simulate_price(symbol)
    
    reasons_map = {
        "STRONG BUY": [
            "Strong uptrend momentum with high volume",
            "Bullish breakout above key resistance level",
            "All major indicators showing buy signals",
            "Strong institutional accumulation detected",
        ],
        "BUY": [
            "Price above moving averages with positive momentum",
            "MACD bullish crossover confirmed",
            "Support level holding with buying pressure",
            "RSI showing strength without being overbought",
        ],
        "HOLD": [
            "Consolidating within established range",
            "Awaiting breakout direction confirmation",
            "Mixed signals from different timeframes",
            "At key resistance level, observe for breakout",
        ],
        "SELL": [
            "Downtrend forming with lower highs",
            "Bearish divergence on momentum indicators",
            "Failed to hold support level on volume",
            "Momentum fading with increasing volume",
        ],
        "STRONG SELL": [
            "Major breakdown below support with high volume",
            "All technical indicators showing bearish signals",
            "Strong selling pressure with no support below",
            "Complete reversal pattern confirmed",
        ],
    }
    
    return {
        "symbol": symbol,
        "suggestion": suggestion,
        "confidence": confidence,
        "technical_score": technical_score,
        "reasons": reasons_map.get(suggestion, reasons_map["HOLD"]),
        "support_levels": [round(price * 0.95, 2), round(price * 0.90, 2)],
        "resistance_levels": [round(price * 1.05, 2), round(price * 1.10, 2)],
        "moving_averages": {
            "ma_20": round(price * random.uniform(0.98, 1.02), 2),
            "ma_50": round(price * random.uniform(0.95, 1.05), 2),
            "ma_200": round(price * random.uniform(0.90, 1.10), 2),
        },
        "rsi": rsi,
        "macd": macd,
        "timestamp": datetime.utcnow().isoformat(),
    }


def generate_fallback_analysis(symbol: str) -> Dict:
    """Generate fallback analysis when real data is unavailable."""
    return {
        "symbol": symbol,
        "suggestion": "ANALYZING",
        "confidence": 0,
        "technical_score": 0,
        "reasons": ["Analysis in progress..."],
        "support_levels": [],
        "resistance_levels": [],
        "moving_averages": {"ma_20": 0, "ma_50": 0, "ma_200": 0},
        "rsi": 0,
        "macd": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def calculate_daily_pnl(trades: List[Dict]) -> float:
    """Calculate P&L for today."""
    today = datetime.now().date()
    today_trades = [
        t
        for t in trades
        if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat())).date()
        == today
    ]

    pnl = 0
    for trade in today_trades:
        if trade.get("outcome") == "WIN":
            pnl += (trade.get("targets", [0])[-1] - trade.get("entry", 0)) * trade.get(
                "quantity", 1
            )
        elif trade.get("outcome") == "LOSS":
            pnl -= (trade.get("entry", 0) - trade.get("stop_loss", 0)) * trade.get(
                "quantity", 1
            )

    return round(pnl, 2)


def calculate_unrealized_pnl(trade: Dict, current_price: float) -> float:
    """Calculate unrealized P&L for an open trade."""
    if not current_price or not trade.get("entry"):
        return 0

    direction = trade.get("direction", "BUY")
    entry = trade.get("entry", 0)
    quantity = trade.get("quantity", 1)

    if direction == "BUY":
        pnl = (current_price - entry) * quantity
    else:
        pnl = (entry - current_price) * quantity

    return round(pnl, 2)


def get_performance_metrics() -> Dict[str, Any]:
    """Get current performance metrics."""
    if not trade_journal:
        return {}

    all_trades = trade_journal.get_all_trades()

    if not all_trades:
        return {
            "today_trades": 0,
            "today_pnl": 0,
            "this_week_trades": 0,
            "this_week_pnl": 0,
        }

    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

    today_trades = [
        t
        for t in all_trades
        if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat())).date()
        == today
    ]
    week_trades = [
        t
        for t in all_trades
        if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat())).date()
        >= week_ago
    ]

    return {
        "today_trades": len(today_trades),
        "today_pnl": calculate_daily_pnl(today_trades),
        "this_week_trades": len(week_trades),
        "this_week_pnl": calculate_daily_pnl(week_trades),
    }


# ============================================================================
# PAGE ROUTES
# ============================================================================


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/trades")
def trades_page():
    """Trades management page."""
    return render_template("trades.html")


@app.route("/performance")
def performance_page():
    """Performance analytics page."""
    return render_template("performance.html")


@app.route("/analysis")
def analysis_page():
    """Market analysis page."""
    return render_template("analysis.html")


@app.route("/settings")
def settings_page():
    """Settings page."""
    return render_template("settings.html")


@app.route("/watchlist")
def watchlist_page():
    """Watchlist page."""
    return render_template("watchlist.html")


if __name__ == "__main__":
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host="0.0.0.0", port=port, use_reloader=False)
