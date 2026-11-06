from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Game, LedgerEntry, LedgerKind, Order, Package, Status, utcnow
from app.services.errors import AlreadyDecided, InsufficientBalance, NotAvailable
from app.services.wallet import get_balance, lock_user


async def create_order(session: AsyncSession, *, user_id: int, package_id: int, player_ref: str, lang: str) -> Order:
    """Debit the wallet and create a pending order in one transaction."""
    package = await session.scalar(
        select(Package).options(selectinload(Package.game)).where(Package.id == package_id)
    )
    if package is None or not package.is_active or not package.game.is_active:
        raise NotAvailable()

    price_cents = package.price_cents  # read before any rollback expires the object
    await lock_user(session, user_id)
    balance = await get_balance(session, user_id)
    if balance < price_cents:
        await session.rollback()
        raise InsufficientBalance(balance, price_cents)

    order = Order(
        user_id=user_id,
        package_id=package.id,
        game_name=package.game.name(lang),
        package_title=package.title,
        price_cents=package.price_cents,
        player_ref=player_ref.strip()[:128],
    )
    session.add(order)
    await session.flush()
    session.add(
        LedgerEntry(
            user_id=user_id,
            amount_cents=-package.price_cents,
            kind=LedgerKind.PURCHASE,
            ref_id=order.id,
        )
    )
    await session.commit()
    return order


async def complete_order(session: AsyncSession, order_id: int, admin_id: int) -> Order:
    result = await session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == Status.PENDING)
        .values(status=Status.COMPLETED, decided_by=admin_id, decided_at=utcnow())
    )
    if result.rowcount != 1:
        await session.rollback()
        raise AlreadyDecided()
    await session.commit()
    order = await session.get(Order, order_id)
    await session.refresh(order)
    return order


async def reject_order(session: AsyncSession, order_id: int, admin_id: int, note: str | None = None) -> Order:
    """Reject and refund the full price back to the wallet, exactly once."""
    order = await session.get(Order, order_id)
    if order is None:
        raise NotAvailable()
    result = await session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == Status.PENDING)
        .values(status=Status.REJECTED, decided_by=admin_id, decided_at=utcnow(), admin_note=note)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise AlreadyDecided()
    session.add(
        LedgerEntry(
            user_id=order.user_id,
            amount_cents=order.price_cents,
            kind=LedgerKind.REFUND,
            ref_id=order_id,
            created_by=admin_id,
            note=note,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AlreadyDecided() from exc
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.scalar(select(Order).options(selectinload(Order.user)).where(Order.id == order_id))


async def list_pending(session: AsyncSession, limit: int = 20) -> list[Order]:
    rows = await session.scalars(
        select(Order).options(selectinload(Order.user)).where(Order.status == Status.PENDING).order_by(Order.created_at).limit(limit)
    )
    return list(rows)


async def list_for_user(session: AsyncSession, user_id: int, limit: int = 10) -> list[Order]:
    rows = await session.scalars(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(limit)
    )
    return list(rows)


async def active_games(session: AsyncSession) -> list[Game]:
    rows = await session.scalars(select(Game).where(Game.is_active.is_(True)).order_by(Game.sort, Game.id))
    return list(rows)


async def active_packages(session: AsyncSession, game_id: int) -> list[Package]:
    rows = await session.scalars(
        select(Package)
        .where(Package.game_id == game_id, Package.is_active.is_(True))
        .order_by(Package.sort, Package.price_cents)
    )
    return list(rows)
