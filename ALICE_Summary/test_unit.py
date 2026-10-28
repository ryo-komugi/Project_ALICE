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

        speaker_summary = WorkspaceIO.summarize_speakers(segments)
        self.assertIn("SPEAKER_01", speaker_summary)
        self.assertIn("SPEAKER_02", speaker_summary)

    def test_markdown_to_plain_text(self):
        md = (
            "# 面談の目的と概要\n\n"
            "これは**テスト**です。\n\n"
            "---\n\n"
            "## 議題1\n"
            "### 1. サブセクション\n"
            "- 項目1\n"
            "  * ネスト項目A\n"
            "  * ネスト項目B\n"
        )
        plain = WorkspaceIO.markdown_to_plain_text(md)
        self.assertIn("■ 面談の目的と概要", plain)
        self.assertIn("これはテストです。", plain)
        self.assertIn("◆ 議題1", plain)
        self.assertIn("▸ 1. サブセクション", plain)
        self.assertIn("・項目1", plain)
        self.assertIn("  ・ネスト項目A", plain)
        self.assertIn("  ・ネスト項目B", plain)
        self.assertNotIn("**", plain)
        self.assertNotIn("---", plain)
        self.assertNotIn("#", plain)

    def test_clean_markdown_output(self):
        raw_md = (
            "承知いたしました。以下に要約レポートを作成します。\n\n"
            "---\n"
            "# 面談の目的と全体概要\n"
            "### N. 冒頭の確認（00:00〜02:00）\n"
            "### N. 課題の深掘り（02:00〜05:00）\n"
        )
        cleaned = WorkspaceIO.clean_markdown_output(raw_md)
        self.assertTrue(cleaned.startswith("# 面談の目的と全体概要"))
        self.assertIn("### 1. 冒頭の確認", cleaned)
        self.assertIn("### 2. 課題の深掘り", cleaned)
        self.assertNotIn("### N.", cleaned)

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

    def test_pydantic_model_validation_and_corrupted_keys(self):
        data = {
            "conversation_overview": {
                "purpose": "業務改善面談",
                "background": "前回の振り返り"
            },
            "timeline_sections": [
                {
                    "start_time": "00:00",
                    "end_time": "05:00",
                    "section_title": "進捗確認",
                    "contradictions_and_evidence": [None, "事実A", ""],
                    "agreed_#rules_and_decisions": ["新ルール1", None],
                }
            ],
            "uncertain_or_ambiguous_points": [None, "不明点1"],
            "topics": [
                {
                    "title": "遅刻の頻発について",
                    "issue": "月3回の遅刻",
                    "confirmed_facts": ["5月中に3回遅刻", None],
                    "participant_statements": ["目覚ましが鳴らなかった"],
                    "interviewer_statements": ["生活習慣の是正を要求"],
                    "evolution_and_resolution": "本人がアラーム増設に合意",
                    "agreed_points": ["今後遅刻ゼロを目指す"]
                }
            ]
        }
        model = AnalysisResult(**data)
        self.assertEqual(model.conversation_overview.purpose, "業務改善面談")
        self.assertEqual(len(model.timeline_sections), 1)
        self.assertEqual(model.timeline_sections[0].contradictions_and_evidence, ["事実A"])
        self.assertEqual(model.timeline_sections[0].agreed_rules_and_decisions, ["新ルール1"])
        self.assertEqual(model.uncertain_or_ambiguous_points, ["不明点1"])
        self.assertEqual(len(model.topics), 1)
        self.assertEqual(model.topics[0].confirmed_facts, ["5月中に3回遅刻"])

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

        # 1. 修正がある場合は修正版要約を採用
        raw_output_modified = (
            "# 整合性検証レポート\n"
            "- 発見された不整合・修正点: タイムスタンプの誤記を1箇所修正しました。\n"
            "- チェック基準別の判定結果: 基準3を修正。\n\n"
            "---\n\n"
            "# 最終修正版要約\n"
            "※ドラフトの完成度が高いため、微修正した版を提示します。\n\n"
            "# 面談（会話）の目的と全体概要\n"
            "これは修正された最終要約です。" + "あ" * 400
        )
        fallback = "# ドラフト要約\nフォールバック用ドラフト要約本文です。" + "い" * 400

        summary_part, report_part = ConsistencyChecker.parse_checker_output(raw_output_modified, fallback_draft=fallback)
        self.assertIn("整合性検証レポート", report_part)
        self.assertIn("これは修正された最終要約です", summary_part)
        self.assertNotIn("整合性検証レポート", summary_part)
        self.assertNotIn("※ドラフトの完成度が高いため", summary_part)

        # 2. 重大な不整合なしの場合はドラフトをそのまま保護
        raw_output_no_issue = (
            "# 整合性検証レポート\n"
            "- 発見された不整合・修正点: 重大な不整合なし（原文と完全に整合）\n"
            "- チェック基準別の判定結果: 全項目OK\n\n"
            "---\n\n"
            "# 最終修正版要約\n"
            "# 面談（会話）の目的と全体概要\n"
            "これは再出力された要約です。" + "う" * 400
        )
        summary_preserved, report_no_issue = ConsistencyChecker.parse_checker_output(raw_output_no_issue, fallback_draft=fallback)
        self.assertEqual(summary_preserved, fallback)
        self.assertIn("重大な不整合なし", report_no_issue)

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
            "metadata": {"conversation_type": "面談", "conversation_category": "interview", "is_target_present": True},
            "conversation_overview": {"purpose": "人事評価および今後のキャリア面談"},
            "timeline_sections": [{"section_title": "目標達成状況の確認"}]
        }
        self.assertEqual(Composer.detect_conversation_type(interview_data), "interview")

        # 2. 会議 (meeting) - 人事・改善キーワードが含まれていても定例会議や対象者不在会議は meeting になること
        meeting_data = {
            "metadata": {"conversation_type": "定例会議"},
            "conversation_overview": {"purpose": "週次進捗共有および人事評価制度の改善討議"},
            "timeline_sections": [{"section_title": "アジェンダ1: リリース判定と勤怠管理"}]
        }
        self.assertEqual(Composer.detect_conversation_type(meeting_data), "meeting")

        # 2b. 対象者不在の管理者間対策会議 (is_target_present=False)
        managers_meeting_data = {
            "metadata": {"conversation_type": "業務改善指導に関する対策協議", "conversation_category": "interview", "is_target_present": False},
            "conversation_overview": {"purpose": "対象者の指導方針に関する管理者間の事前協議"},
        }
        self.assertEqual(Composer.detect_conversation_type(managers_meeting_data), "meeting")

        # 3. 業務相談 (consultation)
        consultation_data = {
            "metadata": {"conversation_type": "業務相談"},
            "conversation_overview": {"purpose": "新機能の設計方針についての壁打ち・相談"},
            "timeline_sections": [{"section_title": "アーキテクチャの選定に関する助言"}]
        }
        self.assertEqual(Composer.detect_conversation_type(consultation_data), "consultation")

        # 4. 汎用 (general)
        general_data = {
            "metadata": {},
            "conversation_overview": {"purpose": "雑談および近況報告"},
            "timeline_sections": [{"section_title": "最近のニュースについて"}]
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
            self.assertFalse(tmpl.startswith("\ufeff"))

        # 未知のタイプは general へフォールバック
        unknown_tmpl = composer._load_prompt_template("unknown_type")
        general_tmpl = composer._load_prompt_template("general")
        self.assertEqual(unknown_tmpl, general_tmpl)

    def test_checker_conversation_type_criteria(self):
        from core.checker import ConsistencyChecker
        from config import SummaryConfig
        from core.ollama_client import OllamaClient

        checker = ConsistencyChecker(config=SummaryConfig(), client=OllamaClient())

        # meeting固有チェック（7, 8, 9 と連番になっていること）
        meeting_tmpl = checker._load_prompt_template("meeting")
        self.assertIn("7. 【決定事項の厳格性】", meeting_tmpl)
        self.assertIn("8. 【タスク・担当者・期限の正確性】", meeting_tmpl)
        self.assertIn("9. 【参加者意見の帰属】", meeting_tmpl)

        # interview固有チェック
        interview_tmpl = checker._load_prompt_template("interview")
        self.assertIn("7. 【評価と事実の混同】", interview_tmpl)
        self.assertIn("8. 【対象者と面談者の発言バランス】", interview_tmpl)

        # consultation固有チェック
        consultation_tmpl = checker._load_prompt_template("consultation")
        self.assertIn("7. 【相談課題と助言の峻別】", consultation_tmpl)
        self.assertIn("8. 【アイデアの決定化防止】", consultation_tmpl)

    def test_summary_config_thinking_and_predict_defaults(self):
        """SummaryConfig の各ステージ思考設定と出力トークン上限（12288）の検証"""
        from config import SummaryConfig
        cfg = SummaryConfig()
        self.assertFalse(cfg.think_stage1)
        self.assertTrue(cfg.think_stage2)
        self.assertFalse(cfg.think_stage3)
        self.assertTrue(cfg.think_commentary)
        self.assertEqual(cfg.num_predict_stage1, 4096)
        self.assertEqual(cfg.num_predict_stage2, 12288)
        self.assertEqual(cfg.num_predict_stage3, 6144)
        self.assertEqual(cfg.num_predict_commentary, 12288)

    def test_ollama_client_think_payload_and_tag_stripping(self):
        """OllamaClient が payload['think'] を送信し、<think>/<thought> タグを分離・除去する検証"""
        import unittest.mock
        client = OllamaClient()
        captured_payload = {}

        class FakeHTTPResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps({
                    "message": {
                        "content": "<think>deep reasoning here</think>\n# 要約タイトル\n本文です。",
                        "thinking": ""
                    },
                    "prompt_eval_count": 100,
                    "eval_count": 50,
                    "total_duration": 1000000000,
                    "load_duration": 100000000,
                }).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            nonlocal captured_payload
            captured_payload = json.loads(req.data.decode("utf-8"))
            return FakeHTTPResponse()

        with unittest.mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.chat(
                model="gemma4:12b",
                messages=[{"role": "user", "content": "test"}],
                think=True,
                num_predict=12288,
            )
            self.assertTrue(captured_payload.get("think"))
            self.assertEqual(captured_payload["options"]["num_predict"], 12288)
            self.assertEqual(resp.content, "# 要約タイトル\n本文です。")
            self.assertEqual(resp.thinking, "deep reasoning here")

    def test_stages_pass_expected_think_and_num_predict(self):
        """Analyzer, Composer, ConsistencyChecker, Commentator が期待通りの think と num_predict を渡す検証"""
        import unittest.mock
        from config import SummaryConfig
        from core.analyzer import Analyzer
        from core.composer import Composer
        from core.checker import ConsistencyChecker
        from core.commentator import Commentator
        from core.ollama_client import OllamaResponse

        cfg = SummaryConfig()
        mock_client = unittest.mock.MagicMock()

        # 1. Analyzer (think=False, num_predict=4096)
        mock_client.chat.return_value = OllamaResponse(
            content='{"conversation_overview": {"purpose": "テスト", "background": "背景"}, "topics": []}',
            thinking=None, prompt_eval_count=10, eval_count=10,
            total_duration_sec=0.1, load_duration_sec=0.0, raw_response={}
        )
        mock_client.extract_json_object.return_value = {
            "conversation_overview": {"purpose": "テスト", "background": "背景"},
            "topics": []
        }
        analyzer = Analyzer(cfg, mock_client)
        analyzer.analyze("[00:00] SPEAKER_01: テスト", model_name="gemma4:12b")
        s1_kwargs = mock_client.chat.call_args.kwargs
        self.assertFalse(s1_kwargs["think"])
        self.assertEqual(s1_kwargs["num_predict"], 4096)

        # 2. Composer (think=True, num_predict=12288)
        mock_client.reset_mock()
        mock_client.chat.return_value = OllamaResponse(
            content="# 面談の目的と全体概要\nテスト要約",
            thinking="stage2 thought", prompt_eval_count=10, eval_count=20,
            total_duration_sec=0.1, load_duration_sec=0.0, raw_response={}
        )
        composer = Composer(cfg, mock_client)
        composer.compose({"metadata": {"conversation_type": "面談"}}, model_name="gemma4:12b")
        s2_kwargs = mock_client.chat.call_args.kwargs
        self.assertTrue(s2_kwargs["think"])
        self.assertEqual(s2_kwargs["num_predict"], 12288)

        # 3. ConsistencyChecker (think=False, num_predict=6144)
        mock_client.reset_mock()
        mock_client.chat.return_value = OllamaResponse(
            content="# 整合性検証レポート\n- 発見された不整合・修正点: 重大な不整合なし",
            thinking=None, prompt_eval_count=10, eval_count=20,
            total_duration_sec=0.1, load_duration_sec=0.0, raw_response={}
        )
        checker = ConsistencyChecker(cfg, mock_client)
        checker.check_and_refine("[00:00] SPEAKER_01: テスト", "# 要約", model_name="gemma4:12b")
        s3_kwargs = mock_client.chat.call_args.kwargs
        self.assertFalse(s3_kwargs["think"])
        self.assertEqual(s3_kwargs["num_predict"], 6144)

        # 4. Commentator (think=True, num_predict=12288)
        mock_client.reset_mock()
        mock_client.chat.return_value = OllamaResponse(
            content="# 面談全体の総括\nテスト講評",
            thinking="commentary thought", prompt_eval_count=10, eval_count=20,
            total_duration_sec=0.1, load_duration_sec=0.0, raw_response={}
        )
        commentator = Commentator(cfg, mock_client)
        commentator.generate_commentary({"metadata": {}}, "# 要約", model_name="gemma4:12b")
        comm_kwargs = mock_client.chat.call_args.kwargs
        self.assertTrue(comm_kwargs["think"])
        self.assertEqual(comm_kwargs["num_predict"], 12288)


if __name__ == "__main__":
    unittest.main()

