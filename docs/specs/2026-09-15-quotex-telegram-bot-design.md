# Quotex Telegram Bot — Design Spec

**Date:** 2026-09-15  
**Status:** Approved  
**Author:** Xafor + Hermes

---

## 1. Overview

A Telegram bot that scans Quotex OTC markets for a specific candlestick pattern, sends signals to users, and optionally auto-trades on their behalf. Multi-user: each person configures their own Quotex session, stake amount, and auto-trade preference.

---

## 2. Strategy

### 2.1 Pattern Definition

**Uptrend (Bullish) — BUY (CALL) Signal:**
1. 4+ consecutive **green** candles (close > open) back-to-back
2. A **red** candle (close < open) appears immediately after
3. → Signal: **BUY (CALL)** — the red is a pullback in an uptrend

**Downtrend (Bearish) — SELL (PUT) Signal:**
1. 4+ consecutive **red** candles back-to-back
2. A **green** candle appears immediately after
3. → Signal: **SELL (PUT)** — the green is a rally in a downtrend

### 2.2 Doji Handling

A **doji** is a candle where `|close - open| / open < 0.002` (0.2% range).

- If a doji appears **at any point** during a streak → **entire pattern cancels**, streak resets to 0
- The counter-candle that triggers the signal must also be non-doji
- Dojis are NOT skipped — they invalidate the pattern

### 2.3 Continuation Rule

If the counter-candle appears but the expected follow-through doesn't materialize (e.g., after a red pullback in an uptrend, no green appears within 3 more candles), a **second signal** is generated for a deeper entry.

### 2.4 Cooldown

After a signal fires for an asset, **5-minute cooldown** applies per user per asset. No duplicate signals during cooldown.

---

## 3. Technical Architecture

### 3.1 Components

```
┌─────────────────────────────────────────────────────────┐
│                     main.py (asyncio loop)               │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ data_feed.py │──│ patterns.py  │──│   bot.py     │   │
│  │ (pyquotex)   │  │ (strategy)   │  │ (Telegram)   │   │
│  └──────────────┘  └──────────────┘  └──────┬───────┘   │
│                                              │           │
│                                     ┌────────▼────────┐  │
│                                     │  trader.py      │  │
│                                     │  (pyquotex)     │  │
│                                     └─────────────────┘  │
│                                                          │
│  ┌──────────────┐                                        │
│  │ database.py  │  (SQLAlchemy + PostgreSQL)             │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Module Responsibilities

#### `data_feed.py` — Market Data Engine
- Connects to Quotex via pyquotex WebSocket
- Subscribes to ALL OTC assets with 80%+ return
- Maintains rolling buffer of last 20 candles per asset
- Pushes completed candles to `asyncio.Queue`
- Auto-reconnects on WebSocket drop (10s retry interval)

#### `patterns.py` — Strategy Engine
- Consumes candles from queue
- Tracks streak per asset (consecutive same-color, non-doji candles)
- Detects pattern completion (4+ streak + opposite-color counter-candle)
- Applies cooldown check (queries database)
- Creates `Signal` objects and passes to `bot.py`

#### `bot.py` — Telegram Bot
- Manages Telegram bot lifecycle (python-telegram-bot)
- Handles user commands (`/start`, `/set_ssid`, `/set_stake`, etc.)
- On signal: iterates active users, checks their asset filter
- If `auto_trade = true` → passes to `trader.py`
- If `auto_trade = false` → sends DM with BUY/SELL inline buttons (60s expiry)
- Sends trade outcome messages (PROFIT/LOSS + P&L + balance)

#### `trader.py` — Trade Execution
- Executes trades via pyquotex using user's SSID
- Monitors trade result (win/loss)
- Fetches updated balance from Quotex
- Returns outcome to `bot.py` for user notification

#### `database.py` — Data Layer
- SQLAlchemy ORM with PostgreSQL
- Tables: `users`, `signals`, `trades`
- Connection pooling via asyncpg

---

## 4. Database Schema

### 4.1 `users` Table

| Column | Type | Description |
|--------|------|-------------|
| `chat_id` | BIGINT PK | Telegram chat ID |
| `ssid` | TEXT | Quotex session token (encrypted) |
| `stake` | NUMERIC | Trade amount in USD |
| `auto_trade` | BOOLEAN | Auto-execute trades |
| `assets` | JSONB | List of asset names, or `["ALL"]` |
| `paused` | BOOLEAN | Pause signal delivery |
| `created_at` | TIMESTAMP | Account creation time |
| `updated_at` | TIMESTAMP | Last settings update |

### 4.2 `signals` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Auto-increment |
| `asset` | VARCHAR(20) | e.g., EURUSD_OTC |
| `direction` | VARCHAR(4) | CALL or PUT |
| `strength` | NUMERIC | Confidence score (0-100) |
| `created_at` | TIMESTAMP | Signal generation time |

### 4.3 `trades` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Auto-increment |
| `user_id` | BIGINT FK | References users.chat_id |
| `signal_id` | INTEGER FK | References signals.id |
| `asset` | VARCHAR(20) | Traded asset |
| `direction` | VARCHAR(4) | CALL or PUT |
| `amount` | NUMERIC | Stake amount |
| `result` | VARCHAR(10) | WIN or LOSS |
| `pnl` | NUMERIC | Profit/loss amount |
| `balance_after` | NUMERIC | Balance after trade |
| `created_at` | TIMESTAMP | Trade execution time |

---

## 5. Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + setup instructions |
| `/set_ssid <ssid>` | Save Quotex session token |
| `/set_stake <amount>` | Set trade stake (USD) |
| `/auto_on` | Enable auto-trade |
| `/auto_off` | Disable auto-trade (use buttons) |
| `/assets` | Select OTC pairs or ALL |
| `/status` | Show settings + last 5 trades + P&L |
| `/pause` | Stop receiving signals |
| `/resume` | Resume signals |
| `/balance` | Check Quotex account balance |

---

## 6. Signal Flow

```
1. Candle closes on Quotex WebSocket
2. data_feed.py → push to asyncio.Queue
3. patterns.py → consume candle:
   a. Check doji → if yes, reset streak to 0, exit
   b. Update streak (same color → +1, opposite → reset to 1)
   c. If streak >= 4 and next candle is opposite color:
      → SIGNAL detected
4. Check cooldown in database:
   → Signal for this asset in last 5 min? Skip if yes
5. Record signal in database
6. For each active user:
   a. Check if user's assets include this pair (or ALL)
   b. If auto_trade = true:
      - trader.py executes trade via user's SSID
      - Wait for result (1 min expiry)
      - Send DM: PROFIT/LOSS + P&L + balance
   c. If auto_trade = false:
      - Send DM with BUY/SELL inline buttons
      - Wait for user tap (60s expiry)
      - If tapped → trader.py executes
      - If expired → edit message to "EXPIRED"
```

---

## 7. Message Formats

### 7.1 Signal Alert (Auto-trade OFF)

```
🔴 SELL SIGNAL — EUR/USD OTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Timeframe: 1m
Pattern: 4x Green → Red reversal
Strength: 87%
Return: 87%

⏰ 14:32:05 UTC

[ BUY (CALL) ]  [ SELL (PUT) ]
```

### 7.2 Trade Confirmation

```
📈 BUY EUR/USD OTC — $10.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: Active
Waiting for result...
```

### 7.3 Trade Outcome — Win

```
✅ PROFIT — EUR/USD OTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━
P&L: +$8.70
Balance: $108.70
```

### 7.4 Trade Outcome — Loss

```
❌ LOSS — EUR/USD OTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━
P&L: -$10.00
Balance: $98.70
```

---

## 8. Error Handling

| Scenario | Response |
|----------|----------|
| Quotex SSID expired | DM: "⚠️ Session expired. Send new /set_ssid" |
| WebSocket disconnect | Auto-reconnect every 10s, log attempts |
| Insufficient balance | DM: "⚠️ Insufficient balance. Current: $X.XX" |
| Trade execution failed | DM: "❌ Trade failed: <reason>" |
| Telegram rate limit | Queue messages, send with 1s delays |
| Database connection lost | Retry 3x, then graceful shutdown |
| pyquotex API change | Alert admin, pause scanning |

---

## 9. Deployment (Railway)

### 9.1 Infrastructure

| Component | Railway Resource |
|-----------|------------------|
| Bot process | Background worker service |
| Database | Railway PostgreSQL add-on |
| Secrets | Railway environment variables |

### 9.2 Configuration Files

**Procfile**
```
worker: python main.py
```

**railway.toml**
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python main.py"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10
```

### 9.3 Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `DATABASE_URL` | Railway PostgreSQL connection string |
| `ADMIN_CHAT_ID` | Admin Telegram ID for alerts |
| `LOG_LEVEL` | INFO or DEBUG |

### 9.4 Deploy Flow

1. Push code to GitHub repo
2. Connect repo to Railway
3. Railway auto-deploys on push to main
4. Monitor logs in Railway dashboard

---

## 10. File Structure

```
quotex-bot/
├── main.py              # asyncio entry point
├── data_feed.py         # pyquotex WebSocket manager
├── patterns.py          # Strategy detection engine
├── bot.py               # Telegram bot + command handlers
├── trader.py            # Trade execution + result tracking
├── database.py          # SQLAlchemy models + connection
├── config.py            # Environment variable loader
├── requirements.txt     # Python dependencies
├── Procfile             # Railway process definition
├── railway.toml         # Railway configuration
├── .env.example         # Template for local dev
├── .gitignore
└── README.md            # Setup + usage guide
```

---

## 11. Dependencies

```
pyquotex>=1.0
python-telegram-bot>=20.0
sqlalchemy>=2.0
asyncpg>=0.29
alembic>=1.13
pyyaml>=60.0
python-dotenv>=1.0
```

---

## 12. Security Considerations

- User SSIDs stored encrypted at rest (AES-256 via Fernet)
- Database connections use SSL
- Telegram bot token in environment variables only
- No sensitive data in logs
- Rate limiting on commands (1 second per user)

---

## 13. Future Enhancements (Out of Scope)

- Multiple timeframe scanning (5m, 15m)
- Additional pattern strategies
- Web dashboard for analytics
- Signal performance tracking per user
- Referral system
- Payment integration for premium features

---

## 14. Open Questions

1. **Stake calculation:** Fixed amount only, or % of balance option?
2. **Doji threshold:** 0.2% range — confirm or adjust?
3. **Continuation signals:** How many candles to wait before firing the "deeper entry" signal? (Proposed: 3)
4. **Asset filter UI:** Inline keyboard for asset selection, or text command?

---

**Spec approved by:** Xafor  
**Date:** 2026-09-15
