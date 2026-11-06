"""Force-join check: the user must be a member of every required channel."""

import logging
import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from app.config import settings

log = logging.getLogger(__name__)

_JOINED = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
_CACHE_SECONDS = 600
_cache: dict[int, float] = {}  # user_id -> time the user was last confirmed as joined


async def is_joined(bot: Bot, user_id: int, *, fresh: bool = False) -> bool:
    if not settings.required_channels:
        return True
    if not fresh and time.monotonic() - _cache.get(user_id, -_CACHE_SECONDS) < _CACHE_SECONDS:
        return True
    for channel in settings.required_channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
        except Exception:  # bot not admin in channel / channel renamed: fail closed but log it loudly
            log.exception("Membership check failed for %s — is the bot an admin there?", channel)
            return False
        if member.status not in _JOINED:
            _cache.pop(user_id, None)
            return False
    _cache[user_id] = time.monotonic()
    return True
