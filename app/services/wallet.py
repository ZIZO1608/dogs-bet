from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LedgerEntry, LedgerKind, User
from app.services.errors import InsufficientBalance


async def get_balance(session: AsyncSession, user_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(LedgerEntry.user_id == user_id)
    )
    return int(total or 0)


async def lock_user(session: AsyncSession, user_id: int) -> User | None:
    """Row-lock the user for the rest of the transaction (Postgres). SQLite serializes writers anyway."""
    return await session.scalar(select(User).where(User.id == user_id).with_for_update())


async def admin_adjust(session: AsyncSession, user_id: int, amount_cents: int, admin_id: int, note: str) -> int:
    """Manual credit (+) or debit (-) by an admin. Returns the new balance. Commits."""
    if amount_cents == 0:
        raise ValueError("amount must be non-zero")
    await lock_user(session, user_id)
    balance = await get_balance(session, user_id)
    if balance + amount_cents < 0:
        await session.rollback()
        raise InsufficientBalance(balance, -amount_cents)
    session.add(
        LedgerEntry(
            user_id=user_id,
            amount_cents=amount_cents,
            kind=LedgerKind.ADJUST,
            ref_id=None,
            note=note,
            created_by=admin_id,
        )
    )
    await session.commit()
    return await get_balance(session, user_id)
