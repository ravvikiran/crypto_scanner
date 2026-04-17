# Railway Telegram Setup Guide

## The Problem You Were Experiencing

You weren't receiving heartbeat messages because:
1. ❌ The Telegram bot polling was never started (now fixed)
2. ❌ Configuration might be missing or incorrect

---

## Step-by-Step Railway Configuration

### Step 1: Get Your Telegram Bot Token
1. Open Telegram and message @BotFather
2. Send `/newbot`
3. Follow the prompts to create a bot
4. Copy the token (looks like: `123456789:ABCDEFghijklmnop_XYZ`)

### Step 2: Get Your Numeric Chat ID
⚠️ **Important:** Use numeric ID, NOT @username

1. Open Telegram and message @userinfobot
2. It will reply with your User ID (e.g., `987654321`)
3. Save this number

For a **group/channel**:
1. Add your bot to the group
2. Send a message in the group
3. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Find the chat ID in the response (negative number for channels)

---

### Step 3: Set Railway Environment Variables

On Railway dashboard:

1. Go to your project → Variables
2. Add these environment variables:

```
TELEGRAM_BOT_TOKEN=123456789:ABCDEFghijklmnop_XYZ
TELEGRAM_CHAT_ID=987654321
```

3. **Save and redeploy**

---

### Step 4: Verify Configuration

After deployment, you should see in Railway logs:

```
✅ Telegram bot polling started - ready to receive commands
✅ Telegram bot is configured - ready to send alerts
📤 Startup alert sent to Telegram
```

Then you'll receive in Telegram:
```
🔄 QuantGrid Scanner Started

Scanner is now running and monitoring for signals.

⏰ Scan interval: every 15 minutes
```

---

## What Happens Now (After Fix)

### Timeline:

| Time | Event |
|------|-------|
| T+0s | App starts on Railway |
| T+5s | Telegram bot starts polling ✅ |
| T+10s | Startup alert sent 🔔 |
| T+15m | First scan runs |
| T+4h | First heartbeat sent 💚 |
| Every 15m | Regular scans (if enabled) |
| Ongoing | Bot listens for your commands (/signals, /help, etc.) |

---

## Heartbeat Details

The heartbeat message sends every **4 hours** and looks like:

```
💚 QuantGrid Scanner - Heartbeat

✅ Application is running and monitoring for signals.

⏰ Next scan in ~15 minutes
⏱️ Heartbeat: Every 4 hours
```

**When you'll see it:**
- First heartbeat: 4 hours after startup
- Then: Every 4 hours after that
- Plus: Startup alert on first run

---

## Troubleshooting

### Not receiving heartbeat after 4+ hours?

Check Railway logs for errors:

```
❌ Missing: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID
   → Add to Variables and redeploy

⚠️ Telegram bot not initialized - check TELEGRAM_BOT_TOKEN configuration
   → Token is invalid, get new one from @BotFather

Telegram alert failed: 400 Bad Request
   → Chat ID might be invalid, use numeric ID from @userinfobot
```

### Bot not responding to commands?

1. Try `/start` in Telegram
2. Check Railway logs for "Telegram bot polling started"
3. Verify both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set

### Still not working?

Run locally to test:
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_id"
python main.py --schedule
```

---

## Commands Available

Once bot is running:

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message |
| `/signals` | Show latest trading signals |
| `/help` | Command list |
| `/analyze SYMBOL` | AI analysis (e.g., `/analyze BTC`) |
| `/refresh` | Instructions to run new scan |
| `/next` | Next signal (in list) |
| `/prev` | Previous signal |

---

## Important Notes

- Use **numeric chat ID** (e.g., `123456789`), NOT @username
- Railway needs **environment variables**, not `config.yaml`
- Bot runs in background - no need to interact with it
- Heartbeat = proof that the scanner is alive and running
- All alerts (signals, heartbeat) go to the same chat ID
