"""License verification middleware for local Auto Capcut Pro mode.

Verifies Bearer token against be.4mmo.top with a 5-minute in-memory cache.
Skips /health so the desktop app can probe readiness without a key.
"""

import time
import threading
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import httpx
import config
from src.utils.logger import logger

# Thread-safe in-memory cache: { license_key: (valid: bool, expires_at: float) }
_cache: dict[str, tuple[bool, float]] = {}
_cache_lock = threading.Lock()

# Paths that do not require a license key
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


def _verify_remote(license_key: str) -> bool:
    """Call be.4mmo.top to verify the key. Returns True if valid."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                config.LICENSE_VERIFY_URL,
                json={"license_key": license_key},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return bool(data.get("valid", False))
            logger.warning("License verify returned HTTP %d", resp.status_code)
            return False
    except Exception as exc:
        logger.error("License verify error: %s", exc)
        return False


def _is_valid(license_key: str) -> bool:
    """Return True if the key is valid (cached or freshly verified)."""
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(license_key)
        if entry is not None:
            valid, expires_at = entry
            if now < expires_at:
                return valid
    # Cache miss or expired — call remote
    valid = _verify_remote(license_key)
    with _cache_lock:
        _cache[license_key] = (valid, now + config.LICENSE_CACHE_TTL)
    return valid


class LicenseMiddleware(BaseHTTPMiddleware):
    """Require a valid Bearer license key for all routes except _SKIP_PATHS."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"code": 401, "message": "Authorization header missing or invalid"},
            )

        license_key = auth[len("Bearer "):].strip()
        if not license_key or not _is_valid(license_key):
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "License key invalid or expired"},
            )

        return await call_next(request)
