# database.py
from sqlalchemy import Column, BigInteger, Numeric, Boolean, String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timedelta
from typing import Optional, List
from config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    chat_id = Column(BigInteger, primary_key=True)
    ssid = Column(String, nullable=False)  # Encrypted
    stake = Column(Numeric, nullable=False, default=1.0)
    auto_trade = Column(Boolean, default=False)
    assets = Column(JSON, nullable=False, default=list)  # ["ALL"] or ["EURUSD_OTC", ...]
    paused = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset = Column(String(20), nullable=False)
    direction = Column(String(4), nullable=False)  # CALL or PUT
    strength = Column(Numeric, nullable=False, default=50.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.chat_id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    asset = Column(String(20), nullable=False)
    direction = Column(String(4), nullable=False)
    amount = Column(Numeric, nullable=False)
    result = Column(String(10))  # WIN or LOSS
    pnl = Column(Numeric, default=0.0)
    balance_after = Column(Numeric)
    order_id = Column(String(50))  # Quotex order ID for result checking
    created_at = Column(DateTime, default=datetime.utcnow)


engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    return async_session()


async def get_user(session: AsyncSession, chat_id: int) -> Optional[User]:
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.chat_id == chat_id))
    return result.scalar_one_or_none()


async def save_user(session: AsyncSession, user: User):
    await session.merge(user)
    await session.commit()


async def get_active_users(session: AsyncSession) -> List[User]:
    from sqlalchemy import select
    result = await session.execute(
        select(User).where(User.paused == False)
    )
    return result.scalars().all()


async def save_signal(session: AsyncSession, signal: Signal) -> Signal:
    session.add(signal)
    await session.commit()
    await session.refresh(signal)
    return signal


async def save_trade(session: AsyncSession, trade: Trade) -> Trade:
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return trade


async def was_signal_recent(session: AsyncSession, asset: str, minutes: int = 5) -> bool:
    """Check if a signal was sent for this asset within the cooldown window."""
    from sqlalchemy import select
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    result = await session.execute(
        select(Signal).where(
            Signal.asset == asset,
            Signal.created_at > cutoff
        )
    )
    return result.scalar_one_or_none() is not None
