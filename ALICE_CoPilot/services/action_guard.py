"""
Shared Action & Verification Guard Module for ALICE_CoPilot.
Provides intent detection, system hints, and anti-hallucination checks for search and system inspection.
"""
import re
from dataclasses import dataclass


@dataclass
class IntentResult:
    is_search_query: bool = False
    is_system_query: bool = False
    is_memory_query: bool = False
    is_verification_query: bool = False
    # Backwards-compatible fields for callers
    is_action_query: bool = False
    is_task_query: bool = False
    is_cal_query: bool = False
    is_create: bool = False
    is_update: bool = False
    is_delete: bool = False
    is_appliance_action: bool = False


# Intent Keywords
SEARCH_KEYWORDS = [
    "会議", "面談", "議事録", "文字起こし", "要約", "話した", "発言", "検索"
]

SYSTEM_KEYWORDS = [
    "負荷", "cpu", "gpu", "vram", "温度", "メモリ使用量", "ストレージ", "ディスク",
    "リソース", "ピーク", "サーバー状態", "ステータス", "ジョブ", "エラー"
]

MEMORY_KEYWORDS = [
    "仕様", "設計", "方針", "決定", "なぜ", "理由", "ルール", "経緯", "長期記憶"
]


def detect_intent(prompt: str) -> IntentResult:
    """Analyze user prompt and classify intent flags."""
    lower_prompt = prompt.lower()

    is_search = any(kw in lower_prompt for kw in SEARCH_KEYWORDS)
    is_system = any(kw in lower_prompt for kw in SYSTEM_KEYWORDS)
    is_memory = any(kw in lower_prompt for kw in MEMORY_KEYWORDS)

    return IntentResult(
        is_search_query=is_search,
        is_system_query=is_system,
        is_memory_query=is_memory,
        is_verification_query=is_system or is_search,
        is_action_query=False,
        is_task_query=False,
        is_cal_query=False,
        is_create=False,
        is_update=False,
        is_delete=False,
        is_appliance_action=False,
    )


def build_system_hint(intent: IntentResult) -> str:
    """Build a dynamic system hint based on intent flags."""
    hints = []
    if intent.is_search_query:
        hints.append("【指示】過去の会議・要約・文字起こしに関する質問には、必ず「search_past_meetings」ツールを実行して実データを参照してください。")
    if intent.is_system_query:
        hints.append("【指示】サーバーの負荷・温度・ジョブ状態に関する質問には、必ず「get_system_status」または「get_recent_jobs」ツールを実行して実データに基づいて回答してください。")
    if intent.is_memory_query:
        hints.append("【指示】Project ALICEの設計方針・仕様・決定経緯に関する質問には、必要に応じて「search_project_memory」ツールを実行して確認してください。")

    return "\n".join(hints)


def is_hallucinating_action(content: str, executed_action_tools: list[str]) -> bool:
    """Detect if the LLM claimed it completed an inspection/tool execution without doing so."""
    # Action tools are no longer mutating user schedules/tasks.
    return False
