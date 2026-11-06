"""Starter payment methods, inserted only when the tables are empty."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, PaymentMethod

METHODS = [
    ("shamcash_usd", "ShamCash (USD)", "شام كاش (دولار)", Currency.USD, 1, True, True),
    ("shamcash_syp", "ShamCash (SYP)", "شام كاش (ليرة سورية)", Currency.SYP, 10000, True, False),
    ("crypto_usdt", "USDT (TRC20)", "USDT (TRC20)", Currency.USD, 5, True, True),
    ("visa", "Visa / Mastercard", "فيزا / ماستركارد", Currency.USD, 5, True, False),
]


async def seed_if_empty(session: AsyncSession) -> None:
    if not await session.scalar(select(func.count(PaymentMethod.id))):
        for sort, (code, en, ar, currency, minimum, for_dep, for_wd) in enumerate(METHODS):
            session.add(
                PaymentMethod(
                    code=code,
                    name_en=en,
                    name_ar=ar,
                    currency=currency,
                    min_amount=minimum,
                    sort=sort,
                    for_deposit=for_dep,
                    for_withdraw=for_wd,
                    details_en="⚠️ Admin: set the account details / QR from /admin → Payment methods.",
                    details_ar="⚠️ للإدارة: أضف تفاصيل الحساب / QR من /admin ← Payment methods.",
                    is_active=False,  # hidden until admin fills details
                )
            )
    await session.commit()
