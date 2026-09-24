import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
from core.logger import initialize_logger
from core.ip_monitor import ip_monitor_loop

# New Layer Imports
from gateway.webhook import router as webhook_router
from portal.download import router as download_router
from portal.viewer import router as viewer_router
from portal.admin import router as admin_router
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

    ip_task = asyncio.create_task(ip_monitor_loop(interval_seconds=1800))
    print("[Main] GlobalIPMonitor loop started")

    yield

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

# Admin認証ミドルウェア (/admin配下をセッション保護)
app.add_middleware(AdminAuthMiddleware)

app.include_router(webhook_router)
app.include_router(download_router)
app.include_router(viewer_router)
app.include_router(admin_router, prefix="/admin")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/share", StaticFiles(directory=config.DIR_SHARE), name="share")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root(request: Request):
    host = (request.headers.get("host") or "").lower()
    if host.startswith("admin."):
        return RedirectResponse(url="/admin", status_code=303)
    return {"status": "ok", "service": "ALICE Core"}
