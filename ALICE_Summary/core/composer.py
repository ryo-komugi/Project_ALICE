import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from core.ollama_client import OllamaClient, OllamaResponse
from config import SummaryConfig

logger = logging.getLogger(__name__)


class Composer:
    """Stage 2: 構造化データからの高品質な要約文章化を担当するエンジン"""

    VALID_TYPES = ("interview", "meeting", "consultation", "general")

    def __init__(self, config: SummaryConfig, client: OllamaClient):
        self.config = config
        self.client = client
        self.prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        self.templates_dir = self.prompts_dir / "templates"

    @staticmethod
    def detect_conversation_type(analysis_data: Dict[str, Any]) -> str:
        """analysis_data から最適な会話タイプ（interview / meeting / consultation / general）を自動判定する"""
        text_corpus = []

        meta = analysis_data.get("metadata", {})
        if isinstance(meta, dict) and meta.get("conversation_type"):
            text_corpus.append(str(meta.get("conversation_type")))

        overview = analysis_data.get("conversation_overview", {})
        if isinstance(overview, dict):
            text_corpus.append(str(overview.get("purpose", "")))
            text_corpus.append(str(overview.get("background", "")))

        speakers = analysis_data.get("speakers_analysis", [])
        if isinstance(speakers, list):
            for sp in speakers:
                if isinstance(sp, dict):
                    text_corpus.append(str(sp.get("estimated_role", "")))

        topics = analysis_data.get("topics", [])
        if isinstance(topics, list):
            for tp in topics:
                if isinstance(tp, dict):
                    text_corpus.append(str(tp.get("title", "")))
                    text_corpus.append(str(tp.get("issue", "")))

        full_text = " ".join(text_corpus)

        interview_keywords = ["面談", "指導", "評価", "1on1", "ヒアリング", "証言", "人事", "改善", "遅刻", "勤怠", "処分", "警告", "内省"]
        meeting_keywords = ["会議", "定例", "ミーティング", "打ち合わせ", "進捗", "プロジェクト", "レビュー", "アジェンダ", "議事"]
        consultation_keywords = ["相談", "壁打ち", "ブレスト", "アドバイス", "悩み", "検討", "アイデア", "提案"]

        interview_score = sum(full_text.count(k) for k in interview_keywords)
        meeting_score = sum(full_text.count(k) for k in meeting_keywords)
        consultation_score = sum(full_text.count(k) for k in consultation_keywords)

        scores = [
            ("interview", interview_score),
            ("meeting", meeting_score),
            ("consultation", consultation_score),
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        best_type, best_score = scores[0]
        if best_score > 0:
            return best_type
        return "general"

    def _load_prompt_template(self, conv_type: str = "interview") -> str:
        from core.workspace_io import WorkspaceIO

        if conv_type not in self.VALID_TYPES:
            conv_type = "general"

        template_base = self.templates_dir / f"stage2_{conv_type}"
        try:
            return WorkspaceIO.read_prompt_file(template_base)
        except FileNotFoundError:
            pass

        fallback_base = self.prompts_dir / "stage2_composition"
        return WorkspaceIO.read_prompt_file(fallback_base)

    def compose(
        self,
        analysis_data: Dict[str, Any],
        model_name: str,
        num_ctx: int | None = None,
        keep_alive: str | int | None = None,
        conv_type: str = "auto",
    ) -> Tuple[str, OllamaResponse, str]:
        """analysis_data (dict) を入力として要約 Markdown 文章を生成する"""
        if conv_type == "auto" or not conv_type:
            applied_type = self.detect_conversation_type(analysis_data)
        elif conv_type in self.VALID_TYPES:
            applied_type = conv_type
        else:
            logger.warning(f"Unknown conversation type '{conv_type}'. Falling back to 'general'.")
            applied_type = "general"

        logger.info(f"[Composer] Selected conversation template: '{applied_type}' (requested: '{conv_type}')")
        template = self._load_prompt_template(applied_type)

        analysis_json_str = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        prompt = template.replace("{analysis_json}", analysis_json_str)

        effective_num_ctx = num_ctx or min(self.config.num_ctx, 32768)
        effective_keep_alive = keep_alive if keep_alive is not None else self.config.keep_alive

        messages = [
            {
                "role": "system",
                "content": "あなたは高品質なビジネス文書および会話分析レポートを作成するAIです。提供された分析データのみに基づき、事実・認識・指摘の区別や着地点が明確に伝わる自然な日本語の文章を作成してください。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        logger.info(f"[Composer] Calling Ollama for Stage 2 with model '{model_name}' (type={applied_type}, num_ctx={effective_num_ctx})...")
        t0 = time.time()
        fallback = self.config.fallback_model if self.config.enable_fallback else None
        resp = self.client.chat(
            model=model_name,
            messages=messages,
            format_json=False,
            temperature=self.config.temperature_stage2,
            num_ctx=effective_num_ctx,
            num_predict=self.config.num_predict_stage2,
            repeat_penalty=self.config.repeat_penalty,
            timeout_sec=self.config.timeout_sec,
            keep_alive=effective_keep_alive,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            backoff_factor=self.config.backoff_factor,
            fallback_model=fallback,
        )
        elapsed = time.time() - t0
        logger.info(f"[Composer] Stage 2 Ollama response received in {elapsed:.2f}s")

        summary_md = resp.content.strip()

        # もしMarkdownコードブロックで全体が囲まれている場合は剥がす
        if summary_md.startswith("```markdown") and summary_md.endswith("```"):
            summary_md = summary_md[len("```markdown") : -3].strip()
        elif summary_md.startswith("```md") and summary_md.endswith("```"):
            summary_md = summary_md[len("```md") : -3].strip()

        return summary_md, resp, applied_type
