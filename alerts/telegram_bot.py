"""
Telegram Bot for Crypto Scanner
Supports interactive commands and signal navigation.
"""

import os
import io
import json
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

import telebot
from telebot import types

from loguru import logger

from models import TradingSignal, SignalDirection, StrategyType
from config import get_config


class TelegramBot:
    """Interactive Telegram bot for the crypto scanner"""
    
    def __init__(self, signal_provider: Callable = None):
        self.config = get_config()
        self.alerts = self.config.alerts
        self.signal_provider = signal_provider
        
        self.bot = None
        self._running = False
        self._thread = None
        
        self._user_sessions: Dict[int, Dict[str, Any]] = {}
        self._last_signals: List[TradingSignal] = []
        
        self._setup_bot()
    
    def _setup_bot(self):
        """Initialize the bot if credentials are available"""
        if not self.alerts.telegram_bot_token:
            logger.warning("Telegram bot token not configured")
            return
        
        try:
            self.bot = telebot.TeleBot(self.alerts.telegram_bot_token)
            # Clear any existing webhook to avoid conflicts with polling
            try:
                self.bot.remove_webhook(drop_pending_updates=True)
                logger.info("Cleared any existing webhook and pending updates")
            except Exception as hook_error:
                logger.warning(f"Could not clear webhook (may not be set): {hook_error}")
            self._register_handlers()
            logger.info("Telegram bot initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.bot = None
    
    def _register_handlers(self):
        """Register command handlers"""
        if not self.bot:
            return
        
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            self._send_welcome(message)
        
        @self.bot.message_handler(commands=['help'])
        def handle_help(message):
            self._send_help(message)
        
        @self.bot.message_handler(commands=['analyze'])
        def handle_analyze(message):
            self._handle_analyze_command(message)
        
        @self.bot.message_handler(commands=['signals'])
        def handle_signals(message):
            self._handle_signals_command(message)
        
        @self.bot.message_handler(commands=['next'])
        def handle_next(message):
            self._handle_navigation(message, 'next')
        
        @self.bot.message_handler(commands=['prev'])
        def handle_prev(message):
            self._handle_navigation(message, 'prev')
        
        @self.bot.message_handler(commands=['refresh'])
        def handle_refresh(message):
            self._send_refresh_instructions(message)
        
        @self.bot.message_handler(commands=['stop'])
        def handle_stop(message):
            self._handle_stop_command(message)
        
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call):
            self._handle_callback(call)
    
    def _send_welcome(self, message):
        """Send welcome message"""
        welcome_text = """
👋 <b>Welcome to Crypto Scanner Bot!</b>

I'll help you track trading opportunities in the crypto market.

<b>Available Commands:</b>
/start - Welcome message
/help - Show all commands
/signals - View latest trading signals
/analyze SYMBOL - AI-powered analysis
/refresh - Run a new scan
/stop - Stop the bot

<i>Use /signals to see current setups!</i>
"""
        self.bot.reply_to(message, welcome_text, parse_mode='HTML')
    
    def _send_help(self, message):
        """Send help message"""
        help_text = """
📖 <b>Command Reference</b>

<b>Main Commands:</b>
/signals - View latest trading signals
/analyze SYMBOL - AI analysis of a symbol
/refresh - Instructions to run new scan

<b>Navigation:</b>
/next - Next signal
/prev - Previous signal

<b>Control:</b>
/start - Welcome message
/help - Show this help
/stop - Stop the bot

<b>Tips:</b>
• Signals are sorted by confidence
• Use /analyze for detailed AI insights
• Each signal shows entry/stop/targets
"""
        self.bot.reply_to(message, help_text, parse_mode='HTML')
    
    def _handle_signals_command(self, message):
        """Handle /signals command"""
        signals = self._get_latest_signals()
        
        if not signals:
            self.bot.reply_to(message, "📭 No signals available. Run a scan to generate signals.")
            return
        
        self._user_sessions[message.chat.id] = {
            'current_index': 0,
            'signals': signals
        }
        
        self._display_signal(message.chat.id, 0, signals)
    
    def _handle_navigation(self, message, direction: str):
        """Handle next/prev navigation"""
        session = self._user_sessions.get(message.chat.id)
        
        if not session:
            self.bot.reply_to(message, "No signals loaded. Use /signals to view signals.")
            return
        
        signals = session['signals']
        current_index = session['current_index']
        
        if direction == 'next':
            new_index = (current_index + 1) % len(signals)
        else:
            new_index = (current_index - 1 + len(signals)) % len(signals)
        
        session['current_index'] = new_index
        
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        self._display_signal(message.chat.id, new_index, signals)
    
    def _display_signal(self, chat_id: int, index: int, signals: List[TradingSignal]):
        """Display a signal with navigation buttons"""
        if index >= len(signals):
            return
        
        signal = signals[index]
        message = self._format_signal_message(signal, index + 1, len(signals))
        
        keyboard = types.InlineKeyboardMarkup()
        
        nav_buttons = []
        if len(signals) > 1:
            prev_btn = types.InlineKeyboardButton("◀️ Prev", callback_data=f"prev_{index}")
            next_btn = types.InlineKeyboardButton("Next ▶️", callback_data=f"next_{index}")
            nav_buttons.append(prev_btn)
            nav_buttons.append(next_btn)
        
        if nav_buttons:
            keyboard.row(*nav_buttons)
        
        refresh_btn = types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_signals")
        stop_btn = types.InlineKeyboardButton("⏹️ Stop", callback_data="stop_bot")
        keyboard.row(refresh_btn, stop_btn)
        
        try:
            self.bot.send_message(chat_id, message, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error displaying signal: {e}")
    
    def _format_signal_message(self, signal: TradingSignal, current: int, total: int) -> str:
        """Format signal as detailed message"""
        direction_emoji = "🟢" if signal.direction == SignalDirection.LONG else "🔴"
        direction_text = "LONG" if signal.direction == SignalDirection.LONG else "SHORT"
        
        rr = f"1:{signal.risk_reward:.1f}"
        
        risk_level = self._get_risk_level(signal)
        
        message = f"""
{direction_emoji} <b>{signal.symbol}</b> - {direction_text}

📊 <b>Signal {current}/{total}</b>
Strategy: {signal.strategy_type.value}
Timeframe: {signal.timeframe}
Confidence: {signal.confidence_score:.1f}/10

💰 <b>Entry Zone</b>
{signal.entry_zone_min:.4f} - {signal.entry_zone_max:.4f}

🛡️ <b>Stop Loss</b>
{signal.stop_loss:.4f}

🎯 <b>Targets</b>
T1: {signal.target_1:.4f}
T2: {signal.target_2:.4f}

📈 <b>Risk/Reward</b>
{rr}

⚠️ <b>Risk Level</b>
{risk_level}
"""
        
        if signal.reasoning:
            message += f"""
📝 <b>Reasoning</b>
{signal.reasoning[:300]}
"""
        
        return message
    
    def _get_risk_level(self, signal: TradingSignal) -> str:
        """Determine risk level based on confidence and R/R"""
        if signal.confidence_score >= 8 and signal.risk_reward >= 2:
            return "🟢 LOW"
        elif signal.confidence_score >= 6 and signal.risk_reward >= 1.5:
            return "🟡 MEDIUM"
        else:
            return "🔴 HIGH"
    
    def _handle_analyze_command(self, message):
        """Handle /analyze command"""
        parts = message.text.split()
        
        if len(parts) < 2:
            self.bot.reply_to(message, "Usage: /analyze SYMBOL\nExample: /analyze BTC")
            return
        
        symbol = parts[1].upper().replace('/', '')
        
        self.bot.reply_to(message, f"🔍 Analyzing {symbol}...")
        
        if self.signal_provider:
            result = self.signal_provider(symbol)
            if result:
                self.bot.reply_to(message, result, parse_mode='HTML')
            else:
                self.bot.reply_to(message, f"No data found for {symbol}")
        else:
            self.bot.reply_to(message, "AI analysis not available. Configure LLM providers.")
    
    def _send_refresh_instructions(self, message):
        """Send instructions to refresh signals"""
        refresh_text = """
🔄 <b>To Run a New Scan</b>

1. Run the scanner manually:
   <code>python main.py --scan</code>

2. Or wait for the scheduled scan

3. Use /signals to view new signals

<b>Note:</b> Scans run automatically every 15 minutes if scheduled.
"""
        self.bot.reply_to(message, refresh_text, parse_mode='HTML')
    
    def _handle_stop_command(self, message):
        """Handle /stop command"""
        stop_text = """
⏹️ <b>Bot Stopped</b>

The scanner will continue running in the background.
To restart the bot, restart the application.

Thank you for using Crypto Scanner!
"""
        self.bot.reply_to(message, stop_text, parse_mode='HTML')
        
        if self._running:
            self.stop()
    
    def _handle_callback(self, call):
        """Handle inline button callbacks"""
        data = call.data
        
        if data == "refresh_signals":
            self._handle_signals_command(types.Message(1, None, None, None, None))
        elif data == "stop_bot":
            self._handle_stop_command(types.Message(1, None, None, None, None))
        elif data.startswith("prev_") or data.startswith("next_"):
            direction = data.split("_")[0]
            session = self._user_sessions.get(call.message.chat.id)
            
            if session:
                signals = session['signals']
                current_index = session['current_index']
                
                if direction == 'next':
                    new_index = (current_index + 1) % len(signals)
                else:
                    new_index = (current_index - 1 + len(signals)) % len(signals)
                
                session['current_index'] = new_index
                self._display_signal(call.message.chat.id, new_index, signals)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def _get_latest_signals(self) -> List[TradingSignal]:
        """Get latest signals from provider"""
        if self.signal_provider:
            return self.signal_provider()
        return self._last_signals
    
    def update_signals(self, signals: List[TradingSignal]):
        """Update the bot's signal cache"""
        self._last_signals = signals
        
        for session in self._user_sessions.values():
            session['signals'] = signals
    
    def start(self):
        """Start the bot in a separate thread"""
        if not self.bot:
            logger.warning("Cannot start Telegram bot - not initialized")
            return
        
        if self._running:
            logger.warning("Telegram bot already running")
            return
        
        self._running = True
        
        def run_bot():
            max_retries = 3
            retry_count = 0
            
            while self._running and retry_count < max_retries:
                try:
                    import time
                    # Small delay to ensure webhook cleanup is processed
                    time.sleep(2)
                    logger.info("Starting Telegram bot polling...")
                    self.bot.infinity_polling(
                        timeout=60,
                        long_polling_timeout=60,
                        allowed_updates=["message", "callback_query"]
                    )
                except Exception as e:
                    retry_count += 1
                    if self._running and retry_count < max_retries:
                        logger.error(f"Telegram bot error (attempt {retry_count}/{max_retries}): {e}")
                        time.sleep(5 * retry_count)  # Exponential backoff
                    else:
                        logger.error(f"Telegram bot stopped after {retry_count} attempts: {e}")
                        break
            
            self._running = False
        
        self._thread = threading.Thread(target=run_bot, daemon=True)
        self._thread.start()
        
        logger.info("Telegram bot started in background")
    
    def stop(self):
        """Stop the bot"""
        self._running = False
        
        if self.bot:
            try:
                self.bot.stop_polling()
            except:
                pass
        
        logger.info("Telegram bot stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running


class SignalDuplicateChecker:
    """Prevents duplicate alerts within 24-hour cooldown"""
    
    def __init__(self, cooldown_hours: int = 24):
        self.cooldown = timedelta(hours=cooldown_hours)
        self._sent_signals: Dict[str, datetime] = {}
    
    def should_send(self, symbol: str) -> bool:
        """Check if signal should be sent (not in cooldown)"""
        key = symbol.upper()
        
        if key not in self._sent_signals:
            return True
        
        last_sent = self._sent_signals[key]
        if datetime.now() - last_sent > self.cooldown:
            return True
        
        return False
    
    def mark_sent(self, symbol: str):
        """Mark signal as sent"""
        self._sent_signals[symbol.upper()] = datetime.now()
    
    def cleanup_old_entries(self):
        """Remove entries older than cooldown period"""
        now = datetime.now()
        self._sent_signals = {
            k: v for k, v in self._sent_signals.items()
            if now - v <= self.cooldown
        }
    
    def get_remaining_cooldown(self, symbol: str) -> Optional[timedelta]:
        """Get remaining cooldown time for symbol"""
        key = symbol.upper()
        
        if key not in self._sent_signals:
            return None
        
        last_sent = self._sent_signals[key]
        remaining = self.cooldown - (datetime.now() - last_sent)
        
        if remaining.total_seconds() <= 0:
            return None
        
        return remaining


def create_telegram_bot(signal_provider: Callable = None) -> Optional[TelegramBot]:
    """Create and return Telegram bot instance"""
    config = get_config()
    
    if not config.alerts.telegram_bot_token:
        logger.warning("Telegram bot not configured - missing token")
        return None
    
    return TelegramBot(signal_provider=signal_provider)
