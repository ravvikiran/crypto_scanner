"""
Risk Management Engine
Implements PRD risk management rules:
- Risk per trade: 1%
- Max trades/day: 5
- Daily loss cap: 3%
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from loguru import logger

from config import get_config


@dataclass
class TradeRisk:
    """Risk parameters for a single trade"""
    entry_price: float
    stop_loss: float
    risk_percent: float
    position_size: float = 0
    risk_amount: float = 0


@dataclass 
class DailyRiskStatus:
    """Daily risk tracking status"""
    date: str = ""
    trades_today: int = 0
    daily_pnl_percent: float = 0.0
    daily_loss_cap_hit: bool = False
    max_trades_hit: bool = False


class RiskManagementEngine:
    """
    PRD Risk Management Engine
    
    Rules:
    - Risk per trade: 1% max
    - Max trades per day: 5
    - Daily loss cap: 3%
    """
    
    # PRD Constants
    MAX_RISK_PER_TRADE = 0.01  # 1%
    MAX_TRADES_PER_DAY = 5
    DAILY_LOSS_CAP = 0.03  # 3%
    
    def __init__(self):
        self.config = get_config()
        
        # Daily tracking
        self._daily_trades: List[Dict] = []
        self._last_reset_date: str = ""
        
        # Load from config if available
        self.max_risk_per_trade = getattr(
            self.config.strategy, 'max_risk_per_trade', self.MAX_RISK_PER_TRADE
        )
        self.max_trades_per_day = getattr(
            self.config.scanner, 'max_trades_per_day', self.MAX_TRADES_PER_DAY
        )
        self.daily_loss_cap = getattr(
            self.config.scanner, 'daily_loss_cap', self.DAILY_LOSS_CAP
        )
    
    def can_open_trade(self) -> tuple[bool, str]:
        """
        Check if a new trade can be opened based on risk rules.
        
        Returns:
            (can_trade, reason)
        """
        self._check_daily_reset()
        
        current_status = self.get_daily_status()
        
        # Check 1: Max trades per day
        if current_status.trades_today >= self.max_trades_per_day:
            logger.warning(f"Max trades per day reached: {current_status.trades_today}/{self.max_trades_per_day}")
            return False, f"Max trades per day ({self.max_trades_per_day}) reached"
        
        # Check 2: Daily loss cap
        if current_status.daily_loss_cap_hit:
            logger.warning(f"Daily loss cap hit: {current_status.daily_pnl_percent:.2f}%")
            return False, f"Daily loss cap ({self.daily_loss_cap*100}%) already hit"
        
        return True, "Risk check passed"
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float
    ) -> tuple[float, float]:
        """
        Calculate position size based on risk rules.
        
        Args:
            account_balance: Total account balance
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            
        Returns:
            (position_size, risk_amount)
        """
        # Risk amount = account_balance * risk_percent
        risk_amount = account_balance * self.max_risk_per_trade
        
        # Position size = risk_amount / (entry - stop_loss)
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk > 0:
            position_size = risk_amount / price_risk
        else:
            position_size = 0
            risk_amount = 0
        
        # Ensure risk doesn't exceed max
        actual_risk_percent = (risk_amount / account_balance) * 100
        if actual_risk_percent > self.max_risk_per_trade * 100:
            # Adjust to max risk
            risk_amount = account_balance * self.max_risk_per_trade
            position_size = risk_amount / price_risk if price_risk > 0 else 0
        
        return position_size, risk_amount
    
    def validate_trade_risk(
        self,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        direction: str
    ) -> tuple[bool, str, float]:
        """
        Validate trade risk parameters.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            target_price: Target price
            direction: "LONG" or "SHORT"
            
        Returns:
            (is_valid, reason, risk_reward_ratio)
        """
        if direction == "LONG":
            price_risk = entry_price - stop_loss
            reward = target_price - entry_price
        else:
            price_risk = stop_loss - entry_price
            reward = entry_price - target_price
        
        if price_risk <= 0:
            return False, "Invalid risk (stop loss must be on opposite side of entry)", 0
        
        risk_reward = reward / price_risk if price_risk > 0 else 0
        
        # PRD: Min RR is 2:0
        min_rr = 2.0
        if risk_reward < min_rr:
            return False, f"Risk/Reward below minimum ({min_rr}:1)", risk_reward
        
        # Calculate risk percentage
        risk_percent = (price_risk / entry_price) * 100
        
        if risk_percent > self.max_risk_per_trade * 100:
            return False, f"Risk exceeds {self.max_risk_per_trade*100}% per trade", risk_reward
        
        return True, "Risk validated", risk_reward
    
    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        direction: str
    ):
        """Record a trade for daily tracking"""
        self._check_daily_reset()
        
        trade = {
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "direction": direction,
            "timestamp": datetime.now().isoformat()
        }
        
        self._daily_trades.append(trade)
        logger.info(f"Recorded trade: {symbol} {direction} at {entry_price}")
    
    def update_pnl(self, pnl_percent: float):
        """Update daily PnL for loss cap tracking"""
        self._check_daily_reset()
        
        # Update last trade PnL
        if self._daily_trades:
            self._daily_trades[-1]["pnl_percent"] = pnl_percent
        
        # Calculate total daily PnL
        total_pnl = sum(
            t.get("pnl_percent", 0) 
            for t in self._daily_trades 
            if "pnl_percent" in t
        )
        
        # Check loss cap
        if total_pnl <= -self.daily_loss_cap * 100:
            logger.warning(f"Daily loss cap reached: {total_pnl:.2f}%")
    
    def get_daily_status(self) -> DailyRiskStatus:
        """Get current daily risk status"""
        self._check_daily_reset()
        
        status = DailyRiskStatus(
            date=datetime.now().strftime("%Y-%m-%d"),
            trades_today=len(self._daily_trades)
        )
        
        # Calculate daily PnL
        total_pnl = sum(
            t.get("pnl_percent", 0)
            for t in self._daily_trades
            if "pnl_percent" in t
        )
        status.daily_pnl_percent = total_pnl
        
        # Check caps
        if total_pnl <= -self.daily_loss_cap * 100:
            status.daily_loss_cap_hit = True
        
        if len(self._daily_trades) >= self.max_trades_per_day:
            status.max_trades_hit = True
        
        return status
    
    def _check_daily_reset(self):
        """Reset daily tracking if new day"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if self._last_reset_date != today:
            self._daily_trades = []
            self._last_reset_date = today
            logger.info(f"Daily risk tracking reset for {today}")
    
    def get_risk_summary(self) -> Dict:
        """Get complete risk management summary"""
        status = self.get_daily_status()
        
        return {
            "trades_today": status.trades_today,
            "max_trades": self.max_trades_per_day,
            "daily_pnl": f"{status.daily_pnl_percent:.2f}%",
            "loss_cap": f"{self.daily_loss_cap*100}%",
            "loss_cap_hit": status.daily_loss_cap_hit,
            "can_trade": status.trades_today < self.max_trades_per_day and not status.daily_loss_cap_hit,
            "risk_per_trade": f"{self.max_risk_per_trade*100}%"
        }
    
    def should_take_signal(self, signal_score: float) -> tuple[bool, str]:
        """
        Determine if a signal should be taken based on risk management.
        
        Args:
            signal_score: Signal confidence score (0-100)
            
        Returns:
            (should_take, reason)
        """
        can_trade, reason = self.can_open_trade()
        
        if not can_trade:
            return False, reason
        
        # PRD: Only take signals with score 45+
        if signal_score < 45:
            return False, f"Signal score {signal_score} below minimum (45)"
        
        return True, "Signal approved by risk management"