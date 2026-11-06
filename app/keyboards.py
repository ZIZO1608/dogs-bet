from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import settings
from app.i18n import t
from app.models import PaymentMethod
from app.money import fmt_usd


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇸🇾 العربية", callback_data="lang:ar"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def channel_url(channel: str) -> str:
    return f"https://t.me/{channel.lstrip('@')}"


def terms_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    accept_key = "btn_accept_join" if settings.required_channels else "btn_accept"
    kb.button(text=t(lang, accept_key), callback_data="gate:accept")
    for ch in settings.required_channels:
        kb.button(text=t(lang, "btn_channel", channel=ch), url=channel_url(ch))
    kb.adjust(1)
    return kb.as_markup()


def main_menu(lang: str, is_admin: bool) -> ReplyKeyboardMarkup:
    """Branded main menu for Dogs Bet."""
    rows = [
        [KeyboardButton(text=t(lang, "m_create_account"))],
        [KeyboardButton(text=t(lang, "m_my_accounts"))],
        [
            KeyboardButton(text=t(lang, "m_topup")),
            KeyboardButton(text=t(lang, "m_withdraw")),
        ],
        [KeyboardButton(text=t(lang, "m_balances"))],
        [
            KeyboardButton(text=t(lang, "m_gift")),
            KeyboardButton(text=t(lang, "m_offers")),
        ],
        [
            KeyboardButton(text=t(lang, "m_referrals")),
            KeyboardButton(text=t(lang, "m_website")),
        ],
        [
            KeyboardButton(text=t(lang, "m_support")),
            KeyboardButton(text=t(lang, "m_terms_channels")),
        ],
        [KeyboardButton(text=t(lang, "m_lang"))],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=t(lang, "m_admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb(lang: str, data: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data=data)]]
    )


def methods_kb(methods: list[PaymentMethod], lang: str, prefix: str = "top") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for m in methods:
        kb.button(text=f"💳 {m.name(lang)}", callback_data=f"{prefix}:m:{m.id}")
    kb.button(text=t(lang, "btn_back"), callback_data=f"{prefix}:home")
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb(lang: str, yes_data: str, no_data: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_confirm"), callback_data=yes_data),
                InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data=no_data),
            ]
        ]
    )


def back_kb(lang: str, data: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_back"), callback_data=data)]]
    )
