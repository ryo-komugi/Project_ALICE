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
from portal.home import router as home_router
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


app = FastAPI(
    title="ALICE Core",
    version="0.2.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_https_for_browser_portals(request: Request, call_next):
    path = request.url.path
    is_browser_portal = any(path == root or path.startswith(root + "/") for root in ("/home", "/noel", "/kureha"))
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

# LINE Gateway Adapter (将来の脱LINE・別アダプタ移行を考慮したオプショナルマウント)
if config.LINE_ENABLED:
    from gateway.webhook import router as webhook_router
    app.include_router(webhook_router)
    print("[Main] LINE Gateway Adapter: ENABLED (/webhook)")
else:
    print("[Main] LINE Gateway Adapter: DISABLED (missing CHANNEL_SECRET/CHANNEL_ACCESS_TOKEN)")

app.include_router(download_router)
app.include_router(viewer_router)
app.include_router(admin_router, prefix="/admin")
app.include_router(browser_minutes_router)
app.include_router(home_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
Path(config.DIR_SHARE).mkdir(parents=True, exist_ok=True)
app.mount("/share", StaticFiles(directory=config.DIR_SHARE), name="share")
NOEL_DIR = Path(__file__).resolve().parents[1] / "ALICE_Navigators" / "Noel"
app.mount("/noel/assets", StaticFiles(directory=NOEL_DIR / "images"), name="noel-assets")
HOME_DIR = Path(__file__).resolve().parents[1] / "ALICE_Navigators" / "Home"
app.mount("/home/assets", StaticFiles(directory=HOME_DIR / "images"), name="home-assets")
KUREHA_DIR = Path(__file__).resolve().parents[1] / "ALICE_Navigators" / "Kureha"
app.mount("/kureha/assets", StaticFiles(directory=KUREHA_DIR / "images"), name="kureha-assets")


@app.get("/kureha", include_in_schema=False)
@app.get("/kureha/", include_in_schema=False)
async def kureha_page():
    return FileResponse(
        KUREHA_DIR / "index.html",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; connect-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/noel", include_in_schema=False)
@app.get("/noel/", include_in_schema=False)
async def noel_page():
    return FileResponse(
        NOEL_DIR / "index.html",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        },
    )


@app.get("/")
async def root(request: Request):
    host = (request.headers.get("host") or "").lower()
    if host.startswith("admin."):
        return RedirectResponse(url="/admin", status_code=303)
    return {"status": "ok", "service": "ALICE Core"}
