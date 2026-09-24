"""
Stage 1 Analyzer for ALICE_Minute.
Structures conversation transcript into MinuteAnalysisResult using hybrid input:
Summary outline (agenda/timeline) + raw transcript facts.
"""
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import config
from core.models import MinuteAnalysisResult
from core.ollama_client import OllamaClient
from core.workspace_io import WorkspaceIO

logger = logging.getLogger(__name__)


class MinuteAnalyzer:
    def __init__(self, client: Optional[OllamaClient] = None, prompt_path: Optional[Path] = None):
        self.client = client or OllamaClient(
            host=config.ollama_host,
            model=config.model_name,
            timeout=config.timeout_seconds,
            fallback_model=config.fallback_model,
        )
        self.prompt_path = prompt_path or (config.prompts_dir / "stage1_analysis.md")

    def _load_prompt_template(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"Stage 1 prompt template not found: {self.prompt_path}")
        with open(self.prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def _determine_num_ctx(self, text_length: int) -> int:
        """文字数から安全なコンテキスト長（num_ctx）を動的決定"""
        # 日本語 1 文字 ≒ 1.0 〜 1.5 トークン
        if text_length <= config.ctx_threshold_standard:
            return config.num_ctx  # 32768
        elif text_length <= config.ctx_threshold_extended:
            return 49152
        else:
            return config.max_num_ctx  # 65536

    @staticmethod
    def _format_summary_guidance(summary_data: Dict[str, Any]) -> str:
        """ALICE_Summary の Stage 1 分析結果から議事録用の見取り図テキストを構築"""
        lines = ["### 先行モジュールによる会議見取り図 (Summary Outline):"]

        overview = summary_data.get("conversation_overview", {})
        if overview.get("purpose"):
            lines.append(f"- **会議目的**: {overview['purpose']}")
        if overview.get("background"):
            lines.append(f"- **背景**: {overview['background']}")

        speakers = summary_data.get("speakers_analysis", [])
        if speakers:
            lines.append("- **出席者と推定役割**:")
            for spk in speakers:
                lines.append(
                    f"  - {spk.get('speaker_label')}: {spk.get('estimated_role', '不明')} "
                    f"({spk.get('basis', '')})"
                )

        timeline = summary_data.get("timeline_sections", [])
        if timeline:
            lines.append("- **特定された時系列アジェンダ・セクション一覧**:")
            for idx, sec in enumerate(timeline, start=1):
                start = sec.get("start_time", "00:00")
                end = sec.get("end_time", "00:00")
                title = sec.get("section_title", f"議題 {idx}")
                decisions = sec.get("agreed_rules_and_decisions", [])
                lines.append(f"  {idx}. [{start} - {end}] {title}")
                for d in decisions:
                    lines.append(f"     ・合意方針: {d}")

        return "\n".join(lines)

    def run(
        self,
        segments: List[Dict[str, Any]],
        summary_analysis: Optional[Dict[str, Any]] = None,
    ) -> tuple[MinuteAnalysisResult, float]:
        """
        セグメント一覧（生発話）と Summary 分析見取り図（存在する場合）から
        MinuteAnalysisResult を抽出し、処理時間(秒)とともに返す。
        """
        logger.info(
            f"[Analyzer] Starting Stage 1 analysis with {len(segments)} segments "
            f"(Summary guidance: {'YES' if summary_analysis else 'NO'})..."
        )
        t0 = time.time()

        prompt_template = self._load_prompt_template()
        formatted_transcript = WorkspaceIO.format_transcript_for_prompt(segments)

        context_parts = [prompt_template]

        if summary_analysis:
            summary_guidance = self._format_summary_guidance(summary_analysis)
            context_parts.append(
                f"\n{summary_guidance}\n\n"
                f"※ 上記の「Summary Outline」をアジェンダの骨格として尊重しつつ、"
                f"以下の一次文字起こしテキスト（Transcript）の発話内容から各議題の決定事項、"
                f"具体的アクションアイテム（TODO・担当・期日）、保留事項を漏れなく厳格抽出してください。"
            )

        context_parts.append(
            f"\n=== 対象の文字起こしデータ（Transcript） ===\n\n"
            f"{formatted_transcript}"
        )

        user_content = "\n".join(context_parts)
        num_ctx = self._determine_num_ctx(len(user_content))

        messages = [
            {
                "role": "user",
                "content": user_content,
            }
        ]

        logger.info(
            f"[Analyzer] Calling Ollama for Stage 1 with model '{self.client.model}' "
            f"(num_ctx={num_ctx}, content_len={len(user_content)} chars)..."
        )
        result = self.client.chat_structured(
            messages=messages,
            schema_class=MinuteAnalysisResult,
            temperature=config.stage1_temperature,
            num_ctx=num_ctx,
            keep_alive=config.keep_alive,
            think=config.stage1_think,
            num_predict=config.stage1_num_predict,
        )

        elapsed = time.time() - t0
        logger.info(f"[Analyzer] Stage 1 Ollama response received in {elapsed:.2f}s")
        return result, elapsed
