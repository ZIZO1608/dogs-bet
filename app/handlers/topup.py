from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cards import deposit_card, fmt_amount
from app.i18n import both, menu_texts, t
from app.keyboards import cancel_kb, methods_kb
from app.models import PaymentMethod, User
from app.money import fmt_usd, parse_positive_int
from app.notify import notify_admins
from app.services import deposits
from app.services.errors import StoreError
from app.services.settings_store import get_syp_rate
from app.services.wallet import get_balance
from app.states import TopupFlow

router = Router(name="topup")


async def _methods_view(session: AsyncSession, lang: str, balance: int) -> tuple[str, InlineKeyboardMarkup | None]:
    rows = await session.scalars(
        select(PaymentMethod)
        .where(PaymentMethod.is_active.is_(True), PaymentMethod.for_deposit.is_(True))
        .order_by(PaymentMethod.sort, PaymentMethod.id)
    )
    methods = list(rows)
    if not methods:
        return t(lang, "topup_empty"), None
    min_amount = min((m.min_amount for m in methods), default=1)
    return (
        t(lang, "topup_title", balance=fmt_usd(balance), min=fmt_amount(min_amount, methods[0].currency)),
        methods_kb(methods, lang, prefix="top"),
    )


@router.message(F.text.in_(both("m_topup")))
async def open_topup(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    await state.clear()
    balance = await get_balance(session, user.id)
    text, kb = await _methods_view(session, lang, balance)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "top:home")
async def topup_home(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext):
    await state.clear()
    balance = await get_balance(session, user.id)
    text, kb = await _methods_view(session, lang, balance)
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "top:cancel")
async def topup_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data.startswith("top:m:"))
async def pick_method(cb: CallbackQuery, session: AsyncSession, lang: str, state: FSMContext):
    method = await session.get(PaymentMethod, int(cb.data.rsplit(":", 1)[1]))
    if method is None or not method.is_active:
        await cb.answer(t(lang, "err_not_available"), show_alert=True)
        return
    await state.set_state(TopupFlow.amount)
    await state.update_data(method_id=method.id)
    text = t(
        lang,
        "topup_details",
        method=escape(method.name(lang)),
        details=method.details(lang) or "—",
        min=fmt_amount(method.min_amount, method.currency),
        currency=method.currency,
    )
    # If method has a QR, send it first
    if method.qr_file_id:
        await cb.message.answer_photo(method.qr_file_id, caption=text, reply_markup=cancel_kb(lang, "top:cancel"))
        await cb.message.delete()
    else:
        await cb.message.edit_text(text, reply_markup=cancel_kb(lang, "top:cancel"))
    await cb.answer()


@router.message(TopupFlow.amount, F.text, ~F.text.in_(menu_texts()))
async def got_amount(message: Message, session: AsyncSession, lang: str, state: FSMContext):
    amount = parse_positive_int(message.text)
    if amount is None:
        await message.answer(t(lang, "amount_invalid"))
        return
    method = await session.get(PaymentMethod, (await state.get_data()).get("method_id", 0))
    if method is None or not method.is_active:
        await state.clear()
        await message.answer(t(lang, "err_not_available"))
        return
    if amount < method.min_amount:
        await message.answer(t(lang, "err_below_min"))
        return
    await state.update_data(amount=amount)
    await state.set_state(TopupFlow.txn_ref)
    await message.answer(t(lang, "ask_txn"), reply_markup=cancel_kb(lang, "top:cancel"))


@router.message(TopupFlow.txn_ref, F.text, ~F.text.in_(menu_texts()))
async def got_txn(message: Message, lang: str, state: FSMContext):
    ref = (message.text or "").strip()
    if not (3 <= len(ref) <= 128):
        await message.answer(t(lang, "amount_invalid"))
        return
    await state.update_data(txn_ref=ref)
    await state.set_state(TopupFlow.proof)
    await message.answer(t(lang, "ask_proof"), reply_markup=cancel_kb(lang, "top:cancel"))


@router.message(TopupFlow.proof, F.photo | F.document | F.text)
async def got_proof(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext, bot: Bot):
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
    elif message.text and message.text.strip().lower() in ("skip", "تخطي", "تخطيء"):
        file_id = None
    else:
        await message.answer(t(lang, "proof_invalid"))
        return

    data = await state.get_data()
    await state.clear()
    try:
        deposit = await deposits.create_deposit(
            session,
            user_id=user.id,
            method_id=data["method_id"],
            amount=data["amount"],
            txn_ref=data["txn_ref"],
            proof_file_id=file_id,
        )
    except StoreError as exc:
        await message.answer(t(lang, exc.code))
        return

    method = await session.get(PaymentMethod, deposit.method_id)
    await message.answer(
        t(lang, "deposit_created", id=deposit.id, amount=fmt_amount(deposit.amount, deposit.currency))
    )

    rate = await get_syp_rate(session)
    text, kb = deposit_card(deposit, user, method, rate)
    await notify_admins(bot, text, kb, photo=file_id)
