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
    
    def send_all_alerts(self, signals: List[TradingSignal]):
        """Send alerts through all configured channels"""
        
        threshold = self.alerts.confidence_threshold
        if threshold <= 10:
            threshold = threshold * 10
        
        qualified_signals = [s for s in signals if s.normalized_confidence >= threshold]
        
        if not qualified_signals:
            self._send_no_signals_message()
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
            self._send_telegram(message)
            self._send_discord_single(signal)
            self._send_email([signal])
    
    def _send_no_signals_message(self):
        """Send message when no signals meet confidence threshold"""
        now = datetime.now()
        
        if self._last_no_signals_message:
            if (now - self._last_no_signals_message).total_seconds() < 86400:
                return
        
        self._last_no_signals_message = now
        
        message = "📊 No coins met confidence threshold (≥6.0) this scan."
        self._send_telegram(message)
    
    def _send_discord_single(self, signal: TradingSignal):
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
            chat_id = self.alerts.telegram_channel_chat_id or self.alerts.telegram_chat_id
            
            if not chat_id:
                logger.warning("Telegram: No chat_id configured")
                return
            
            if chat_id and chat_id.startswith('@'):
                logger.warning(f"Telegram: Using username '{chat_id}'. For better reliability, get numeric chat ID from @userinfobot bot")
            
            url = f"https://api.telegram.org/bot{self.alerts.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 200:
                logger.info("Telegram alert sent successfully")
            else:
                logger.error(f"Telegram alert failed: {response.text}")
                
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
    
    def _send_email(self, signals: List[TradingSignal]):
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