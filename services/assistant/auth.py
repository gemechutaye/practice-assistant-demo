"""Validate identity with Supabase before resolving a fictional office role."""

import hashlib
import threading
import time

import httpx
import jwt

from .config import Settings
from .domain import DomainError


class Identity:
    def __init__(self, config: Settings):
        self.config = config
        self._cache = {}
        self._lock = threading.Lock()

    def user_id(self, authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise DomainError("Sign in to open your demonstration workspace.", "unauthorized", 401)
        token = authorization[7:]
        if len(token) > 16000:
            raise DomainError("The session token is invalid.", "unauthorized", 401)
        if self.config.environment == "local" and self.config.local_auth_secret:
            try:
                payload = jwt.decode(
                    token,
                    self.config.local_auth_secret,
                    algorithms=["HS256"],
                    issuer="practice-assistant-local",
                    audience="practice-assistant",
                )
                return payload["sub"]
            except (jwt.PyJWTError, KeyError):
                pass
        if not self.config.supabase_url or not self.config.supabase_anon_key:
            raise DomainError(
                "Supabase identity is not configured on this deployment.", "auth_unavailable", 503
            )
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            cached = self._cache.get(digest)
            if cached and cached[0] > time.time():
                return cached[1]
        try:
            response = httpx.get(
                self.config.supabase_url + "/auth/v1/user",
                headers={"Authorization": authorization, "apikey": self.config.supabase_anon_key},
                timeout=10,
            )
        except httpx.RequestError:
            raise DomainError(
                "The identity service is temporarily unavailable.", "auth_unavailable", 503
            ) from None
        if response.status_code != 200:
            raise DomainError("Your session expired. Sign in again.", "unauthorized", 401)
        user = response.json()
        if not isinstance(user.get("id"), str):
            raise DomainError("The identity service returned no user.", "unauthorized", 401)
        with self._lock:
            if len(self._cache) > 1000:
                self._cache.clear()
            self._cache[digest] = (time.time() + 15, user["id"])
        return user["id"]
