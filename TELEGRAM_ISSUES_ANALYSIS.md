# Telegram Bot Issues - Analysis & Fixes

## Problems Found

### 1. **CRITICAL: Telegram Bot Polling Not Started**
**File:** [main.py](main.py#L67-L145)
**Issue:** The Telegram bot is NEVER started in polling mode on Railway.

When Railway runs the app with `python main.py --schedule`:
- ✅ Scheduler is created and started
- ✅ AlertManager is initialized
- ✅ Heartbeat job is scheduled (sends message every 4 hours)
- ❌ **Telegram bot polling/listening thread is NEVER started**

```python
# Current code (BROKEN):
alert_mgr = AlertManager()
scheduler.set_alert_manager(alert_mgr)
# ... scheduler starts ...
# But the bot never calls .start() to begin polling!
```

**Impact:**
- Bot won't receive ANY incoming messages
- You won't be able to use /signals, /analyze, /help commands
- Heartbeat messages WILL send (one-way), but bot can't listen

---

### 2. **Bot Instance Not Created in AlertManager**
**File:** [alerts/alert_manager.py](alerts/alert_manager.py#L14-L22)
**Issue:** AlertManager creates NO bot instance

```python
class AlertManager:
    def __init__(self):
        self.config = get_config()
        self.alerts = self.config.alerts
        # ... NO telegram bot created!
```

The bot is only created in `telegram_bot.py` but never instantiated in AlertManager.

---

### 3. **Missing Bot Initialization in run_scheduled()**
**File:** [main.py](main.py#L67-L85)
**Issue:** The `run_scheduled()` function doesn't create or start the Telegram bot

```python
def run_scheduled(config: dict, logger):
    # ... scheduler setup ...
    alert_mgr = AlertManager()
    # Missing: Create and start the Telegram bot
    # bot = create_telegram_bot()
    # bot.start()  # <-- This should be here!
```

---

## Solution

### Fix 1: Create Telegram Bot in run_scheduled()
Modify `main.py` to create and start the bot:

```python
def run_scheduled(config: dict, logger):
    """
    Run the scanner with scheduler and Telegram bot (both running together)
    """
    logger.info("Initializing scheduler and Telegram bot...")
    
    signal_publisher = get_signal_publisher()
    logger.info(f"Signal Publisher initialized: {signal_publisher.get_status()}")
    
     from infrastructure.scanner_scheduler import ScannerScheduler
    scheduler = ScannerScheduler(config)
    scheduler.set_signal_publisher(signal_publisher)
    
    alert_mgr = AlertManager()
    scheduler.set_alert_manager(alert_mgr)
    
    # NEW: Create and start Telegram bot
    from alerts.telegram_bot import create_telegram_bot
    telegram_bot = create_telegram_bot()
    if telegram_bot:
        telegram_bot.start()
        logger.info("Telegram bot polling started")
    else:
        logger.warning("Telegram bot not created - check token configuration")
    
    # ... rest of the code ...
```

---

## Configuration Checklist

Verify these environment variables are set on Railway:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_numeric_chat_id (NOT @username)
```

**Note:** Use numeric chat ID (e.g., `123456789`), not username (e.g., `@yourchannel`)

Get your numeric chat ID:
1. Message @userinfobot on Telegram
2. It will respond with your numeric ID
3. Set as `TELEGRAM_CHAT_ID`

---

## Expected Behavior After Fix

✅ Bot will be listening for incoming messages  
✅ Heartbeat will send every 4 hours  
✅ Scanning continues every 15 minutes  
✅ Signal alerts will be sent when generated  
✅ Commands like /signals, /help, /analyze will work  

---

## Railway Startup Command

The Procfile is correct:
```
worker: python main.py --schedule
```

This will:
1. Start the scheduler (scans every 15 min)
2. Start the Telegram bot (after fix)
3. Send heartbeat every 4 hours
4. Listen for incoming commands
