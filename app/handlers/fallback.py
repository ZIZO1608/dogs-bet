from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.i18n import t
from app.keyboards import main_menu

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message, lang: str = "ar", is_admin: bool = False):
    await message.answer(t(lang, "use_menu"), reply_markup=main_menu(lang, is_admin))


@router.callback_query()
async def unknown_callback(cb: CallbackQuery, lang: str = "ar"):
    await cb.answer(t(lang, "err_already_decided"))
