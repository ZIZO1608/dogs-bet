import asyncio
import json
import logging
import urllib.request

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import create_tables, make_engine, make_sessionmaker
from app.handlers import build_router
from app.i18n import t
from app.middlewares import DbSessionMiddleware, UserMiddleware
from app.seed import seed_if_empty
from app.services.settings_store import set_syp_rate

log = logging.getLogger("dogs_bet")


def _fetch_rate() -> float:
    with urllib.request.urlopen(settings.syp_rate_api_url, timeout=15) as resp:  # noqa: S310 (admin-configured URL)
        data = json.load(resp)
    value = data
    for key in settings.syp_rate_json_key.split("."):
        value = value[key]
    return float(value)


async def refresh_syp_rate(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Pull the SYP rate from your rate API every N minutes. Keeps the last good value on failure."""
    while True:
        try:
            rate = await asyncio.to_thread(_fetch_rate)
            async with sessionmaker() as session:
                await set_syp_rate(session, rate)
            log.info("SYP rate updated: %s", rate)
        except Exception:
            log.warning("SYP rate refresh failed; keeping the last value", exc_info=True)
        await asyncio.sleep(settings.syp_rate_refresh_minutes * 60)


def build_dispatcher(sessionmaker: async_sessionmaker[AsyncSession]) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(DbSessionMiddleware(sessionmaker))
        observer.outer_middleware(UserMiddleware())
    dp.include_router(build_router())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("Unhandled error", exc_info=event.exception)
        upd = event.update
        try:
            if upd.callback_query:
                await upd.callback_query.answer(t("ar", "error_generic") + "\n" + t("en", "error_generic"), show_alert=True)
            elif upd.message:
                await upd.message.answer(t("ar", "error_generic"))
        except Exception:
            pass
        return True

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("Starting Dogs Bet...")
    log.info("BOT_TOKEN set: %s", bool(settings.bot_token))
    log.info("ADMIN_IDS: %s", settings.admin_ids)
    log.info("DATABASE_URL starts with: %s", (settings.database_url or "")[:40])
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")
    if not settings.admin_ids:
        log.warning("ADMIN_IDS is empty — nobody can approve top-ups or orders!")

    try:
        engine = make_engine(settings.database_url)
        await create_tables(engine)
        sessionmaker = make_sessionmaker(engine)
        async with sessionmaker() as session:
            await seed_if_empty(session)
        log.info("Database ready")
    except Exception as exc:
        log.exception("Database connection failed: %s", exc)
        raise

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Branding: commands + short description (visible in Telegram profile)
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Main menu / القائمة الرئيسية"),
        BotCommand(command="admin", description="🛠 Admin panel (admins only)"),
    ])
    try:
        await bot.set_my_description(
            "🐶 Dogs Bet — Create account, top up & withdraw securely.\n"
            "إنشاء حساب، شحن وسحب رصيد بأمان."
        )
        await bot.set_my_short_description("🐶 Dogs Bet — top up & accounts")
    except Exception:
        pass  # older Bot API / no permission
    dp = build_dispatcher(sessionmaker)

    rate_task = asyncio.create_task(refresh_syp_rate(sessionmaker)) if settings.syp_rate_api_url else None
    log.info("%s is running", settings.store_name)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if rate_task:
            rate_task.cancel()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
