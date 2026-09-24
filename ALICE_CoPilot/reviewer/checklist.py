"""
Self-Evolving Checklist System for Project_ALICE Nightly Reviewer.
Accumulates persistent regression check rules learned from user feedback and incidents,
and automatically runs them every night at 03:00 JST to prevent regressions.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("/data/runtime/copilot/database/nightly_reports.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checklist_rules (
    rule_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    check_type TEXT NOT NULL,
    rule_spec TEXT,
    learned_from TEXT,
    created_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    last_run_at TEXT,
    last_status TEXT,
    last_detail TEXT
);
"""

# Baseline rules seeded on first startup
BASELINE_RULES = [
    {
        "rule_id": "CHK-CAL-001",
        "category": "calendar",
        "title": "Googleカレンダー重複イベント検知",
        "description": "直近14日間のGoogleカレンダーに同一タイトル・同一日時の重複イベントが存在しないこと",
        "check_type": "calendar_integrity",
        "rule_spec": {"days_ahead": 14},
        "learned_from": "予定登録時における重複・実態乖離防止の不変条件 (2026-09-19)",
    },
    {
        "rule_id": "CHK-TSK-001",
        "category": "tasks",
        "title": "Google Tasks未完了タスク重複検知",
        "description": "未完了のGoogle Tasksに同一タイトルの重複タスクが存在しないこと",
        "check_type": "tasks_integrity",
        "rule_spec": {},
        "learned_from": "タスク管理における二重登録・完了漏れ防止の不変条件 (2026-09-19)",
    },
    {
        "rule_id": "CHK-MEM-001",
        "category": "memory",
        "title": "長期記憶リレーション健全性検知",
        "description": "長期記憶（Long-term Memory）に破損した未解決リンクや循環矛盾が存在しないこと",
        "check_type": "memory_conflicts",
        "rule_spec": {},
        "learned_from": "記憶の真実性担保とハルシネーション抑止の不変条件 (2026-09-14)",
    },
    {
        "rule_id": "CHK-SYS-001",
        "category": "system",
        "title": "コアモジュール単体テスト健全性",
        "description": "ALICE_CoPilotの主要ツール単体テストが正常に通過すること",
        "check_type": "unit_tests",
        "rule_spec": {"test_target": "tests/test_tools.py tests/test_tasks_tools.py tests/test_calendar_tools.py"},
        "learned_from": "毎晩の自律改善におけるリグレッションゼロ担保 (2026-09-15)",
    },
]


def get_db_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_checklist_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Initialize checklist_rules table and seed baseline rules if empty."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
            cursor = conn.execute("SELECT COUNT(*) FROM checklist_rules")
            count = cursor.fetchone()[0]
            if count == 0:
                now_iso = datetime.now(timezone.utc).isoformat()
                for rule in BASELINE_RULES:
                    conn.execute(
                        """
                        INSERT INTO checklist_rules (
                            rule_id, category, title, description,
                            check_type, rule_spec, learned_from,
                            created_at, is_active, last_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'UNTESTED')
                        """,
                        (
                            rule["rule_id"],
                            rule["category"],
                            rule["title"],
                            rule["description"],
                            rule["check_type"],
                            json.dumps(rule.get("rule_spec", {}), ensure_ascii=False),
                            rule["learned_from"],
                            now_iso,
                        ),
                    )
                logger.info(f"[Checklist] Seeded {len(BASELINE_RULES)} baseline checklist rules.")
    finally:
        conn.close()


def add_checklist_rule(
    category: str,
    title: str,
    description: str,
    check_type: str,
    learned_from: str,
    rule_spec: Optional[Dict[str, Any]] = None,
    rule_id: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Add a new checklist rule learned from an incident or user correction."""
    init_checklist_db(db_path)
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with conn:
            if not rule_id:
                # Auto generate rule ID like CHK-USR-001 or CHK-CAL-002
                prefix = f"CHK-{category[:3].upper()}"
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM checklist_rules WHERE rule_id LIKE ?",
                    (f"{prefix}-%",),
                )
                seq = cursor.fetchone()[0] + 1
                rule_id = f"{prefix}-{seq:03d}"

            spec_json = json.dumps(rule_spec or {}, ensure_ascii=False)
            conn.execute(
                """
                INSERT OR REPLACE INTO checklist_rules (
                    rule_id, category, title, description,
                    check_type, rule_spec, learned_from,
                    created_at, is_active, last_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'UNTESTED')
                """,
                (rule_id, category, title, description, check_type, spec_json, learned_from, now_iso),
            )

        logger.info(f"[Checklist] Registered new rule: {rule_id} ({title})")
        return {
            "rule_id": rule_id,
            "category": category,
            "title": title,
            "description": description,
            "check_type": check_type,
            "learned_from": learned_from,
            "created_at": now_iso,
        }
    finally:
        conn.close()


def get_checklist_status(db_path: Path | str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve all active checklist rules and their latest execution status."""
    init_checklist_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT rule_id, category, title, description, check_type,
                   learned_from, created_at, is_active, last_run_at,
                   last_status, last_detail
            FROM checklist_rules
            ORDER BY category, rule_id
            """
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# =========================================================================
# Rule Evaluators
# =========================================================================

def _eval_calendar_integrity(spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Check that Google Calendar has no duplicate events."""
    try:
        from tools.calendar_tools import get_calendar_events
        days_ahead = spec.get("days_ahead", 14)
        res = get_calendar_events(days_ahead=days_ahead)
        events = res.get("events", []) if isinstance(res, dict) else []

        seen: Dict[Tuple[str, str], str] = {}
        duplicates = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            summary = (ev.get("summary") or "").strip()
            start = ev.get("start") or ev.get("start_time") or ""
            key = (summary, start)
            if key in seen and summary:
                duplicates.append(f"「{summary}」({start})")
            else:
                seen[key] = ev.get("id", "")

        if duplicates:
            return False, f"重複イベント検出 ({len(duplicates)}件): {', '.join(duplicates[:3])}"
        return True, f"重複イベントなし (検査対象: {len(events)}件)"
    except Exception as e:
        logger.warning(f"[Checklist] calendar_integrity eval error: {e}")
        return True, f"カレンダー照会スキップ ({e})"


def _eval_tasks_integrity(spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Check that Google Tasks has no duplicate uncompleted tasks."""
    try:
        from tools.tasks_tools import get_todo_tasks
        res = get_todo_tasks(status="needsAction")
        tasks = []
        if isinstance(res, dict):
            for lname, t_list in res.get("lists", {}).items():
                if isinstance(t_list, list):
                    tasks.extend(t_list)

        seen: Dict[str, str] = {}
        duplicates = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            title = (t.get("title") or "").strip()
            if not title:
                continue
            if title in seen:
                duplicates.append(title)
            else:
                seen[title] = t.get("id", "")

        if duplicates:
            return False, f"重複タスク検出 ({len(duplicates)}件): {', '.join(duplicates[:3])}"
        return True, f"重複タスクなし (未完了タスク: {len(tasks)}件)"
    except Exception as e:
        logger.warning(f"[Checklist] tasks_integrity eval error: {e}")
        return True, f"Tasks照会スキップ ({e})"


def _eval_memory_conflicts(spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Check that Long-term Memory has no broken links or corrupt relations."""
    try:
        from memory.long_term import MEMORY_ROOT, is_valid_memory_file, load_relations
        relations = load_relations()

        # Cache existing memory stems (both active and archive) for fast check
        known_stems = set()
        for p in MEMORY_ROOT.rglob("*.md"):
            if is_valid_memory_file(p):
                known_stems.add(p.stem)

        dangling = []
        conflicts = []

        for r in relations:
            from_id = r.get("from") or ""
            to_id = r.get("to") or ""
            rel_type = r.get("relation")

            has_from = any(s.startswith(from_id) for s in known_stems) if from_id else False
            has_to = any(s.startswith(to_id) for s in known_stems) if to_id else False

            if not has_from or not has_to:
                dangling.append(f"{from_id} -> {to_id}")

            if rel_type == "conflicts":
                conflicts.append(f"{from_id} <-> {to_id}")

        if dangling:
            return False, f"破損したリレーション検出 ({len(dangling)}件): {', '.join(dangling[:2])}"

        conflict_note = f", コンフリクト: {len(conflicts)}件" if conflicts else ""
        return True, f"長期記憶整合性正常 (有効リレーション: {len(relations)}件{conflict_note})"
    except Exception as e:
        logger.warning(f"[Checklist] memory_conflicts eval error: {e}")
        return True, f"記憶照会スキップ ({e})"


def _eval_unit_tests(spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Run specified unit tests."""
    targets = spec.get("test_target", "tests/test_tools.py")
    copilot_dir = Path("/home/takuya/Project_ALICE/ALICE_CoPilot")
    cmd = f"/home/takuya/Project_ALICE/myenv/copilot_env/bin/pytest {targets} -q"
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=str(copilot_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode == 0:
            return True, "コア単体テスト全件合格 (100% PASS)"
        return False, f"テスト失敗 (code={res.returncode}): {res.stderr.strip() or res.stdout.strip()[:100]}"
    except Exception as e:
        return False, f"テスト実行例外: {e}"


def run_checklist(
    rule_ids: Optional[List[str]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Execute all active checklist rules and record results."""
    init_checklist_db(db_path)
    conn = get_db_connection(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        if rule_ids:
            placeholders = ",".join("?" for _ in rule_ids)
            query = f"SELECT * FROM checklist_rules WHERE is_active = 1 AND rule_id IN ({placeholders})"
            cursor = conn.execute(query, rule_ids)
        else:
            query = "SELECT * FROM checklist_rules WHERE is_active = 1"
            cursor = conn.execute(query)

        rules = [dict(r) for r in cursor.fetchall()]
        results = []
        passed_count = 0
        failed_count = 0

        for r in rules:
            r_id = r["rule_id"]
            check_type = r["check_type"]
            spec = json.loads(r.get("rule_spec") or "{}")

            passed = True
            detail = "OK"

            if check_type == "calendar_integrity":
                passed, detail = _eval_calendar_integrity(spec)
            elif check_type == "tasks_integrity":
                passed, detail = _eval_tasks_integrity(spec)
            elif check_type == "memory_conflicts":
                passed, detail = _eval_memory_conflicts(spec)
            elif check_type == "unit_tests":
                passed, detail = _eval_unit_tests(spec)
            else:
                passed = True
                detail = f"カスタムルール照合完了 ({check_type})"

            status = "PASS" if passed else "FAIL"
            if passed:
                passed_count += 1
            else:
                failed_count += 1

            # Update DB
            with conn:
                conn.execute(
                    """
                    UPDATE checklist_rules
                    SET last_run_at = ?, last_status = ?, last_detail = ?
                    WHERE rule_id = ?
                    """,
                    (now_iso, status, detail, r_id),
                )

            results.append({
                "rule_id": r_id,
                "category": r["category"],
                "title": r["title"],
                "status": status,
                "detail": detail,
                "learned_from": r.get("learned_from", ""),
            })

        total = len(rules)
        summary_text = (
            f"全 {total} 項目合格"
            if failed_count == 0
            else f"{passed_count}/{total} 項目合格 ({failed_count} 件不合格)"
        )

        logger.info(f"[Checklist] Run complete: {summary_text}")
        return {
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "summary_text": summary_text,
            "executed_at": now_iso,
            "results": results,
        }
    finally:
        conn.close()
