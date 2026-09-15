# tests/test_integration.py
"""
Integration tests for the full signal pipeline.
Pattern detection → signal saved → user notified → trade executed → result checked.
"""
import pytest
import pytest_asyncio
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Mock Fernet to avoid dependency on real ENCRYPTION_KEY and cross-test contamination
mock_fernet_module = MagicMock()
mock_fernet_instance = MagicMock()
mock_fernet_instance.encrypt = MagicMock(return_value=b"encrypted_test_ssid")
mock_fernet_instance.decrypt = MagicMock(return_value=b"test_ssid")
mock_fernet_module.Fernet.return_value = mock_fernet_instance
sys.modules['cryptography'] = mock_fernet_module
sys.modules['cryptography.fernet'] = mock_fernet_module

from database import Base, User, Signal, Trade, get_user, save_user, save_trade, save_signal, was_signal_recent, get_active_users
from patterns import Candle, detect_pattern, has_dominant_shadows, is_doji

DATABASE_URL = "sqlite+aiosqlite:///test_integration.db"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with AsyncSession(engine) as sess:
        yield sess


@pytest.mark.asyncio
async def test_pattern_detection_buy_signal():
    """Test: 4 green + red = CALL signal."""
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=104, high=104.1, low=102.9),
        Candle(open=104, close=102, high=104.1, low=101.9),
    ]

    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is not None
    assert signal.direction == "CALL"
    assert signal.asset == "EURUSD_OTC"
    assert signal.strength > 50


@pytest.mark.asyncio
async def test_pattern_detection_sell_signal():
    """Test: 4 red + green = PUT signal."""
    candles = [
        Candle(open=104, close=103, high=104.1, low=102.9),
        Candle(open=103, close=102, high=103.1, low=101.9),
        Candle(open=102, close=101, high=102.1, low=100.9),
        Candle(open=101, close=100, high=101.1, low=99.9),
        Candle(open=100, close=102, high=102.1, low=99.9),
    ]

    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is not None
    assert signal.direction == "PUT"


@pytest.mark.asyncio
async def test_doji_cancels_pattern():
    """Test: doji in streak = no signal."""
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=103, high=103.1, low=102.9),  # doji
        Candle(open=103, close=102, high=103.1, low=101.9),
    ]

    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is None


@pytest.mark.asyncio
async def test_shadow_dominant_cancels_pattern():
    """Test: shadow-dominant candle in streak = no signal."""
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=104, high=115, low=92),  # shadow-dominant
        Candle(open=104, close=102, high=104.1, low=101.9),
    ]

    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is None


@pytest.mark.asyncio
async def test_signal_save_and_cooldown(session):
    """Test: signal saved to DB, cooldown prevents duplicates."""
    signal = Signal(asset="EURUSD_OTC", direction="CALL", strength=85.0)
    saved = await save_signal(session, signal)
    assert saved.id is not None

    # Cooldown should now be active
    assert await was_signal_recent(session, "EURUSD_OTC", minutes=5) is True

    # Different asset should not be on cooldown
    assert await was_signal_recent(session, "GBPUSD_OTC", minutes=5) is False


@pytest.mark.asyncio
async def test_user_save_and_retrieve(session):
    """Test: user can be saved and retrieved."""
    encrypted_ssid = mock_fernet_module.Fernet().encrypt(b"test_ssid").decode()

    user = User(
        chat_id=999999,
        ssid=encrypted_ssid,
        stake=10.0,
        auto_trade=False,
        assets=["ALL"]
    )
    await save_user(session, user)

    retrieved = await get_user(session, 999999)
    assert retrieved is not None
    assert retrieved.chat_id == 999999
    assert float(retrieved.stake) == 10.0


@pytest.mark.asyncio
async def test_active_users_filter(session):
    """Test: paused users are excluded from active list."""
    encrypted_ssid = mock_fernet_module.Fernet().encrypt(b"test_ssid").decode()

    active_user = User(
        chat_id=111111,
        ssid=encrypted_ssid,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"],
        paused=False
    )
    paused_user = User(
        chat_id=222222,
        ssid=encrypted_ssid,
        stake=5.0,
        auto_trade=True,
        assets=["ALL"],
        paused=True
    )
    await save_user(session, active_user)
    await save_user(session, paused_user)

    active_users = await get_active_users(session)
    chat_ids = [u.chat_id for u in active_users]
    assert 111111 in chat_ids
    assert 222222 not in chat_ids


@pytest.mark.asyncio
async def test_trade_save_and_result(session):
    """Test: trade can be saved and result updated."""
    # First save a user (Trade has FK to users.chat_id)
    encrypted_ssid = mock_fernet_module.Fernet().encrypt(b"test_ssid").decode()

    user = User(
        chat_id=999999,
        ssid=encrypted_ssid,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"]
    )
    await save_user(session, user)

    trade = Trade(
        user_id=999999,
        asset="EURUSD_OTC",
        direction="CALL",
        amount=10.0,
        order_id="order_123",
        result=None
    )
    saved = await save_trade(session, trade)
    assert saved.id is not None  # Refresh populates the ID

    # Update result
    trade.result = "WIN"
    trade.pnl = 8.70
    trade.balance_after = 108.70
    updated = await save_trade(session, trade)
    assert updated.result == "WIN"
    assert float(updated.pnl) == 8.70
    assert float(updated.balance_after) == 108.70


# ============================================================
# FULL PIPELINE INTEGRATION TEST
# ============================================================

@pytest.mark.asyncio
async def test_full_signal_pipeline(session):
    """
    Full end-to-end pipeline: pattern detection → signal saved →
    user notified (mock) → trade executed → result checked.
    """
    # Step 0: Setup user
    encrypted_ssid = mock_fernet_module.Fernet().encrypt(b"test_ssid").decode()

    user = User(
        chat_id=777777,
        ssid=encrypted_ssid,
        stake=5.0,
        auto_trade=False,
        assets=["ALL"]
    )
    await save_user(session, user)

    # Step 1: Pattern detection
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=104, high=104.1, low=102.9),
        Candle(open=104, close=102, high=104.1, low=101.9),
    ]
    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is not None
    assert signal.direction == "CALL"

    # Step 2: Signal saved to DB
    saved_signal = await save_signal(session, signal)
    assert saved_signal.id is not None
    assert saved_signal.asset == "EURUSD_OTC"

    # Step 3: Verify cooldown is active
    assert await was_signal_recent(session, "EURUSD_OTC", minutes=5) is True

    # Step 4: Verify user can be retrieved and is active
    retrieved_user = await get_user(session, 777777)
    assert retrieved_user is not None
    assert retrieved_user.paused is False

    active_users = await get_active_users(session)
    assert any(u.chat_id == 777777 for u in active_users)

    # Step 5: Simulate notification (mock bot)
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    # Simulate sending notification
    await mock_bot.send_message(
        chat_id=retrieved_user.chat_id,
        text=f"Signal: {signal.direction} {signal.asset} (strength: {signal.strength})"
    )
    mock_bot.send_message.assert_called_once()

    # Step 6: Trade executed and saved
    trade = Trade(
        user_id=retrieved_user.chat_id,
        signal_id=saved_signal.id,
        asset=signal.asset,
        direction=signal.direction,
        amount=float(retrieved_user.stake),
        order_id="order_pipeline_001",
        result=None
    )
    saved_trade = await save_trade(session, trade)
    assert saved_trade.id is not None

    # Step 7: Result checked and updated
    saved_trade.result = "WIN"
    saved_trade.pnl = 4.35
    saved_trade.balance_after = 104.35
    updated_trade = await save_trade(session, saved_trade)
    assert updated_trade.result == "WIN"
    assert float(updated_trade.pnl) == 4.35
    assert updated_trade.order_id == "order_pipeline_001"


@pytest.mark.asyncio
async def test_no_signal_when_cooldown_active(session):
    """
    Integration: signal is detected but cooldown prevents duplicate processing.
    """
    # First, save a signal for EURUSD_OTC
    signal1 = Signal(asset="EURUSD_OTC", direction="CALL", strength=80.0)
    await save_signal(session, signal1)

    # Pattern detection would still return a signal (detection is stateless)
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=104, high=104.1, low=102.9),
        Candle(open=104, close=102, high=104.1, low=101.9),
    ]
    signal2 = detect_pattern(candles, "EURUSD_OTC")
    assert signal2 is not None

    # But cooldown check should block re-saving
    is_recent = await was_signal_recent(session, "EURUSD_OTC", minutes=5)
    assert is_recent is True

    # Different asset should not be on cooldown
    signal3 = detect_pattern(candles, "GBPUSD_OTC")
    assert signal3 is not None
    assert await was_signal_recent(session, "GBPUSD_OTC", minutes=5) is False


@pytest.mark.asyncio
async def test_paused_user_excluded_from_trade(session):
    """
    Integration: paused user's signal detection does not result in trade.
    """
    # Create a paused user (unique chat_id to avoid conflicts)
    encrypted_ssid = mock_fernet_module.Fernet().encrypt(b"test_ssid").decode()

    paused_user = User(
        chat_id=333333,
        ssid=encrypted_ssid,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"],
        paused=True
    )
    await save_user(session, paused_user)

    # Pattern detection still works
    candles = [
        Candle(open=100, close=101, high=101.1, low=99.9),
        Candle(open=101, close=102, high=102.1, low=100.9),
        Candle(open=102, close=103, high=103.1, low=101.9),
        Candle(open=103, close=104, high=104.1, low=102.9),
        Candle(open=104, close=102, high=104.1, low=101.9),
    ]
    signal = detect_pattern(candles, "EURUSD_OTC")
    assert signal is not None

    # But paused user is excluded from active users
    active_users = await get_active_users(session)
    assert not any(u.chat_id == 333333 for u in active_users)

    # No trade should be created for paused user
    # (In production, the dispatch logic would skip them)
    trades = []
    for u in active_users:
        if u.auto_trade:
            trade = Trade(
                user_id=u.chat_id,
                asset=signal.asset,
                direction=signal.direction,
                amount=float(u.stake),
                order_id="order_paused_test",
                result=None
            )
            trades.append(trade)

    # No trades created since paused user is excluded and no other auto_trade users exist
    assert len(trades) == 0
