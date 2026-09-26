"""
ALICE_Core Admin Authentication Middleware.
Features:
- Cloudflare Zero Trust (Access) auto-pass for admin.project-alice.net.
- Conditional Access: Automatic free-pass for Tailscale (tailnet) & local LAN connections.
- Persistent session cookie support (180 days for PWA / trusted devices).
- 404 Not Found block for any /admin attempt on the public apex domain (project-alice.net).
"""
import base64
import hmac
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import config

logger = logging.getLogger("ALICE_Core.AdminAuth")

COOKIE_NAME = "admin_session"
DEFAULT_SESSION_DURATION = 180 * 86400  # 180 days

# Trusted IP Networks (Tailscale, Private LAN, Loopback)
TRUSTED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),       # Tailscale IPv4 CGNAT range
    ipaddress.ip_network("fd7a:115c:a1e0::/48"), # Tailscale IPv6 ULA range
]


def get_client_ip(request: Request) -> str:
    """Extract effective client IP."""
    cf_ip = request.headers.get("cf-connecting-ip") or request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        first_ip = x_forwarded.split(",")[0].strip()
        return first_ip

    if request.client and request.client.host:
        return request.client.host.strip()

    return "127.0.0.1"


def is_trusted_network(request: Request) -> bool:
    """
    Determine if the request originates from a trusted network
    (Tailscale tailnet, local LAN, or loopback).
    """
    client_ip_str = get_client_ip(request)
    try:
        ip_obj = ipaddress.ip_address(client_ip_str)
        for net in TRUSTED_NETWORKS:
            if ip_obj in net:
                return True
    except ValueError:
        pass

    return False


def _get_signing_key() -> bytes:
    secret = (
        getattr(config, "ADMIN_SECRET_KEY", None)
        or os.getenv("ADMIN_SECRET_KEY")
        or getattr(config, "SECRET_KEY", None)
        or os.getenv("SECRET_KEY")
    )
    if not secret:
        secret = "alice_in_cyber_wonderland_fallback_secret_key_2026"
    return secret.encode("utf-8")


def create_session_token(username: str, duration: int = DEFAULT_SESSION_DURATION) -> str:
    """Generate an HMAC-signed session token with expiration timestamp."""
    exp = int(time.time()) + duration
    payload = {"sub": username, "exp": exp}
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")

    signature = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> Optional[str]:
    """Verify HMAC signature and expiration of session token. Returns username if valid."""
    if not token or "." not in token:
        return None

    parts = token.split(".", 1)
    if len(parts) != 2:
        return None

    payload_b64, sig_b64 = parts
    expected_sig = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")

    if not secrets.compare_digest(sig_b64, expected_sig_b64):
        return None

    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None

        return payload.get("sub")
    except Exception as e:
        logger.debug(f"[AdminAuth] Failed to decode session token: {e}")
        return None


def set_session_cookie(response: Response, username: str, remember_me: bool = True):
    """Attach 180-day persistent session cookie to response."""
    duration = DEFAULT_SESSION_DURATION
    token = create_session_token(username, duration)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=duration,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_session_cookie(response: Response):
    """Remove session cookie from response."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware intercepting /admin routes.
    1. Blocks any /admin access on the public apex domain (project-alice.net) with 404 Not Found.
    2. Allows public assets (/admin/sw.js, /admin/api/client-error).
    3. Validates existing HMAC session cookies.
    4. Auto-authenticates and grants 180-day session cookies for:
       - Cloudflare Zero Trust verified access (admin.project-alice.net or CF header)
       - Trusted internal networks (Tailscale tailnet, LAN, localhost)
    5. Rejects any other unauthenticated external requests with 403/401.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only protect /admin and its subpaths
        if not (path == "/admin" or path.startswith("/admin/")):
            return await call_next(request)

        # 1. Block direct /admin access on public apex domain (project-alice.net) entirely
        host = (request.headers.get("host") or "").lower()
        if host == "project-alice.net" or host.startswith("project-alice.net:"):
            logger.warning(f"[AdminAuth] 404 Blocked: Direct /admin access on public domain from {get_client_ip(request)}")
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        # Publicly allowed endpoints under /admin (PWA service worker, error logging)
        if path in ("/admin/sw.js", "/admin/api/client-error"):
            return await call_next(request)

        # 2. Check Session Cookie
        token = request.cookies.get(COOKIE_NAME)
        user = verify_session_token(token) if token else None
        if user:
            request.state.admin_user = user
            return await call_next(request)

        # 3. Conditional Access: Cloudflare Zero Trust / Tailscale / Local LAN Auto-pass
        cf_email = (
            request.headers.get("cf-access-authenticated-user-email")
            or request.headers.get("CF-Access-Authenticated-User-Email")
        )
        is_cf_access = host.startswith("admin.project-alice.net") or bool(cf_email)
        is_trusted = is_trusted_network(request)

        if is_cf_access or is_trusted:
            admin_user = getattr(config, "ADMIN_USERNAME", "alice")
            request.state.admin_user = admin_user
            source = "Cloudflare Zero Trust" if is_cf_access else f"Trusted network ({get_client_ip(request)})"
            logger.debug(f"[AdminAuth] Auto-pass granted via {source} for {admin_user}")

            response = await call_next(request)
            if not token and isinstance(response, Response):
                set_session_cookie(response, admin_user, remember_me=True)
            return response

        # 4. Unauthenticated External Handling (No Zero Trust, No Trusted Network, No Cookie)
        if path.startswith("/admin/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized. Access must be via admin.project-alice.net or tailnet."},
            )

        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden. Access must be via admin.project-alice.net or tailnet."},
        )
