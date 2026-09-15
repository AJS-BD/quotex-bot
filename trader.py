# trader.py
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self):
        self._clients = {}  # chat_id -> Quotex instance

    async def _get_client(self, user):
        """Get or create Quotex client for user."""
        if user.chat_id not in self._clients:
            from cryptography.fernet import Fernet
            from config import ENCRYPTION_KEY

            f = Fernet(ENCRYPTION_KEY.encode())
            email = f.decrypt(user.email.encode()).decode()
            password = f.decrypt(user.password.encode()).decode()

            from quotexpy import Quotex
            client = Quotex(email=email, password=password)
            await client.connect()
            self._clients[user.chat_id] = client

        return self._clients[user.chat_id]

    async def execute_trade(self, user, signal) -> Optional:
        """Execute trade on Quotex for user based on signal."""
        try:
            client = await self._get_client(user)

            direction = signal.direction.lower()
            order = await client.trade(
                asset=signal.asset,
                amount=float(user.stake),
                direction=direction,
                duration=60
            )

            from database import Trade

            trade = Trade(
                user_id=user.chat_id,
                signal_id=signal.id if hasattr(signal, 'id') else None,
                asset=signal.asset,
                direction=signal.direction,
                amount=user.stake,
                result=None,
                pnl=0.0
            )

            logger.info(f"Trade placed: {signal.direction} {signal.asset} @ ${user.stake}")
            return trade

        except Exception as e:
            logger.error(f"Trade execution failed for user {user.chat_id}: {e}")
            return None

    async def check_result(self, trade, user) -> dict:
        """Check trade result and return outcome with formatted message."""
        try:
            client = await self._get_client(user)

            # Wait for expiry (1 minute)
            await asyncio.sleep(60)

            # quotexpy returns check_win result
            result = await client.check_win(trade.asset)
            pnl = float(result.get("profit", 0))
            balance = float(result.get("balance", 0))

            return {
                "result": "WIN" if pnl > 0 else "LOSS",
                "pnl": pnl,
                "balance": balance,
                "message": self._format_result_message(pnl, balance, trade.asset)
            }

        except Exception as e:
            logger.error(f"Failed to check trade result: {e}")
            return {"result": "ERROR", "pnl": 0, "balance": 0, "message": f"❌ Error checking result: {e}"}

    def _format_result_message(self, pnl: float, balance: float, asset: str = None) -> str:
        """Format trade outcome message for user notification."""
        emoji = "✅" if pnl > 0 else "❌"
        result_text = "WIN" if pnl > 0 else "LOSS"
        # Handle negative sign: for negative pnl, format as -$X.XX (not +-X.XX)
        if pnl >= 0:
            pnl_str = f"+${pnl:.2f}"
        else:
            pnl_str = f"-${abs(pnl):.2f}"
        asset_str = asset if asset else "N/A"
        return (
            f"{emoji} {result_text} — {asset_str}\n"
            f"P&L: {pnl_str}\n"
            f"Balance: ${balance:.2f}"
        )

    async def get_balance(self, user) -> float:
        """Get user's Quotex balance."""
        try:
            client = await self._get_client(user)
            balance = await client.get_balance()
            return float(balance)
        except Exception as e:
            logger.error(f"Failed to get balance for {user.chat_id}: {e}")
            return 0.0
