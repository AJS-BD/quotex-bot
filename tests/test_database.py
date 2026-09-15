# tests/test_database.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from database import Base, User, Signal, Trade, get_user, save_user, create_tables, get_active_users, was_signal_recent, save_signal

DATABASE_URL = "sqlite+aiosqlite:///test.db"

EMAIL_KEY = "encrypted_email_string"
PASS_KEY = "encrypted_pass_string"


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
async def test_create_user(session):
    user = User(
        chat_id=123456,
        email=EMAIL_KEY,
        password=PASS_KEY,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"],
    )
    await save_user(session, user)

    result = await get_user(session, 123456)
    assert result is not None
    assert result.chat_id == 123456
    assert result.stake == 10.0
    assert result.auto_trade is True


@pytest.mark.asyncio
async def test_save_user_upsert(session):
    """Test that save_user updates existing user via merge."""
    user = User(
        chat_id=777,
        email=EMAIL_KEY,
        password=PASS_KEY,
        stake=5.0,
        auto_trade=False,
        assets=["ALL"],
    )
    await save_user(session, user)

    # Update
    user.stake = 25.0
    user.auto_trade = True
    await save_user(session, user)

    result = await get_user(session, 777)
    assert result.stake == 25.0
    assert result.auto_trade is True


@pytest.mark.asyncio
async def test_get_user_not_found(session):
    """Test get_user returns None for unknown user."""
    result = await get_user(session, 999999)
    assert result is None


@pytest.mark.asyncio
async def test_create_signal(session):
    signal = Signal(asset="EURUSD_OTC", direction="CALL", strength=75.0)
    session.add(signal)
    await session.commit()
    await session.refresh(signal)

    assert signal.id is not None
    assert signal.asset == "EURUSD_OTC"
    assert signal.direction == "CALL"


@pytest.mark.asyncio
async def test_create_trade(session):
    user = User(
        chat_id=555,
        email=EMAIL_KEY,
        password=PASS_KEY,
        stake=10.0,
        auto_trade=True,
        assets=["ALL"],
    )
    await save_user(session, user)

    trade = Trade(
        user_id=555,
        asset="EURUSD_OTC",
        direction="CALL",
        amount=10.0,
        result="WIN",
        pnl=8.70,
        balance_after=108.70
    )
    session.add(trade)
    await session.commit()
    await session.refresh(trade)

    assert trade.id is not None
    assert trade.result == "WIN"
    assert float(trade.pnl) == 8.70


@pytest.mark.asyncio
async def test_get_active_users(session):
    """Test fetching non-paused users."""
    u1 = User(
        chat_id=100, email=EMAIL_KEY, password=PASS_KEY,
        stake=1.0, auto_trade=False, assets=["ALL"], paused=False,
    )
    u2 = User(
        chat_id=101, email=EMAIL_KEY, password=PASS_KEY,
        stake=1.0, auto_trade=False, assets=["ALL"], paused=True,
    )
    await save_user(session, u1)
    await save_user(session, u2)

    active = await get_active_users(session)
    chat_ids = {u.chat_id for u in active}
    assert 100 in chat_ids
    assert 101 not in chat_ids


@pytest.mark.asyncio
async def test_was_signal_recent(session):
    """Test signal cooldown window."""
    recent = await was_signal_recent(session, "EURUSD_OTC", minutes=5)
    assert recent is False

    signal = Signal(asset="EURUSD_OTC", direction="CALL", strength=80.0)
    await save_signal(session, signal)

    recent = await was_signal_recent(session, "EURUSD_OTC", minutes=5)
    assert recent is True
