"""
Stage 2 Composer for ALICE_Minute.
Generates human-readable Markdown meeting minutes from MinuteAnalysisResult
using dynamic templates (standard, interview, executive, consultation, etc.).
"""
import json
import logging
import re
import time
from typing import Optional
from config import config
from core.models import MinuteAnalysisResult
from core.ollama_client import OllamaClient
from core.workspace_io import WorkspaceIO

logger = logging.getLogger(__name__)


class MinuteComposer:
    def __init__(self, client: Optional[OllamaClient] = None):
        self.client = client or OllamaClient(
            host=config.ollama_host,
            model=config.model_name,
            timeout=config.timeout_seconds,
            fallback_model=config.fallback_model,
        )

    @staticmethod
    def _clean_markdown_output(raw_text: str) -> str:
        """思考タグ残骸や不適切なマークダウン装飾をクリーンアップ"""
        text = raw_text.strip()

        # 思考タグの除去 (<thought>...</thought> または <think>...</think>)
        text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", text, flags=re.DOTALL).strip()

        # 外側の ```markdown ... ``` のみで全体が囲まれている場合は中身を展開
        match = re.match(r"^```(?:markdown)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        return text.strip()

    def run(
        self,
        analysis: MinuteAnalysisResult,
        template_name: str = "standard",
    ) -> tuple[str, float]:
        """
        MinuteAnalysisResult とテンプレート名を入力として Markdown 議事録文章を生成する。
        戻り値: (markdown_text, elapsed_seconds)
        """
        logger.info(f"[Composer] Starting Stage 2 composition (template: '{template_name}')...")
        t0 = time.time()

        template_content = WorkspaceIO.load_template(template_name)
        analysis_json_str = (
            analysis.model_dump_json(indent=2)
            if hasattr(analysis, "model_dump_json")
            else json.dumps(analysis.dict(), ensure_ascii=False, indent=2)
        )

        user_content = (
            f"{template_content}\n\n"
            f"=== 抽出済み議事録分析データ (Minute Analysis JSON) ===\n\n"
            f"{analysis_json_str}"
        )

        messages = [
            {
                "role": "user",
                "content": user_content,
            }
        ]

        logger.info(
            f"[Composer] Calling Ollama for Stage 2 with model '{self.client.model}' "
            f"(template='{template_name}', content_len={len(user_content)} chars)..."
        )
        try:
            content, thinking = self.client.chat(
                messages=messages,
                temperature=config.stage2_temperature,
                num_ctx=config.num_ctx,
                format_json=False,
                keep_alive="0",  # Stage 2 完了後は VRAM を即時解放
                think=config.stage2_think,
                num_predict=config.stage2_num_predict,
            )
        finally:
            # 確実に VRAM をアンロード
            self.client.unload_model()

        cleaned_content = self._clean_markdown_output(content)

        # 完了検証と末尾フレーズ（以上）の確実な付与
        has_final_section = bool(re.search(r"##\s*5\.", cleaned_content))
        has_closing_phrase = bool(re.search(r"（以上）|以上\s*$", cleaned_content.strip()))

        if has_final_section:
            if not has_closing_phrase:
                cleaned_content = cleaned_content.strip() + "\n\n---\n\n（以上）"
        else:
            logger.warning("[Composer] Output does not contain final section '## 5.'. Output was likely truncated!")

        elapsed = time.time() - t0
        logger.info(f"[Composer] Stage 2 completed in {elapsed:.2f}s (len={len(cleaned_content)} chars)")
        return cleaned_content, elapsed
