"""Admin-facing cards for deposits and orders (English, one format everywhere)."""

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Currency, Deposit, Order, PaymentMethod, Status, User
from app.money import fmt_syp, fmt_usd, to_cents


def who(user: User) -> str:
    name = f"@{escape(user.username)}" if user.username else escape(user.full_name or "—")
    return f"{name} (<code>{user.id}</code>)"


def fmt_amount(amount: int, currency: str) -> str:
    return fmt_syp(amount) if currency == Currency.SYP else fmt_usd(amount * 100)


def deposit_card(deposit: Deposit, user: User, method: PaymentMethod, rate: float) -> tuple[str, InlineKeyboardMarkup | None]:
    estimate = fmt_usd(to_cents(deposit.amount, deposit.currency, rate))
    text = (
        f"💰 <b>Top-up request #{deposit.id}</b>\n"
        f"👤 {who(user)}\n"
        f"💳 {escape(method.name_en)}\n"
        f"💵 Amount: <b>{fmt_amount(deposit.amount, deposit.currency)}</b>"
        + (f" → {estimate} at {rate:,.0f}" if deposit.currency == Currency.SYP else "")
        + f"\n🔢 Txn: <code>{escape(deposit.txn_ref)}</code>\n"
        f"🕒 {deposit.created_at:%Y-%m-%d %H:%M} UTC"
    )
    if deposit.status != Status.PENDING:
        return text, None
    text += "\n\nCheck the transfer in your account before approving."
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Approve {estimate}", callback_data=f"adm:dep:ok:{deposit.id}")],
            [
                InlineKeyboardButton(text="✏️ Other amount", callback_data=f"adm:dep:custom:{deposit.id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"adm:dep:no:{deposit.id}"),
            ],
        ]
    )
    return text, kb


def order_card(order: Order, user: User) -> tuple[str, InlineKeyboardMarkup | None]:
    text = (
        f"🆕 <b>Order #{order.id}</b>\n"
        f"👤 {who(user)}\n"
        f"🎮 {escape(order.game_name)} — {escape(order.package_title)}\n"
        f"🆔 Player: <code>{escape(order.player_ref)}</code>\n"
        f"💵 {fmt_usd(order.price_cents)} (paid from wallet)\n"
        f"🕒 {order.created_at:%Y-%m-%d %H:%M} UTC"
    )
    if order.status != Status.PENDING:
        return text, None
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Delivered", callback_data=f"adm:ord:done:{order.id}"),
                InlineKeyboardButton(text="❌ Reject + refund", callback_data=f"adm:ord:no:{order.id}"),
            ]
        ]
    )
    return text, kb
