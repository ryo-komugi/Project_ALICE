"""
Internal API Server for ALICE_CoPilot.
Provides local HTTP/SSE interface (port 8005) for ALICE_Core WebUI integration.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import aiohttp
from aiohttp import web

# Ensure project root is in sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import config
from memory.short_term import get_recent_messages, initialize_database
from services.assistant_service import stream_assistant
from services.dev_copilot_service import ANTIGRAVITY_STATE, stream_copilot

HOST = "127.0.0.1"
PORT = 8005


async def handle_status(request: web.Request) -> web.Response:
    """Returns real-time status of Ollama (with /api/ps VRAM status) and Antigravity."""
    ollama_info = {
        "online": False,
        "model": config.OLLAMA_MODEL,
        "vram_loaded": False,
        "expires_at": None,
        "size_vram_mb": 0,
    }

    # 1. Check Ollama running models via /api/ps
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.get("http://localhost:11434/api/ps") as resp:
                if resp.status == 200:
                    ollama_info["online"] = True
                    data = await resp.json()
                    models = data.get("models", [])
                    for m in models:
                        # Check if configured model or prefix matches
                        m_name = m.get("name", "")
                        if config.OLLAMA_MODEL in m_name or m_name.startswith(config.OLLAMA_MODEL.split(":")[0]):
                            ollama_info["vram_loaded"] = True
                            ollama_info["expires_at"] = m.get("expires_at")
                            ollama_info["size_vram_mb"] = round(m.get("size_vram", 0) / (1024 * 1024), 1)
                            break
    except Exception as e:
        ollama_info["online"] = False

    from services.antigravity_manager import load_antigravity_settings, update_selected_model, SUPPORTED_MODELS

    # 2. Antigravity status & quota
    ag_settings = load_antigravity_settings()
    antigravity_info = {
        "active": ANTIGRAVITY_STATE.get("active", False),
        "current_tool": ANTIGRAVITY_STATE.get("current_tool", ""),
        "selected_model": ag_settings.get("selected_model", "Gemini 3.8 Flash (High)"),
        "models": SUPPORTED_MODELS,
        "quota": {
            "five_hour_limit": ag_settings.get("five_hour_limit", {}),
            "weekly_limit": ag_settings.get("weekly_limit", {}),
        },
        "last_run": ANTIGRAVITY_STATE.get("last_run"),
    }

    return web.json_response({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama": ollama_info,
        "antigravity": antigravity_info,
    })


async def handle_get_antigravity_settings(request: web.Request) -> web.Response:
    from services.antigravity_manager import load_antigravity_settings, SUPPORTED_MODELS
    settings = load_antigravity_settings()
    return web.json_response({
        "status": "ok",
        "settings": settings,
        "supported_models": SUPPORTED_MODELS,
    })


async def handle_post_antigravity_settings(request: web.Request) -> web.Response:
    from services.antigravity_manager import update_selected_model, SUPPORTED_MODELS
    try:
        body = await request.json()
        model_id = body.get("model_id")
        if not model_id:
            return web.json_response({"status": "error", "message": "model_id is required"}, status=400)
        updated = update_selected_model(model_id)
        return web.json_response({"status": "ok", "settings": updated})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_chat(request: web.Request) -> web.StreamResponse:
    """Handles chat stream via Server-Sent Events (SSE)."""
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON body")

    prompt = body.get("prompt", "").strip()
    mode = body.get("mode", "assistant").lower()
    session_id = body.get("session_id", f"web_{mode}")

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)

    async def sse_send(data_dict: dict):
        msg = f"data: {json.dumps(data_dict, ensure_ascii=False)}\n\n"
        await response.write(msg.encode("utf-8"))

    try:
        if mode == "copilot":
            generator = stream_copilot(prompt, session_id=session_id)
        else:
            generator = stream_assistant(prompt, session_id=session_id)

        async for event in generator:
            await sse_send(event)

    except Exception as e:
        await sse_send({"type": "error", "message": f"ストリーミング処理例外: {str(e)}"})
    finally:
        await sse_send({"type": "stream_end"})

    return response


async def handle_history(request: web.Request) -> web.Response:
    """Returns conversation history for a given session."""
    mode = request.query.get("mode", "assistant")
    session_id = request.query.get("session_id", f"web_{mode}")
    limit = int(request.query.get("limit", "30"))

    rows = get_recent_messages(channel_id=session_id, limit=limit)
    # rows is list of (role, content) in chronological order
    history = [{"role": r, "content": c} for r, c in rows]
    return web.json_response({"session_id": session_id, "messages": history})


async def handle_clear(request: web.Request) -> web.Response:
    """Clears history for a session by generating a new session ID timestamp or resetting."""
    try:
        body = await request.json()
        mode = body.get("mode", "assistant")
        session_id = body.get("session_id", f"web_{mode}")
    except Exception:
        mode = "assistant"
        session_id = "web_assistant"

    # Save system reset marker
    from memory.short_term import save_message
    save_message(
        timestamp=datetime.now(timezone.utc).isoformat(),
        channel_id=session_id,
        user_id="system",
        role="system",
        content="[Session Cleared]",
    )
    return web.json_response({"status": "cleared", "session_id": session_id})


def create_app() -> web.Application:
    initialize_database()
    app = web.Application()
    app.router.add_get("/api/status", handle_status)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/history", handle_history)
    app.router.add_post("/api/clear", handle_clear)
    app.router.add_get("/api/antigravity/settings", handle_get_antigravity_settings)
    app.router.add_post("/api/antigravity/settings", handle_post_antigravity_settings)
    return app


if __name__ == "__main__":
    app = create_app()
    print(f"Starting ALICE_CoPilot Internal API on http://{HOST}:{PORT}...")
    web.run_app(app, host=HOST, port=PORT)
