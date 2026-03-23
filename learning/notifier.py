"""
Resolution Notifier Module
Sends notifications for signal resolutions via Telegram and Discord.
"""

import requests
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from models import SignalOutcome, SignalResolution, SignalDirection
from config import get_config


def send_resolution_alert(
    outcome: SignalOutcome,
    overall_win_rate: float,
    strategy_win_rates: Dict[str, float]
) -> None:
    """
    Send resolution alert notification.
    
    Args:
        outcome: The resolved SignalOutcome
        overall_win_rate: Current overall win rate
        strategy_win_rates: Win rates by strategy type
    """
    config = get_config()
    alerts = config.alerts
    
    # Format the message
    message = _format_resolution_message(
        outcome, 
        overall_win_rate, 
        strategy_win_rates
    )
    
    # Send to Telegram
    if alerts.telegram_bot_token and alerts.telegram_chat_id:
        _send_telegram(alerts.telegram_bot_token, alerts.telegram_chat_id, message)
    
    # Send to Discord
    if alerts.discord_webhook_url:
        _send_discord(alerts.discord_webhook_url, outcome, overall_win_rate, strategy_win_rates)


def _format_resolution_message(
    outcome: SignalOutcome,
    overall_win_rate: float,
    strategy_win_rates: Dict[str, float]
) -> str:
    """
    Format the resolution alert message.
    
    Args:
        outcome: The resolved SignalOutcome
        overall_win_rate: Current overall win rate
        strategy_win_rates: Win rates by strategy type
        
    Returns:
        Formatted message string
    """
    # Determine emoji based on result
    if outcome.resolution in [SignalResolution.TARGET_1_HIT, SignalResolution.TARGET_2_HIT]:
        result_emoji = "✅"
        pnl_emoji = "🟢"
    else:
        result_emoji = "❌"
        pnl_emoji = "🔴"
    
    # Get strategy win rate
    strategy = outcome.strategy_type.value
    strategy_win_rate = strategy_win_rates.get(strategy, 0)
    
    # Format timestamps
    signal_timestamp = outcome.timestamp.strftime("%Y-%m-%d %H:%M")
    resolution_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Format PnL with sign
    pnl_sign = "+" if outcome.pnl_percent > 0 else ""
    
    return f"""
{result_emoji} SIGNAL RESOLUTION

{outcome.symbol} {outcome.direction.value}
Strategy: {strategy}
Timeframe: {outcome.timeframe}
Resolution: {outcome.resolution.value}

Entry: ${outcome.entry_price:.2f}
Exit: ${outcome.price_at_resolution:.2f}
{pnl_emoji} PnL: {pnl_sign}{outcome.pnl_percent:.2f}%

📊 Win Rates
Overall: {overall_win_rate:.1f}%
{strategy}: {strategy_win_rate:.1f}%

Generated: {signal_timestamp}
Resolved: {resolution_timestamp}
"""


def _send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Send message via Telegram.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        message: Message to send
        
    Returns:
        True if successful, False otherwise
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            logger.info("Resolution Telegram alert sent successfully")
            return True
        else:
            logger.error(f"Telegram alert failed: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending Telegram resolution alert: {e}")
        return False


def _send_discord(
    webhook_url: str,
    outcome: SignalOutcome,
    overall_win_rate: float,
    strategy_win_rates: Dict[str, float]
) -> bool:
    """
    Send message via Discord webhook.
    
    Args:
        webhook_url: Discord webhook URL
        outcome: The resolved SignalOutcome
        overall_win_rate: Current overall win rate
        strategy_win_rates: Win rates by strategy type
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Determine color based on result
        if outcome.resolution in [SignalResolution.TARGET_1_HIT, SignalResolution.TARGET_2_HIT]:
            color = 0x00FF00  # Green for win
        else:
            color = 0xFF0000  # Red for loss
        
        # Determine emoji
        if outcome.resolution in [SignalResolution.TARGET_1_HIT, SignalResolution.TARGET_2_HIT]:
            result_emoji = "✅"
        else:
            result_emoji = "❌"
        
        # Get strategy win rate
        strategy = outcome.strategy_type.value
        strategy_win_rate = strategy_win_rates.get(strategy, 0)
        
        # Format PnL
        pnl_sign = "+" if outcome.pnl_percent > 0 else ""
        
        embed = {
            "title": f"{result_emoji} {outcome.symbol} {outcome.direction.value} - {outcome.resolution.value}",
            "color": color,
            "fields": [
                {"name": "Strategy", "value": strategy, "inline": True},
                {"name": "Timeframe", "value": outcome.timeframe, "inline": True},
                {"name": "Entry Price", "value": f"${outcome.entry_price:.2f}", "inline": True},
                {"name": "Exit Price", "value": f"${outcome.price_at_resolution:.2f}", "inline": True},
                {"name": "PnL", "value": f"{pnl_sign}{outcome.pnl_percent:.2f}%", "inline": True},
                {"name": "Overall Win Rate", "value": f"{overall_win_rate:.1f}%", "inline": True},
                {"name": f"{strategy} Win Rate", "value": f"{strategy_win_rate:.1f}%", "inline": True}
            ],
            "footer": {
                "text": f"Generated: {outcome.timestamp.strftime('%Y-%m-%d %H:%M')} | Resolved: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            }
        }
        
        data = {
            "content": f"**Signal Resolution Alert**",
            "embeds": [embed]
        }
        
        response = requests.post(
            webhook_url,
            json=data,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            logger.info("Resolution Discord alert sent successfully")
            return True
        else:
            logger.error(f"Discord alert failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending Discord resolution alert: {e}")
        return False
