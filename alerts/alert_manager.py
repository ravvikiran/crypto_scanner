"""
Alert Manager
Manages all alert notifications via Telegram, Discord, Email, and TradingView.
"""

import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from loguru import logger

from models import TradingSignal, SignalDirection, StrategyType
from config import get_config
from alerts.telegram_bot import SignalDuplicateChecker


class AlertManager:
    """Manages all alert notifications"""
    
    def __init__(self):
        self.config = get_config()
        self.alerts = self.config.alerts
        self._duplicate_checker = SignalDuplicateChecker(cooldown_hours=24)
        self._last_no_signals_message: Optional[datetime] = None
        self._startup_alert_sent = False
        self._market_sentiment_enabled = getattr(self.alerts, 'use_market_sentiment_filter', True)
    
    def send_startup_alert(self):
        """Send a startup alert to confirm the scanner is running"""
        if self._startup_alert_sent:
            return
        if not self.alerts.telegram_bot_token:
            return
        
        self._startup_alert_sent = True
        
        message = "🔄 <b>QuantGrid Scanner Started</b>\n\nScanner is now running and monitoring for signals.\n\n⏰ Scan interval: every 15 minutes"
        self._send_telegram(message)
    
    def send_all_alerts(self, signals: List[TradingSignal], market_sentiment=None):
        """
        Send alerts through all configured channels.
        
        Args:
            signals: List of trading signals
            market_sentiment: Optional MarketSentimentScore for filtering
        """
        
        threshold = self.alerts.confidence_threshold
        if threshold <= 10:
            threshold = threshold * 10
        
        qualified_signals = [s for s in signals if s.normalized_confidence >= threshold]
        
        # NEW: Filter signals by market sentiment if enabled
        if self._market_sentiment_enabled and market_sentiment:
            qualified_signals = self._filter_signals_by_sentiment(qualified_signals, market_sentiment)
        
        if not qualified_signals:
            self._send_no_signals_message(market_sentiment)
            return
        
        signals_to_send = []
        for signal in qualified_signals:
            if self._duplicate_checker.should_send(signal.id):
                signals_to_send.append(signal)
                self._duplicate_checker.mark_sent(signal.id)
        
        if not signals_to_send:
            logger.info("All signals in cooldown - skipping alerts")
            return
        
        for signal in signals_to_send:
            message = signal.to_alert_string()
            # Add market sentiment info to message
            if market_sentiment:
                message += self._append_sentiment_info(market_sentiment)
            self._send_telegram(message)
            self._send_discord_single(signal, market_sentiment)
            self._send_email([signal], market_sentiment)
    
    def send_trend_alerts(self, trend_alerts: List):
        """
        Send market trend alerts through all configured channels.
        
        Args:
            trend_alerts: List of TrendAlert objects
        """
        
        if not trend_alerts:
            return
        
        for alert in trend_alerts:
            # Send via Telegram
            self._send_telegram(alert.message)
            
            # Send via Discord if available
            if self.alerts.discord_webhook_url:
                self._send_discord_trend_alert(alert)
            
            logger.info(f"Trend alert sent: {alert.alert_type.value}")
    
    def _send_discord_trend_alert(self, trend_alert):
        """Send trend alert via Discord"""
        
        try:
            # Color based on alert type
            if "BULLISH" in trend_alert.alert_type.value:
                color = 0x00FF00  # Green
            elif "BEARISH" in trend_alert.alert_type.value:
                color = 0xFF0000  # Red
            else:
                color = 0xFFA500  # Orange
            
            embed = {
                "title": trend_alert.alert_type.value,
                "description": trend_alert.message,
                "color": color,
                "fields": [
                    {"name": "Previous Score", "value": f"{trend_alert.previous_score:.0f}/100", "inline": True},
                    {"name": "Current Score", "value": f"{trend_alert.current_score:.0f}/100", "inline": True},
                    {"name": "Impact Level", "value": trend_alert.impact_level.upper(), "inline": True}
                ],
                "footer": {"text": f"Timestamp: {trend_alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"}
            }
            
            data = {"content": "", "embeds": [embed]}
            
            response = requests.post(
                self.alerts.discord_webhook_url,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.debug(f"Discord trend alert sent: {trend_alert.alert_type.value}")
            else:
                logger.error(f"Discord trend alert failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Discord trend alert: {e}")
    
    def _filter_signals_by_sentiment(self, signals: List[TradingSignal], market_sentiment) -> List[TradingSignal]:
        """
        Filter signals based on market sentiment favorability.
        
        Returns only signals that align with market sentiment:
        - LONG signals: Keep if market is bullish
        - SHORT signals: Keep if market is bearish
        - In neutral sentiment: Keep only high-confidence signals
        """
        
        if not market_sentiment:
            return signals
        
        filtered = []
        
        for signal in signals:
            is_long = signal.direction.value == "LONG"
            
            # Check sentiment favorability
            if is_long:
                is_favorable = market_sentiment.sentiment.value in ["VERY_BULLISH", "BULLISH"]
            else:  # SHORT
                is_favorable = market_sentiment.sentiment.value in ["VERY_BEARISH", "BEARISH"]
            
            # In NEUTRAL sentiment, be more strict
            if market_sentiment.sentiment.value == "NEUTRAL":
                if is_long and market_sentiment.market_strength > 55:
                    is_favorable = True
                elif not is_long and market_sentiment.market_strength < 45:
                    is_favorable = True
                else:
                    # In neutral, only allow very high confidence signals
                    is_favorable = signal.normalized_confidence >= 75
            
            if is_favorable:
                filtered.append(signal)
                logger.info(
                    f"Signal {signal.symbol} {signal.direction.value} kept - "
                    f"favorable for {market_sentiment.sentiment.value}"
                )
            else:
                logger.info(
                    f"Signal {signal.symbol} {signal.direction.value} filtered - "
                    f"not favorable for {market_sentiment.sentiment.value}"
                )
        
        return filtered
    
    def _append_sentiment_info(self, market_sentiment) -> str:
        """Append market sentiment information to alert message"""
        
        sentiment_str = f"""

📊 <b>Market Context</b>
Sentiment: {market_sentiment.sentiment.value} ({market_sentiment.score:.0f}/100)
Gainers: {market_sentiment.gainers_pct:.0f}% | Losers: {market_sentiment.losers_pct:.0f}%
Market Strength: {market_sentiment.market_strength:.0f}/100
Altcoin Strength: {market_sentiment.altcoin_strength:.0f}/100
Volatility: {market_sentiment.volatility_level.upper()}
BTC Trend: {market_sentiment.btc_trend.value}

ℹ️ {market_sentiment.reason}
"""
        
        return sentiment_str
    
    def _send_no_signals_message(self, market_sentiment=None):
        """Send message when no signals meet confidence threshold"""
        now = datetime.now()
        
        if self._last_no_signals_message:
            if (now - self._last_no_signals_message).total_seconds() < 86400:
                return
        
        self._last_no_signals_message = now
        
        message = "📊 No coins met confidence threshold (≥6.0) this scan."
        
        # Include market sentiment info if available
        if market_sentiment:
            message += f"\n\n📈 Market Status: {market_sentiment.sentiment.value} ({market_sentiment.score:.0f}/100)\n"
            message += f"Reason: {market_sentiment.reason}"
        
        self._send_telegram(message)
    
    def _send_discord_single(self, signal: TradingSignal, market_sentiment=None):
        """Send single signal via Discord webhook"""
        if not self.alerts.discord_webhook_url:
            return
        
        try:
            color = 0x00FF00 if signal.direction.value == "LONG" else 0xFF0000
            
            embed = {
                "title": f"{signal.direction.value} - {signal.symbol}",
                "description": signal.reasoning,
                "color": color,
                "fields": [
                    {"name": "Entry Zone", "value": f"{signal.entry_zone_min:.2f} - {signal.entry_zone_max:.2f}", "inline": True},
                    {"name": "Stop Loss", "value": f"{signal.stop_loss:.2f}", "inline": True},
                    {"name": "Target 1", "value": f"{signal.target_1:.2f}", "inline": True},
                    {"name": "Strategy", "value": signal.strategy_type.value, "inline": True},
                    {"name": "Timeframe", "value": signal.timeframe, "inline": True},
                    {"name": "Confidence", "value": f"{signal.confidence_score:.1f}/10", "inline": True}
                ],
                "footer": {"text": f"Risk/Reward: 1:{signal.risk_reward:.1f}"}
            }
            
            data = {"content": "", "embeds": [embed]}
            
            response = requests.post(
                self.alerts.discord_webhook_url,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info(f"Discord alert sent for {signal.symbol}")
            else:
                logger.error(f"Discord alert failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
    
    def _format_signals_message(self, signals: List[TradingSignal]) -> str:
        """Format signals into alert message"""
        
        emoji = "🚀"
        
        if len(signals) == 1:
            signal = signals[0]
            return signal.to_alert_string()
        
        message = f"""
{emoji} MULTIPLE SETUPS DETECTED - {len(signals)} Signals

"""
        
        for i, signal in enumerate(signals, 1):
            direction_emoji = "🟢" if signal.direction.value == "LONG" else "🔴"
            message += f"""
{i}. {direction_emoji} {signal.symbol} - {signal.direction.value}
   Strategy: {signal.strategy_type.value}
   Entry: {signal.entry_zone_min:.2f}-{signal.entry_zone_max:.2f}
   Stop: {signal.stop_loss:.2f}
   Target: {signal.target_1:.2f}
   Confidence: {signal.confidence_score:.1f}/10

"""
        
        return message
    
    def _send_telegram(self, message: str):
        """Send message via Telegram bot"""
        try:
            # Determine which chat ID is being used
            if self.alerts.telegram_channel_chat_id:
                chat_id = self.alerts.telegram_channel_chat_id
                chat_type = "CHANNEL"
            elif self.alerts.telegram_chat_id:
                chat_id = self.alerts.telegram_chat_id
                chat_type = "USER/GROUP"
            else:
                logger.warning("Telegram: No chat_id or channel_chat_id configured")
                return
            
            if chat_id and chat_id.startswith('@'):
                logger.warning(f"Telegram: Using username '{chat_id}'. For better reliability, use numeric chat ID")
            
            url = f"https://api.telegram.org/bot{self.alerts.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            logger.debug(f"Sending Telegram message to {chat_type} (ID: {chat_id})")
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"✅ Telegram alert sent successfully to {chat_type}")
            else:
                error_data = response.json() if response.text else {}
                error_code = error_data.get("error_code", response.status_code)
                error_desc = error_data.get("description", response.text)
                
                logger.error(f"Telegram error ({error_code}): {error_desc}")
                
                # Provide helpful diagnostic info
                if error_code == 403:
                    logger.error(f"❌ Bot cannot send to this {chat_type} ID: {chat_id}")
                    logger.error("   Possible causes:")
                    logger.error("   1. Bot is not added to the channel/group")
                    logger.error("   2. Bot doesn't have 'send message' permission")
                    logger.error(f"   3. {chat_type} ID might be a bot ID (bots can't receive from bots)")
                    logger.error("   4. Use @userinfobot to verify your user ID")
                elif error_code == 400:
                    logger.error(f"❌ Invalid chat ID format: {chat_id}")
                    
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
    
    def _send_discord(self, message: str, signals: List[TradingSignal]):
        """Send message via Discord webhook"""
        try:
            if signals:
                signal = signals[0]
                color = 0x00FF00 if signal.direction.value == "LONG" else 0xFF0000
            else:
                color = 0xFFFF00
            
            embeds = []
            for signal in signals[:10]:
                embed = {
                    "title": f"{signal.direction.value} - {signal.symbol}",
                    "description": signal.reasoning,
                    "color": color,
                    "fields": [
                        {"name": "Entry Zone", "value": f"{signal.entry_zone_min:.2f} - {signal.entry_zone_max:.2f}", "inline": True},
                        {"name": "Stop Loss", "value": f"{signal.stop_loss:.2f}", "inline": True},
                        {"name": "Target 1", "value": f"{signal.target_1:.2f}", "inline": True},
                        {"name": "Strategy", "value": signal.strategy_type.value, "inline": True},
                        {"name": "Timeframe", "value": signal.timeframe, "inline": True},
                        {"name": "Confidence", "value": f"{signal.confidence_score:.1f}/10", "inline": True}
                    ],
                    "footer": {"text": f"Risk/Reward: 1:{signal.risk_reward:.1f}"}
                }
                embeds.append(embed)
            
            if len(signals) == 1:
                data = {"content": message, "embeds": embeds}
            else:
                data = {"content": f"🚨 **{len(signals)} Trading Signals Detected**", "embeds": embeds}
            
            response = requests.post(
                self.alerts.discord_webhook_url,
                json=data,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                logger.info("Discord alert sent successfully")
            else:
                logger.error(f"Discord alert failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
    
    def _send_email(self, signals: List[TradingSignal], market_sentiment=None):
        """Send email notification"""
        try:
            if not signals:
                return
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🔔 Crypto Scanner: {len(signals)} Trading Signals"
            msg["From"] = self.alerts.email_from
            msg["To"] = self.alerts.email_to
            
            html_content = self._create_html_email(signals)
            
            part = MIMEText(html_content, "html")
            msg.attach(part)
            
            with smtplib.SMTP(self.alerts.smtp_server, self.alerts.smtp_port) as server:
                server.starttls()
                server.login(self.alerts.smtp_username, self.alerts.smtp_password)
                server.send_message(msg)
            
            logger.info("Email alert sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
    
    def _create_html_email(self, signals: List[TradingSignal]) -> str:
        """Create HTML email content"""
        
        rows = ""
        for signal in signals:
            direction_color = "green" if signal.direction.value == "LONG" else "red"
            rows += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;"><strong>{signal.symbol}</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd; color: {direction_color};"><strong>{signal.direction.value}</strong></td>
                <td style="padding: 10px; border: 1px solid #ddd;">{signal.entry_zone_min:.2f} - {signal.entry_zone_max:.2f}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{signal.stop_loss:.2f}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{signal.target_1:.2f}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{signal.confidence_score:.1f}/10</td>
            </tr>
            """
        
        html = f"""
        <html>
        <head>
            <style>
                table {{ border-collapse: collapse; width: 100%; }}
                th {{ background-color: #4CAF50; color: white; padding: 12px; }}
                td {{ padding: 10px; border: 1px solid #ddd; text-align: center; }}
            </style>
        </head>
        <body>
            <h2>🚀 Crypto Scanner - Trading Signals</h2>
            <p>{len(signals)} trading signals detected:</p>
            <table>
                <tr>
                    <th>Coin</th>
                    <th>Direction</th>
                    <th>Entry Zone</th>
                    <th>Stop Loss</th>
                    <th>Target</th>
                    <th>Confidence</th>
                </tr>
                {rows}
            </table>
        </body>
        </html>
        """
        
        return html
    
    def _generate_tradingview_alerts(self, signals: List[TradingSignal]):
        """Generate TradingView alert syntax"""
        try:
            alerts = []
            
            for signal in signals:
                if signal.direction == "LONG":
                    alert = f"{signal.symbol} LONG Entry:{signal.entry_zone_min} SL:{signal.stop_loss} TP:{signal.target_1}"
                else:
                    alert = f"{signal.symbol} SHORT Entry:{signal.entry_zone_max} SL:{signal.stop_loss} TP:{signal.target_1}"
                
                alerts.append(alert)
            
            logger.info(f"TradingView Alerts: {alerts}")
            
        except Exception as e:
            logger.error(f"Error generating TradingView alerts: {e}")
    
    def send_heartbeat(self):
        """Send a periodic heartbeat message to confirm app is running"""
        if not self.alerts.telegram_bot_token:
            return
        
        message = "💚 <b>QuantGrid Scanner - Heartbeat</b>\n\n✅ Application is running and monitoring for signals.\n\n⏰ Next scan in ~15 minutes\n⏱️ Heartbeat: Every 4 hours"
        self._send_telegram(message)
    
    def send_test_alert(self) -> bool:
        """Send a test alert to verify configuration"""
        try:
            test_signal = TradingSignal(
                symbol="BTC",
                name="Bitcoin",
                direction=SignalDirection.LONG,
                strategy_type=StrategyType.TREND_CONTINUATION,
                entry_zone_min=50000,
                entry_zone_max=51000,
                stop_loss=48000,
                target_1=55000,
                target_2=60000,
                confidence_score=8.5,
                reasoning="Test signal - configuration verified"
            )
            
            self.send_all_alerts([test_signal])
            return True
            
        except Exception as e:
            logger.error(f"Test alert failed: {e}")
            return False