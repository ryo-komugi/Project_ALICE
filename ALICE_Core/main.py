import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from infrastructure.logger import initialize_logger
from infrastructure.ip_monitor import ip_monitor_loop

# New Layer Imports
from gateway.webhook import router as webhook_router
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

    ip_task = None
    if os.getenv("ALICE_ENABLE_IP_MONITOR", "true").strip().lower() not in {"0", "false", "no"}:
        ip_task = asyncio.create_task(ip_monitor_loop(interval_seconds=1800))
        print("[Main] GlobalIPMonitor loop started")

    yield

    if ip_task is not None:
        ip_task.cancel()
        try:
            await ip_task
        except asyncio.CancelledError:
            pass

    job_service.stop()
    print("[Main] Hub JobService / CoreWorker shutdown completed")


app = FastAPI(
    title="ALICE Core",
    version="0.2.0",
    lifespan=lifespan
)


@app.middleware("http")
async def require_https_for_browser_portals(request: Request, call_next):
    path = request.url.path
    is_browser_portal = path == "/home" or path.startswith("/home/") or path == "/noel" or path.startswith("/noel/")
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

app.include_router(webhook_router)
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
