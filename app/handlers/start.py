from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.gate import is_joined
from app.i18n import both, t
from app.keyboards import lang_kb, main_menu, terms_kb
from app.middlewares import support_link
from app.models import User
from app.money import fmt_usd
from app.services.wallet import get_balance

router = Router(name="start")


def terms_text(lang: str) -> str:
    text = t(lang, "terms", store=escape(settings.store_name))
    if settings.required_channels:
        text += t(lang, "terms_join")
    return text


async def show_gate(message: Message, user: User) -> None:
    """Send whichever onboarding step the user is missing."""
    if user.lang is None:
        await message.answer(
            t("ar", "choose_lang", store=escape(settings.store_name)),
            reply_markup=lang_kb(),
        )
    else:
        await message.answer(
            terms_text(user.lang),
            reply_markup=terms_kb(user.lang),
            disable_web_page_preview=True,
        )


async def send_welcome(message: Message, session: AsyncSession, user: User, lang: str, is_admin: bool) -> None:
    balance = await get_balance(session, user.id)
    await message.answer(
        t(lang, "welcome", name=escape(user.full_name or ""), balance=fmt_usd(balance)),
        reply_markup=main_menu(lang, is_admin),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    user: User,
    is_admin: bool,
    bot: Bot,
    state: FSMContext,
):
    await state.clear()
    # Deep-link referral: /start ref_123456
    if message.text and " " in message.text:
        payload = message.text.split(maxsplit=1)[1].strip()
        if payload.startswith("ref_") and user.referrer_id is None:
            try:
                ref_id = int(payload[4:])
                if ref_id != user.id:
                    user.referrer_id = ref_id
                    await session.commit()
            except ValueError:
                pass

    if user.lang and user.accepted_terms and (is_admin or await is_joined(bot, user.id)):
        await send_welcome(message, session, user, user.lang, is_admin)
    else:
        await show_gate(message, user)


@router.callback_query(F.data.startswith("lang:"))
async def pick_language(cb: CallbackQuery, session: AsyncSession, user: User, is_admin: bool):
    lang = cb.data.split(":", 1)[1]
    if lang not in ("ar", "en"):
        await cb.answer()
        return
    user.lang = lang
    await session.commit()
    await cb.answer()
    if user.accepted_terms:
        await cb.message.edit_text(t(lang, "lang_changed"))
        await send_welcome(cb.message, session, user, lang, is_admin)
    else:
        await cb.message.edit_text(
            terms_text(lang),
            reply_markup=terms_kb(lang),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data == "gate:accept")
async def accept_terms(
    cb: CallbackQuery,
    session: AsyncSession,
    user: User,
    lang: str,
    is_admin: bool,
    bot: Bot,
):
    if not is_admin and not await is_joined(bot, user.id, fresh=True):
        await cb.answer(t(lang, "not_joined"), show_alert=True)
        return
    user.accepted_terms = True
    await session.commit()
    await cb.answer("✅")
    await cb.message.edit_reply_markup(reply_markup=None)
    await send_welcome(cb.message, session, user, lang, is_admin)


@router.message(F.text.in_(both("m_lang")))
async def toggle_language(message: Message, session: AsyncSession, user: User, is_admin: bool):
    user.lang = "en" if (user.lang or "ar") == "ar" else "ar"
    await session.commit()
    await message.answer(
        t(user.lang, "lang_changed"),
        reply_markup=main_menu(user.lang, is_admin),
    )


@router.message(F.text.in_(both("m_support")))
async def support(message: Message, lang: str):
    await message.answer(t(lang, "support", support=support_link()))
