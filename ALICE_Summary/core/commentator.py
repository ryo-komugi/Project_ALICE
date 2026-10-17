import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from core.ollama_client import OllamaClient, OllamaResponse
from core.workspace_io import WorkspaceIO
from config import SummaryConfig

logger = logging.getLogger(__name__)


class Commentator:
    """Stage 2-B: 面談・会議の総括および人物・指導講評（Commentary）を生成するエンジン"""

    def __init__(self, config: SummaryConfig, client: OllamaClient):
        self.config = config
        self.client = client
        self.prompts_dir = Path(__file__).resolve().parent.parent / "prompts"

    def _load_prompt_template(self, conv_type: str = "interview", analysis_data: Dict[str, Any] | None = None) -> str:
        # 対象者不在の会議（is_target_present == False）や meeting/consultation/general の場合は commentary_general を使用
        use_interview = (conv_type == "interview")
        if use_interview and isinstance(analysis_data, dict):
            meta = analysis_data.get("metadata", {})
            if isinstance(meta, dict) and meta.get("is_target_present") is False:
                use_interview = False

        target_name = "commentary_interview" if use_interview else "commentary_general"
        prompt_base = self.prompts_dir / target_name
        try:
            return WorkspaceIO.read_prompt_file(prompt_base)
        except FileNotFoundError:
            fallback_base = self.prompts_dir / "commentary_general"
            return WorkspaceIO.read_prompt_file(fallback_base)

    def generate_commentary(
        self,
        analysis_data: Dict[str, Any],
        draft_summary: str,
        model_name: str,
        num_ctx: int | None = None,
        keep_alive: str | int | None = None,
        conv_type: str = "interview",
    ) -> Tuple[str, OllamaResponse]:
        """分析データと要約ドラフトから解説・講評レポート（commentary_md）を生成する"""
        template = self._load_prompt_template(conv_type=conv_type, analysis_data=analysis_data)

        analysis_json_str = json.dumps(analysis_data, ensure_ascii=False, indent=2)
        prompt = template.replace("{analysis_json}", analysis_json_str).replace(
            "{draft_summary}", draft_summary.strip()
        )

        required_ctx = WorkspaceIO.calculate_dynamic_num_ctx(
            prompt, base_margin=self.config.num_predict_stage2 + 1024
        )
        effective_num_ctx = max(num_ctx or min(self.config.num_ctx, 32768), required_ctx)
        effective_keep_alive = keep_alive if keep_alive is not None else self.config.keep_alive

        messages = [
            {
                "role": "system",
                "content": "あなたは組織マネジメント、業務推進およびコミュニケーション力学分析のエキスパートAIです。提供された客観的分析データと要約に基づき、深い洞察を備えた実務的な分析・講評レポートを作成してください。前置きや挨拶は出力せず、直ちに指定のMarkdown見出しから開始してください。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        logger.info(f"[Commentator] Calling Ollama for Commentary with model '{model_name}' (type={conv_type}, num_ctx={effective_num_ctx})...")
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
        logger.info(f"[Commentator] Commentary Ollama response received in {elapsed:.2f}s")

        commentary_md = WorkspaceIO.clean_markdown_output(resp.content)
        return commentary_md, resp
