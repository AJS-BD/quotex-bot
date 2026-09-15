PASS_KEY = "encrypted_pass_string"

# tests/test_trader.py
import pytest
import pytest_asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock quotexpy before importing trader
mock_quotexpy = MagicMock()
sys.modules["quotexpy"] = mock_quotexpy

# Mock Fernet
mock_crypto = MagicMock()
sys.modules["cryptography"] = mock_crypto
sys.modules["cryptography.fernet"] = mock_crypto

from trader import Trader
from database import User


@pytest.fixture
def sample_user():
    return User(
        chat_id=123456,
        email="encrypted_email",
        password=PASS_KEY,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"],
    )


@pytest.mark.asyncio
async def test_trader_initialization():
    trader = Trader()
    assert trader is not None
    assert trader._clients == {}


@pytest.mark.asyncio
async def test_execute_trade_returns_trade_object(sample_user):
    mock_qx = AsyncMock()
    mock_qx.trade = AsyncMock(return_value={"status": "active"})
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    signal = MagicMock(asset="EURUSD_OTC", direction="CALL", id=1)
    trade = await trader.execute_trade(sample_user, signal)

    assert trade is not None
    assert trade.asset == "EURUSD_OTC"
    assert trade.direction == "CALL"
    assert trade.amount == 10.0
    assert trade.result is None


@pytest.mark.asyncio
async def test_execute_trade_returns_none_on_error(sample_user):
    mock_qx = AsyncMock()
    mock_qx.trade = AsyncMock(side_effect=Exception("API error"))
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    signal = MagicMock(asset="EURUSD_OTC", direction="CALL", id=1)
    trade = await trader.execute_trade(sample_user, signal)

    assert trade is None


@pytest.mark.asyncio
async def test_check_win_result(sample_user):
    mock_qx = AsyncMock()
    mock_qx.check_win = AsyncMock(return_value={"profit": 8.70, "balance": 108.70})
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    trade = MagicMock(asset="EURUSD_OTC")
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await trader.check_result(trade, sample_user)

    assert result["result"] == "WIN"
    assert result["pnl"] == 8.70
    assert result["balance"] == 108.70


@pytest.mark.asyncio
async def test_check_loss_result(sample_user):
    mock_qx = AsyncMock()
    mock_qx.check_win = AsyncMock(return_value={"profit": -10.0, "balance": 90.0})
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    trade = MagicMock(asset="EURUSD_OTC")
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await trader.check_result(trade, sample_user)

    assert result["result"] == "LOSS"
    assert result["pnl"] == -10.0


@pytest.mark.asyncio
async def test_get_balance(sample_user):
    mock_qx = AsyncMock()
    mock_qx.get_balance = AsyncMock(return_value=100.0)
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    balance = await trader.get_balance(sample_user)

    assert balance == 100.0


@pytest.mark.asyncio
async def test_get_balance_returns_zero_on_error(sample_user):
    mock_qx = AsyncMock()
    mock_qx.get_balance = AsyncMock(side_effect=Exception("Connection error"))
    mock_qx.connect = AsyncMock()
    mock_quotexpy.Quotex.return_value = mock_qx

    trader = Trader()
    balance = await trader.get_balance(sample_user)

    assert balance == 0.0
