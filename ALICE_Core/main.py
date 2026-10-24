from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from infrastructure.logger import initialize_logger

from portal.download import router as download_router
from portal.viewer import router as viewer_router
from portal.admin import router as admin_router
from portal.browser_minutes import router as browser_minutes_router
from portal.rabbit_hole import router as rabbit_hole_router
from portal.auth import AdminAuthMiddleware
from hub.container import job_service

initialize_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # サーバー再起動時のジョブリカバリ (RUNNING クローズ / QUEUED 再投入)
    try:
        aborted, requeued = job_service.recover_interrupted_jobs()
        if aborted > 0 or requeued > 0:
            print(f"[Main] Recovered from restart: {aborted} aborted, {requeued} requeued")
    except Exception as e:
        print(f"[Main] Error during startup recovery: {e}")

    job_service.start()
    print("[Main] Hub JobService / CoreWorker started")

    yield
    job_service.stop()
    print("[Main] Hub JobService / CoreWorker shutdown completed")


# ==============================================================================
# Dynamic Portal Roots (populated during Navigator auto-mount)
# ==============================================================================
dynamic_portal_roots = ["/rabbit-hole"]

app = FastAPI(
    title="ALICE Core",
    version="0.2.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_https_for_browser_portals(request: Request, call_next):
    client_ip = request.client.host if request.client else ""
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return await call_next(request)
    path = request.url.path
    is_browser_portal = any(path == root or path.startswith(root + "/") for root in dynamic_portal_roots)
    if is_browser_portal and request.url.scheme != "https":
        return JSONResponse(
            status_code=400,
            content={"detail": "HTTPS is required"},
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )
    return await call_next(request)

# Admin認証ミドルウェア (/admin配下をセッション保護)
app.add_middleware(AdminAuthMiddleware)


app.include_router(download_router)
app.include_router(viewer_router)
app.include_router(admin_router, prefix="/admin")
app.include_router(browser_minutes_router)
app.include_router(rabbit_hole_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
Path(config.DIR_SHARE).mkdir(parents=True, exist_ok=True)
app.mount("/share", StaticFiles(directory=config.DIR_SHARE), name="share")

# ==============================================================================
# ALICE Navigators Plugin Auto-Mount
# ==============================================================================
NAVIGATORS_DIR = Path(__file__).resolve().parents[1] / "ALICE_Navigators"

def _create_navigator_handler(html_file: Path, csp: str):
    async def _handler():
        return FileResponse(
            html_file,
            headers={
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": csp,
            },
        )
    return _handler

if NAVIGATORS_DIR.is_dir():
    for nav_dir in sorted(NAVIGATORS_DIR.iterdir()):
        if not nav_dir.is_dir():
            continue
        slug = nav_dir.name.lower()
        if slug == "rabbithole":
            # RabbitHole assets mount
            images_dir = nav_dir / "images"
            if images_dir.is_dir():
                app.mount("/rabbit-hole/assets", StaticFiles(directory=images_dir), name="rabbit-hole-assets")
            continue

        manifest_file = nav_dir / "navigator.json"
        index_file = nav_dir / "index.html"
        images_dir = nav_dir / "images"

        if manifest_file.exists() and index_file.exists():
            portal_route = f"/{slug}"
            dynamic_portal_roots.append(portal_route)

            # Mount images asset directory
            if images_dir.is_dir():
                app.mount(f"/{slug}/assets", StaticFiles(directory=images_dir), name=f"{slug}-assets")

            # Content Security Policy (allow blob: for recording audio/minutes download)
            csp = (
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; "
                "connect-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'"
            )

            handler = _create_navigator_handler(index_file, csp)
            app.add_api_route(f"/{slug}", handler, methods=["GET"], include_in_schema=False)
            app.add_api_route(f"/{slug}/", handler, methods=["GET"], include_in_schema=False)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root(request: Request):
    host = (request.headers.get("host") or "").lower()
    if host.startswith("admin."):
        return RedirectResponse(url="/admin", status_code=303)
    return {"status": "ok", "service": "ALICE Core"}
