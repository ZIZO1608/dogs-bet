from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import both, menu_texts, t
from app.keyboards import cancel_kb, methods_kb
from app.models import LedgerEntry, LedgerKind, PaymentMethod, Status, User, Withdrawal, utcnow
from app.money import fmt_usd, parse_positive_int
from app.notify import notify_admins
from app.services.errors import AlreadyDecided, InsufficientBalance, StoreError
from app.services.wallet import get_balance, lock_user
from app.states import WithdrawFlow

router = Router(name="withdraw")

MIN_WITHDRAW_CENTS = 500  # $5 minimum


@router.message(F.text.in_(both("m_withdraw")))
async def open_withdraw(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    await state.clear()
    balance = await get_balance(session, user.id)
    rows = await session.scalars(
        select(PaymentMethod)
        .where(PaymentMethod.is_active.is_(True), PaymentMethod.for_withdraw.is_(True))
        .order_by(PaymentMethod.sort)
    )
    methods = list(rows)
    if not methods:
        # Fallback: allow same methods as deposit for now
        rows = await session.scalars(
            select(PaymentMethod).where(PaymentMethod.is_active.is_(True)).order_by(PaymentMethod.sort)
        )
        methods = list(rows)
    if not methods:
        await message.answer(t(lang, "withdraw_empty"))
        return
    await message.answer(
        t(lang, "withdraw_title", balance=fmt_usd(balance), min=fmt_usd(MIN_WITHDRAW_CENTS)),
        reply_markup=methods_kb(methods, lang, prefix="wd"),
    )


@router.callback_query(F.data == "wd:home")
async def wd_home(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data == "wd:cancel")
async def wd_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data.startswith("wd:m:"))
async def pick_wd_method(cb: CallbackQuery, session: AsyncSession, lang: str, state: FSMContext):
    method = await session.get(PaymentMethod, int(cb.data.rsplit(":", 1)[1]))
    if method is None:
        await cb.answer(t(lang, "err_not_available"), show_alert=True)
        return
    await state.set_state(WithdrawFlow.amount)
    await state.update_data(method_code=method.code, method_name=method.name(lang))
    await cb.message.edit_text(
        t(lang, "withdraw_ask_amount"),
        reply_markup=cancel_kb(lang, "wd:cancel"),
    )
    await cb.answer()


@router.message(WithdrawFlow.amount, F.text, ~F.text.in_(menu_texts()))
async def got_wd_amount(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    amount = parse_positive_int(message.text)
    if amount is None:
        await message.answer(t(lang, "amount_invalid"))
        return
    cents = amount * 100
    if cents < MIN_WITHDRAW_CENTS:
        await message.answer(t(lang, "err_below_min"))
        return
    balance = await get_balance(session, user.id)
    if balance < cents:
        await message.answer(t(lang, "withdraw_insufficient"))
        return
    await state.update_data(amount_cents=cents)
    await state.set_state(WithdrawFlow.destination)
    await message.answer(t(lang, "withdraw_ask_dest"), reply_markup=cancel_kb(lang, "wd:cancel"))


@router.message(WithdrawFlow.destination, F.text, ~F.text.in_(menu_texts()))
async def got_wd_dest(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext, bot: Bot):
    dest = (message.text or "").strip()
    if len(dest) < 5 or len(dest) > 256:
        await message.answer(t(lang, "amount_invalid"))
        return
    data = await state.get_data()
    await state.clear()
    cents = data["amount_cents"]

    await lock_user(session, user.id)
    balance = await get_balance(session, user.id)
    if balance < cents:
        await session.rollback()
        await message.answer(t(lang, "withdraw_insufficient"))
        return

    wd = Withdrawal(
        user_id=user.id,
        amount_cents=cents,
        method_code=data["method_code"],
        destination=dest,
    )
    session.add(wd)
    await session.flush()

    # Hold the money immediately (debit ledger)
    session.add(
        LedgerEntry(
            user_id=user.id,
            amount_cents=-cents,
            kind=LedgerKind.WITHDRAW,
            ref_id=wd.id,
            note=f"Withdraw to {dest[:40]}",
        )
    )
    await session.commit()

    await message.answer(
        t(lang, "withdraw_created", id=wd.id, amount=fmt_usd(cents))
    )

    # Notify admins
    text = (
        f"💸 <b>Withdrawal #{wd.id}</b>\n"
        f"User: {escape(user.full_name or '')} (@{user.username or '—'})\n"
        f"ID: <code>{user.id}</code>\n"
        f"Amount: {fmt_usd(cents)}\n"
        f"Method: {escape(data.get('method_name', data['method_code']))}\n"
        f"To: <code>{escape(dest)}</code>"
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"admin:wd:ok:{wd.id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"admin:wd:no:{wd.id}"),
        ]
    ])
    await notify_admins(bot, text, kb)
