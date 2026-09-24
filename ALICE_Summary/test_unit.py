import unittest
import tempfile
import json
import shutil
from pathlib import Path
from core.workspace_io import WorkspaceIO
from core.ollama_client import OllamaClient
from core.models import AnalysisResult, Topic


class TestSummaryUnit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_workspace_io_formatting(self):
        segments = [
            {"start": 10.5, "end": 15.0, "speaker": "SPEAKER_01", "text": "こんにちは"},
            {"start": 16.0, "end": 20.0, "speaker": "SPEAKER_02", "text": "お疲れ様です"},
            {"start": 21.0, "end": 22.0, "speaker": "SPEAKER_01", "text": ""},  # empty text should be skipped
        ]
        formatted = WorkspaceIO.format_transcript_for_prompt(segments)
        self.assertIn("[00:10] SPEAKER_01: こんにちは", formatted)
        self.assertIn("[00:16] SPEAKER_02: お疲れ様です", formatted)
        self.assertEqual(len(formatted.splitlines()), 2)

    def test_markdown_to_plain_text(self):
        md = (
            "# 面談の目的と概要\n\n"
            "これは**テスト**です。\n\n"
            "## 議題1\n"
            "- 項目1\n"
            "- 項目2\n"
        )
        plain = WorkspaceIO.markdown_to_plain_text(md)
        self.assertIn("■ 面談の目的と概要", plain)
        self.assertIn("これはテストです。", plain)
        self.assertIn("◆ 議題1", plain)
        self.assertIn("・項目1", plain)
        self.assertNotIn("**", plain)
        self.assertNotIn("#", plain)

    def test_json_extractor(self):
        # Direct json
        raw = '{"status": "ok", "count": 5}'
        d = OllamaClient.extract_json_object(raw)
        self.assertEqual(d["status"], "ok")

        # Code block json
        raw_block = "Here is the result:\n```json\n{\"status\": \"ok\", \"nested\": {\"a\": 1}}\n```\nHope it helps!"
        d_block = OllamaClient.extract_json_object(raw_block)
        self.assertEqual(d_block["status"], "ok")
        self.assertEqual(d_block["nested"]["a"], 1)

        # Embedded json
        raw_embed = "Prefix text {\"answer\": 42} suffix text"
        d_embed = OllamaClient.extract_json_object(raw_embed)
        self.assertEqual(d_embed["answer"], 42)

        # Thought tags + trailing comma
        raw_thought = "<thought>thinking process</thought>{\"answer\": 99, \"list\": [1, 2, ],}"
        d_thought = OllamaClient.extract_json_object(raw_thought)
        self.assertEqual(d_thought["answer"], 99)
        self.assertEqual(d_thought["list"], [1, 2])

        # Missing closing brace repair
        raw_incomplete = "{\"status\": \"repaired\", \"val\": 123"
        d_repaired = OllamaClient.extract_json_object(raw_incomplete)
        self.assertEqual(d_repaired["status"], "repaired")

    def test_pydantic_model_validation(self):
        data = {
            "conversation_overview": {
                "purpose": "業務改善面談",
                "background": "前回の振り返り"
            },
            "topics": [
                {
                    "title": "遅刻の頻発について",
                    "issue": "月3回の遅刻",
                    "confirmed_facts": ["5月中に3回遅刻"],
                    "participant_statements": ["目覚ましが鳴らなかった"],
                    "interviewer_statements": ["生活習慣の是正を要求"],
                    "evolution_and_resolution": "本人がアラーム増設に合意",
                    "agreed_points": ["今後遅刻ゼロを目指す"]
                }
            ]
        }
        model = AnalysisResult(**data)
        self.assertEqual(model.conversation_overview.purpose, "業務改善面談")
        self.assertEqual(len(model.topics), 1)
        self.assertEqual(model.topics[0].title, "遅刻の頻発について")

    def test_dynamic_num_ctx_calculation(self):
        # 短いテキスト (~1,000文字)
        short_text = "あ" * 1000
        ctx_short = WorkspaceIO.calculate_dynamic_num_ctx(short_text)
        self.assertEqual(ctx_short, 32768)

        # 中規模テキスト (~20,000文字)
        mid_text = "あ" * 20000
        ctx_mid = WorkspaceIO.calculate_dynamic_num_ctx(mid_text)
        self.assertEqual(ctx_mid, 49152)

        # 長尺テキスト (~35,000文字)
        long_text = "あ" * 35000
        ctx_long = WorkspaceIO.calculate_dynamic_num_ctx(long_text)
        self.assertEqual(ctx_long, 65536)

    def test_checker_output_parsing(self):
        from core.checker import ConsistencyChecker

        raw_output = (
            "# 整合性検証レポート\n"
            "- 重大な不整合なし。\n"
            "- 全7項目チェックOK。\n\n"
            "---\n\n"
            "# 最終修正版要約\n"
            "※ドラフトの完成度が高いため、微修正した版を提示します。\n\n"
            "# 面談（会話）の目的と全体概要\n"
            "これは修正された最終要約です。" + "あ" * 400
        )
        fallback = "# ドラフト要約\nフォールバック用ドラフト要約本文です。" + "い" * 400

        summary_part, report_part = ConsistencyChecker.parse_checker_output(raw_output, fallback_draft=fallback)

        self.assertIn("整合性検証レポート", report_part)
        self.assertIn("重大な不整合なし", report_part)
        self.assertIn("これは修正された最終要約です", summary_part)
        self.assertNotIn("整合性検証レポート", summary_part)
        self.assertNotIn("※ドラフトの完成度が高いため", summary_part)


    def test_ollama_retry_success(self):
        import unittest.mock
        client = OllamaClient()
        call_count = 0

        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Temporary connection drop")
            from core.ollama_client import OllamaResponse
            return OllamaResponse(
                content="retry success",
                thinking=None,
                prompt_eval_count=10,
                eval_count=5,
                total_duration_sec=0.1,
                load_duration_sec=0.0,
                raw_response={},
                actual_model="gemma4:12b",
            )

        with unittest.mock.patch.object(client, "_execute_request", side_effect=mock_execute):
            resp = client.chat(
                model="gemma4:12b",
                messages=[{"role": "user", "content": "hi"}],
                max_retries=3,
                retry_delay=0.01,
            )
            self.assertEqual(resp.content, "retry success")
            self.assertEqual(call_count, 2)

    def test_ollama_fallback_success(self):
        import unittest.mock
        import urllib.error
        client = OllamaClient()
        attempted_models = []

        def mock_execute(model, *args, **kwargs):
            attempted_models.append(model)
            if model == "gemma4:12b":
                raise urllib.error.HTTPError("http://localhost:11434/api/chat", 404, "Not Found", {}, None)
            from core.ollama_client import OllamaResponse
            return OllamaResponse(
                content="fallback success",
                thinking=None,
                prompt_eval_count=10,
                eval_count=5,
                total_duration_sec=0.1,
                load_duration_sec=0.0,
                raw_response={},
                actual_model=model,
            )

        with unittest.mock.patch.object(client, "_execute_request", side_effect=mock_execute):
            resp = client.chat(
                model="gemma4:12b",
                messages=[{"role": "user", "content": "hi"}],
                fallback_model="qwen3:14b",
                max_retries=2,
                retry_delay=0.01,
            )
            self.assertEqual(resp.content, "fallback success")
            self.assertEqual(resp.actual_model, "qwen3:14b")
            self.assertIn("gemma4:12b", attempted_models)
            self.assertIn("qwen3:14b", attempted_models)

    def test_conversation_type_detection(self):
        from core.composer import Composer

        # 1. 面談 (interview)
        interview_data = {
            "metadata": {"conversation_type": "面談"},
            "conversation_overview": {"purpose": "人事評価および今後のキャリア面談"},
            "topics": [{"title": "目標達成状況の確認"}]
        }
        self.assertEqual(Composer.detect_conversation_type(interview_data), "interview")

        # 2. 会議 (meeting)
        meeting_data = {
            "metadata": {"conversation_type": "定例会議"},
            "conversation_overview": {"purpose": "週次進捗共有および課題の討議"},
            "topics": [{"title": "アジェンダ1: リリース判定"}]
        }
        self.assertEqual(Composer.detect_conversation_type(meeting_data), "meeting")

        # 3. 業務相談 (consultation)
        consultation_data = {
            "metadata": {"conversation_type": "業務相談"},
            "conversation_overview": {"purpose": "新機能の設計方針についての壁打ち・相談"},
            "topics": [{"title": "アーキテクチャの選定に関する助言"}]
        }
        self.assertEqual(Composer.detect_conversation_type(consultation_data), "consultation")

        # 4. 汎用 (general)
        general_data = {
            "metadata": {},
            "conversation_overview": {"purpose": "雑談および近況報告"},
            "topics": [{"title": "最近のニュースについて"}]
        }
        self.assertEqual(Composer.detect_conversation_type(general_data), "general")

    def test_template_loading(self):
        from core.composer import Composer
        from config import SummaryConfig
        from core.ollama_client import OllamaClient

        composer = Composer(config=SummaryConfig(), client=OllamaClient())

        for c_type in ["interview", "meeting", "consultation", "general"]:
            tmpl = composer._load_prompt_template(c_type)
            self.assertTrue(len(tmpl) > 0)
            self.assertIn("{analysis_json}", tmpl)

        # 未知のタイプは general へフォールバック
        unknown_tmpl = composer._load_prompt_template("unknown_type")
        general_tmpl = composer._load_prompt_template("general")
        self.assertEqual(unknown_tmpl, general_tmpl)

    def test_checker_conversation_type_criteria(self):
        from core.checker import ConsistencyChecker
        from config import SummaryConfig
        from core.ollama_client import OllamaClient

        checker = ConsistencyChecker(config=SummaryConfig(), client=OllamaClient())

        # meeting固有チェック
        meeting_tmpl = checker._load_prompt_template("meeting")
        self.assertIn("決定事項の厳格性", meeting_tmpl)
        self.assertIn("タスク・担当者・期限の正確性", meeting_tmpl)

        # interview固有チェック
        interview_tmpl = checker._load_prompt_template("interview")
        self.assertIn("発言者と指摘の混同", interview_tmpl)

        # consultation固有チェック
        consultation_tmpl = checker._load_prompt_template("consultation")
        self.assertIn("相談課題と助言の峻別", consultation_tmpl)


if __name__ == "__main__":
    unittest.main()

