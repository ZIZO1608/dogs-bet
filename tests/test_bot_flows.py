"""End-to-end run of the real handlers against a fake Telegram API (no network)."""

import itertools
from datetime import datetime, timezone

import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    EditMessageCaption,
    EditMessageReplyMarkup,
    EditMessageText,
    GetChatMember,
    SendMessage,
    SendPhoto,
    SetMyCommands,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, ChatMemberLeft, ChatMemberMember, Message, MessageId, PhotoSize, Update, User
from sqlalchemy import update as sa_update

from app.__main__ import build_dispatcher
from app.db import create_tables, make_engine, make_sessionmaker
from app.handlers import account, admin, fallback, shop, start, topup
from app.models import PaymentMethod
from app.seed import seed_if_empty
from app.services.wallet import get_balance

USER_ID, ADMIN_ID = 111, 999
_ids = itertools.count(1)


class FakeTelegram(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.member = True

    async def close(self):
        pass

    async def stream_content(self, *a, **k):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        now = datetime.now(timezone.utc)
        if isinstance(method, (SendMessage, SendPhoto)):
            return Message(
                message_id=next(_ids),
                date=now,
                chat=Chat(id=method.chat_id, type="private"),
                text=getattr(method, "text", None),
                caption=getattr(method, "caption", None),
            )
        if isinstance(method, GetChatMember):
            user = User(id=method.user_id, is_bot=False, first_name="x")
            return ChatMemberMember(user=user) if self.member else ChatMemberLeft(user=user)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(_ids))
        if isinstance(method, (EditMessageText, EditMessageCaption, EditMessageReplyMarkup, AnswerCallbackQuery, SetMyCommands)):
            return True
        raise AssertionError(f"unexpected call {type(method).__name__}")

    # helpers
    def sent_to(self, chat_id: int) -> list[TelegramMethod]:
        return [c for c in self.calls if getattr(c, "chat_id", None) == chat_id]

    def last_text(self, chat_id: int) -> str:
        for c in reversed(self.calls):
            if getattr(c, "chat_id", None) == chat_id and isinstance(c, (SendMessage, EditMessageText, SendPhoto)):
                return getattr(c, "text", None) or getattr(c, "caption", "")
        return ""

    def buttons(self, chat_id: int) -> list[tuple[str, str]]:
        """(text, callback_data) of the last inline keyboard sent to chat_id."""
        for c in reversed(self.calls):
            if getattr(c, "chat_id", None) != chat_id:
                continue
            markup = getattr(c, "reply_markup", None)
            if markup is not None and hasattr(markup, "inline_keyboard"):
                return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row if b.callback_data]
        return []


def tg_user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name="Admin" if uid == ADMIN_ID else "Sami", username=f"u{uid}")


def msg(uid: int, text: str | None = None, photo: bool = False) -> Update:
    m = Message(
        message_id=next(_ids),
        date=datetime.now(timezone.utc),
        chat=Chat(id=uid, type="private"),
        from_user=tg_user(uid),
        text=text,
        photo=[PhotoSize(file_id="PHOTO1", file_unique_id="u1", width=10, height=10)] if photo else None,
    )
    return Update(update_id=next(_ids), message=m)


def cb(uid: int, data: str) -> Update:
    m = Message(message_id=next(_ids), date=datetime.now(timezone.utc), chat=Chat(id=uid, type="private"), text="x")
    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(id=str(next(_ids)), from_user=tg_user(uid), chat_instance="c", data=data, message=m),
    )


@pytest_asyncio.fixture
async def env(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/bot.db")
    await create_tables(engine)
    sm = make_sessionmaker(engine)
    async with sm() as s:
        await seed_if_empty(s)
    fake = FakeTelegram()
    bot = Bot("42:TEST", session=fake)
    # Routers are module singletons; detach them so each test can build a fresh dispatcher.
    for module in (account, admin, fallback, shop, start, topup):
        module.router._parent_router = None
    dp = build_dispatcher(sm)

    async def feed(update: Update):
        await dp.feed_update(bot, update)

    yield fake, feed, sm
    await engine.dispose()


def find(buttons, needle: str) -> str:
    for text, data in buttons:
        if needle in text or needle == data:
            return data
    raise AssertionError(f"button {needle!r} not in {buttons}")


async def test_full_store_flow(env):
    fake, feed, sm = env

    # Onboarding: language → terms → force-join
    await feed(msg(USER_ID, "/start"))
    assert "اختر لغتك" in fake.last_text(USER_ID)
    await feed(cb(USER_ID, "lang:en"))
    assert "terms of use" in fake.last_text(USER_ID)
    assert ("📢 @dogs_test" in str(fake.calls[-1].reply_markup))

    fake.member = False
    await feed(cb(USER_ID, "gate:accept"))
    assert any(isinstance(c, AnswerCallbackQuery) and c.show_alert for c in fake.calls[-1:])
    await feed(msg(USER_ID, "🎮 Game top-ups"))  # blocked: not accepted yet → gate shown again
    assert "terms of use" in fake.last_text(USER_ID)

    fake.member = True
    await feed(cb(USER_ID, "gate:accept"))
    assert "Balance: <b>$0.00</b>" in fake.last_text(USER_ID)

    # Shop with empty wallet → insufficient
    await feed(msg(USER_ID, "🎮 Game top-ups"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "PUBG Mobile")))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "325 UC")))
    assert "Player ID" in fake.last_text(USER_ID)
    await feed(msg(USER_ID, "5123456789"))
    assert "Confirm order" in fake.last_text(USER_ID)
    await feed(cb(USER_ID, "shop:confirm"))
    assert "Not enough balance" in fake.last_text(USER_ID)

    # Payment methods start hidden until the admin fills details
    await feed(msg(USER_ID, "💰 Top up wallet"))
    assert "No payment methods" in fake.last_text(USER_ID)

    # Admin: set ShamCash USD details + show it
    await feed(msg(ADMIN_ID, "/admin"))
    await feed(cb(ADMIN_ID, "adm:methods"))
    sham = find(fake.buttons(ADMIN_ID), "ShamCash (USD)")
    await feed(cb(ADMIN_ID, sham))
    await feed(cb(ADMIN_ID, find(fake.buttons(ADMIN_ID), "Details EN")))
    await feed(msg(ADMIN_ID, "Send to ShamCash account 0999 000 000 (Dogs Store)"))
    await feed(cb(ADMIN_ID, find(fake.buttons(ADMIN_ID), "Show")))

    # User top-up: method → amount → txn → photo
    await feed(msg(USER_ID, "💰 Top up wallet"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "ShamCash")))
    assert "0999 000 000" in fake.last_text(USER_ID)
    await feed(msg(USER_ID, "abc"))
    assert "whole number" in fake.last_text(USER_ID)
    await feed(msg(USER_ID, "10"))
    await feed(msg(USER_ID, "TX-7788"))
    await feed(msg(USER_ID, "not a photo"))
    assert "photo" in fake.last_text(USER_ID)
    await feed(msg(USER_ID, photo=True))
    assert "received" in fake.last_text(USER_ID)

    # Admin got the receipt with buttons; approve twice → credited once
    admin_photo = [c for c in fake.sent_to(ADMIN_ID) if isinstance(c, SendPhoto)][-1]
    approve = find(fake.buttons(ADMIN_ID), "Approve $10.00")
    await feed(cb(ADMIN_ID, approve))
    await feed(cb(ADMIN_ID, approve))
    async with sm() as s:
        assert await get_balance(s, USER_ID) == 1000
    assert "approved" in fake.last_text(USER_ID)
    assert admin_photo.photo == "PHOTO1"

    # Same transaction ID again is refused
    await feed(msg(USER_ID, "💰 Top up wallet"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "ShamCash")))
    await feed(msg(USER_ID, "10"))
    await feed(msg(USER_ID, "tx-7788"))
    await feed(msg(USER_ID, photo=True))
    assert "already used" in fake.last_text(USER_ID)

    # Buy now succeeds; menu press mid-flow cancels instead of being taken as player ID
    await feed(msg(USER_ID, "🎮 Game top-ups"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "PUBG Mobile")))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "325 UC")))
    await feed(msg(USER_ID, "👤 My account"))
    assert "My account" in fake.last_text(USER_ID)
    await feed(msg(USER_ID, "🎮 Game top-ups"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "PUBG Mobile")))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "325 UC")))
    await feed(msg(USER_ID, "5123456789"))
    await feed(cb(USER_ID, "shop:confirm"))
    await feed(cb(USER_ID, "shop:confirm"))  # double tap: no second order
    assert "deducted" in [t for t in (getattr(c, "text", "") for c in fake.sent_to(USER_ID)) if "deducted" in t][0]
    async with sm() as s:
        assert await get_balance(s, USER_ID) == 1000 - 499

    # Admin rejects with a reason → refund + user told why
    await feed(cb(ADMIN_ID, find(fake.buttons(ADMIN_ID), "Reject + refund")))
    await feed(msg(ADMIN_ID, "Wrong player ID"))
    async with sm() as s:
        assert await get_balance(s, USER_ID) == 1000
    assert "Wrong player ID" in fake.last_text(USER_ID)

    # Buy again, admin delivers
    await feed(msg(USER_ID, "🎮 Game top-ups"))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "Free Fire")))
    await feed(cb(USER_ID, find(fake.buttons(USER_ID), "520 Diamonds")))
    await feed(msg(USER_ID, "998877"))
    await feed(cb(USER_ID, "shop:confirm"))
    await feed(cb(ADMIN_ID, find(fake.buttons(ADMIN_ID), "Delivered")))
    assert "delivered" in fake.last_text(USER_ID)

    # Language switch to Arabic
    await feed(msg(USER_ID, "🌐 العربية"))
    assert "تم تغيير اللغة" in fake.last_text(USER_ID)

    # Admin tools: stats, price change, ban
    await feed(cb(ADMIN_ID, "adm:stats"))
    assert "Orders delivered today: <b>1</b>" in fake.last_text(ADMIN_ID)
    await feed(cb(ADMIN_ID, "adm:user"))
    await feed(msg(ADMIN_ID, f"{USER_ID}"))
    assert "Balance: <b>$5.01</b>" in fake.last_text(ADMIN_ID)
    await feed(cb(ADMIN_ID, f"adm:u:ban:{USER_ID}"))
    await feed(msg(USER_ID, "/start"))
    assert "محظور" in fake.last_text(USER_ID)

    # A normal user can't reach admin callbacks
    async with sm() as s:
        await s.execute(sa_update(PaymentMethod).values(is_active=True))
        await s.commit()
    before = len(fake.calls)
    await feed(cb(222, "adm:stats"))
    texts = " ".join(str(getattr(c, "text", "")) for c in fake.calls[before:])
    assert "Stats" not in texts


async def test_forged_callback_is_handled(env):
    fake, feed, _ = env
    await feed(msg(USER_ID, "/start"))
    await feed(cb(USER_ID, "lang:ar"))
    await feed(cb(USER_ID, "gate:accept"))
    await feed(cb(USER_ID, "shop:p:notanumber"))
    last = fake.calls[-1]
    assert isinstance(last, AnswerCallbackQuery) and last.show_alert
