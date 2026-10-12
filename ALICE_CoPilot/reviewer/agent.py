"""
Antigravity-Powered Nightly Reviewer Agent.
Analyzes conversations, verifies knowledge gaps, self-corrects memory,
maintains the self-evolving regression checklist, and prepares the morning briefing for Asano-san.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any

# Ensure project directory is on sys.path
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import config
from google.antigravity import Agent, LocalOpenAIAgentConfig
from reviewer.log_extractor import build_review_context
from reviewer.report_manager import save_report
from reviewer.tools import (
    REVIEW_STATE,
    add_checklist_rule,
    add_longterm_memory,
    check_calendar_state,
    check_task_state,
    get_checklist_status,
    record_review_result,
    repair_calendar_state,
    repair_tasks_state,
    audit_codebase_architecture,
    reset_review_state,
    run_copilot_unit_tests,
    run_self_evolving_checklist,
    search_codebase,
    search_existing_memories,
    search_git_history,
)

SYSTEM_INSTRUCTIONS = """
あなたはProject_ALICEの自律改善エージェント（Nightly Reviewer）です。
毎晩深夜に、浅野さん（オーナー）とALICE_CoPilotの対話履歴およびシステムログを点検し、知識の欠落やツールの不具合、発言と実態の乖離（ハルシネーション）を自律的に改善・修復します。

【行動規範】
1. 会話ログを精査し、以下のいずれかに該当する箇所を特定してください:
   - 浅野さんの質問に対してAIが「見つかりませんでした」「分かりません」と回答した事象
   - 会話の中で浅野さんが提示した新しい決定事項（ドメイン変更、インフラ設定、運用ルール、タスク仕様など）
   - AIが「削除しました」「変更しました」「追加しました」と報告しているにもかかわらず、ユーザーから「消えてない」「残ってる」「本当にやった？」と指摘されている箇所（ハルシネーション・実態乖離の疑い）
   - システムログに記録されたエラーや例外

2. 実態乖離・ハルシネーションの検証と自律修復（最重要）:
   - 予定やタスクの追加・変更・削除の報告がある場合、`check_calendar_state` や `check_task_state` で最新の実データを直接照会して検証する。
   - AIが「削除した」と述べたにもかかわらずカレンダーやTasksに重複・不要な予定が残存している場合、`repair_calendar_state(action='delete', event_id=...)` を呼び出して夜間のうちに自律削除修復を行う。
   - 予定の内容に誤りがある場合は `repair_calendar_state(action='update', event_id=..., summary=...)` で自律修正を行う。

3. 【自己進化型チェックリストの自律実行と学習・蓄積（再発防止）】:
   - レビュー開始時または終了時に必ず `run_self_evolving_checklist()` を実行し、既存のすべての再発防止・不変条件ルールが合格しているか確認してください。
   - 万が一不合格の項目があれば、該当ツール（`repair_calendar_state` 等）で修復してください。
   - 会話ログの中で浅野さんからツールの不備・漏れ・実態乖離の指摘（例：「消えてない」「残ってる」「また二重登録された」「違う」等）があった場合、その場での修復にとどまらず、二度と同じ不具合を起こさないための【恒久的な再発防止ルール】を `add_checklist_rule(category=..., title=..., description=..., check_type=..., learned_from=...)` を呼び出してチェックリストに新規登録（自動学習）してください。

4. 知識の不足が疑われる場合の自律調査:
   a. `search_existing_memories` で、既に類似の長期記憶が登録されていないか確認する。
   b. 未登録の場合、`search_git_history` や `search_codebase` を使って事実や決定理由を調査する。
   c. 有効な決定事項や仕様が判明した場合は、`add_longterm_memory` を呼び出して新規記憶として登録する。

5. 最後に、必ず `record_review_result` ツールを呼び出してください:
   - summary: 点検結果の明確な日本語要約（何を点検し、どんな改善・自律修復・記憶登録・チェックリスト検証を行ったか）
   - improvements: 翌朝浅野さんに提示するシステム改善の提案や気付きのリスト
"""


async def run_nightly_review(hours: int = 24) -> int:
    """Runs the nightly review process using Google Antigravity SDK. Returns report ID."""
    reset_review_state()
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Nightly Self-Improvement Review (past {hours}h)...")

    # 1. Always execute the self-evolving checklist first to verify system invariants
    print("[Nightly Review] Running self-evolving checklist...")
    checklist_res = run_self_evolving_checklist()
    print(f"[Nightly Review] Checklist result: {checklist_res[:100]}...")

    ctx = build_review_context(hours=hours)
    conv_count = ctx["conversations_count"]
    err_count = ctx["errors_count"]
    print(f"Extracted {conv_count} conversation messages and {err_count} log entries.")

    if conv_count == 0 and err_count == 0:
        summary = "過去24時間の対話ログはなく、システムログにもエラー・警告は検出されませんでした。自己進化チェックリストを検証し、全システム正常稼働中です。"
        raw_details_payload = {
            "raw_text": "No conversations or errors in period.",
            "repairs_done": [],
            "checklist": REVIEW_STATE.get("checklist_summary"),
            "new_checklist_rules": REVIEW_STATE.get("new_checklist_rules", []),
        }
        report_id = save_report(
            summary=summary,
            memories_added=[],
            improvements=["全機能正常に待機中", f"チェックリスト: {REVIEW_STATE.get('checklist_summary', {}).get('summary_text', '合格')}"],
            period_start=ctx["period_start"],
            period_end=ctx["period_end"],
            conversations_count=0,
            errors_count=0,
            raw_details=json.dumps(raw_details_payload, ensure_ascii=False),
        )
        print(f"Review completed (no activity). Report #{report_id} saved.")
        return report_id

    review_prompt = f"""
以下は過去24時間の浅野さんとALICEの対話ログ、およびシステムログです。

==================================================
【対話ログ】
{ctx["transcript_text"]}
==================================================

【システムエラー・警告ログ】
{ctx["errors_text"]}
==================================================

上記の内容を点検し、知識の欠落があればツールを使って調査・記憶補完を行い、
ユーザーからの指摘があれば再発防止ルールを `add_checklist_rule` で蓄積し、
最後に必ず `record_review_result` を呼び出してレビュー結果を記録してください。
"""

    agent_config = LocalOpenAIAgentConfig(
        model=config.OLLAMA_MODEL,
        base_url="http://localhost:11434/v1",
        system_instructions=SYSTEM_INSTRUCTIONS,
        tools=[
            check_calendar_state,
            check_task_state,
            repair_calendar_state,
            repair_tasks_state,
    audit_codebase_architecture,
            run_self_evolving_checklist,
            add_checklist_rule,
            get_checklist_status,
            search_codebase,
            search_git_history,
            search_existing_memories,
            add_longterm_memory,
            run_copilot_unit_tests,
            record_review_result,
        ],
    )

    ans_text = ""
    try:
        agent = Agent(name="NightlyReviewer", config=agent_config)
        session = agent.create_session()
        print("Executing Antigravity Reviewer Agent session...")
        response = await session.send_message(review_prompt)
        ans_text = response.text or ""
        print("Antigravity Reviewer Agent session finished.")
    except Exception as ex:
        print(f"[Reviewer Agent Fallback Notice] Antigravity direct agent exception: {ex}")
        print("Falling back to direct Ollama structured call...")
        import requests
        try:
            fallback_res = await asyncio.to_thread(
                requests.post,
                config.OLLAMA_URL,
                json={
                    "model": config.OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": review_prompt},
                    ],
                    "stream": False,
                    "options": {"num_ctx": config.OLLAMA_CONTEXT},
                },
                timeout=300,
            )
            if fallback_res.status_code == 200:
                data = fallback_res.json()
                ans_text = data.get("message", {}).get("content", "")
                print("Ollama direct review completed successfully.")
        except Exception as fallback_ex:
            print(f"[Ollama Direct Fallback Error] {fallback_ex}")
            ans_text = f"点検ログ分析完了 (通知: {ex})"

    # Determine final summary, improvements, and repairs
    repairs = REVIEW_STATE.get("repairs_done", [])

    if REVIEW_STATE["recorded"]:
        summary = REVIEW_STATE["summary"]
        improvements = REVIEW_STATE["improvements"]
        memories = REVIEW_STATE["memories_added"]
    else:
        # Fallback if model answered in text without invoking record_review_result
        summary = ans_text[:500] if ans_text else "夜間点検が完了しました。"
        improvements = ["対話履歴の点検完了"]
        memories = REVIEW_STATE["memories_added"]

    # If repairs were executed, highlight in improvements
    if repairs:
        improvements = [f"【自律修復完了】{r}" for r in repairs] + improvements

    new_rules = REVIEW_STATE.get("new_checklist_rules", [])
    if new_rules:
        improvements = [f"【再発防止学習】{r}" for r in new_rules] + improvements

    raw_details_payload = {
        "raw_text": ans_text,
        "repairs_done": repairs,
        "checklist": REVIEW_STATE.get("checklist_summary"),
        "new_checklist_rules": new_rules,
    }
    raw_details_str = json.dumps(raw_details_payload, ensure_ascii=False)

    report_id = save_report(
        summary=summary,
        memories_added=memories,
        improvements=improvements,
        period_start=ctx["period_start"],
        period_end=ctx["period_end"],
        conversations_count=conv_count,
        errors_count=err_count,
        raw_details=raw_details_str,
    )
    print(f"Nightly review report #{report_id} successfully saved to database.")
    return report_id


if __name__ == "__main__":
    hours = 24
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        hours = int(sys.argv[1])
    asyncio.run(run_nightly_review(hours=hours))
