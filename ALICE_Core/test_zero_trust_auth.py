"""
Unit and Integration Tests for Admin Authentication Middleware.
Verifies Cloudflare Zero Trust (Access), Tailscale / LAN bypass, and Apex 404 block.
Uses direct ASGI / Starlette dispatch testing compatible with core_env without external packages.
"""
import pytest
from starlette.requests import Request
from starlette.responses import Response

import config
from core.admin_auth import (
    COOKIE_NAME,
    DEFAULT_SESSION_DURATION,
    AdminAuthMiddleware,
    create_session_token,
    verify_session_token,
    set_session_cookie,
    clear_session_cookie,
    is_trusted_network,
    get_client_ip,
)


@pytest.fixture(autouse=True)
def setup_admin_env(monkeypatch):
    """Ensure consistent test configuration."""
    monkeypatch.setattr(config, "ADMIN_SECRET_KEY", "super_secret_test_key_for_hmac_123456789")
    monkeypatch.setattr(config, "ADMIN_USERNAME", "alice")


def make_request(path: str, method: str = "GET", headers: dict = None, cookies: dict = None) -> Request:
    """Helper to build a mock Starlette Request from path and headers."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    if cookies:
        cookie_parts = [f"{k}={v}" for k, v in cookies.items()]
        raw_headers.append((b"cookie", "; ".join(cookie_parts).encode("latin-1")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


async def dummy_call_next(request: Request) -> Response:
    """Simulated endpoint returning 200 OK."""
    return Response(content='{"status": "ok"}', media_type="application/json", status_code=200)


def test_token_creation_and_verification():
    """Verify HMAC session token can be created and verified."""
    token = create_session_token("alice", duration=3600)
    assert token is not None
    assert "." in token

    # Valid token verification
    username = verify_session_token(token)
    assert username == "alice"

    # Tampered token verification fails
    tampered_token = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert verify_session_token(tampered_token) is None

    # Invalid format fails
    assert verify_session_token("invalid_token_without_dot") is None
    assert verify_session_token("") is None


def test_session_cookie_helpers():
    """Verify set_session_cookie and clear_session_cookie headers."""
    resp = Response()
    set_session_cookie(resp, "alice", remember_me=True)
    cookie_header = resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in cookie_header
    assert f"Max-Age={DEFAULT_SESSION_DURATION}" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "samesite=lax" in cookie_header.lower()

    # Test clear_session_cookie
    resp_clear = Response()
    clear_session_cookie(resp_clear)
    clear_header = resp_clear.headers.get("set-cookie", "")
    assert COOKIE_NAME in clear_header
    assert "Max-Age=0" in clear_header


@pytest.mark.anyio
async def test_admin_subdomain_auto_pass():
    """Requests on admin.project-alice.net bypass auth and receive session cookie."""
    middleware = AdminAuthMiddleware(app=None)
    req = make_request(
        path="/admin",
        headers={
            "Host": "admin.project-alice.net",
            "X-Forwarded-For": "203.0.113.50",  # Public untrusted IP
        }
    )
    resp = await middleware.dispatch(req, dummy_call_next)
    assert resp.status_code == 200
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")
    assert req.state.admin_user == "alice"


@pytest.mark.anyio
async def test_apex_domain_admin_returns_404():
    """Direct /admin access on project-alice.net is sealed and returns 404."""
    middleware = AdminAuthMiddleware(app=None)
    req = make_request(
        path="/admin",
        headers={
            "Host": "project-alice.net",
            "X-Forwarded-For": "203.0.113.50",
        }
    )
    resp = await middleware.dispatch(req, dummy_call_next)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_tailscale_ip_bypass():
    """Tailscale CGNAT (100.64.0.0/10) auto-passes and receives session cookie."""
    middleware = AdminAuthMiddleware(app=None)
    req = make_request(
        path="/admin/api/status",
        headers={
            "Host": "alice-server:8000",
            "X-Forwarded-For": "100.85.120.45",
        }
    )
    resp = await middleware.dispatch(req, dummy_call_next)
    assert resp.status_code == 200
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")
    assert req.state.admin_user == "alice"


@pytest.mark.anyio
async def test_local_lan_ip_bypass():
    """Private LAN (192.168.x.x, 10.x.x.x) auto-passes."""
    middleware = AdminAuthMiddleware(app=None)
    req = make_request(
        path="/admin",
        headers={
            "Host": "192.168.1.50:8000",
            "X-Forwarded-For": "192.168.1.100",
        }
    )
    resp = await middleware.dispatch(req, dummy_call_next)
    assert resp.status_code == 200
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")


@pytest.mark.anyio
async def test_public_and_service_worker_endpoints():
    """Non-admin paths and /admin/sw.js pass through unconditionally."""
    middleware = AdminAuthMiddleware(app=None)

    # /health (non-admin path)
    req_health = make_request(path="/health", headers={"Host": "project-alice.net"})
    resp_health = await middleware.dispatch(req_health, dummy_call_next)
    assert resp_health.status_code == 200

    # /admin/sw.js
    req_sw = make_request(
        path="/admin/sw.js",
        headers={
            "Host": "some-other-domain.com",
            "X-Forwarded-For": "203.0.113.50",
        }
    )
    resp_sw = await middleware.dispatch(req_sw, dummy_call_next)
    assert resp_sw.status_code == 200


@pytest.mark.anyio
async def test_cookie_authenticated_request():
    """Client from untrusted IP with valid cookie is allowed."""
    middleware = AdminAuthMiddleware(app=None)
    valid_token = create_session_token("alice", duration=3600)
    req = make_request(
        path="/admin/api/metrics",
        headers={
            "Host": "random.domain.com",
            "X-Forwarded-For": "203.0.113.50",
        },
        cookies={COOKIE_NAME: valid_token}
    )
    resp = await middleware.dispatch(req, dummy_call_next)
    assert resp.status_code == 200
    assert req.state.admin_user == "alice"


@pytest.mark.anyio
async def test_unauthenticated_public_ip_rejected():
    """Untrusted public IP without Zero Trust header or cookie is rejected."""
    middleware = AdminAuthMiddleware(app=None)

    # Web page gets 403 Forbidden
    req_page = make_request(
        path="/admin",
        headers={
            "Host": "random.domain.com",
            "X-Forwarded-For": "203.0.113.50",
        }
    )
    resp_page = await middleware.dispatch(req_page, dummy_call_next)
    assert resp_page.status_code == 403

    # API gets 401 Unauthorized
    req_api = make_request(
        path="/admin/api/system",
        headers={
            "Host": "random.domain.com",
            "X-Forwarded-For": "203.0.113.50",
        }
    )
    resp_api = await middleware.dispatch(req_api, dummy_call_next)
    assert resp_api.status_code == 401
