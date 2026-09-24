import time
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from core.ollama_client import OllamaClient, OllamaResponse
from core.models import AnalysisResult
from config import SummaryConfig

logger = logging.getLogger(__name__)


class Analyzer:
    """Stage 1: 会話理解・構造化を担当するエンジン"""

    def __init__(self, config: SummaryConfig, client: OllamaClient):
        self.config = config
        self.client = client
        self.prompt_template_base = Path(__file__).resolve().parent.parent / "prompts" / "stage1_analysis"

    def _load_prompt_template(self) -> str:
        from core.workspace_io import WorkspaceIO
        return WorkspaceIO.read_prompt_file(self.prompt_template_base)

    def analyze(
        self, formatted_transcript: str, model_name: str, num_ctx: int | None = None
    ) -> Tuple[Dict[str, Any], OllamaResponse]:
        """Transcript テキストを構造化分析し、analysis.json 用の辞書とメトリクスを返す"""
        template = self._load_prompt_template()
        prompt = template.replace("{transcript}", formatted_transcript)

        effective_num_ctx = num_ctx or self.config.num_ctx

        messages = [
            {
                "role": "system",
                "content": "あなたは高度な会話分析・情報構造化の専門家です。指示されたJSONスキーマに従い、客観的事実と各話者の認識を峻別して正確に構造化してください。",
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
