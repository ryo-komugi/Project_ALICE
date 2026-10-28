import time
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from core.ollama_client import OllamaClient, OllamaResponse
from core.models import AnalysisResult
from core.workspace_io import WorkspaceIO
from config import SummaryConfig

logger = logging.getLogger(__name__)


class Analyzer:
    """Stage 1: 会話理解・構造化を担当するエンジン"""

    def __init__(self, config: SummaryConfig, client: OllamaClient):
        self.config = config
        self.client = client
        self.prompt_template_base = Path(__file__).resolve().parent.parent / "prompts" / "stage1_analysis"

    def _load_prompt_template(self) -> str:
        return WorkspaceIO.read_prompt_file(self.prompt_template_base)

    def analyze(
        self,
        formatted_transcript: str,
        model_name: str,
        num_ctx: int | None = None,
        segments: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], OllamaResponse]:
        """Transcript テキストを構造化分析し、analysis.json 用の辞書とメトリクスを返す"""
        template = self._load_prompt_template()

        speaker_summary = WorkspaceIO.summarize_speakers(segments) if segments else ""
        if "{speaker_summary}" in template:
            prompt = template.replace("{speaker_summary}", speaker_summary or "（集計情報なし）").replace(
                "{transcript}", formatted_transcript
            )
        elif speaker_summary:
            prompt = template.replace(
                "{transcript}",
                f"【発話が確認された全話者一覧（全員漏れなく speakers_analysis に含めること）】\n{speaker_summary}\n\n{formatted_transcript}",
            )
        else:
            prompt = template.replace("{transcript}", formatted_transcript)

        # 全プロンプト長 + 出力上限から必要な num_ctx を再計算し、指定 num_ctx との大きい方を採用
        required_ctx = WorkspaceIO.calculate_dynamic_num_ctx(
            prompt, base_margin=self.config.num_predict_stage1 + 1024
        )
        effective_num_ctx = max(num_ctx or self.config.num_ctx, required_ctx)

        messages = [
            {
                "role": "system",
                "content": "あなたは高度な会話分析・情報構造化の専門家です。指示されたJSONスキーマに従い、文字起こし内の客観的事実と各話者の発言・認識のみを厳格に区別して正確に構造化してください。文字起こしにない事例や文脈を絶対に混入させないでください。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        logger.info(f"[Analyzer] Calling Ollama with model '{model_name}' (num_ctx={effective_num_ctx})...")
        t0 = time.time()
        fallback = self.config.fallback_model if self.config.enable_fallback else None
        resp = self.client.chat(
            model=model_name,
            messages=messages,
            format_json=True,
            temperature=self.config.temperature_stage1,
            num_ctx=effective_num_ctx,
            num_predict=self.config.num_predict_stage1,
            repeat_penalty=self.config.repeat_penalty,
            timeout_sec=self.config.timeout_sec,
            keep_alive=self.config.keep_alive,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            backoff_factor=self.config.backoff_factor,
            fallback_model=fallback,
            think=self.config.think_stage1,
        )
        elapsed = time.time() - t0
        logger.info(f"[Analyzer] Stage 1 Ollama response received in {elapsed:.2f}s")

        # JSON 抽出
        raw_json_dict = self.client.extract_json_object(resp.content)

        # Pydantic による検証と正規化
        try:
            validated_model = AnalysisResult(**raw_json_dict)
            structured_data = validated_model.model_dump()
        except Exception as e:
            logger.warning(f"[Analyzer] Pydantic validation partial warning: {e}. Using raw parsed json.")
            structured_data = raw_json_dict

        return structured_data, resp
