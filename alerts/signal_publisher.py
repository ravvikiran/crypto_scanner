"""
Signal Publisher Module
Manages publishing signals to Telegram, tracks daily limits, journals trades,
and monitors SL/TP for published signals.
"""

import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from loguru import logger

from models import TradingSignal, SignalDirection
from config import get_config
from alerts import AlertManager
from learning import TradeJournal
from collectors import MarketDataCollector


class SignalPublisher:
    """
    Manages signal publishing workflow:
    - Limits daily signals to max 3
    - Journals published signals to TradeJournal
    - Monitors SL/TP every 15 minutes
    - Sends immediate alerts on SL/TP hit
    """
    
    def __init__(self):
        self.config = get_config()
        self.alert_manager = AlertManager()
        self.trade_journal = TradeJournal(self.config)
        
        self._storage_file = Path("data/signal_publisher.json")
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._published_signals: Dict[str, Dict[str, Any]] = {}
        self._daily_published_count = 0
        self._last_reset_date: Optional[datetime] = None
        self._load_state()
        
        logger.info(f"SignalPublisher initialized - daily limit: {self.config.alerts.max_daily_signals}, published: {self._daily_published_count}")
    
    def _load_state(self):
        """Load published signals state from storage."""
        if not self._storage_file.exists():
            return
        
        try:
            with open(self._storage_file, 'r') as f:
                data = json.load(f)
            
            self._published_signals = data.get('published_signals', {})
            last_reset = data.get('last_reset_date')
            
            if last_reset:
                self._last_reset_date = datetime.fromisoformat(last_reset)
                self._check_daily_reset()
            
            self._daily_published_count = len([
                s for s in self._published_signals.values()
                if s.get('published_date') == datetime.now().strftime('%Y-%m-%d')
            ])
            
            logger.info(f"Loaded {len(self._published_signals)} published signals")
        except Exception as e:
            logger.error(f"Failed to load publisher state: {e}")
    
    def _save_state(self):
        """Persist publisher state to storage."""
        try:
            data = {
                'published_signals': self._published_signals,
                'last_reset_date': self._last_reset_date.isoformat() if self._last_reset_date else None
            }
            
            with open(self._storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save publisher state: {e}")
    
    def _check_daily_reset(self):
        """Reset daily count if it's a new day."""
        today = datetime.now().date()
        
        if self._last_reset_date is None or self._last_reset_date.date() < today:
            self._daily_published_count = 0
            self._last_reset_date = datetime.now()
            logger.info("Daily signal count reset")
    
    def can_publish(self) -> bool:
        """Check if a new signal can be published today."""
        self._check_daily_reset()
        max_daily = getattr(self.config.alerts, 'max_daily_signals', 3)
        return self._daily_published_count < max_daily
    
    def get_remaining_slots(self) -> int:
        """Get remaining signal slots for today."""
        self._check_daily_reset()
        max_daily = getattr(self.config.alerts, 'max_daily_signals', 3)
        return max(0, max_daily - self._daily_published_count)
    
    def publish_signal(self, signal: TradingSignal) -> bool:
        """
        Publish a signal to Telegram and journal it.
        
        Args:
            signal: The signal to publish
            
        Returns:
            True if successfully published, False otherwise
        """
        if not self.can_publish():
            logger.info(f"Daily signal limit reached ({self._daily_published_count}), cannot publish {signal.symbol}")
            return False
        
        try:
            logger.info(f"Publishing signal: {signal.symbol} {signal.direction.value}")
            
            self.alert_manager.send_all_alerts([signal])
            
            self._journal_signal(signal)
            
            self._published_signals[signal.id] = {
                'signal_id': signal.id,
                'symbol': signal.symbol,
                'direction': signal.direction.value,
                'entry_price': signal.entry_zone_min,
                'stop_loss': signal.stop_loss,
                'target_1': signal.target_1,
                'target_2': signal.target_2,
                'strategy_type': signal.strategy_type.value,
                'timeframe': signal.timeframe,
                'published_date': datetime.now().strftime('%Y-%m-%d'),
                'published_time': datetime.now().isoformat(),
                'status': 'OPEN'
            }
            
            self._daily_published_count += 1
            self._save_state()
            
            logger.info(f"Signal published and journaled: {signal.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish signal: {e}")
            return False
    
    def _journal_signal(self, signal: TradingSignal):
        """Add published signal to trade journal."""
        try:
            trade_id = self.trade_journal.journal_entry(
                symbol=signal.symbol,
                direction=signal.direction.value,
                entry_price=signal.entry_zone_min,
                quantity=1.0,
                stop_loss=signal.stop_loss,
                target_1=signal.target_1,
                target_2=signal.target_2,
                strategy_type=signal.strategy_type.value,
                timeframe=signal.timeframe,
                notes=f"Auto-published signal (ID: {signal.id[:20]}...)"
            )
            logger.info(f"Signal journaled as trade: {trade_id}")
        except Exception as e:
            logger.error(f"Failed to journal signal: {e}")
    
    def get_open_signals(self) -> List[Dict[str, Any]]:
        """Get all open signals that are being monitored."""
        return [
            s for s in self._published_signals.values()
            if s.get('status') == 'OPEN'
        ]
    
    async def check_signals_resolution(self) -> List[Dict[str, Any]]:
        """
        Check if any published signals have hit SL or TP.
        Runs every 15 minutes.
        
        Returns:
            List of resolved signals with resolution details
        """
        resolved_signals = []
        
        open_signals = self.get_open_signals()
        if not open_signals:
            return resolved_signals
        
        logger.info(f"Checking {len(open_signals)} published signals for SL/TP")
        
        try:
            async with MarketDataCollector() as collector:
                for signal_data in open_signals:
                    symbol = signal_data['symbol']
                    direction = signal_data['direction']
                    entry_price = signal_data['entry_price']
                    stop_loss = signal_data['stop_loss']
                    target_1 = signal_data['target_1']
                    target_2 = signal_data['target_2']
                    
                    try:
                        candles = await collector.get_candles(symbol, "1h")
                        if not candles or len(candles) < 1:
                            continue
                        
                        current_price = candles[-1].close
                        
                        resolution = None
                        exit_reason = None
                        
                        if direction == 'LONG':
                            if current_price <= stop_loss:
                                resolution = 'STOP_LOSS_HIT'
                                exit_reason = 'STOP_LOSS_HIT'
                                logger.warning(f"SL HIT: {symbol} LONG - Price ${current_price} <= SL ${stop_loss}")
                            elif current_price >= target_2:
                                resolution = 'TARGET_2_HIT'
                                exit_reason = 'TARGET_2_HIT'
                                logger.info(f"TARGET 2 HIT: {symbol} LONG - Price ${current_price} >= T2 ${target_2}")
                            elif current_price >= target_1:
                                resolution = 'TARGET_1_HIT'
                                exit_reason = 'TARGET_1_HIT'
                                logger.info(f"TARGET 1 HIT: {symbol} LONG - Price ${current_price} >= T1 ${target_1}")
                        else:
                            if current_price >= stop_loss:
                                resolution = 'STOP_LOSS_HIT'
                                exit_reason = 'STOP_LOSS_HIT'
                                logger.warning(f"SL HIT: {symbol} SHORT - Price ${current_price} >= SL ${stop_loss}")
                            elif current_price <= target_2:
                                resolution = 'TARGET_2_HIT'
                                exit_reason = 'TARGET_2_HIT'
                                logger.info(f"TARGET 2 HIT: {symbol} SHORT - Price ${current_price} <= T2 ${target_2}")
                            elif current_price <= target_1:
                                resolution = 'TARGET_1_HIT'
                                exit_reason = 'TARGET_1_HIT'
                                logger.info(f"TARGET 1 HIT: {symbol} SHORT - Price ${current_price} <= T1 ${target_1}")
                        
                        if resolution:
                            outcome = self.trade_journal.close_trade_by_symbol(
                                symbol=symbol,
                                exit_price=current_price,
                                exit_reason=exit_reason,
                                notes=f"Auto-closed via signal monitoring"
                            )
                            
                            if outcome:
                                signal_data['status'] = 'CLOSED'
                                signal_data['resolution'] = resolution
                                signal_data['exit_price'] = current_price
                                signal_data['exit_time'] = datetime.now().isoformat()
                                signal_data['pnl_percent'] = outcome.pnl_percent
                                
                                self._send_resolution_alert(signal_data, current_price, resolution)
                                
                                resolved_signals.append(signal_data)
                                logger.info(f"Signal resolved: {symbol} - {resolution} @ ${current_price} ({outcome.pnl_percent:+.2f}%)")
                    
                    except Exception as e:
                        logger.error(f"Error checking {symbol}: {e}")
            
            self._save_state()
            
        except Exception as e:
            logger.error(f"Error in signal resolution check: {e}")
        
        return resolved_signals
    
    def _send_resolution_alert(self, signal_data: Dict[str, Any], current_price: float, resolution: str):
        """Send immediate Telegram alert when SL/TP is hit."""
        try:
            symbol = signal_data['symbol']
            direction = signal_data['direction']
            entry_price = signal_data['entry_price']
            pnl = signal_data.get('pnl_percent', 0)
            
            if 'STOP_LOSS' in resolution:
                emoji = "🔴"
                title = f"{emoji} STOP LOSS HIT"
            elif 'TARGET_2' in resolution:
                emoji = "🎯"
                title = f"{emoji} TARGET 2 HIT"
            elif 'TARGET_1' in resolution:
                emoji = "🎯"
                title = f"{emoji} TARGET 1 HIT"
            else:
                emoji = "⚠️"
                title = f"{emoji} SIGNAL RESOLVED"
            
            message = f"""
{title}

{symbol} {direction}

📊 Entry: ${entry_price:.4f}
📈 Current: ${current_price:.4f}
📏 PnL: {pnl:+.2f}%

⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            from config import get_config
            cfg = get_config()
            
            if cfg.alerts.telegram_bot_token and cfg.alerts.telegram_chat_id:
                import requests
                chat_id = cfg.alerts.telegram_channel_chat_id or cfg.alerts.telegram_chat_id
                url = f"https://api.telegram.org/bot{cfg.alerts.telegram_bot_token}/sendMessage"
                data = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                requests.post(url, json=data, timeout=10)
                logger.info(f"Resolution alert sent for {symbol}")
            
        except Exception as e:
            logger.error(f"Failed to send resolution alert: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get publisher status."""
        self._check_daily_reset()
        return {
            'daily_published': self._daily_published_count,
            'max_daily': getattr(self.config.alerts, 'max_daily_signals', 3),
            'remaining_slots': self.get_remaining_slots(),
            'open_signals': len(self.get_open_signals()),
            'total_published': len(self._published_signals)
        }


_signal_publisher: Optional[SignalPublisher] = None


def get_signal_publisher() -> SignalPublisher:
    """Get or create the global SignalPublisher instance."""
    global _signal_publisher
    if _signal_publisher is None:
        _signal_publisher = SignalPublisher()
    return _signal_publisher