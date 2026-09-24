"""
WebUI Chat Router & Proxy for Project_ALICE Cockpit.
Bridges WebUI client requests to ALICE_CoPilot internal API (port 8005).
Supports real-time SSE streaming, status querying, and session history.
"""
import json
import asyncio
from typing import AsyncGenerator
import aiohttp
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/chat", tags=["chat"])

INTERNAL_COPILOT_URL = "http://127.0.0.1:8005"


class ChatMessageRequest(BaseModel):
    prompt: str
    mode: str = "assistant"
    session_id: str | None = None


class ChatClearRequest(BaseModel):
    mode: str = "assistant"
    session_id: str | None = None


import time

_last_chat_status: dict | None = None
_last_chat_status_time: float = 0.0


@router.get("/status")
async def get_chat_status():
    """Fetches real-time status of Ollama (VRAM load) and Antigravity from CoPilot server."""
    global _last_chat_status, _last_chat_status_time
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.5)) as session:
            async with session.get(f"{INTERNAL_COPILOT_URL}/api/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "antigravity" in data and isinstance(data["antigravity"], dict):
                        if "model" not in data["antigravity"]:
                            data["antigravity"]["model"] = data["antigravity"].get("selected_model", "qwen3.5:9b")
                    _last_chat_status = data
                    _last_chat_status_time = time.time()
                    return data
    except Exception:
        pass

    # If momentary timeout occurs while CoPilot is busy executing tools (e.g. Google Calendar API), return last healthy status
    if _last_chat_status and (time.time() - _last_chat_status_time) < 15.0:
        return _last_chat_status

    # Fallback if internal CoPilot server is genuinely not reachable
    return JSONResponse(
        status_code=200,
        content={
            "status": "offline",
            "error": "CoPilot internal API is unreachable",
            "ollama": {
                "online": False,
                "model": "qwen3.5:9b",
                "vram_loaded": False,
                "expires_at": None,
                "size_vram_mb": 0,
            },
            "antigravity": {
                "active": False,
                "current_tool": "",
                "model": "qwen3.5:9b",
                "selected_model": "qwen3.5:9b",
                "last_run": None,
            },
        },
    )


@router.post("/message")
async def send_chat_message(payload: ChatMessageRequest):
    """Proxies chat prompt to CoPilot server and streams SSE back to WebUI."""
    session_id = payload.session_id or f"web_{payload.mode}"
    req_body = {
        "prompt": payload.prompt,
        "mode": payload.mode,
        "session_id": session_id,
    }

    async def sse_stream_generator() -> AsyncGenerator[str, None]:
        try:
            timeout = aiohttp.ClientTimeout(total=300, sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{INTERNAL_COPILOT_URL}/api/chat",
                    json=req_body,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        yield f"data: {json.dumps({'type': 'error', 'message': f'CoPilot server error: {resp.status} - {err_text}'}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'stream_end'}, ensure_ascii=False)}\n\n"
                        return

                    async for line in resp.content:
                        if line:
                            decoded = line.decode("utf-8", errors="replace")
                            yield decoded

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'通信中継エラー: {str(e)}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse_stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
async def get_chat_history(mode: str = "assistant", limit: int = 30):
    """Fetches chat history for the specified mode."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.get(
                f"{INTERNAL_COPILOT_URL}/api/history",
                params={"mode": mode, "limit": str(limit)},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        return JSONResponse(status_code=200, content={"session_id": f"web_{mode}", "messages": [], "error": str(e)})

    return JSONResponse(status_code=200, content={"session_id": f"web_{mode}", "messages": []})


@router.post("/clear")
async def clear_chat_history(payload: ChatClearRequest):
    """Clears chat history for the specified mode."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.post(
                f"{INTERNAL_COPILOT_URL}/api/clear",
                json={"mode": payload.mode, "session_id": payload.session_id},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    return JSONResponse(status_code=200, content={"status": "cleared"})


class AntigravityModelRequest(BaseModel):
    model_id: str


@router.get("/antigravity/settings")
async def get_antigravity_settings():
    """Fetches Antigravity settings, supported models, and quota limits."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.get(f"{INTERNAL_COPILOT_URL}/api/antigravity/settings") as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return JSONResponse(status_code=500, content={"status": "error"})


@router.post("/antigravity/settings")
async def update_antigravity_settings(payload: AntigravityModelRequest):
    """Updates selected Antigravity model."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
            async with session.post(
                f"{INTERNAL_COPILOT_URL}/api/antigravity/settings",
                json={"model_id": payload.model_id},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    return JSONResponse(status_code=500, content={"status": "error"})
