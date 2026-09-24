"""
Tests for the Self-Evolving Checklist system in ALICE_CoPilot.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reviewer.checklist import (
    add_checklist_rule,
    get_checklist_status,
    init_checklist_db,
    run_checklist,
)
from reviewer.report_manager import build_morning_briefing_embed
from reviewer.tools import (
    REVIEW_STATE,
    add_checklist_rule as tool_add_rule,
    get_checklist_status as tool_get_status,
    reset_review_state,
    run_self_evolving_checklist,
)


class TestSelfEvolvingChecklist(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_nightly_reports.db"
        reset_review_state()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init_and_seed_checklist_db(self):
        """データベース初期化とベースラインルールの自動シード検証"""
        init_checklist_db(self.db_path)
        rules = get_checklist_status(self.db_path)
        self.assertEqual(len(rules), 4)

        rule_ids = [r["rule_id"] for r in rules]
        self.assertIn("CHK-CAL-001", rule_ids)
        self.assertIn("CHK-TSK-001", rule_ids)
        self.assertIn("CHK-MEM-001", rule_ids)
        self.assertIn("CHK-SYS-001", rule_ids)

        for r in rules:
            self.assertEqual(r["last_status"], "UNTESTED")

    def test_add_checklist_rule(self):
        """インシデント・ユーザー指摘からの新ルール自動学習・追加検証"""
        init_checklist_db(self.db_path)

        rule = add_checklist_rule(
            category="calendar",
            title="削除指示済み予定の残存防止",
            description="削除指示のあった予定IDがカレンダー内に残存していないこと",
            check_type="calendar_integrity",
            learned_from="2026-09-22 ユーザー指摘: '消えてない'の再発防止",
            db_path=self.db_path,
        )

        self.assertEqual(rule["rule_id"], "CHK-CAL-002")
        self.assertEqual(rule["category"], "calendar")

        rules = get_checklist_status(self.db_path)
        self.assertEqual(len(rules), 5)
        new_rule = next(r for r in rules if r["rule_id"] == "CHK-CAL-002")
        self.assertEqual(new_rule["title"], "削除指示済み予定の残存防止")
        self.assertIn("消えてない", new_rule["learned_from"])

    def test_run_checklist(self):
        """チェックリストの一括実行と合否記録の検証"""
        init_checklist_db(self.db_path)

        # Mock out the evaluators to test run_checklist cleanly
        with patch("reviewer.checklist._eval_calendar_integrity", return_value=(True, "重複なし")), \
             patch("reviewer.checklist._eval_tasks_integrity", return_value=(True, "タスク正常")), \
             patch("reviewer.checklist._eval_memory_conflicts", return_value=(True, "コンフリクトなし")), \
             patch("reviewer.checklist._eval_unit_tests", return_value=(True, "全件PASS")):

            res = run_checklist(db_path=self.db_path)

            self.assertEqual(res["total"], 4)
            self.assertEqual(res["passed"], 4)
            self.assertEqual(res["failed"], 0)
            self.assertEqual(res["summary_text"], "全 4 項目合格")

        # Verify persisted status in DB
        rules = get_checklist_status(self.db_path)
        for r in rules:
            self.assertEqual(r["last_status"], "PASS")

    def test_run_checklist_failure_detection(self):
        """不合格項目の検知と集計の検証"""
        init_checklist_db(self.db_path)

        with patch("reviewer.checklist._eval_calendar_integrity", return_value=(False, "重複イベント検出: 会議A")), \
             patch("reviewer.checklist._eval_tasks_integrity", return_value=(True, "OK")), \
             patch("reviewer.checklist._eval_memory_conflicts", return_value=(True, "OK")), \
             patch("reviewer.checklist._eval_unit_tests", return_value=(True, "OK")):

            res = run_checklist(db_path=self.db_path)

            self.assertEqual(res["total"], 4)
            self.assertEqual(res["passed"], 3)
            self.assertEqual(res["failed"], 1)
            self.assertIn("3/4 項目合格", res["summary_text"])
            self.assertIn("1 件不合格", res["summary_text"])

    def test_morning_briefing_embed_with_checklist(self):
        """モーニングブリーフィング Embed へのチェックリストバッジ統合テスト"""
        report_data = {
            "id": 1,
            "summary": "対話ログおよびシステム点検が完了しました。",
            "memories_added": [],
            "improvements": ["全システム正常稼働"],
            "conversations_count": 10,
            "errors_count": 0,
            "raw_details": json.dumps({
                "checklist": {
                    "total": 5,
                    "passed": 5,
                    "failed": 0,
                    "summary_text": "全 5 項目合格",
                },
                "new_checklist_rules": [
                    "【チェックリスト新規登録】[CHK-CAL-002] 予定削除時の二重確認",
                ],
            }, ensure_ascii=False),
        }

        embed = build_morning_briefing_embed(report_data)

        # Check that checklist field is in embed
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("自己進化チェックリスト" in name for name in field_names))

        checklist_field = next(f for f in embed.fields if "自己進化チェックリスト" in f.name)
        self.assertIn("5/5 項目 合格", checklist_field.value)
        self.assertIn("新規学習・蓄積: 1件", checklist_field.value)

    def test_reviewer_tools_integration(self):
        """reviewer/tools.py のチェックリストツール連携テスト"""
        with patch("reviewer.checklist.DEFAULT_DB_PATH", self.db_path), \
             patch("reviewer.checklist._eval_calendar_integrity", return_value=(True, "OK")), \
             patch("reviewer.checklist._eval_tasks_integrity", return_value=(True, "OK")), \
             patch("reviewer.checklist._eval_memory_conflicts", return_value=(True, "OK")), \
             patch("reviewer.checklist._eval_unit_tests", return_value=(True, "OK")):

            # 1. run_self_evolving_checklist
            out = run_self_evolving_checklist()
            self.assertIn("【自己進化チェックリスト実行結果】", out)
            self.assertIn("CHK-CAL-001", out)
            self.assertIsNotNone(REVIEW_STATE["checklist_summary"])

            # 2. add_checklist_rule
            msg = tool_add_rule(
                category="user_rule",
                title="タスク期日フォーマット検証",
                description="期日はISO形式で保存されること",
                check_type="custom",
                learned_from="ユーザー指摘",
            )
            self.assertIn("チェックリストに新ルールを登録・永続化しました", msg)
            self.assertEqual(len(REVIEW_STATE["new_checklist_rules"]), 1)

            # 3. get_checklist_status
            status_out = tool_get_status()
            self.assertIn("タスク期日フォーマット検証", status_out)


if __name__ == "__main__":
    unittest.main()
