# tests/test_trader.py
import pytest
import pytest_asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock pyquotex before importing trader
mock_pyquotex_module = MagicMock()
mock_qx_instance = AsyncMock()
mock_pyquotex_module.Quotex.return_value = mock_qx_instance
sys.modules['pyquotex'] = mock_pyquotex_module

# Mock Fernet for SSID decryption
mock_fernet_module = MagicMock()
mock_fernet_instance = MagicMock()
mock_fernet_instance.decrypt = MagicMock(return_value=b"decrypted_ssid")
mock_fernet_module.Fernet.return_value = mock_fernet_instance
sys.modules['cryptography'] = mock_fernet_module
sys.modules['cryptography.fernet'] = mock_fernet_module

from trader import Trader
from database import User


@pytest.fixture
def sample_user():
    return User(
        chat_id=123456,
        ssid="gAAAAABltest_encrypted_ssid",
        stake=10.0,
        auto_trade=True,
        assets=["ALL"]
    )


@pytest.mark.asyncio
async def test_trader_initialization():
    trader = Trader()
    assert trader is not None
    assert trader._clients == {}


@pytest.mark.asyncio
async def test_execute_trade_returns_trade_object(sample_user):
    mock_qx = AsyncMock()
    mock_qx.place_order = AsyncMock(return_value={"id": "order_123", "status": "active"})
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    signal = MagicMock(asset="EURUSD_OTC", direction="CALL", id=1)
    trade = await trader.execute_trade(sample_user, signal)

    assert trade is not None
    assert trade.asset == "EURUSD_OTC"
    assert trade.direction == "CALL"
    assert trade.amount == 10.0
    assert trade.result is None
    assert trade.order_id == "order_123"


@pytest.mark.asyncio
async def test_execute_trade_returns_none_on_error(sample_user):
    mock_qx = AsyncMock()
    mock_qx.place_order = AsyncMock(side_effect=Exception("API error"))
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    signal = MagicMock(asset="EURUSD_OTC", direction="CALL", id=1)
    trade = await trader.execute_trade(sample_user, signal)

    assert trade is None


@pytest.mark.asyncio
async def test_check_win_result(sample_user):
    mock_qx = AsyncMock()
    mock_qx.check_order_result = AsyncMock(return_value={"pnl": 8.70, "balance": 108.70})
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await trader.check_result("order_123", sample_user)

    assert result["result"] == "WIN"
    assert result["pnl"] == 8.70
    assert result["balance"] == 108.70
    assert "WIN" in result["message"]
    assert "+$8.70" in result["message"]
    assert "$108.70" in result["message"]


@pytest.mark.asyncio
async def test_check_loss_result(sample_user):
    mock_qx = AsyncMock()
    mock_qx.check_order_result = AsyncMock(return_value={"pnl": -10.0, "balance": 90.0})
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await trader.check_result("order_123", sample_user)

    assert result["result"] == "LOSS"
    assert result["pnl"] == -10.0
    assert result["balance"] == 90.0
    assert "LOSS" in result["message"]
    assert "-$10.00" in result["message"]


@pytest.mark.asyncio
async def test_format_result_message_win():
    trader = Trader()
    msg = trader._format_result_message(pnl=8.70, balance=108.70, asset="EURUSD_OTC")
    assert "✅" in msg
    assert "WIN" in msg
    assert "EURUSD_OTC" in msg
    assert "+$8.70" in msg
    assert "$108.70" in msg


@pytest.mark.asyncio
async def test_format_result_message_loss():
    trader = Trader()
    msg = trader._format_result_message(pnl=-10.0, balance=90.0, asset="EURUSD_OTC")
    assert "❌" in msg
    assert "LOSS" in msg
    assert "EURUSD_OTC" in msg
    assert "-$10.00" in msg


@pytest.mark.asyncio
async def test_format_result_message_no_asset():
    trader = Trader()
    msg = trader._format_result_message(pnl=5.0, balance=100.0, asset=None)
    assert "N/A" in msg
    assert "+$5.00" in msg


@pytest.mark.asyncio
async def test_get_balance(sample_user):
    mock_qx = AsyncMock()
    mock_qx.get_balance = AsyncMock(return_value=100.0)
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    balance = await trader.get_balance(sample_user)

    assert balance == 100.0


@pytest.mark.asyncio
async def test_get_balance_returns_zero_on_error(sample_user):
    mock_qx = AsyncMock()
    mock_qx.get_balance = AsyncMock(side_effect=Exception("Connection error"))
    mock_qx.connect = AsyncMock()
    mock_pyquotex_module.Quotex.return_value = mock_qx

    trader = Trader()
    balance = await trader.get_balance(sample_user)

    assert balance == 0.0
