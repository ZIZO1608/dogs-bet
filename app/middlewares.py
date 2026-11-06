from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.gate import is_joined
from app.i18n import t
from app.models import User

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

# Updates allowed before the user has picked a language, accepted terms and joined channels.
_OPEN_CALLBACK_PREFIXES = ("lang:", "gate:")


def support_link() -> str:
    return f"@{settings.support_username}" if settings.support_username else "—"


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self.sessionmaker = sessionmaker

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Loads/creates the user, blocks banned users, and enforces language + terms + channel gate."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data["session"]
        user = await session.get(User, tg_user.id)
        if user is None:
            user = User(id=tg_user.id, username=tg_user.username, full_name=tg_user.full_name)
            session.add(user)
            await session.commit()
        elif user.username != tg_user.username or user.full_name != tg_user.full_name:
            user.username = tg_user.username
            user.full_name = tg_user.full_name
            await session.commit()

        is_admin = tg_user.id in settings.admin_ids
        data["user"] = user
        data["lang"] = user.lang or "ar"
        data["is_admin"] = is_admin

        if user.is_banned and not is_admin:
            text = t(data["lang"], "banned", support=support_link())
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(text)
            return None

        if is_admin or self._is_open(event):
            return await handler(event, data)

        ready = user.lang is not None and user.accepted_terms and await is_joined(data["bot"], user.id)
        if not ready:
            # Send them back through /start, which shows the right step.
            from app.handlers.start import show_gate  # local import avoids a cycle

            if isinstance(event, CallbackQuery):
                await event.answer()
                if event.message:
                    await show_gate(event.message, user)
            elif isinstance(event, Message):
                await show_gate(event, user)
            return None
        return await handler(event, data)

    @staticmethod
    def _is_open(event: TelegramObject) -> bool:
        if isinstance(event, CallbackQuery):
            return (event.data or "").startswith(_OPEN_CALLBACK_PREFIXES)
        if isinstance(event, Message):
            return (event.text or "").startswith("/start")
        return False
