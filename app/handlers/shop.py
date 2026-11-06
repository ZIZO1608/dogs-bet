from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cards import order_card
from app.i18n import both, menu_texts, t
from app.keyboards import cancel_kb, confirm_order_kb, games_kb, packages_kb, topup_now_kb
from app.models import Game, Package, User
from app.money import fmt_usd
from app.notify import notify_admins
from app.services import orders
from app.services.errors import InsufficientBalance, StoreError
from app.services.wallet import get_balance
from app.states import ShopFlow

router = Router(name="shop")

MAX_PLAYER_REF = 64


async def _load_package(session: AsyncSession, package_id: int) -> Package | None:
    return await session.scalar(select(Package).options(selectinload(Package.game)).where(Package.id == package_id))


async def _games_view(session: AsyncSession, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    games = await orders.active_games(session)
    if not games:
        return t(lang, "shop_empty"), None
    return t(lang, "shop_title"), games_kb(games, lang)


@router.message(F.text.in_(both("m_shop")))
async def open_shop(message: Message, session: AsyncSession, lang: str, state: FSMContext):
    await state.clear()
    text, kb = await _games_view(session, lang)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "shop:home")
async def shop_home(cb: CallbackQuery, session: AsyncSession, lang: str, state: FSMContext):
    await state.clear()
    text, kb = await _games_view(session, lang)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("shop:g:"))
async def pick_game(cb: CallbackQuery, session: AsyncSession, lang: str):
    game = await session.get(Game, int(cb.data.rsplit(":", 1)[1]))
    if game is None or not game.is_active:
        await cb.answer(t(lang, "err_not_available"), show_alert=True)
        return
    packages = await orders.active_packages(session, game.id)
    text = t(lang, "packages_title", emoji=game.emoji, game=escape(game.name(lang)))
    if not packages:
        text += "\n\n" + t(lang, "packages_empty")
    await cb.message.edit_text(text, reply_markup=packages_kb(packages, lang))
    await cb.answer()


@router.callback_query(F.data.startswith("shop:p:"))
async def pick_package(cb: CallbackQuery, session: AsyncSession, lang: str, state: FSMContext):
    package = await _load_package(session, int(cb.data.rsplit(":", 1)[1]))
    if package is None or not package.is_active or not package.game.is_active:
        await cb.answer(t(lang, "err_not_available"), show_alert=True)
        return
    await state.set_state(ShopFlow.player_ref)
    await state.update_data(package_id=package.id)
    game = package.game
    await cb.message.edit_text(
        t(
            lang,
            "ask_player",
            emoji=game.emoji,
            game=escape(game.name(lang)),
            package=escape(package.title),
            price=fmt_usd(package.price_cents),
            label=escape(game.id_label(lang)),
        ),
        reply_markup=cancel_kb(lang, "shop:cancel"),
    )
    await cb.answer()


@router.message(ShopFlow.player_ref, F.text, ~F.text.in_(menu_texts()))
async def got_player_ref(message: Message, session: AsyncSession, user: User, lang: str, state: FSMContext):
    player_ref = message.text.strip()
    if not player_ref or len(player_ref) > MAX_PLAYER_REF or "\n" in player_ref:
        await message.answer(t(lang, "player_invalid"))
        return
    data = await state.get_data()
    package = await _load_package(session, data.get("package_id", 0))
    if package is None or not package.is_active:
        await state.clear()
        await message.answer(t(lang, "err_not_available"))
        return
    await state.update_data(player_ref=player_ref)
    await state.set_state(ShopFlow.confirm)
    balance = await get_balance(session, user.id)
    await message.answer(
        t(
            lang,
            "confirm_order",
            game=escape(package.game.name(lang)),
            package=escape(package.title),
            label=escape(package.game.id_label(lang)),
            player=escape(player_ref),
            price=fmt_usd(package.price_cents),
            balance=fmt_usd(balance),
        ),
        reply_markup=confirm_order_kb(lang),
    )


@router.callback_query(ShopFlow.confirm, F.data == "shop:confirm")
async def confirm_order(cb: CallbackQuery, session: AsyncSession, user: User, lang: str, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()  # clear first: a double tap must not create two orders
    await cb.message.edit_reply_markup(reply_markup=None)
    try:
        order = await orders.create_order(
            session, user_id=user.id, package_id=data["package_id"], player_ref=data["player_ref"], lang=lang
        )
    except InsufficientBalance as exc:
        await cb.message.answer(
            t(lang, exc.code, balance=fmt_usd(exc.balance_cents), needed=fmt_usd(exc.needed_cents)),
            reply_markup=topup_now_kb(lang),
        )
        await cb.answer()
        return
    except StoreError as exc:
        await cb.message.answer(t(lang, exc.code))
        await cb.answer()
        return

    await cb.message.answer(t(lang, "order_created", id=order.id, price=fmt_usd(order.price_cents)))
    await cb.answer("✅")

    text, kb = order_card(order, user)
    await notify_admins(bot, text, kb)


@router.callback_query(F.data == "shop:cancel")
async def cancel_order(cb: CallbackQuery, lang: str, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(t(lang, "cancelled"))
    await cb.answer()


@router.callback_query(F.data == "shop:confirm")
async def stale_confirm(cb: CallbackQuery, lang: str):
    """Confirm tapped on an old message (state already cleared)."""
    await cb.answer(t(lang, "err_already_decided"), show_alert=True)
