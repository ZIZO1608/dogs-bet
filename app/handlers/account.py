"""Account / history helpers (kept for admin and internal use)."""

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.models import Deposit, Order, User, Withdrawal
from app.money import fmt_syp, fmt_usd, usd_cents_to_syp
from app.services import deposits
from app.services.settings_store import get_syp_rate
from app.services.wallet import get_balance

router = Router(name="account")


def _status(lang: str, status: str) -> str:
    return t(lang, f"st_{status}", **{}) if f"st_{status}" else status


@router.callback_query(F.data == "acc:deps")
async def show_deposits(cb: CallbackQuery, session: AsyncSession, user: User, lang: str):
    rows = await deposits.list_for_user(session, user.id)
    if not rows:
        await cb.answer(t(lang, "deposits_empty") if "deposits_empty" in dir() else "No deposits", show_alert=True)
        return
    lines = ["💳 Latest top-ups:"]
    for d in rows:
        lines.append(f"#{d.id} {fmt_usd(d.credited_cents or 0)} — {_status(lang, d.status)}")
    await cb.message.answer("\n".join(lines))
    await cb.answer()
