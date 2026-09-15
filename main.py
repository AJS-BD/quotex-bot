# main.py
import asyncio
import logging
import signal as os_signal
import sys

from config import TELEGRAM_BOT_TOKEN, LOG_LEVEL
from database import create_tables, get_session, Trade, User, get_user, save_trade
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from data_feed import DataFeed
from patterns import detect_pattern, Candle
from bot import QuotexBot
from trader import Trader

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

async def candle_processor(bot: QuotexBot, feed: DataFeed):
    """Process candles from feed and dispatch signals."""
    while True:
        try:
            event = await feed.get_candle()
            asset = event["asset"]
            candles = event["candles"]
            
            signal = detect_pattern(candles, asset)
            if signal:
                logger.info(f"Signal detected: {signal.direction} {signal.asset}")
                await bot.dispatch_signal(signal)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error processing candle: {e}")
            await asyncio.sleep(1)

async def auto_trade_checker():
    """Check results of auto-trades that are pending."""
    trader = Trader()
    while True:
        try:
            await asyncio.sleep(65)  # Check slightly after 1min expiry
            
            async with get_session() as session:
                cutoff = datetime.utcnow() - timedelta(minutes=2)
                result = await session.execute(
                    select(Trade).where(
                        Trade.result == None,
                        Trade.order_id != None,
                        Trade.created_at < cutoff
                    )
                )
                pending = result.scalars().all()
                
                for trade in pending:
                    user = await get_user(session, trade.user_id)
                    if user and trade.order_id:
                        res = await trader.check_result(trade, user)
                        trade.result = res["result"]
                        trade.pnl = res["pnl"]
                        trade.balance_after = res["balance"]
                        await save_trade(session, trade)
                        
                        logger.info(f"Trade result: {trade.result} {trade.asset}")
                        
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in trade checker: {e}")

async def main():
    logger.info("Starting Quotex Signal Bot...")
    
    # Create tables
    await create_tables()
    logger.info("Database ready")
    
    # Start bot
    bot = QuotexBot(token=TELEGRAM_BOT_TOKEN)
    logger.info("Telegram bot initialized")
    
    # Start data feed (no SSID needed — quotexpy handles auth internally)
    feed = DataFeed()
    try:
        await feed.connect()
        # Subscribe to OTC assets (fetch from Quotex API in production)
        sample_assets = [
            "EURUSD_OTC", "GBPUSD_OTC", "USDJPY_OTC", "AUDUSD_OTC",
            "EURJPY_OTC", "GBPJPY_OTC", "USDCHF_OTC", "NZDUSD_OTC"
        ]
        for asset in sample_assets:
            await feed.subscribe(asset)
        logger.info("Data feed connected")
    except Exception as e:
        logger.error(f"Data feed failed: {e}")
        logger.warning("Running without market data — signals won't be generated")
    
    # Run bot and candle processor concurrently
    loop = asyncio.get_event_loop()
    
    bot_task = loop.create_task(bot.app.start())
    processor_task = loop.create_task(candle_processor(bot, feed))
    checker_task = loop.create_task(auto_trade_checker())
    
    def shutdown():
        logger.info("Shutting down...")
        bot_task.cancel()
        processor_task.cancel()
        checker_task.cancel()
    
    os_signal.signal(os_signal.SIGINT, lambda s, f: shutdown())
    os_signal.signal(os_signal.SIGTERM, lambda s, f: shutdown())
    
    try:
        await asyncio.gather(bot_task, processor_task, checker_task)
    except asyncio.CancelledError:
        pass
    finally:
        await bot.app.stop()
        logger.info("Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
