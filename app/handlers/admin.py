"""Admin panel inside the bot. Every handler here is restricted to ADMIN_IDS by the router filter."""

import asyncio
import logging
from datetime import datetime, time, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cards import deposit_card, order_card
from app.config import settings
from app.i18n import both, menu_texts, t
from app.models import Deposit, Game, Order, Package, PaymentMethod, Status, User, utcnow
from app.money import fmt_syp, fmt_usd, parse_usd_to_cents
from app.notify import notify_user
from app.services import deposits, orders
from app.services.errors import AlreadyDecided, InsufficientBalance, StoreError
from app.services.settings_store import get_syp_rate, set_syp_rate
from app.services.wallet import admin_adjust, get_balance
from app.middlewares import support_link
from app.states import AdminFlow

log = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.from_user.id.in_(settings.admin_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_ids))

TYPING = ~F.text.in_(menu_texts())  # free-text steps must not swallow main-menu presses


def _back(data: str = "adm:home") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="🔙 Back", callback_data=data)]


def panel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Stats", callback_data="adm:stats")
    kb.button(text="💰 Pending top-ups", callback_data="adm:deps")
    kb.button(text="📦 Pending orders", callback_data="adm:ords")
    kb.button(text="🎮 Games & prices", callback_data="adm:games")
    kb.button(text="💳 Payment methods", callback_data="adm:methods")
    kb.button(text="👤 Find user", callback_data="adm:user")
    kb.button(text="📢 Broadcast", callback_data="adm:bc")
    kb.button(text="💱 SYP rate", callback_data="adm:rate")
    kb.adjust(1, 2, 2, 2, 1)
    return kb.as_markup()


async def _stamp(message: Message, line: str) -> None:
    """Append a decision line to an admin card (photo caption or text) and drop its buttons."""
    body = message.html_text or ""
    try:
        if message.photo:
            await message.edit_caption(caption=f"{body}\n\n{line}"[:1024], reply_markup=None)
        else:
            await message.edit_text(f"{body}\n\n{line}", reply_markup=None)
    except Exception:
        log.debug("Could not edit admin card", exc_info=True)


def _admin_name(cb: CallbackQuery | Message) -> str:
    u = cb.from_user
    return f"@{escape(u.username)}" if u.username else escape(u.full_name)


# ───────────────────────── panel ─────────────────────────


@router.message(Command("admin"))
@router.message(F.text.in_(both("m_admin")))
async def open_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"🛠 <b>{escape(settings.store_name)} — admin</b>", reply_markup=panel_kb())


@router.callback_query(F.data == "adm:home")
async def panel_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(f"🛠 <b>{escape(settings.store_name)} — admin</b>", reply_markup=panel_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:cancel")
async def admin_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Cancelled.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]))
    await cb.answer()


CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="adm:cancel")]])


# ───────────────────────── stats ─────────────────────────


@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery, session: AsyncSession):
    today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)

    async def scalar(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    users = await scalar(select(func.count(User.id)))
    users_today = await scalar(select(func.count(User.id)).where(User.created_at >= today))
    dep_today = await scalar(
        select(func.sum(Deposit.credited_cents)).where(Deposit.status == Status.APPROVED, Deposit.decided_at >= today)
    )
    dep_all = await scalar(select(func.sum(Deposit.credited_cents)).where(Deposit.status == Status.APPROVED))
    ord_today = await scalar(
        select(func.sum(Order.price_cents)).where(Order.status == Status.COMPLETED, Order.decided_at >= today)
    )
    ord_today_n = await scalar(
        select(func.count(Order.id)).where(Order.status == Status.COMPLETED, Order.decided_at >= today)
    )
    ord_all = await scalar(select(func.sum(Order.price_cents)).where(Order.status == Status.COMPLETED))
    pend_dep = await scalar(select(func.count(Deposit.id)).where(Deposit.status == Status.PENDING))
    pend_ord = await scalar(select(func.count(Order.id)).where(Order.status == Status.PENDING))

    text = (
        "📊 <b>Stats</b> (UTC day)\n\n"
        f"👥 Users: <b>{users}</b> (+{users_today} today)\n\n"
        f"💰 Top-ups approved today: <b>{fmt_usd(dep_today)}</b>\n"
        f"💰 Top-ups approved all time: {fmt_usd(dep_all)}\n\n"
        f"📦 Orders delivered today: <b>{ord_today_n}</b> · {fmt_usd(ord_today)}\n"
        f"📦 Orders delivered all time: {fmt_usd(ord_all)}\n\n"
        f"⏳ Pending: {pend_dep} top-ups · {pend_ord} orders"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]))
    await cb.answer()


# ───────────────────────── deposits ─────────────────────────


@router.callback_query(F.data == "adm:deps")
async def pending_deposits(cb: CallbackQuery, session: AsyncSession):
    rows = await deposits.list_pending(session)
    if not rows:
        await cb.answer("No pending top-ups 👌", show_alert=True)
        return
    rate = await get_syp_rate(session)
    await cb.answer()
    for d in rows:
        text, kb = deposit_card(d, d.user, d.method, rate)
        if d.proof_file_id:
            await cb.message.answer_photo(d.proof_file_id, caption=text, reply_markup=kb)
        else:
            await cb.message.answer(text, reply_markup=kb)



async def _push_to_platform(session: AsyncSession, deposit: Deposit) -> str | None:
    """If user has a platform account and Agent API is on, credit the real player wallet."""
    from app.services.agent_api import agent_api, AgentAPIError
    from app.models import PlatformAccount
    from sqlalchemy import select
    if not agent_api.enabled or not deposit.credited_cents:
        return None
    acc = await session.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == deposit.user_id,
            PlatformAccount.is_active == True,  # noqa: E712
        )
    )
    if not acc or not acc.platform_player_id:
        return None
    amount = deposit.credited_cents / 100.0
    try:
        await agent_api.deposit_to_player(
            player_id=acc.platform_player_id,
            amount=amount,
            currency_code="USD",
            currency="USD",
            comment=f"bot top-up #{deposit.id}",
        )
        return f"platform +{amount} USD"
    except AgentAPIError as e:
        return f"platform error: {e.message}"
    except Exception as e:
        return f"platform error: {e}"


async def _tell_user_deposit_approved(bot: Bot, session: AsyncSession, deposit: Deposit) -> None:
    user = await session.get(User, deposit.user_id)
    balance = await get_balance(session, deposit.user_id)
    await notify_user(
        bot,
        deposit.user_id,
        t(user.lang, "deposit_approved", id=deposit.id, credited=fmt_usd(deposit.credited_cents), balance=fmt_usd(balance)),
    )


@router.callback_query(F.data.startswith("adm:dep:ok:"))
async def approve_deposit(cb: CallbackQuery, session: AsyncSession, bot: Bot):
    deposit_id = int(cb.data.rsplit(":", 1)[1])
    rate = await get_syp_rate(session)
    try:
        deposit = await deposits.approve_deposit(session, deposit_id, cb.from_user.id, rate)
    except AlreadyDecided:
        await cb.answer("Already processed by someone.", show_alert=True)
        await _stamp(cb.message, "ℹ️ Already processed")
        return
    await cb.answer("Approved ✅")
    note = await _push_to_platform(session, deposit)
    stamp = f"✅ Approved {fmt_usd(deposit.credited_cents)} by {_admin_name(cb)}"
    if note:
        stamp += f" · {note}"
    await _stamp(cb.message, stamp)
    await _tell_user_deposit_approved(bot, session, deposit)


@router.callback_query(F.data.startswith("adm:dep:custom:"))
async def approve_custom_start(cb: CallbackQuery, state: FSMContext):
    deposit_id = int(cb.data.rsplit(":", 1)[1])
    await state.set_state(AdminFlow.custom_credit)
    await state.update_data(deposit_id=deposit_id, card_chat=cb.message.chat.id, card_msg=cb.message.message_id)
    await cb.message.answer(
        f"✏️ Top-up #{deposit_id}: send the amount to credit in <b>USD</b> (e.g. 8.50):", reply_markup=CANCEL_KB
    )
    await cb.answer()


@router.message(AdminFlow.custom_credit, F.text, TYPING)
async def approve_custom_amount(message: Message, session: AsyncSession, state: FSMContext, bot: Bot):
    cents = parse_usd_to_cents(message.text)
    if cents is None:
        await message.answer("Send a positive amount like 8.50")
        return
    data = await state.get_data()
    await state.clear()
    rate = await get_syp_rate(session)
    try:
        deposit = await deposits.approve_deposit(session, data["deposit_id"], message.from_user.id, rate, credited_cents=cents)
    except AlreadyDecided:
        await message.answer("ℹ️ That top-up was already processed.")
        return
    await message.answer(f"✅ Top-up #{deposit.id} approved: {fmt_usd(cents)}")
    try:
        await bot.edit_message_reply_markup(chat_id=data["card_chat"], message_id=data["card_msg"], reply_markup=None)
    except Exception:
        pass
    await _tell_user_deposit_approved(bot, session, deposit)


@router.callback_query(F.data.startswith("adm:dep:no:"))
async def reject_deposit(cb: CallbackQuery, session: AsyncSession, bot: Bot):
    deposit_id = int(cb.data.rsplit(":", 1)[1])
    try:
        deposit = await deposits.reject_deposit(session, deposit_id, cb.from_user.id)
    except AlreadyDecided:
        await cb.answer("Already processed by someone.", show_alert=True)
        await _stamp(cb.message, "ℹ️ Already processed")
        return
    await cb.answer("Rejected")
    await _stamp(cb.message, f"❌ Rejected by {_admin_name(cb)}")
    user = await session.get(User, deposit.user_id)
    await notify_user(bot, deposit.user_id, t(user.lang, "deposit_rejected", id=deposit.id, support=support_link()))


# ───────────────────────── orders ─────────────────────────


@router.callback_query(F.data == "adm:ords")
async def pending_orders(cb: CallbackQuery, session: AsyncSession):
    rows = await orders.list_pending(session)
    if not rows:
        await cb.answer("No pending orders 👌", show_alert=True)
        return
    await cb.answer()
    for o in rows:
        text, kb = order_card(o, o.user)
        await cb.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:ord:done:"))
async def order_done(cb: CallbackQuery, session: AsyncSession, bot: Bot):
    order_id = int(cb.data.rsplit(":", 1)[1])
    try:
        order = await orders.complete_order(session, order_id, cb.from_user.id)
    except AlreadyDecided:
        await cb.answer("Already processed by someone.", show_alert=True)
        await _stamp(cb.message, "ℹ️ Already processed")
        return
    await cb.answer("Delivered ✅")
    await _stamp(cb.message, f"✅ Delivered by {_admin_name(cb)}")
    user = await session.get(User, order.user_id)
    await notify_user(
        bot,
        order.user_id,
        t(user.lang, "order_done", id=order.id, game=escape(order.game_name), package=escape(order.package_title)),
    )


@router.callback_query(F.data.startswith("adm:ord:no:"))
async def order_reject_start(cb: CallbackQuery, state: FSMContext):
    order_id = int(cb.data.rsplit(":", 1)[1])
    await state.set_state(AdminFlow.reject_order_note)
    await state.update_data(order_id=order_id, card_chat=cb.message.chat.id, card_msg=cb.message.message_id)
    await cb.message.answer(
        f"❌ Order #{order_id}: send the reason the customer will see (or <code>-</code> for none).\n"
        "The full price is refunded to their wallet.",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.reject_order_note, F.text, TYPING)
async def order_reject_finish(message: Message, session: AsyncSession, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    note = None if message.text.strip() == "-" else message.text.strip()[:500]
    try:
        order = await orders.reject_order(session, data["order_id"], message.from_user.id, note)
    except (AlreadyDecided, StoreError):
        await message.answer("ℹ️ That order was already processed.")
        return
    await message.answer(f"❌ Order #{order.id} rejected, {fmt_usd(order.price_cents)} refunded.")
    try:
        await bot.edit_message_reply_markup(chat_id=data["card_chat"], message_id=data["card_msg"], reply_markup=None)
    except Exception:
        pass
    user = await session.get(User, order.user_id)
    note_text = f"\n📝 {escape(note)}" if note else ""
    await notify_user(
        bot, order.user_id, t(user.lang, "order_rejected", id=order.id, price=fmt_usd(order.price_cents), note=note_text)
    )


# ───────────────────────── catalog ─────────────────────────


async def _games_kb(session: AsyncSession) -> InlineKeyboardMarkup:
    games = await session.scalars(select(Game).order_by(Game.sort, Game.id))
    kb = InlineKeyboardBuilder()
    for g in games:
        kb.button(text=f"{'✅' if g.is_active else '⛔️'} {g.emoji} {g.name_en}", callback_data=f"adm:game:{g.id}")
    kb.button(text="➕ Add game", callback_data="adm:game:new")
    kb.button(text="🔙 Back", callback_data="adm:home")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "adm:games")
async def games_list(cb: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("🎮 <b>Games</b> (✅ visible · ⛔️ hidden)", reply_markup=await _games_kb(session))
    await cb.answer()


async def _game_view(session: AsyncSession, game_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    game = await session.get(Game, game_id)
    if game is None:
        return None
    packages = list(await session.scalars(select(Package).where(Package.game_id == game_id).order_by(Package.sort, Package.price_cents)))
    text = (
        f"{game.emoji} <b>{escape(game.name_en)}</b> / {escape(game.name_ar)}\n"
        f"Asks for: {escape(game.id_label_en)} / {escape(game.id_label_ar)}\n"
        f"Status: {'✅ visible' if game.is_active else '⛔️ hidden'}\n\n"
        f"Packages ({len(packages)}): tap one to edit."
    )
    kb = InlineKeyboardBuilder()
    for p in packages:
        kb.button(text=f"{'✅' if p.is_active else '⛔️'} {p.title} — {fmt_usd(p.price_cents)}", callback_data=f"adm:pkg:{p.id}")
    kb.button(text="➕ Add package", callback_data=f"adm:pkg:new:{game.id}")
    kb.button(text="👁 Hide game" if game.is_active else "👁 Show game", callback_data=f"adm:game:tog:{game.id}")
    kb.button(text="🔙 Games", callback_data="adm:games")
    kb.adjust(1)
    return text, kb.as_markup()


@router.callback_query(F.data.regexp(r"^adm:game:(\d+)$"))
async def game_view(cb: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    view = await _game_view(session, int(cb.data.rsplit(":", 1)[1]))
    if view is None:
        await cb.answer("Not found", show_alert=True)
        return
    await cb.message.edit_text(view[0], reply_markup=view[1])
    await cb.answer()


@router.callback_query(F.data.startswith("adm:game:tog:"))
async def game_toggle(cb: CallbackQuery, session: AsyncSession):
    game = await session.get(Game, int(cb.data.rsplit(":", 1)[1]))
    if game is None:
        await cb.answer("Not found", show_alert=True)
        return
    game.is_active = not game.is_active
    await session.commit()
    text, kb = await _game_view(session, game.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer("Saved")


@router.callback_query(F.data == "adm:game:new")
async def game_new_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.new_game)
    await cb.message.answer(
        "➕ Send the new game in one line:\n"
        "<code>English name | Arabic name | emoji | ID label EN | ID label AR</code>\n\n"
        "Example:\n<code>Genshin Impact | جنشن إمباكت | ✨ | UID | رقم UID</code>\n"
        "(the last three are optional)",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.new_game, F.text, TYPING)
async def game_new_save(message: Message, session: AsyncSession, state: FSMContext):
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        await message.answer("Need at least: <code>English name | Arabic name</code>")
        return
    game = Game(name_en=parts[0][:128], name_ar=parts[1][:128])
    if len(parts) > 2 and parts[2]:
        game.emoji = parts[2][:8]
    if len(parts) > 3 and parts[3]:
        game.id_label_en = parts[3][:64]
    if len(parts) > 4 and parts[4]:
        game.id_label_ar = parts[4][:64]
    session.add(game)
    await session.commit()
    await state.clear()
    text, kb = await _game_view(session, game.id)
    await message.answer("✅ Game added.\n\n" + text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:pkg:new:"))
async def package_new_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.new_package)
    await state.update_data(game_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer(
        "➕ Send packages, one per line, as <code>title | price in USD</code>\n\nExample:\n"
        "<code>60 UC | 0.99\n325 UC | 4.99\n660 UC | 9.99</code>",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.new_package, F.text, TYPING)
async def package_new_save(message: Message, session: AsyncSession, state: FSMContext):
    game_id = (await state.get_data())["game_id"]
    added, bad = 0, []
    for line in message.text.splitlines():
        if not line.strip():
            continue
        title, _, price = line.rpartition("|")
        cents = parse_usd_to_cents(price)
        if not title.strip() or cents is None:
            bad.append(line)
            continue
        session.add(Package(game_id=game_id, title=title.strip()[:64], price_cents=cents))
        added += 1
    await session.commit()
    await state.clear()
    text, kb = await _game_view(session, game_id)
    note = f"✅ Added {added} package(s)."
    if bad:
        note += "\n⚠️ Skipped (wrong format):\n" + "\n".join(f"<code>{escape(b)}</code>" for b in bad)
    await message.answer(f"{note}\n\n{text}", reply_markup=kb)


async def _package_view(session: AsyncSession, package_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    p = await session.get(Package, package_id)
    if p is None:
        return None
    text = f"📦 <b>{escape(p.title)}</b>\nPrice: <b>{fmt_usd(p.price_cents)}</b>\nStatus: {'✅ visible' if p.is_active else '⛔️ hidden'}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💲 Change price", callback_data=f"adm:pkg:price:{p.id}")],
            [InlineKeyboardButton(text="👁 Hide" if p.is_active else "👁 Show", callback_data=f"adm:pkg:tog:{p.id}")],
            _back(f"adm:game:{p.game_id}"),
        ]
    )
    return text, kb


@router.callback_query(F.data.regexp(r"^adm:pkg:(\d+)$"))
async def package_view(cb: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    view = await _package_view(session, int(cb.data.rsplit(":", 1)[1]))
    if view is None:
        await cb.answer("Not found", show_alert=True)
        return
    await cb.message.edit_text(view[0], reply_markup=view[1])
    await cb.answer()


@router.callback_query(F.data.startswith("adm:pkg:tog:"))
async def package_toggle(cb: CallbackQuery, session: AsyncSession):
    p = await session.get(Package, int(cb.data.rsplit(":", 1)[1]))
    if p is None:
        await cb.answer("Not found", show_alert=True)
        return
    p.is_active = not p.is_active
    await session.commit()
    text, kb = await _package_view(session, p.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer("Saved")


@router.callback_query(F.data.startswith("adm:pkg:price:"))
async def package_price_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.package_price)
    await state.update_data(package_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer("💲 Send the new price in USD (e.g. 4.99):", reply_markup=CANCEL_KB)
    await cb.answer()


@router.message(AdminFlow.package_price, F.text, TYPING)
async def package_price_save(message: Message, session: AsyncSession, state: FSMContext):
    cents = parse_usd_to_cents(message.text)
    if cents is None:
        await message.answer("Send a positive price like 4.99")
        return
    p = await session.get(Package, (await state.get_data())["package_id"])
    await state.clear()
    if p is None:
        await message.answer("Package not found.")
        return
    p.price_cents = cents
    await session.commit()
    text, kb = await _package_view(session, p.id)
    await message.answer("✅ Price updated.\n\n" + text, reply_markup=kb)


# ───────────────────────── payment methods ─────────────────────────


@router.callback_query(F.data == "adm:methods")
async def methods_list(cb: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    rows = await session.scalars(select(PaymentMethod).order_by(PaymentMethod.sort, PaymentMethod.id))
    kb = InlineKeyboardBuilder()
    for m in rows:
        kb.button(text=f"{'✅' if m.is_active else '⛔️'} {m.name_en} ({m.currency})", callback_data=f"adm:m:{m.id}")
    kb.button(text="🔙 Back", callback_data="adm:home")
    kb.adjust(1)
    await cb.message.edit_text("💳 <b>Payment methods</b>", reply_markup=kb.as_markup())
    await cb.answer()


async def _method_view(session: AsyncSession, method_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    m = await session.get(PaymentMethod, method_id)
    if m is None:
        return None
    min_txt = fmt_syp(m.min_amount) if m.currency == "SYP" else fmt_usd(m.min_amount * 100)
    text = (
        f"💳 <b>{escape(m.name_en)}</b> / {escape(m.name_ar)} ({m.currency})\n"
        f"Status: {'✅ visible' if m.is_active else '⛔️ hidden'} · Minimum: {min_txt}\n\n"
        f"<b>Shown to users (EN):</b>\n{escape(m.details_en) or '—'}\n\n"
        f"<b>Shown to users (AR):</b>\n{escape(m.details_ar) or '—'}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Details EN", callback_data=f"adm:m:det:en:{m.id}"),
                InlineKeyboardButton(text="✏️ Details AR", callback_data=f"adm:m:det:ar:{m.id}"),
            ],
            [InlineKeyboardButton(text="👁 Hide" if m.is_active else "👁 Show", callback_data=f"adm:m:tog:{m.id}")],
            _back("adm:methods"),
        ]
    )
    return text, kb


@router.callback_query(F.data.regexp(r"^adm:m:(\d+)$"))
async def method_view(cb: CallbackQuery, session: AsyncSession):
    view = await _method_view(session, int(cb.data.rsplit(":", 1)[1]))
    if view is None:
        await cb.answer("Not found", show_alert=True)
        return
    await cb.message.edit_text(view[0], reply_markup=view[1])
    await cb.answer()


@router.callback_query(F.data.startswith("adm:m:tog:"))
async def method_toggle(cb: CallbackQuery, session: AsyncSession):
    m = await session.get(PaymentMethod, int(cb.data.rsplit(":", 1)[1]))
    if m is None:
        await cb.answer("Not found", show_alert=True)
        return
    m.is_active = not m.is_active
    await session.commit()
    text, kb = await _method_view(session, m.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer("Saved")


@router.callback_query(F.data.startswith("adm:m:det:"))
async def method_details_start(cb: CallbackQuery, state: FSMContext):
    _, _, _, lang, method_id = cb.data.split(":")
    await state.set_state(AdminFlow.method_details)
    await state.update_data(method_id=int(method_id), lang=lang)
    await cb.message.answer(
        f"✏️ Send the payment details users will see ({lang.upper()}): account number, name, and instructions.",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.method_details, F.text, TYPING)
async def method_details_save(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    m = await session.get(PaymentMethod, data["method_id"])
    if m is None:
        await message.answer("Method not found.")
        return
    if data["lang"] == "ar":
        m.details_ar = message.text[:2000]
    else:
        m.details_en = message.text[:2000]
    await session.commit()
    text, kb = await _method_view(session, m.id)
    await message.answer("✅ Saved.\n\n" + text, reply_markup=kb)


# ───────────────────────── users ─────────────────────────


async def _user_view(session: AsyncSession, user: User) -> tuple[str, InlineKeyboardMarkup]:
    balance = await get_balance(session, user.id)
    n_orders = await session.scalar(select(func.count(Order.id)).where(Order.user_id == user.id))
    n_deps = await session.scalar(
        select(func.count(Deposit.id)).where(Deposit.user_id == user.id, Deposit.status == Status.APPROVED)
    )
    text = (
        f"👤 <b>{escape(user.full_name or '—')}</b> {('@' + escape(user.username)) if user.username else ''}\n"
        f"🆔 <code>{user.id}</code> · lang: {user.lang or '—'}\n"
        f"💰 Balance: <b>{fmt_usd(balance)}</b>\n"
        f"📦 Orders: {n_orders or 0} · 💳 Approved top-ups: {n_deps or 0}\n"
        f"Joined: {user.created_at:%Y-%m-%d}\n"
        f"Status: {'⛔️ BANNED' if user.is_banned else '✅ active'}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="± Adjust balance", callback_data=f"adm:u:adj:{user.id}")],
            [InlineKeyboardButton(text="✅ Unban" if user.is_banned else "⛔️ Ban", callback_data=f"adm:u:ban:{user.id}")],
            _back(),
        ]
    )
    return text, kb


@router.callback_query(F.data == "adm:user")
async def find_user_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.find_user)
    await cb.message.answer("👤 Send the user's Telegram ID or @username:", reply_markup=CANCEL_KB)
    await cb.answer()


@router.message(AdminFlow.find_user, F.text, TYPING)
async def find_user(message: Message, session: AsyncSession, state: FSMContext):
    query = message.text.strip()
    if query.lstrip("-").isdigit():
        user = await session.get(User, int(query))
    else:
        user = await session.scalar(select(User).where(func.lower(User.username) == query.lstrip("@").lower()))
    if user is None:
        await message.answer("Not found. Send another ID / @username, or Cancel.", reply_markup=CANCEL_KB)
        return
    await state.clear()
    text, kb = await _user_view(session, user)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:u:ban:"))
async def toggle_ban(cb: CallbackQuery, session: AsyncSession):
    user = await session.get(User, int(cb.data.rsplit(":", 1)[1]))
    if user is None:
        await cb.answer("Not found", show_alert=True)
        return
    if user.id in settings.admin_ids:
        await cb.answer("Can't ban an admin.", show_alert=True)
        return
    user.is_banned = not user.is_banned
    await session.commit()
    text, kb = await _user_view(session, user)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer("Saved")


@router.callback_query(F.data.startswith("adm:u:adj:"))
async def adjust_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.adjust_balance)
    await state.update_data(user_id=int(cb.data.rsplit(":", 1)[1]))
    await cb.message.answer(
        "± Send the change in USD and a reason, e.g.\n<code>+5 bonus</code>\n<code>-2.50 correction</code>",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.adjust_balance, F.text, TYPING)
async def adjust_save(message: Message, session: AsyncSession, state: FSMContext):
    raw, _, reason = message.text.strip().partition(" ")
    sign = -1 if raw.startswith("-") else 1
    cents = parse_usd_to_cents(raw.lstrip("+-"))
    if cents is None or not raw[:1] in "+-":
        await message.answer("Format: <code>+5 reason</code> or <code>-2.50 reason</code>")
        return
    user_id = (await state.get_data())["user_id"]
    try:
        new_balance = await admin_adjust(session, user_id, sign * cents, message.from_user.id, reason.strip() or "admin adjustment")
    except InsufficientBalance as exc:
        await message.answer(f"⚠️ Balance would go negative (balance {fmt_usd(exc.balance_cents)}).")
        return
    await state.clear()
    user = await session.get(User, user_id)
    text, kb = await _user_view(session, user)
    await message.answer(f"✅ Done. New balance: {fmt_usd(new_balance)}\n\n{text}", reply_markup=kb)


# ───────────────────────── broadcast ─────────────────────────


@router.callback_query(F.data == "adm:bc")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.broadcast)
    await cb.message.answer(
        "📢 Send the message to broadcast (text, photo, video…). You'll confirm before it's sent.",
        reply_markup=CANCEL_KB,
    )
    await cb.answer()


@router.message(AdminFlow.broadcast, TYPING)
async def broadcast_preview(message: Message, session: AsyncSession, state: FSMContext):
    count = await session.scalar(select(func.count(User.id)).where(User.is_banned.is_(False)))
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await message.answer(
        f"Send this to <b>{count}</b> users?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Send", callback_data="adm:bc:go"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="adm:cancel"),
                ]
            ]
        ),
    )


@router.callback_query(AdminFlow.broadcast, F.data == "adm:bc:go")
async def broadcast_go(cb: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await cb.message.edit_text("📢 Sending…")
    await cb.answer()
    user_ids = list(await session.scalars(select(User.id).where(User.is_banned.is_(False))))
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.copy_message(uid, data["src_chat"], data["src_msg"])
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # stay under Telegram's ~30 msg/s limit
    await cb.message.edit_text(f"📢 Broadcast done: ✅ {sent} sent · ❌ {failed} failed (blocked the bot).")


# ───────────────────────── SYP rate ─────────────────────────


@router.callback_query(F.data == "adm:rate")
async def rate_start(cb: CallbackQuery, session: AsyncSession, state: FSMContext):
    rate = await get_syp_rate(session)
    await state.set_state(AdminFlow.syp_rate)
    auto = "\nAuto-update from your rate API is ON." if settings.syp_rate_api_url else ""
    await cb.message.answer(
        f"💱 Current rate: <b>1 USD = {rate:,.0f} SYP</b>{auto}\n\nSend a new rate to change it:", reply_markup=CANCEL_KB
    )
    await cb.answer()


@router.message(AdminFlow.syp_rate, F.text, TYPING)
async def rate_save(message: Message, session: AsyncSession, state: FSMContext):
    try:
        rate = float(message.text.replace(",", "").strip())
        await set_syp_rate(session, rate)
    except ValueError:
        await message.answer("Send a positive number like 13000")
        return
    await state.clear()
    await message.answer(f"✅ Rate saved: 1 USD = {rate:,.0f} SYP", reply_markup=panel_kb())


# ───────────────────────── Withdrawals ─────────────────────────


@router.callback_query(F.data.startswith("admin:wd:ok:"))
async def approve_withdrawal(cb: CallbackQuery, session: AsyncSession, bot: Bot):
    wd_id = int(cb.data.rsplit(":", 1)[1])
    from app.models import Withdrawal
    from sqlalchemy import update as sa_update
    result = await session.execute(
        sa_update(Withdrawal)
        .where(Withdrawal.id == wd_id, Withdrawal.status == Status.PENDING)
        .values(status=Status.COMPLETED, decided_by=cb.from_user.id, decided_at=utcnow())
    )
    if result.rowcount != 1:
        await cb.answer("Already processed", show_alert=True)
        return
    await session.commit()
    wd = await session.get(Withdrawal, wd_id)
    await cb.message.edit_text(cb.message.text + "\n\n✅ Approved")
    await cb.answer("✅")
    try:
        await bot.send_message(
            wd.user_id,
            t("ar", "withdraw_approved", id=wd.id, amount=fmt_usd(wd.amount_cents))
            + "\n"
            + t("en", "withdraw_approved", id=wd.id, amount=fmt_usd(wd.amount_cents)),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin:wd:no:"))
async def reject_withdrawal(cb: CallbackQuery, session: AsyncSession, bot: Bot):
    wd_id = int(cb.data.rsplit(":", 1)[1])
    from app.models import Withdrawal, LedgerEntry, LedgerKind
    from sqlalchemy import update as sa_update
    from app.services.wallet import lock_user

    wd = await session.get(Withdrawal, wd_id)
    if wd is None or wd.status != Status.PENDING:
        await cb.answer("Already processed", show_alert=True)
        return

    await lock_user(session, wd.user_id)
    result = await session.execute(
        sa_update(Withdrawal)
        .where(Withdrawal.id == wd_id, Withdrawal.status == Status.PENDING)
        .values(status=Status.REJECTED, decided_by=cb.from_user.id, decided_at=utcnow())
    )
    if result.rowcount != 1:
        await session.rollback()
        await cb.answer("Already processed", show_alert=True)
        return

    # Refund the held amount
    session.add(
        LedgerEntry(
            user_id=wd.user_id,
            amount_cents=wd.amount_cents,
            kind=LedgerKind.REFUND,
            ref_id=wd.id,
            note=f"Withdraw #{wd.id} rejected",
            created_by=cb.from_user.id,
        )
    )
    await session.commit()
    await cb.message.edit_text(cb.message.text + "\n\n❌ Rejected + refunded")
    await cb.answer("❌")
    try:
        await bot.send_message(
            wd.user_id,
            t("ar", "withdraw_rejected", id=wd.id, note="")
            + "\n"
            + t("en", "withdraw_rejected", id=wd.id, note=""),
        )
    except Exception:
        pass
