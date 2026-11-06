import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.config import settings

log = logging.getLogger(__name__)


async def notify_admins(
    bot: Bot, text: str, keyboard: InlineKeyboardMarkup | None = None, photo: str | None = None
) -> None:
    for admin_id in settings.admin_ids:
        try:
            if photo:
                await bot.send_photo(admin_id, photo, caption=text, reply_markup=keyboard)
            else:
                await bot.send_message(admin_id, text, reply_markup=keyboard)
        except Exception:  # admin blocked the bot / never started it
            log.warning("Could not notify admin %s", admin_id, exc_info=True)


async def notify_user(bot: Bot, user_id: int, text: str, keyboard: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=keyboard)
        return True
    except Exception:
        log.info("Could not message user %s (blocked the bot?)", user_id)
        return False
