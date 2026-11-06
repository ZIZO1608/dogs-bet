"""Agent API client for the betting platform.

Handles authentication (signIn + refreshToken rotation), player registration,
deposits, withdrawals, and balance checks.

Base URL example: https://example.com  (paths are /global/api/UserApi/...)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from app.config import settings

log = logging.getLogger("dogs_bet.agent_api")


class AgentAPIError(Exception):
    def __init__(self, message: str, code: int | None = None, raw: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.raw = raw


class AgentAPI:
    """Async client. One instance per process; tokens are kept in memory."""

    def __init__(self) -> None:
        self.base_url = (settings.agent_api_base_url or "").rstrip("/")
        self.username = settings.agent_username or ""
        self.password = settings.agent_password or ""
        self._access: str | None = None
        self._refresh: str | None = None
        self._access_expires_at: float = 0  # monotonic
        self.affiliate_id: str | None = None  # from JWT, used as parentId

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def _url(self, path: str) -> str:
        # path like "global/api/UserApi/signIn"
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _post(self, path: str, body: dict, *, auth: bool = True) -> dict:
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self._access:
                await self.sign_in()
            headers["Authorization"] = f"Bearer {self._access}"

        async with aiohttp.ClientSession() as session:
            async with session.post(self._url(path), json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401 or (isinstance(data, dict) and data.get("result") == "ex"):
                    # token expired — refresh once and retry
                    await self.refresh()
                    headers["Authorization"] = f"Bearer {self._access}"
                    async with session.post(self._url(path), json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp2:
                        data = await resp2.json(content_type=None)
                        if resp2.status >= 400:
                            raise AgentAPIError(self._err_msg(data), resp2.status, data)
                        return data
                if resp.status == 403:
                    raise AgentAPIError("No permission for this action", 403, data)
                if resp.status >= 400:
                    raise AgentAPIError(self._err_msg(data), resp.status, data)
                return data

    @staticmethod
    def _err_msg(data: Any) -> str:
        if not isinstance(data, dict):
            return str(data)
        notes = data.get("notification") or []
        if notes and isinstance(notes, list):
            first = notes[0]
            if isinstance(first, dict) and first.get("content"):
                return str(first["content"])
        if data.get("result") is False:
            return "Request failed"
        return str(data.get("result") or "Unknown error")

    async def sign_in(self) -> None:
        if not self.enabled:
            raise AgentAPIError("Agent API is not configured")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._url("global/api/UserApi/signIn"),
                json={"username": self.username, "password": self.password},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or not isinstance(data.get("result"), dict):
                    raise AgentAPIError(self._err_msg(data), resp.status, data)
                result = data["result"]
                self._access = result["accessToken"]
                self._refresh = result["refreshToken"]
                self._access_expires_at = time.monotonic() + 3500  # ~58 min
                # Extract affiliateId from JWT for parentId
                try:
                    import base64, json as _json
                    payload = self._access.split(".")[1]
                    payload += "=" * (4 - len(payload) % 4)
                    claims = _json.loads(base64.urlsafe_b64decode(payload))
                    self.affiliate_id = str(claims.get("affiliateId") or "")
                    log.info("Agent affiliateId: %s", self.affiliate_id)
                except Exception:
                    log.warning("Could not parse affiliateId from token")
                log.info("Agent API signed in as %s", self.username)

    async def refresh(self) -> None:
        if not self._refresh:
            await self.sign_in()
            return
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._url("global/api/UserApi/refreshToken"),
                json={"refreshToken": self._refresh},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or not isinstance(data.get("result"), dict):
                    # refresh failed → full sign-in
                    log.warning("Refresh failed, signing in again")
                    await self.sign_in()
                    return
                result = data["result"]
                self._access = result["accessToken"]
                self._refresh = result["refreshToken"]
                self._access_expires_at = time.monotonic() + 3500
                log.info("Agent API token refreshed")

    async def ensure_token(self) -> None:
        if not self._access or time.monotonic() > self._access_expires_at:
            if self._refresh:
                try:
                    await self.refresh()
                    return
                except Exception:
                    pass
            await self.sign_in()

    # ── Player endpoints ───────────────────────────────────────────────────

    async def register_player(self, login: str, password: str, email: str | None = None, parent_id: str | None = None) -> dict:
        """Register a new player under this agent. Returns dict with playerId if found."""
        await self.ensure_token()
        pid = parent_id or self.affiliate_id
        if not pid:
            raise AgentAPIError("Agent affiliateId missing — cannot register player")
        player: dict[str, Any] = {
            "login": login,
            "password": password,
            "email": email or f"{login}@dogsbet.local",
            "parentId": str(pid),
        }
        data = await self._post("global/api/UserApi/registerPlayer", {"player": player})
        if data.get("result") is False:
            raise AgentAPIError(self._err_msg(data), raw=data)
        # Fetch the new player to get real playerId
        try:
            players = await self.get_players()
            for p in players:
                if p.get("username") == login:
                    return {"playerId": p.get("playerId"), "username": login}
        except Exception:
            log.warning("Could not fetch playerId after register", exc_info=True)
        return {"playerId": None, "username": login, "result": data.get("result")}

    async def get_players(self) -> list[dict]:
        """List players under current agent."""
        await self.ensure_token()
        data = await self._post("global/api/UserApi/getPlayersForCurrentAgent", {})
        result = data.get("result") or {}
        return result.get("records") or []

    async def get_player_balance(self, player_id: str) -> list[dict]:
        """Return list of balance objects for the player."""
        await self.ensure_token()
        data = await self._post("global/api/UserApi/getPlayerBalanceById", {"playerId": str(player_id)})
        result = data.get("result")
        if result is False or result is None:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []

    async def deposit_to_player(
        self,
        player_id: str,
        amount: float,
        currency_code: str = "USD",
        currency: str = "USD",
        comment: str = "bot deposit",
        money_status: int = 5,
    ) -> dict:
        await self.ensure_token()
        body = {
            "amount": amount,
            "comment": comment,
            "playerId": str(player_id),
            "currencyCode": currency_code,
            "currency": currency,
            "moneyStatus": money_status,
        }
        data = await self._post("global/api/UserApi/depositToPlayer", body)
        if data.get("result") is False:
            raise AgentAPIError(self._err_msg(data), raw=data)
        return data.get("result") or {}

    async def withdraw_from_player(
        self,
        player_id: str,
        amount: float,
        currency_code: str = "USD",
        currency: str = "USD",
        comment: str = "bot withdraw",
        money_status: int = 5,
    ) -> dict:
        await self.ensure_token()
        body = {
            "amount": amount,
            "comment": comment,
            "playerId": str(player_id),
            "currencyCode": currency_code,
            "currency": currency,
            "moneyStatus": money_status,
        }
        data = await self._post("global/api/UserApi/withdrawFromPlayer", body)
        if data.get("result") is False:
            raise AgentAPIError(self._err_msg(data), raw=data)
        return data.get("result") or {}

    async def get_agent_wallets(self) -> list[dict]:
        await self.ensure_token()
        data = await self._post("global/api/UserApi/getAgentAllWallets", {})
        result = data.get("result")
        return result if isinstance(result, list) else []


# Singleton used by handlers
agent_api = AgentAPI()
