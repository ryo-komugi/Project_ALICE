"""
Shared Action & Verification Guard Module for ALICE_CoPilot (dev).
Provides intent detection, system hints, and anti-hallucination checks.
Excludes environment-specific hardware devices (e.g. SwitchBot).
"""
import re
from dataclasses import dataclass


@dataclass
class IntentResult:
    is_action_query: bool = False
    is_task_query: bool = False
    is_cal_query: bool = False
    is_verification_query: bool = False
    is_past_query: bool = False
    is_create: bool = False
    is_update: bool = False
    is_delete: bool = False
    is_appliance_action: bool = False  # Compatibility stub for dev


# Intent Keywords
TASK_KEYWORDS = [
    "タスク", "task", "todo", "マイタスク", "業務タスク", "やること",
    "締切", "提出", "期限", "回答〆", "提〆"
]

CALENDAR_KEYWORDS = [
    "予定", "スケジュール", "カレンダー", "ミーティング", "mtg",
    "動静", "休暇", "全休", "会議", "出張"
]

CREATE_KEYWORDS = [
    "登録", "追加", "入れて", "入れといて", "作成", "作って",
    "設定して", "新規"
]

UPDATE_KEYWORDS = [
    "変更", "ずらして", "更新", "移動", "変えて", "伸ばして",
    "終日", "終日にチェック"
]

DELETE_KEYWORDS = [
    "削除", "消して", "消去", "キャンセル", "取り消し", "やめ", "完了にして", "終わった"
]

VERIFICATION_KEYWORDS = [
    "確認", "登録されて", "入ってる", "入った", "ある？", "あったっけ", "チェックして"
]

PAST_KEYWORDS = [
    "過去", "先週", "昨日", "おととい", "前回", "昔"
]


def detect_intent(prompt: str) -> IntentResult:
    """Analyze user prompt and classify intent flags."""
    lower_prompt = prompt.lower()

    is_task = any(kw in lower_prompt for kw in TASK_KEYWORDS)
    is_cal = any(kw in lower_prompt for kw in CALENDAR_KEYWORDS)
    is_create = any(kw in lower_prompt for kw in CREATE_KEYWORDS)
    is_update = any(kw in lower_prompt for kw in UPDATE_KEYWORDS)
    is_delete = any(kw in lower_prompt for kw in DELETE_KEYWORDS)
    is_verify = any(kw in lower_prompt for kw in VERIFICATION_KEYWORDS)
    is_past = any(kw in lower_prompt for kw in PAST_KEYWORDS)

    is_action = is_create or is_update or is_delete

    return IntentResult(
        is_action_query=is_action,
        is_task_query=is_task,
        is_cal_query=is_cal,
        is_verification_query=is_verify,
        is_past_query=is_past,
        is_create=is_create,
        is_update=is_update,
        is_delete=is_delete,
        is_appliance_action=False,
    )


def build_system_hint(intent: IntentResult) -> str:
    """Build a dynamic system hint based on intent flags."""
    hints = []
    if intent.is_create:
        if intent.is_task_query and not intent.is_cal_query:
            hints.append("【指示】タスク追加には必ず「create_todo_task」ツールを呼び出してください。カレンダーへの登録は行わないでください。")
        elif intent.is_cal_query and not intent.is_task_query:
            hints.append("【指示】予定登録には必ず「create_calendar_event」ツールを呼び出してください。")
        else:
            hints.append("【指示】追加・登録依頼には「create_todo_task」または「create_calendar_event」ツールを必ず呼び出してください。")

    if intent.is_update:
        if intent.is_task_query:
            hints.append("【指示】タスク変更には「update_todo_task」ツールを呼び出してください。")
        elif intent.is_cal_query:
            hints.append("【指示】予定変更には「update_calendar_event」ツールを呼び出してください。")

    if intent.is_delete:
        if intent.is_task_query:
            hints.append("【指示】タスク完了・削除には「complete_todo_task」ツールを呼び出してください。")
        elif intent.is_cal_query:
            hints.append("【指示】予定削除には「delete_calendar_event」ツールを呼び出してください。")

    if intent.is_verification_query:
        hints.append("【指示】存在確認には必ず「get_todo_tasks」または「get_calendar_events」ツールを実行し、最新実データに基づいて回答してください。推測回答は禁止です。")

    return "\n".join(hints)


def is_hallucinating_action(content: str, executed_action_tools: list[str]) -> bool:
    """Detect if the LLM claimed it completed an action without executing tools."""
    if executed_action_tools:
        return False

    patterns = [
        r"(追加|登録|設定|作成|反映)(し(まし)?た|完了(し(まし)?た)?)",
        r"(削除|消去|キャンセル|取り消し)(し(まし)?た|完了(し(まし)?た)?)",
        r"(変更|更新|移動)(し(まし)?た|完了(し(まし)?た)?)",
        r"カレンダーに(追加|登録)",
        r"タスクに(追加|登録)",
    ]
    return any(re.search(p, content) for p in patterns)
