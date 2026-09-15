# tests/test_bot.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot import QuotexBot


def make_mock_session(user=None, trades=None):
    """Create a properly configured mock async session."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # Create a result mock that supports both scalar_one_or_none and scalars().all()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    result.scalars.return_value.all.return_value = trades or []

    # execute must return an awaitable
    async def execute_side_effect(*args, **kwargs):
        return result
    mock_session.execute = execute_side_effect
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.merge = AsyncMock()
    return mock_session


@pytest.fixture
def mock_application():
    """Mock the Telegram Application to prevent actual network calls."""
    with patch("bot.Application") as MockApp:
        mock_app = MagicMock()
        mock_app.bot = AsyncMock()
        mock_app.add_handler = MagicMock()
        mock_app.run_polling = MagicMock()
        MockApp.builder.return_value.token.return_value.build.return_value = mock_app
        yield MockApp


@pytest.fixture
def mock_trader():
    with patch("bot.Trader") as MockTrader:
        mock_instance = AsyncMock()
        mock_instance.get_balance = AsyncMock(return_value=100.0)
        mock_instance.execute_trade = AsyncMock(return_value=MagicMock(
            order_id="order_123",
            asset="EURUSD_OTC",
            direction="CALL",
            amount=10.0,
            result=None,
            pnl=0.0,
        ))
        mock_instance.check_result = AsyncMock(return_value={
            "result": "WIN",
            "pnl": 8.7,
            "balance": 108.7,
            "message": "✅ WIN — EURUSD_OTC\nP&L: +$8.70\nBalance: $108.70"
        })
        MockTrader.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def bot(mock_application, mock_trader):
    """Create bot instance with mocked Application and Trader."""
    return QuotexBot(token="test_token_123")


@pytest.mark.asyncio
async def test_bot_initialization(bot, mock_application):
    assert bot.token == "test_token_123"
    mock_application.builder.return_value.token.assert_called_once_with("test_token_123")


@pytest.mark.asyncio
async def test_start_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    context = MagicMock()
    context.bot = AsyncMock()

    await bot.start_command(update, context)
    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args[1]
    assert "Welcome" in call_kwargs["text"]
    assert "set_ssid" in call_kwargs["text"]
    assert "set_stake" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_set_ssid_command_new_user(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()
    context.args = ["test_session_id_abc"]

    mock_session = make_mock_session(user=None)

    with patch("bot.get_session", return_value=mock_session):
        with patch("cryptography.fernet.Fernet") as mock_fernet:
            mock_f = MagicMock()
            mock_f.encrypt.return_value = b"encrypted_data"
            mock_fernet.return_value = mock_f
            with patch("config.ENCRYPTION_KEY", "test_key"):
                await bot.set_ssid_command(update, context)

    update.message.reply_text.assert_called_with("✅ Session ID saved!")


@pytest.mark.asyncio
async def test_set_ssid_command_no_args(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()
    context.args = []

    await bot.set_ssid_command(update, context)
    update.message.reply_text.assert_called_with("Usage: /set_ssid <your_quotex_session_id>")


@pytest.mark.asyncio
async def test_set_stake_command_success(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()
    context.args = ["25"]

    mock_user = MagicMock()
    mock_user.stake = 25.0
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.set_stake_command(update, context)

    update.message.reply_text.assert_called_with("✅ Stake set to $25.00")


@pytest.mark.asyncio
async def test_set_stake_command_no_user(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()
    context.args = ["25"]

    mock_session = make_mock_session(user=None)

    with patch("bot.get_session", return_value=mock_session):
        await bot.set_stake_command(update, context)

    update.message.reply_text.assert_called_with("⚠️ First set your SSID with /set_ssid")


@pytest.mark.asyncio
async def test_set_stake_command_invalid(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()
    context.args = ["not_a_number"]

    await bot.set_stake_command(update, context)
    update.message.reply_text.assert_called_with("❌ Invalid amount. Use a number like: /set_stake 10")


@pytest.mark.asyncio
async def test_auto_on_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_user.auto_trade = True
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.auto_on_command(update, context)

    update.message.reply_text.assert_called_with("✅ Auto-trade enabled!")


@pytest.mark.asyncio
async def test_auto_off_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_user.auto_trade = False
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.auto_off_command(update, context)

    update.message.reply_text.assert_called_with("✅ Auto-trade disabled. You'll get buttons to confirm.")


@pytest.mark.asyncio
async def test_status_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_user.stake = 10.0
    mock_user.auto_trade = True
    mock_user.assets = ["ALL"]
    mock_user.paused = False

    mock_trade1 = MagicMock()
    mock_trade1.pnl = 8.7
    mock_trade2 = MagicMock()
    mock_trade2.pnl = -5.0

    mock_session = make_mock_session(user=mock_user, trades=[mock_trade1, mock_trade2])

    with patch("bot.get_session", return_value=mock_session):
        await bot.status_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "$10.00" in call_text
    assert "ON" in call_text
    assert "ACTIVE" in call_text
    assert "+$3.70" in call_text


@pytest.mark.asyncio
async def test_pause_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_user.paused = True
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.pause_command(update, context)

    update.message.reply_text.assert_called_with("⏸️ Paused. Use /resume to restart.")


@pytest.mark.asyncio
async def test_resume_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_user.paused = False
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.resume_command(update, context)

    update.message.reply_text.assert_called_with("▶️ Resumed! Watching for signals...")


@pytest.mark.asyncio
async def test_balance_command(bot):
    update = MagicMock()
    update.effective_user.id = 123456
    update.message = AsyncMock()
    context = MagicMock()

    mock_user = MagicMock()
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        await bot.balance_command(update, context)

    update.message.reply_text.assert_called_with("💰 Balance: $100.00")


@pytest.mark.asyncio
async def test_button_callback(bot):
    update = MagicMock()
    query = AsyncMock()
    query.from_user.id = 123456
    query.data = "CALL_EURUSD_OTC"
    update.callback_query = query

    context = MagicMock()
    context.bot = AsyncMock()

    mock_user = MagicMock()
    mock_user.stake = 10.0
    mock_session = make_mock_session(user=mock_user)

    with patch("bot.get_session", return_value=mock_session):
        with patch("bot.Signal") as MockSignal:
            mock_signal = MagicMock()
            MockSignal.return_value = mock_signal
            await bot.button_callback(update, context)

    query.answer.assert_called_once()
    query.edit_message_text.assert_called()


@pytest.mark.asyncio
async def test_dispatch_signal_with_buttons(bot):
    """Test that dispatch_signal sends buttons to non-auto-trade users."""
    mock_signal = MagicMock()
    mock_signal.asset = "EURUSD_OTC"
    mock_signal.direction = "CALL"
    mock_signal.strength = 80.0

    mock_user = MagicMock()
    mock_user.chat_id = 123456
    mock_user.auto_trade = False
    mock_user.assets = ["ALL"]

    mock_session = make_mock_session()

    with patch("bot.get_session", return_value=mock_session):
        with patch("bot.get_active_users", return_value=[mock_user]):
            with patch("bot.was_signal_recent", return_value=False):
                with patch("bot.save_signal") as mock_save_signal:
                    mock_saved = MagicMock()
                    mock_saved.id = 1
                    mock_saved.asset = "EURUSD_OTC"
                    mock_saved.direction = "CALL"
                    mock_saved.strength = 80.0
                    mock_save_signal.return_value = mock_saved
                    await bot.dispatch_signal(mock_signal)

    bot.app.bot.send_message.assert_called_once()
    call_kwargs = bot.app.bot.send_message.call_args[1]
    assert "CALL" in call_kwargs["text"]
    assert "EURUSD_OTC" in call_kwargs["text"]
    assert "reply_markup" in call_kwargs


@pytest.mark.asyncio
async def test_dispatch_signal_auto_trade_user(bot):
    """Test that dispatch_signal auto-trades for auto_trade users."""
    mock_signal = MagicMock()
    mock_signal.asset = "EURUSD_OTC"
    mock_signal.direction = "CALL"
    mock_signal.strength = 80.0

    mock_user = MagicMock()
    mock_user.chat_id = 123456
    mock_user.auto_trade = True
    mock_user.assets = ["ALL"]

    mock_session = make_mock_session()

    with patch("bot.get_session", return_value=mock_session):
        with patch("bot.get_active_users", return_value=[mock_user]):
            with patch("bot.was_signal_recent", return_value=False):
                with patch("bot.save_signal") as mock_save_signal:
                    mock_saved = MagicMock()
                    mock_saved.id = 1
                    mock_save_signal.return_value = mock_saved
                    await bot.dispatch_signal(mock_signal)

    # For auto-trade user, should NOT send buttons but notify trade start
    bot.app.bot.send_message.assert_called_once()
    call_kwargs = bot.app.bot.send_message.call_args[1]
    assert "Auto-trading" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_dispatch_signal_asset_filter(bot):
    """Test that dispatch_signal filters by user's allowed assets."""
    mock_signal = MagicMock()
    mock_signal.asset = "GBPUSD_OTC"

    mock_user = MagicMock()
    mock_user.chat_id = 123456
    mock_user.auto_trade = False
    mock_user.assets = ["EURUSD_OTC"]  # Not matching

    mock_session = make_mock_session()

    with patch("bot.get_session", return_value=mock_session):
        with patch("bot.get_active_users", return_value=[mock_user]):
            await bot.dispatch_signal(mock_signal)

    # Should not send anything since asset is filtered
    bot.app.bot.send_message.assert_not_called()


def test_run(bot):
    bot.run()
    bot.app.run_polling.assert_called_once()
