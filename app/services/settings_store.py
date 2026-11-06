from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting

SYP_RATE_KEY = "syp_rate"


async def get_setting(session: AsyncSession, key: str) -> str | None:
    row = await session.get(Setting, key)
    return row.value if row else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()


async def get_syp_rate(session: AsyncSession) -> float:
    raw = await get_setting(session, SYP_RATE_KEY)
    try:
        rate = float(raw) if raw else settings.default_syp_rate
    except ValueError:
        rate = settings.default_syp_rate
    return rate if rate > 0 else settings.default_syp_rate


async def set_syp_rate(session: AsyncSession, rate: float) -> None:
    if rate <= 0:
        raise ValueError("rate must be positive")
    await set_setting(session, SYP_RATE_KEY, str(rate))
