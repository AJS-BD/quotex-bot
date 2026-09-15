# Quotex Telegram Bot

Multi-user Telegram bot that scans Quotex OTC markets for 4-candle reversal patterns and auto-trades on behalf of users.

## Strategy

- **4-candle streak** of same-color candles (dojis and shadow-dominant candles cancel the pattern)
- **Counter-candle** triggers signal WITH trend
- **5-minute cooldown** per asset per user
- **1-minute timeframe**

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your values
3. Install dependencies: `pip install -r requirements.txt`
4. Create database tables: `python -c "import asyncio; from database import create_tables; asyncio.run(create_tables())"`
5. Run: `python main.py`

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + setup guide |
| `/set_ssid <ssid>` | Save Quotex session |
| `/set_stake <amount>` | Set trade stake |
| `/auto_on` | Enable auto-trade |
| `/auto_off` | Use buttons instead |
| `/status` | Settings + P&L |
| `/pause` / `/resume` | Toggle alerts |
| `/balance` | Check Quotex balance |

## Deployment (Railway)

1. Push code to GitHub
2. Connect repo to Railway
3. Add PostgreSQL addon
4. Set environment variables in Railway dashboard
5. Deploy

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `ADMIN_CHAT_ID` | Your Telegram ID |
| `DATABASE_URL` | Railway PostgreSQL URL |
| `LOG_LEVEL` | INFO or DEBUG |
| `ENCRYPTION_KEY` | Fernet key (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |

## License

MIT
