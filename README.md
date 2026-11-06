# Dogs Bet 🐶 — Telegram Bot

Wolf-style deposit / account bot for the Dogs Bet platform.

## Features

- Language picker (AR / EN)
- Terms of use (no balance flipping, permanent ban)
- Optional force-join channels
- **Main menu** (same structure as Wolf Official):
  - Create Dogs account
  - Top up bot balance (ShamCash / Crypto / Visa)
  - Withdraw bot balance
  - Bot & site balances
  - Contact support
  - Terms | Our channels
  - Offers | Referrals
  - Gift code
  - Platform website
- Ledger-based wallet (safe, no double credits)
- Admin panel: approve/reject deposits & withdrawals, gift codes, broadcast, SYP rate, payment methods
- Ready for Agent API integration (registerPlayer, depositToPlayer, …)

## Money safety

Balance is never a stored number — it is the sum of ledger entries.
Unique constraints prevent reused transaction IDs and double approvals.

## Setup

1. Create bot with @BotFather → copy token
2. Get your Telegram ID from @userinfobot
3. Copy env:

```bash
cp .env.example .env
# fill BOT_TOKEN, ADMIN_IDS, etc.
```

4. Run:

```bash
# Local (SQLite)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app

# Docker
docker compose up -d --build
```

## Environment

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | From BotFather |
| `ADMIN_IDS` | Comma-separated Telegram IDs |
| `STORE_NAME` | Default: Dogs Bet |
| `SUPPORT_USERNAME` | Without @ |
| `REQUIRED_CHANNELS` | Leave empty for now |
| `PLATFORM_WEBSITE` | Optional link |
| `DATABASE_URL` | Auto-set in Docker |
| `AGENT_API_*` | Optional, for real platform later |

## Project layout

```
app/
  __main__.py      entry point
  config.py        settings
  models.py        users, ledger, deposits, withdrawals, gifts, platform accounts
  services/        pure money logic
  handlers/        start, menu, topup, withdraw, admin
  i18n.py          AR + EN texts
```

## Next steps

1. Fill payment method details from `/admin`
2. Create gift codes from admin
3. When ready: connect Agent API for real player registration & site balance
