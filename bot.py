# bot.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from sqlalchemy import select
from database import (
    get_session, User, Signal, Trade, get_user, save_user,
    get_active_users, save_signal, save_trade, was_signal_recent
)
from trader import Trader

logger = logging.getLogger(__name__)


class QuotexBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.trader = Trader()
        self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("set_email", self.set_email_command))
        self.app.add_handler(CommandHandler("set_password", self.set_password_command))
        self.app.add_handler(CommandHandler("set_stake", self.set_stake_command))
        self.app.add_handler(CommandHandler("auto_on", self.auto_on_command))
        self.app.add_handler(CommandHandler("auto_off", self.auto_off_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("pause", self.pause_command))
        self.app.add_handler(CommandHandler("resume", self.resume_command))
        self.app.add_handler(CommandHandler("balance", self.balance_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        welcome = (
            "🚀 Welcome to Quotex Signal Bot!\n\n"
            "I scan OTC markets for 4-candle reversal patterns.\n\n"
            "Setup:\n"
            "1. /set_email <your_quotex_email>\n"
            "2. /set_password <your_quotex_password>\n"
            "3. /set_stake <amount>\n"
            "4. /auto_on (or use buttons)\n\n"
            "Commands:\n"
            "/status - View settings & P&L\n"
            "/pause /resume - Toggle alerts\n"
            "/balance - Check Quotex balance"
        )
        await context.bot.send_message(chat_id=user_id, text=welcome)

    async def set_email_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("Usage: /set_email <your_quotex_email>")
            return

        from cryptography.fernet import Fernet
        from config import ENCRYPTION_KEY

        email = " ".join(context.args)
        f = Fernet(ENCRYPTION_KEY.encode())
        encrypted_email = f.encrypt(email.encode()).decode()

        async with get_session() as session:
            user = await get_user(session, user_id)
            if user is None:
                user = User(chat_id=user_id, email=encrypted_email, password="", stake=1.0, auto_trade=False, assets=["ALL"])
            else:
                user.email = encrypted_email
            await save_user(session, user)

        await update.message.reply_text("✅ Email saved! Now use /set_password")

    async def set_password_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("Usage: /set_password <your_quotex_password>")
            return

        from cryptography.fernet import Fernet
        from config import ENCRYPTION_KEY

        password = " ".join(context.args)
        f = Fernet(ENCRYPTION_KEY.encode())
        encrypted_password = f.encrypt(password.encode()).decode()

        async with get_session() as session:
            user = await get_user(session, user_id)
            if user is None:
                await update.message.reply_text("⚠️ Set email first with /set_email")
                return
            user.password = encrypted_password
            await save_user(session, user)

        await update.message.reply_text("✅ Password saved! Ready to trade.")

    async def set_stake_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not context.args:
            await update.message.reply_text("Usage: /set_stake <amount_in_usd>")
            return

        try:
            stake = float(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use a number like: /set_stake 10")
            return

        async with get_session() as session:
            user = await get_user(session, user_id)
            if user is None:
                await update.message.reply_text("⚠️ First set your email with /set_email")
                return
            user.stake = stake
            await save_user(session, user)

        await update.message.reply_text(f"✅ Stake set to ${stake:.2f}")

    async def auto_on_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if not user:
                await update.message.reply_text("⚠️ Set email, password and stake first.")
                return
            user.auto_trade = True
            await save_user(session, user)
        await update.message.reply_text("✅ Auto-trade enabled!")

    async def auto_off_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if not user:
                await update.message.reply_text("⚠️ Set email, password and stake first.")
                return
            user.auto_trade = False
            await save_user(session, user)
        await update.message.reply_text("✅ Auto-trade disabled. You'll get buttons to confirm.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if not user:
                await update.message.reply_text("⚠️ Not registered. Use /start")
                return

            result = await session.execute(
                select(Trade).where(Trade.user_id == user_id).order_by(Trade.created_at.desc()).limit(5)
            )
            trades = result.scalars().all()

            total_pnl = sum(float(t.pnl) for t in trades)

            text = (
                f"📊 Status\n"
                f"━━━━━━━━━━━━━━━\n"
                f"Stake: ${float(user.stake):.2f}\n"
                f"Auto-trade: {'ON' if user.auto_trade else 'OFF'}\n"
                f"Assets: {', '.join(user.assets)}\n"
                f"Status: {'PAUSED' if user.paused else 'ACTIVE'}\n\n"
                f"Recent P&L (last 5): {'+' if total_pnl >= 0 else ''}${total_pnl:.2f}\n"
                f"Trades: {len(trades)}"
            )
            await update.message.reply_text(text)

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if user:
                user.paused = True
                await save_user(session, user)
        await update.message.reply_text("⏸️ Paused. Use /resume to restart.")

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if user:
                user.paused = False
                await save_user(session, user)
        await update.message.reply_text("▶️ Resumed! Watching for signals...")

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        async with get_session() as session:
            user = await get_user(session, user_id)
            if not user:
                await update.message.reply_text("⚠️ Not registered.")
                return
            balance = await self.trader.get_balance(user)
            await update.message.reply_text(f"💰 Balance: ${balance:.2f}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button taps (BUY/SELL)."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data  # "CALL_EURUSD_OTC" or "PUT_EURUSD_OTC"

        parts = data.split("_", 1)
        direction = parts[0]
        asset = parts[1] if len(parts) > 1 else ""

        async with get_session() as session:
            user = await get_user(session, user_id)
            if not user:
                await query.edit_message_text("⚠️ Not registered. Use /start")
                return

            signal = Signal(asset=asset, direction=direction, strength=80.0)
            trade = await self.trader.execute_trade(user, signal)

            if trade:
                await save_trade(session, trade)
                await query.edit_message_text(f"📈 {direction} {asset} @ ${float(user.stake):.2f} — Active")

                # Check result after 60s
                result = await self.trader.check_result(trade, user)
                trade.result = result["result"]
                trade.pnl = result["pnl"]
                trade.balance_after = result["balance"]
                await save_trade(session, trade)

                await context.bot.send_message(chat_id=user_id, text=result["message"])
            else:
                await query.edit_message_text("❌ Trade failed to execute.")

    async def dispatch_signal(self, signal: Signal):
        """Send signal to all active users."""
        async with get_session() as session:
            users = await get_active_users(session)

            for user in users:
                if "ALL" not in user.assets and signal.asset not in user.assets:
                    continue

                if await was_signal_recent(session, signal.asset, minutes=5):
                    continue

                saved_signal = await save_signal(session, signal)

                if user.auto_trade:
                    trade = await self.trader.execute_trade(user, signal)
                    if trade:
                        trade.signal_id = saved_signal.id
                        await save_trade(session, trade)
                        await self._notify_trade_start(user.chat_id, signal, user)
                else:
                    await self._send_signal_with_buttons(user.chat_id, saved_signal)

    async def _send_signal_with_buttons(self, chat_id: int, signal: Signal):
        keyboard = [
            [
                InlineKeyboardButton("📈 BUY (CALL)", callback_data=f"CALL_{signal.asset}"),
                InlineKeyboardButton("📉 SELL (PUT)", callback_data=f"PUT_{signal.asset}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        direction_emoji = "🔴" if signal.direction == "PUT" else "🟢"

        text = (
            f"{direction_emoji} {signal.direction} SIGNAL — {signal.asset}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Timeframe: 1m\n"
            f"Strength: {signal.strength}%\n"
            f"Return: {int(signal.strength)}%"
        )

        await self.app.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    async def _notify_trade_start(self, chat_id: int, signal, user):
        text = f"📈 Auto-trading: {signal.direction} {signal.asset} @ ${float(user.stake):.2f}"
        await self.app.bot.send_message(chat_id=chat_id, text=text)

    def run(self):
        """Start the bot."""
        self.app.run_polling()
