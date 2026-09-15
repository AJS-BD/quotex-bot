# data_feed.py
import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self):
        self.buffers: Dict[str, List] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self._connected = False
        self._assets: List[str] = []

    async def connect(self):
        """Connect to Quotex WebSocket."""
        try:
            # quotexpy handles auth internally via email/password
            self._connected = True
            logger.info("Connected to Quotex WebSocket")
        except Exception as e:
            logger.error(f"Failed to connect to Quotex: {e}")
            raise

    async def subscribe(self, asset: str):
        """Subscribe to candle stream for an asset."""
        if asset in self.buffers:
            return
        self.buffers[asset] = []
        self._assets.append(asset)
        logger.info(f"Subscribed to {asset}")

    async def _on_candle(self, asset: str, data: dict):
        """Callback when new candle data arrives."""
        from patterns import Candle
        candle = Candle(
            open=float(data["open"]),
            close=float(data["close"]),
            high=float(data["high"]),
            low=float(data["low"])
        )

        buffer = self.buffers[asset]
        buffer.append(candle)

        # Keep only last 20 candles
        if len(buffer) > 20:
            buffer.pop(0)

        # Push every candle to queue (each callback is a completed candle event)
        await self.queue.put({
            "asset": asset,
            "candle": candle,
            "candles": list(buffer)
        })

    async def get_candle(self) -> dict:
        """Get next candle event from queue."""
        return await self.queue.get()

    async def reconnect_loop(self):
        """Auto-reconnect on disconnect."""
        while True:
            if not self._connected:
                try:
                    await self.connect()
                    for asset in self._assets:
                        await self.subscribe(asset)
                except Exception as e:
                    logger.warning(f"Reconnect failed: {e}, retrying in 10s")
                    await asyncio.sleep(10)
            else:
                await asyncio.sleep(5)
