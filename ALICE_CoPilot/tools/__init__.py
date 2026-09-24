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
from tools.calendar_tools import (
    get_calendar_events,
    create_calendar_event,
    delete_calendar_event,
    update_calendar_event,
)
from tools.tasks_tools import get_todo_tasks, create_todo_task, complete_todo_task, update_todo_task

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
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Google カレンダーから予定・スケジュールを取得します。「今日の予定は？」「今週の予定」「人員動静を教えて」「仕事の予定」などを尋ねられた際に使用します。カレンダー名が指定されない場合は、登録されている全カレンダー（個人予定・仕事・人員動静など）を自動で横断検索してまとめて返します。※ユーザーが『カレンダーのタスク』『明日のタスク』『ToDo』と表現している場合や、カレンダーに予定が見つからない場合は、Google Tasks側（get_todo_tasks）も併せて確認してください。",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_name": {
                        "type": "string",
                        "description": "対象カレンダー名（例: '個人予定', '仕事', '人員動静'）。省略時は全カレンダーをまとめて横断検索します。",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "開始日時（例: '2026-09-13 00:00' や '2026-09-14'。省略時は本日の開始時刻）",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "終了日時（例: '2026-09-20 23:59'。省略時は time_min から days_ahead 日後）",
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "検索する先の日数（デフォルト: 30日間、query指定時は60日間）",
                    },
                    "query": {
                        "type": "string",
                        "description": "予定タイトルや内容で絞り込む検索キーワード（例: '面談', 'リコール'）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Google カレンダーに新しい予定・スケジュールを登録します。「〜日の〜時から〜の予定を入れて」「次回予定を登録して」と依頼された際に使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "予定の件名・タイトル（例: 'A社様との進捗MTG', '病院予約'）",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "開始日時（例: '2026-09-20 14:00'）",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "終了日時（例: '2026-09-20 15:00'。省略時は start_time から duration_minutes 分後）",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "所要時間（分、デフォルト: 60）",
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": "登録先カレンダー名（'個人予定', '仕事', '人員動静'。デフォルト: '個人予定'）",
                    },
                    "description": {
                        "type": "string",
                        "description": "予定の詳細・メモ",
                    },
                    "location": {
                        "type": "string",
                        "description": "予定の場所（例: 'Zoom', 'オフィス'）",
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "終日イベント（休暇、出張、全休など）の場合は true。カレンダーの「終日」フラグにチェックが入ります（デフォルト: false）",
                    },
                },
                "required": ["summary", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Google カレンダーから不要な予定・スケジュールを削除します。「〜の予定を消して」「キャンセルになったので削除して」「重複した予定を削除して」と依頼された際に必ず呼び出します。自律ツールを呼び出さずに勝手に『削除しました』と回答してはいけません。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "削除対象のイベントID（例: 'jqgo6ka2598qpdhd2ud0eafsms'）、または予定タイトル・キーワード",
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": "対象カレンダー名（'個人予定', '仕事', '人員動静'。省略時は全カレンダー横断）",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": "Google カレンダーの既存の予定（タイトル、日時、終日設定、場所等）を変更・更新します。「〜の予定を〜に変更して」「時間を〜時にずらして」「終日にして」「終日にチェック入れて」と依頼された際に呼び出します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "更新対象のイベントID（例: 'jqgo6ka2598qpdhd2ud0eafsms'）、または予定タイトル・キーワード",
                    },
                    "summary": {
                        "type": "string",
                        "description": "変更後の新しい予定タイトル",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "変更後の開始日時（例: '2026-09-20 15:00' または '2026-09-20'）",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "変更後の終了日時（例: '2026-09-20 16:00'）",
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": "対象カレンダー名（'個人予定', '仕事', '人員動静'）",
                    },
                    "description": {
                        "type": "string",
                        "description": "新しい予定の説明・メモ",
                    },
                    "location": {
                        "type": "string",
                        "description": "新しい場所",
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "終日イベントに変更する場合は true、時刻指定に変更する場合は false",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todo_tasks",
            "description": "Google Tasks（ToDo リスト）からタスク一覧を取得します。「今日のToDo教えて」「未完了のタスクは？」「業務タスクの締め切り確認して」「マイタスク教えて」「カレンダーのタスク」「明日のタスク」「〜のタスクあったっけ？」などの質問で使用します。「業務タスク」（【提〆】【回答〆】など）と「マイタスク」の各リストを自動で横断取得し、期限とステータスを返します。特定のタスクを探す場合はqueryを指定できます。未完了タスクに見当たらない場合やタスクの存在確認時は、status='all'で完了済みタスクも含めて確認できます。",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_name": {
                        "type": "string",
                        "description": "対象リスト名（'業務タスク' または 'マイタスク'。省略時は両方のリストを取得）",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["needsAction", "completed", "all"],
                        "description": "タスクの状態（'needsAction': 未完了のみ[デフォルト], 'completed': 完了済み, 'all': すべて。存在確認や完了済みチェック時は'all'）",
                    },
                    "due_max": {
                        "type": "string",
                        "description": "期日の上限（YYYY-MM-DD。例: '2026-09-20'）",
                    },
                    "due_min": {
                        "type": "string",
                        "description": "期日の下限（YYYY-MM-DD。例: '2026-09-18'）",
                    },
                    "query": {
                        "type": "string",
                        "description": "タスク名やメモに含まれるキーワードで絞り込み（例: '動静表', '面談'）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_todo_task",
            "description": "Google Tasks（ToDo リスト）に新しいタスクを追加します。【重要】AIが勝手に【提〆】や【回答〆】等の接頭語を推測・補完してはいけません。ユーザーが「【提〆】〜」と直接書いた場合や「提出期限」「回答期限」と明示した場合を除き、ユーザーが指定したタスク名そのままで登録してください。またGoogle Tasksは日付単位（YYYY-MM-DD）の期限管理であり、特定時刻の通知には対応していません。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "タスクの件名（ユーザーが指定した通りのタスク名。勝手に接頭語を推測・付与しないこと）",
                    },
                    "list_name": {
                        "type": "string",
                        "description": "登録先リスト名（'業務タスク' または 'マイタスク'。デフォルト: '業務タスク'）",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "期限日（YYYY-MM-DD形式。例: '2026-09-20'）",
                    },
                    "notes": {
                        "type": "string",
                        "description": "タスクの詳細メモ",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo_task",
            "description": "Google Tasks（ToDo リスト）のタスクを完了（チェック済み）にします。「〜のタスク終わったよ」「〜を完了にして」と報告された際に使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_title_or_id": {
                        "type": "string",
                        "description": "完了にするタスクのタイトル（またはキーワード、ID）",
                    },
                    "list_name": {
                        "type": "string",
                        "description": "対象リスト名（'業務タスク' または 'マイタスク'。省略可）",
                    },
                },
                "required": ["task_title_or_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo_task",
            "description": "Google Tasks（ToDo リスト）の既存タスクの件名・期限日・メモを更新・修正します。タスク名の変更、接頭語の追加・削除、期限日の変更時に使用します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_title_or_id": {
                        "type": "string",
                        "description": "更新対象のタスク名（またはキーワード、ID）",
                    },
                    "new_title": {
                        "type": "string",
                        "description": "変更後の新しいタスク名（接頭語の変更やタイトル修正時）",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "変更後の新しい期限日（YYYY-MM-DD形式）",
                    },
                    "notes": {
                        "type": "string",
                        "description": "更新する詳細メモ",
                    },
                    "list_name": {
                        "type": "string",
                        "description": "対象リスト名（'業務タスク' または 'マイタスク'。省略可）",
                    },
                },
                "required": ["task_title_or_id"],
            },
        },
    },
]

TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "search_past_meetings": search_past_meetings,
    "search_project_memory": search_project_memory,
    "get_system_status": get_system_status,
    "get_recent_jobs": get_recent_jobs,
    "get_calendar_events": get_calendar_events,
    "create_calendar_event": create_calendar_event,
    "delete_calendar_event": delete_calendar_event,
    "update_calendar_event": update_calendar_event,
    "get_todo_tasks": get_todo_tasks,
    "create_todo_task": create_todo_task,
    "complete_todo_task": complete_todo_task,
    "update_todo_task": update_todo_task,
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
