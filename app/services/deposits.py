from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Deposit, LedgerEntry, LedgerKind, PaymentMethod, Status, utcnow
from app.money import to_cents
from app.services.errors import AlreadyDecided, BelowMinimum, DuplicateTransaction, NotAvailable


def normalize_txn_ref(ref: str) -> str:
    return " ".join(ref.split()).upper()


async def create_deposit(
    session: AsyncSession,
    *,
    user_id: int,
    method_id: int,
    amount: int,
    txn_ref: str,
    proof_file_id: str | None,
) -> Deposit:
    method = await session.get(PaymentMethod, method_id)
    if method is None or not method.is_active:
        raise NotAvailable()
    if amount < method.min_amount:
        raise BelowMinimum()

    ref = normalize_txn_ref(txn_ref)
    exists = await session.scalar(
        select(Deposit.id).where(Deposit.method_id == method_id, Deposit.txn_ref == ref)
    )
    if exists:
        raise DuplicateTransaction()

    deposit = Deposit(
        user_id=user_id,
        method_id=method_id,
        amount=amount,
        currency=method.currency,
        txn_ref=ref,
        proof_file_id=proof_file_id,
    )
    session.add(deposit)
    try:
        await session.commit()
    except IntegrityError as exc:  # race: same ref submitted twice at once
        await session.rollback()
        raise DuplicateTransaction() from exc
    return deposit


async def approve_deposit(
    session: AsyncSession,
    deposit_id: int,
    admin_id: int,
    syp_rate: float,
    credited_cents: int | None = None,
) -> Deposit:
    """Approve once. A second approve (double tap, two admins) raises AlreadyDecided and credits nothing."""
    deposit = await session.get(Deposit, deposit_id)
    if deposit is None:
        raise NotAvailable()
    cents = credited_cents if credited_cents is not None else to_cents(deposit.amount, deposit.currency, syp_rate)
    if cents <= 0:
        raise ValueError("credit must be positive")

    result = await session.execute(
        update(Deposit)
        .where(Deposit.id == deposit_id, Deposit.status == Status.PENDING)
        .values(status=Status.APPROVED, credited_cents=cents, decided_by=admin_id, decided_at=utcnow())
    )
    if result.rowcount != 1:
        await session.rollback()
        raise AlreadyDecided()

    session.add(
        LedgerEntry(
            user_id=deposit.user_id,
            amount_cents=cents,
            kind=LedgerKind.DEPOSIT,
            ref_id=deposit_id,
            created_by=admin_id,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AlreadyDecided() from exc
    await session.refresh(deposit)
    return deposit


async def reject_deposit(session: AsyncSession, deposit_id: int, admin_id: int) -> Deposit:
    result = await session.execute(
        update(Deposit)
        .where(Deposit.id == deposit_id, Deposit.status == Status.PENDING)
        .values(status=Status.REJECTED, decided_by=admin_id, decided_at=utcnow())
    )
    if result.rowcount != 1:
        await session.rollback()
        raise AlreadyDecided()
    await session.commit()
    deposit = await session.get(Deposit, deposit_id)
    await session.refresh(deposit)
    return deposit


async def get_deposit(session: AsyncSession, deposit_id: int) -> Deposit | None:
    return await session.scalar(
        select(Deposit).options(selectinload(Deposit.method), selectinload(Deposit.user)).where(Deposit.id == deposit_id)
    )


async def list_pending(session: AsyncSession, limit: int = 20) -> list[Deposit]:
    rows = await session.scalars(
        select(Deposit)
        .options(selectinload(Deposit.method), selectinload(Deposit.user))
        .where(Deposit.status == Status.PENDING)
        .order_by(Deposit.created_at)
        .limit(limit)
    )
    return list(rows)


async def list_for_user(session: AsyncSession, user_id: int, limit: int = 10) -> list[Deposit]:
    rows = await session.scalars(
        select(Deposit)
        .options(selectinload(Deposit.method))
        .where(Deposit.user_id == user_id)
        .order_by(Deposit.created_at.desc())
        .limit(limit)
    )
    return list(rows)
