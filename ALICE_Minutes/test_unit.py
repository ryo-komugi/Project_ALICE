"""
Unit and integration tests for ALICE_Minute.
"""
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.composer import MinuteComposer
from core.models import (
    ActionItem,
    AgendaItem,
    KeyOpinion,
    MeetingOverview,
    MinuteAnalysisResult,
    Participant,
    PendingTopic,
)
from core.ollama_client import OllamaClient
from core.pipeline import MinutePipeline
from core.workspace_io import WorkspaceIO


class TestMinuteUnit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_minute_analysis_schema_and_extra_fields(self):
        """Pydantic V2 スキーマの妥当性および未知の追加フィールド許容の検証"""
        raw_data = {
            "meeting_overview": {
                "title": "週次進捗会議",
                "purpose": "開発進捗の確認と課題抽出",
                "date_time_context": "2026年9月3日 15:00",
                "meeting_type": "業務進捗定例",
                "extra_overview_field": "LLMが出力した未知のキー",
            },
            "participants": [
                {
                    "speaker_label": "SPEAKER_00",
                    "display_name": "田中マネージャー",
                    "estimated_role": "進行役（マネージャー）",
                    "basis": "会議の進行とタスク確認を主導",
                    "extra_speaker_field": 123,
                }
            ],
            "agenda_items": [
                {
                    "agenda_title": "リリーススケジュールの再調整",
                    "time_range": "02:15 - 08:30",
                    "discussion_summary": "テスト工程の遅れについて原因分析と対策が協議された。",
                    "key_opinions": [
                        {
                            "speaker": "佐藤リーダー",
                            "opinion": "結合テストにあと3日間の追加工数が必要",
                            "time_anchor": "03:40",
                        }
                    ],
                    "decisions": ["結合テスト期間を2日間延長する"],
                    "rationale": "品質確保を最優先としつつ納期の遅延を最小限に抑えるため",
                }
            ],
            "action_items": [
                {
                    "task": "追加リソースの作業環境セットアップ",
                    "assignee": "佐藤リーダー",
                    "due_date": "明日12:00まで",
                    "deliverable_or_condition": "アカウント発行とレポジトリ権限付与",
                    "priority": "HIGH",
                    "status_agreement": "合意済",
                    "time_context": "07:15",
                }
            ],
            "confirmed_decisions": ["結合テスト期間の2日間延長"],
            "pending_and_next_topics": [
                {
                    "topic": "次フェーズのサーバー増強費用",
                    "reason": "インフラチームからの見積もりが未着のため",
                    "next_action": "来週月曜日にインフラ担当者へ再確認",
                    "checkpoint_date": "来週月曜",
                }
            ],
            "unexpected_top_level_field": "should_be_tolerated",
        }

        analysis = MinuteAnalysisResult.model_validate(raw_data)
        self.assertEqual(analysis.meeting_overview.title, "週次進捗会議")
        self.assertEqual(analysis.participants[0].display_name, "田中マネージャー")
        self.assertEqual(analysis.action_items[0].priority, "HIGH")

    def test_workspace_io_save_and_load(self):
        """WorkspaceIO の保存と読み込み検証"""
        ws = self.test_dir / "workspace_001"
        ws.mkdir(parents=True)
        (ws / "transcript").mkdir(parents=True)

        transcript_data = [
            {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_00", "text": "それでは会議を始めます。"},
            {"start": 3.0, "end": 6.5, "speaker": "SPEAKER_01", "text": "本日の議題はスケジュール調整です。"},
        ]
        with open(ws / "transcript" / "transcript.json", "w", encoding="utf-8") as f:
            json.dump({"segments": transcript_data}, f)

        segments = WorkspaceIO.load_transcript(ws)
        self.assertEqual(len(segments), 2)
        formatted = WorkspaceIO.format_transcript_for_prompt(segments)
        self.assertIn("SPEAKER_00: それでは会議を始めます。", formatted)

        # Stage 1 保存と読み込み検証
        analysis = MinuteAnalysisResult(
            meeting_overview=MeetingOverview(
                title="テスト会議",
                purpose="テスト目的",
            ),
            confirmed_decisions=["決定事項A"],
        )
        saved_path = WorkspaceIO.save_stage1_analysis(ws, analysis)
        self.assertTrue(saved_path.exists())

        loaded_analysis = WorkspaceIO.load_stage1_analysis(ws)
        self.assertEqual(loaded_analysis.meeting_overview.title, "テスト会議")
        self.assertEqual(loaded_analysis.confirmed_decisions, ["決定事項A"])

        # Stage 2 成果物保存検証
        md_text = (
            "# 【議事録】テスト会議\n\n"
            "## 1. 会議概要\n"
            "- **件名**: テスト会議\n\n"
            "## 3. アクションアイテム（TODO）\n"
            "- [ ] **【HIGH】** タスクA（担当: 佐藤）\n"
        )
        artifacts = WorkspaceIO.save_stage2_artifacts(
            workspace_dir=ws,
            markdown_text=md_text,
            metadata={"template": "standard"},
        )

        self.assertTrue(artifacts["minutes_md"].exists())
        self.assertTrue(artifacts["minutes_txt"].exists())
        self.assertTrue(artifacts["metadata_json"].exists())

        txt_content = artifacts["minutes_txt"].read_text(encoding="utf-8")
        self.assertIn("■ 【議事録】テスト会議", txt_content)
        self.assertIn("◆ 1. 会議概要", txt_content)
        self.assertIn("□ 【HIGH】 タスクA（担当: 佐藤）", txt_content)

    def test_workspace_io_save_failure_metadata(self):
        """異常終了時のメタデータ出力検証"""
        ws = self.test_dir / "workspace_failure"
        ws.mkdir(parents=True)

        meta_path = WorkspaceIO.save_failure_metadata(
            workspace_dir=ws,
            error_message="Ollama connection refused",
            target_model="gemma4:12b",
            template_name="interview",
        )
        self.assertTrue(meta_path.exists())

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["status"], "FAILED")
        self.assertEqual(data["model"], "gemma4:12b")
        self.assertEqual(data["template"], "interview")
        self.assertFalse(data["is_complete"])
        self.assertIn("Ollama connection refused", data["error"])

    def test_load_summary_analysis(self):
        """ALICE_Summary 構造化中間データの読み込みテスト"""
        ws = self.test_dir / "workspace_002"
        ws.mkdir(parents=True)

        none_res = WorkspaceIO.load_summary_analysis(ws)
        self.assertIsNone(none_res)

        summary_dir = ws / "summary"
        summary_dir.mkdir(parents=True)
        dummy_summary = {
            "conversation_overview": {"purpose": "指導面談"},
            "timeline_sections": [
                {"start_time": "00:10", "end_time": "05:00", "section_title": "勤怠ルール確認"}
            ],
        }
        with open(summary_dir / "analysis.json", "w", encoding="utf-8") as f:
            json.dump(dummy_summary, f)

        res = WorkspaceIO.load_summary_analysis(ws)
        self.assertIsNotNone(res)
        self.assertEqual(res["conversation_overview"]["purpose"], "指導面談")
        self.assertEqual(len(res["timeline_sections"]), 1)

    def test_template_loading(self):
        """全テンプレート（standard, interview, executive, consultation）読み込みのテスト"""
        tpl_standard = WorkspaceIO.load_template("standard")
        self.assertIn("【議事録】", tpl_standard)

        tpl_interview = WorkspaceIO.load_template("interview")
        self.assertIn("【面談記録】", tpl_interview)

        tpl_executive = WorkspaceIO.load_template("executive")
        self.assertIn("【意思決定報告】", tpl_executive)

        tpl_consultation = WorkspaceIO.load_template("consultation")
        self.assertIn("【相談・ヒアリング記録】", tpl_consultation)

        # 存在しないテンプレート名指定時のフォールバック (standard.md)
        tpl_fallback = WorkspaceIO.load_template("non_existent_template")
        self.assertIn("【議事録】", tpl_fallback)

    def test_ollama_client_json_extraction(self):
        """JSON抽出ロジック（コードブロック、外側テキスト等）のテスト"""
        # 1. マークダウンコードブロック
        raw_md = "Here is the result:\n```json\n{\"test\": 123}\n```\nHope it helps."
        res1 = OllamaClient.extract_json_object(raw_md)
        self.assertEqual(res1, {"test": 123})

        # 2. 前後テキスト付きの中括弧
        raw_slice = "Thought: analyzing...\n{\"key\": \"value\"}\nDone."
        res2 = OllamaClient.extract_json_object(raw_slice)
        self.assertEqual(res2, {"key": "value"})

        # 3. 生JSON
        res3 = OllamaClient.extract_json_object('{"pure": true}')
        self.assertEqual(res3, {"pure": True})

    def test_ollama_client_think_tag_cleaning(self):
        """思考タグ (<think>, <thought>) の自動除去と分離テスト"""
        client = OllamaClient(host="http://localhost:11434", model="test-model")

        fake_resp = MagicMock()
        fake_resp.json.return_value = {
            "message": {
                "content": "<think>This is internal thinking</think>\n# Formal Output",
                "thinking": "",
            }
        }
        fake_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=fake_resp):
            content, thinking = client.chat(messages=[{"role": "user", "content": "hi"}])
            self.assertEqual(content, "# Formal Output")
            self.assertEqual(thinking, "This is internal thinking")

    def test_composer_clean_markdown_and_closing(self):
        """Composerのマークダウン整形と（以上）自動付与テスト"""
        composer = MinuteComposer(client=MagicMock())

        # 1. 思考タグとコードブロックの除去
        raw_output = "<thought>Drafting...</thought>\n```markdown\n# Minutes\n\nContent\n```"
        cleaned = composer._clean_markdown_output(raw_output)
        self.assertEqual(cleaned, "# Minutes\n\nContent")

        # 2. セクション5があり（以上）がない場合の自動付与
        analysis = MinuteAnalysisResult(
            meeting_overview=MeetingOverview(title="T", purpose="P"),
        )
        fake_content = "# Minutes\n\n## 5. 保留事項\n- 保留なし"
        composer.client.chat.return_value = (fake_content, "")

        result, _ = composer.run(analysis, template_name="standard")
        self.assertTrue(result.endswith("（以上）"))
        self.assertIn("---\n\n（以上）", result)

    def test_minute_pipeline_mock_run(self):
        """モックを用いた MinutePipeline の通し実行テスト"""
        ws = self.test_dir / "pipeline_ws"
        ws.mkdir(parents=True)
        (ws / "transcript").mkdir(parents=True)

        transcript_data = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "本日の議題を確認します。"}
        ]
        with open(ws / "transcript" / "transcript.json", "w", encoding="utf-8") as f:
            json.dump({"segments": transcript_data}, f)

        mock_client = MagicMock()
        mock_analysis = MinuteAnalysisResult(
            meeting_overview=MeetingOverview(title="テスト会議", purpose="テスト目的"),
            confirmed_decisions=["決定A"],
        )
        mock_client.chat_structured.return_value = mock_analysis
        mock_client.chat.return_value = (
            "# 【議事録】テスト会議\n\n## 1. 概要\n\n## 5. 保留事項\n- なし\n\n---\n\n（以上）",
            "",
        )

        pipeline = MinutePipeline(client=mock_client, model="mock-model")
        result = pipeline.run(workspace_dir=ws, template_name="standard")

        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue((ws / "minutes" / "minutes.md").exists())
        self.assertTrue((ws / "minutes" / "minutes.txt").exists())
        self.assertTrue((ws / "minutes" / "analysis.json").exists())
        self.assertTrue((ws / "minutes" / "metadata.json").exists())

        # VRAM アンロード呼び出し検証
        mock_client.unload_model.assert_called()

    def test_minute_pipeline_failure_handling(self):
        """パイプライン実行時例外のハンドリングと metadata.json 記録のテスト"""
        ws = self.test_dir / "pipeline_failure_ws"
        ws.mkdir(parents=True)
        (ws / "transcript").mkdir(parents=True)

        with open(ws / "transcript" / "transcript.json", "w", encoding="utf-8") as f:
            json.dump({"segments": []}, f)

        mock_client = MagicMock()
        mock_client.chat_structured.side_effect = RuntimeError("Ollama crashed")

        pipeline = MinutePipeline(client=mock_client, model="mock-model")

        with self.assertRaises(RuntimeError):
            pipeline.run(workspace_dir=ws, template_name="standard")

        meta_path = ws / "minutes" / "metadata.json"
        self.assertTrue(meta_path.exists())
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["status"], "FAILED")
        self.assertIn("Ollama crashed", data["error"])
        mock_client.unload_model.assert_called()


if __name__ == "__main__":
    unittest.main()
