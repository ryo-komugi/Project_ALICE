"""
Tools registry and dispatcher for ALICE_CoPilot Tool Calling.
"""
import asyncio
import inspect
import json
import logging
from typing import Any, Callable
from tools.search_tools import search_past_meetings, search_project_memory
from tools.system_tools import get_system_status, get_recent_jobs

logger = logging.getLogger("ALICE_CoPilot.Tools")

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_past_meetings",
            "description": "過去の会議・面談の文字起こし、要約、議事録をキーワードで全文検索します。会議の内容、決定事項、誰と何を話したかを思い出す際に使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索キーワード（例: '面談', '伊藤さん', '予算', '進捗'）",
                    },
                    "module": {
                        "type": "string",
                        "enum": ["summary", "transcript", "minutes"],
                        "description": "対象成果物モジュール（省略可）",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_project_memory",
            "description": "Project ALICEの長期記憶（仕様・設計方針・決定事項・システム構成の変遷・理由）をキーワードで検索します。「なんでドメイン取ったんだっけ？」「Tailscale Funnelをやめた理由は？」「MFAの仕様はどうなってる？」「なぜCloudflare Tunnelにした？」「メモリのルール教えて」など、システムの設計や過去の決定経緯についての質問で使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索キーワード（例: 'ドメイン', 'Tailscale', 'Cloudflare', 'MFA', '認証'）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "取得する最大件数（デフォルト: 5）",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "ALICEサーバーのリソース負荷状況および本日のピーク値（GPU/VRAM使用量とピーク値、GPU温度とピーク値、CPU負荷/CPU温度とピーク値、RAM使用量とピーク値、ストレージ残量、Core/Ollamaサービス稼働状態）を取得します。現在の負荷や温度だけでなく、『今日のVRAMピーク量』『本日の最大負荷』『CPUやGPUの温度』などを質問された際にも使用します。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_jobs",
            "description": "ALICEが処理した最新の音声Job（文字起こし・要約・議事録）の一覧および成否ステータスを取得します。失敗したジョブのエラー原因調査にも使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "取得件数（デフォルト: 5）",
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["COMPLETED", "FAILED"],
                        "description": "特定のステータスのみに絞り込む（例: 'FAILED'で失敗ジョブのみ取得）",
                    },
                },
            },
        },
    },
]

TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "search_past_meetings": search_past_meetings,
    "search_project_memory": search_project_memory,
    "get_system_status": get_system_status,
    "get_recent_jobs": get_recent_jobs,
}


async def execute_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """
    Execute a registered tool safely and return JSON-serializable result.
    """
    if arguments is None:
        arguments = {}

    func = TOOL_FUNCTIONS.get(name)
    if not func:
        logger.warning(f"[Tools] Unknown tool called: {name}")
        return {"error": f"Unknown tool: '{name}'"}

    logger.info(f"[Tools] Executing: {name}({arguments})")

    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**arguments)
        else:
            result = await asyncio.to_thread(func, **arguments)

        logger.info(f"[Tools] Result from {name}: {str(result)[:200]}")
        return result
    except Exception as e:
        logger.error(f"[Tools] Error executing {name}: {e}", exc_info=True)
        return {"error": f"Tool '{name}' failed with error: {str(e)}"}
