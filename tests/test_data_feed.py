# tests/test_data_feed.py
import pytest
import pytest_asyncio
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock pyquotex before importing data_feed
mock_pyquotex_module = MagicMock()
mock_qx_instance = AsyncMock()
mock_pyquotex_module.Quotex.return_value = mock_qx_instance
sys.modules['pyquotex'] = mock_pyquotex_module

from data_feed import DataFeed

@pytest.fixture
def mock_qx():
    return MagicMock()

@pytest.mark.asyncio
async def test_datafeed_initialization():
    feed = DataFeed(ssid="test_ssid")
    assert feed.ssid == "test_ssid"
    assert feed.buffers == {}

@pytest.mark.asyncio
async def test_subscribe_creates_buffer():
    feed = DataFeed(ssid="test")
    await feed.subscribe("EURUSD_OTC")
    assert "EURUSD_OTC" in feed.buffers
    assert len(feed.buffers["EURUSD_OTC"]) == 0

@pytest.mark.asyncio
async def test_on_new_candle_adds_to_buffer():
    feed = DataFeed(ssid="test")
    await feed.subscribe("EURUSD_OTC")
    
    candle = {"open": 100.0, "close": 101.0, "high": 101.5, "low": 99.5, "time": 1234567890}
    await feed._on_candle("EURUSD_OTC", candle)
    
    assert len(feed.buffers["EURUSD_OTC"]) == 1
    assert feed.buffers["EURUSD_OTC"][0].close == 101.0
    assert feed.buffers["EURUSD_OTC"][0].high == 101.5
    assert feed.buffers["EURUSD_OTC"][0].low == 99.5

@pytest.mark.asyncio
async def test_buffer_max_length_20():
    feed = DataFeed(ssid="test")
    await feed.subscribe("EURUSD_OTC")
    
    for i in range(25):
        await feed._on_candle("EURUSD_OTC", {"open": 100+i, "close": 101+i, "high": 101.5+i, "low": 99.5+i, "time": 1234567890+i})
    
    assert len(feed.buffers["EURUSD_OTC"]) == 20

@pytest.mark.asyncio
async def test_get_candle_returns_from_queue():
    feed = DataFeed(ssid="test")
    await feed.subscribe("EURUSD_OTC")
    
    candle = {"open": 100.0, "close": 101.0, "high": 101.5, "low": 99.5, "time": 1234567890}
    await feed._on_candle("EURUSD_OTC", candle)
    
    result = await asyncio.wait_for(feed.get_candle(), timeout=1.0)
    assert result["asset"] == "EURUSD_OTC"
    assert result["candle"].close == 101.0
