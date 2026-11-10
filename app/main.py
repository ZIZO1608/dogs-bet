from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import secrets
from datetime import datetime

app = FastAPI(title="Dogs Bet Owner Panel")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dogsbet-owner-secret-change-me"))
templates = Jinja2Templates(directory="app/templates")

# Owner: everything. Cashier: prices and dollar rate only.
OWNERS = {"owner": os.getenv("OWNER_PASSWORD", "owner123")}
CASHIERS = {}
BOTS = {}
SETTINGS = {
    "syp_rate": 13000,
    "min_deposit": 50,
    "max_deposit": 133000,
    "min_withdraw": 700,
    "max_withdraw": 133000,
    "withdraw_fee": 15,
    "shamcash_secret1": "",
    "shamcash_secret2": "",
    "shamcash_secret3": "",
}

# Default cashier so the panel can be tested before the owner creates one.
CASHIERS["cashier"] = {
    "password": os.getenv("CASHIER_PASSWORD", "cashier123"),
    "name": "Default cashier",
}


def get_user(request: Request):
    return request.session.get("user")


def role_of(user: str | None) -> str | None:
    if not user:
        return None
    if user in OWNERS:
        return "owner"
    if user in CASHIERS:
        return "cashier"
    return None


def require_login(request: Request):
    user = get_user(request)
    if not user or not role_of(user):
        return None
    return user


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login")
    role = role_of(user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "role": role,
        "is_owner": role == "owner",
        "bots": list(BOTS.values()),
        "cashiers": list(CASHIERS.keys()),
        "settings": SETTINGS,
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    ok = OWNERS.get(username) == password or (
        username in CASHIERS and CASHIERS[username]["password"] == password
    )
    if ok:
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "خطأ في البيانات"})


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/bots", response_class=HTMLResponse)
async def bots_page(request: Request):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    return templates.TemplateResponse("bots.html", {"request": request, "bots": list(BOTS.values())})


@app.get("/bots/new", response_class=HTMLResponse)
async def new_bot_page(request: Request):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    return templates.TemplateResponse("new_bot.html", {"request": request})


@app.post("/bots/new")
async def create_bot(
    request: Request,
    name: str = Form(...),
    token: str = Form(...),
    cashier_user: str = Form(""),
    cashier_pass: str = Form(""),
    generate: str = Form(""),
):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    bot_id = secrets.token_hex(4)
    if generate or not cashier_user:
        cashier_user = f"cashier_{bot_id[:4]}"
        cashier_pass = secrets.token_urlsafe(8)
    if cashier_user in OWNERS:
        return templates.TemplateResponse("new_bot.html", {
            "request": request,
            "error": "هذا الاسم محجوز للمالك",
        })
    CASHIERS[cashier_user] = {"password": cashier_pass, "name": name}
    BOTS[bot_id] = {
        "id": bot_id,
        "name": name,
        "token": token[:12] + "...",
        "cashier_user": cashier_user,
        "cashier_pass": cashier_pass,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    return RedirectResponse("/bots", status_code=303)


@app.get("/prices", response_class=HTMLResponse)
async def prices_page(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("prices.html", {
        "request": request,
        "role": role_of(user),
        "settings": SETTINGS,
    })


@app.post("/prices")
async def save_prices(
    request: Request,
    syp_rate: float = Form(13000),
    min_deposit: float = Form(50),
    max_deposit: float = Form(133000),
    min_withdraw: float = Form(700),
    max_withdraw: float = Form(133000),
    withdraw_fee: float = Form(15),
):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login")
    SETTINGS.update({
        "syp_rate": syp_rate,
        "min_deposit": min_deposit,
        "max_deposit": max_deposit,
        "min_withdraw": min_withdraw,
        "max_withdraw": max_withdraw,
        "withdraw_fee": withdraw_fee,
    })
    return RedirectResponse("/prices?saved=1", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": SETTINGS,
    })


@app.post("/settings")
async def save_settings(
    request: Request,
    shamcash_secret1: str = Form(""),
    shamcash_secret2: str = Form(""),
    shamcash_secret3: str = Form(""),
):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    SETTINGS.update({
        "shamcash_secret1": shamcash_secret1,
        "shamcash_secret2": shamcash_secret2,
        "shamcash_secret3": shamcash_secret3,
    })
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = require_login(request)
    if not user or role_of(user) != "owner":
        return RedirectResponse("/")
    users = [
        {"id": 1, "username": "x_store_seb", "balance": 0, "status": "active", "lang": "ar"},
        {"id": 2, "username": "Robert7Gree", "balance": 0, "status": "active", "lang": "en"},
    ]
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
    })
