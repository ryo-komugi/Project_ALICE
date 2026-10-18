import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

from server import handle_chat


@pytest.mark.anyio
async def test_handle_chat_success():
    """Verify standard chat stream writes SSE events and stream_end."""
    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={
        "prompt": "こんにちは",
        "mode": "assistant",
        "session_id": "test_session",
    })

    events = [
        {"type": "delta", "content": "テスト"},
        {"type": "delta", "content": "応答"},
    ]

    async def sample_generator(*args, **kwargs):
        for ev in events:
            yield ev

    written_data = []

    with patch("server.stream_assistant", side_effect=sample_generator):
        with patch.object(web.StreamResponse, "prepare", new_callable=AsyncMock):
            async def fake_write(data):
                written_data.append(data.decode("utf-8"))

            with patch.object(web.StreamResponse, "write", side_effect=fake_write):
                resp = await handle_chat(mock_request)
                assert resp.status == 200

    assert any('"content": "テスト"' in d for d in written_data)
    assert any('"content": "応答"' in d for d in written_data)
    assert any('"type": "stream_end"' in d for d in written_data)


@pytest.mark.anyio
async def test_handle_chat_client_disconnect_no_crash():
    """Verify that ClientConnectionResetError during streaming is handled gracefully without raising."""
    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={
        "prompt": "こんにちは",
        "mode": "assistant",
        "session_id": "test_session",
    })

    call_count = 0

    async def fake_generator(*args, **kwargs):
        yield {"type": "delta", "content": "1"}
        yield {"type": "delta", "content": "2"}
        yield {"type": "delta", "content": "3"}

    async def fake_write(data):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise ClientConnectionResetError("Cannot write to closing transport")

    with patch("server.stream_assistant", side_effect=fake_generator):
        with patch.object(web.StreamResponse, "prepare", new_callable=AsyncMock):
            with patch.object(web.StreamResponse, "write", side_effect=fake_write):
                # Should NOT raise ClientConnectionResetError
                resp = await handle_chat(mock_request)
                assert resp.status == 200
