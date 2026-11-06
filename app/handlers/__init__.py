from aiogram import Router

from app.handlers import account, admin, fallback, menu, start, topup, withdraw


def build_router() -> Router:
    root = Router(name="root")
    # Order matters: admin first (its free-text steps are admin-only), fallback last.
    for module in (start, admin, menu, topup, withdraw, account, fallback):
        root.include_router(module.router)
    return root
