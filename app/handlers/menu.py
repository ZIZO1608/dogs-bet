"""Main menu handlers for Dogs Bet (Wolf-style features)."""

from html import escape
import re
import secrets
import string

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import both, t
from app.keyboards import main_menu
from app.models import GiftCode, GiftRedemption, LedgerEntry, LedgerKind, PlatformAccount, User, utcnow
from app.money import fmt_usd
from app.services.agent_api import AgentAPIError, agent_api
from app.services.wallet import get_balance, lock_user
from app.states import CreateAccountFlow, GiftFlow

router = Router(name="menu")


# ── Create account ──────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_create_account")))
async def create_account_start(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    # Allow multiple accounts per Telegram user
    await state.set_state(CreateAccountFlow.username)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 توليد اسم تلقائي" if lang == "ar" else "🎲 Generate for me", callback_data="create:gen")]
    ])
    await message.answer(t(lang, "create_ask_username"), reply_markup=kb)



@router.callback_query(F.data == "create:gen")
async def create_generate(call: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext):
    await call.answer()
    base = (user.first_name or "dog").lower()
    base = re.sub(r"[^a-z0-9]", "", base)[:8] or "dog"
    username = f"{base}{secrets.token_hex(3)}"[:16]
    while await session.scalar(select(PlatformAccount.id).where(PlatformAccount.username == username)):
        username = f"{base}{secrets.token_hex(3)}"[:16]

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(10))
    platform_player_id = None

    if agent_api.enabled:
        try:
            result = await agent_api.register_player(
                login=username,
                password=password,
                email=f"{username}@dogsbet.local",
            )
            if isinstance(result, dict):
                platform_player_id = str(result.get("playerId") or result.get("id") or "")
            elif result not in (None, False):
                platform_player_id = str(result) if not isinstance(result, bool) else None
        except AgentAPIError as exc:
            await call.message.answer(f"⚠️ {escape(exc.message)}")
            await state.clear()
            return

    acc = PlatformAccount(
        user_id=user.id,
        username=username,
        password=password,
        platform_player_id=platform_player_id,
    )
    session.add(acc)
    await session.commit()
    await state.clear()
    # List all accounts for this user
    accounts = await session.scalars(
        select(PlatformAccount).where(PlatformAccount.user_id == user.id, PlatformAccount.is_active == True)
    )
    acc_list = list(accounts)
    extra = ""
    if len(acc_list) > 1:
        extra = "\n\n📋 حساباتك:\n" + "\n".join(f"• {a.username}" for a in acc_list)
    await call.message.answer(
        t(lang, "create_success", username=escape(username), password=escape(password)) + extra,
        reply_markup=main_menu(lang, False),
    )


@router.message(CreateAccountFlow.username)
async def create_account_username(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    username = (message.text or "").strip()
    # Clean and make it easier: allow letters, numbers, underscore, 3-20
    username = re.sub(r"[^A-Za-z0-9_]", "", username)
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        await message.answer(t(lang, "create_username_invalid"))
        return

    taken = await session.scalar(select(PlatformAccount.id).where(PlatformAccount.username == username))
    if taken:
        await message.answer(t(lang, "create_username_taken"))
        return

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(10))
    platform_player_id = None

    # Real platform registration when Agent API is configured
    if agent_api.enabled:
        try:
            result = await agent_api.register_player(
                login=username,
                password=password,
                email=f"{username}@dogsbet.local",
            )
            # result can be 1 or a player object depending on API
            if isinstance(result, dict):
                platform_player_id = str(result.get("playerId") or result.get("id") or "")
            elif result not in (None, False):
                platform_player_id = str(result) if not isinstance(result, bool) else None
        except AgentAPIError as exc:
            await message.answer(
                f"⚠️ {escape(exc.message)}\n\n" + t(lang, "create_coming")
            )
            await state.clear()
            return
        except Exception:
            await message.answer(t(lang, "error_generic"))
            await state.clear()
            return

    acc = PlatformAccount(
        user_id=user.id,
        username=username,
        password=password,
        platform_player_id=platform_player_id,
    )
    session.add(acc)
    await session.commit()
    await state.clear()
    accounts = await session.scalars(
        select(PlatformAccount).where(PlatformAccount.user_id == user.id, PlatformAccount.is_active == True)
    )
    acc_list = list(accounts)
    extra = ""
    if len(acc_list) > 1:
        extra = "\n\n📋 حساباتك:\n" + "\n".join(f"• {a.username}" for a in acc_list)
    await message.answer(
        t(lang, "create_success", username=escape(username), password=escape(password)) + extra,
        reply_markup=main_menu(lang, False),
    )



# ── My Accounts ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_my_accounts")))
async def my_accounts(message: Message, session: AsyncSession, user: User, lang: str):
    accounts = await session.scalars(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user.id,
            PlatformAccount.is_active == True,  # noqa: E712
        ).order_by(PlatformAccount.created_at.desc())
    )
    acc_list = list(accounts)
    if not acc_list:
        await message.answer(t(lang, "accounts_empty"))
        return
    lines = []
    for a in acc_list:
        lines.append(t(lang, "accounts_item", username=escape(a.username), password=escape(a.password or "—")))
    await message.answer(t(lang, "accounts_list", list="\n".join(lines)))


# ── Balances ────────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_balances")))
async def show_balances(message: Message, session: AsyncSession, user: User, lang: str):
    bot_balance = await get_balance(session, user.id)
    site_balance_txt = "—"
    rate = f"1 USD = {settings.default_syp_rate:,.0f} SYP"

    # Try real site balance from Agent API
    acc = await session.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user.id,
            PlatformAccount.is_active == True,  # noqa: E712
        )
    )
    if acc and acc.platform_player_id and agent_api.enabled:
        try:
            bals = await agent_api.get_player_balance(acc.platform_player_id)
            if bals:
                parts = []
                for b in bals:
                    code = b.get("currencyCode") or b.get("currency") or ""
                    bal = b.get("balance", 0)
                    parts.append(f"{bal} {code}".strip())
                site_balance_txt = " / ".join(parts) if parts else "0"
        except Exception:
            site_balance_txt = "—"

    await message.answer(
        t(
            lang,
            "balances_title",
            bot_balance=fmt_usd(bot_balance),
            site_balance=site_balance_txt,
            rate=rate,
        )
    )


# ── Gift code ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_gift")))
async def gift_start(message: Message, lang: str, state: FSMContext):
    await state.set_state(GiftFlow.code)
    await message.answer(t(lang, "gift_ask"))


@router.message(GiftFlow.code)
async def gift_redeem(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    code_str = (message.text or "").strip().upper()
    await state.clear()

    code = await session.scalar(
        select(GiftCode).where(GiftCode.code == code_str, GiftCode.is_active == True)  # noqa: E712
    )
    if not code:
        await message.answer(t(lang, "gift_invalid"))
        return
    if code.expires_at and code.expires_at < utcnow():
        await message.answer(t(lang, "gift_invalid"))
        return
    if code.used_count >= code.max_uses:
        await message.answer(t(lang, "gift_invalid"))
        return

    already = await session.scalar(
        select(GiftRedemption.id).where(GiftRedemption.code_id == code.id, GiftRedemption.user_id == user.id)
    )
    if already:
        await message.answer(t(lang, "gift_already"))
        return

    await lock_user(session, user.id)
    session.add(GiftRedemption(code_id=code.id, user_id=user.id, amount_cents=code.amount_cents))
    code.used_count += 1
    session.add(
        LedgerEntry(
            user_id=user.id,
            amount_cents=code.amount_cents,
            kind=LedgerKind.GIFT,
            ref_id=code.id,
            note=f"Gift code {code.code}",
        )
    )
    await session.commit()
    balance = await get_balance(session, user.id)
    await message.answer(
        t(lang, "gift_success", amount=fmt_usd(code.amount_cents), balance=fmt_usd(balance)),
        reply_markup=main_menu(lang, False),
    )


# ── Referrals ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_referrals")))
async def referrals(message: Message, session: AsyncSession, user: User, lang: str, bot):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.id}"
    count = await session.scalar(select(func.count(User.id)).where(User.referrer_id == user.id)) or 0
    earnings = 0
    await message.answer(
        t(lang, "referrals_title", link=link, count=count, earnings=fmt_usd(earnings))
    )


# ── Offers ──────────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_offers")))
async def offers(message: Message, lang: str):
    await message.answer(t(lang, "offers_empty"))


# ── Website ─────────────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_website")))
async def website(message: Message, lang: str):
    if settings.platform_website:
        await message.answer(t(lang, "website_msg", url=settings.platform_website))
    else:
        await message.answer(t(lang, "website_empty"))


# ── Terms & channels ────────────────────────────────────────────────────────

@router.message(F.text.in_(both("m_terms_channels")))
async def terms_channels(message: Message, lang: str):
    terms = t(lang, "terms", store=escape(settings.store_name))
    if settings.required_channels:
        ch_list = "\n".join(f"• @{c.lstrip('@')}" for c in settings.required_channels)
        channels = t(lang, "channels_list", list=ch_list)
    else:
        channels = t(lang, "no_channels")
    await message.answer(t(lang, "terms_channels_msg", terms=terms, channels=channels))
