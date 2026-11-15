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
        """思考タグ残骸、プロンプト注釈の写し取り、タイポ、二重括弧等をクリーンアップ"""
        text = raw_text.strip()

        # 1. 思考タグの除去 (<thought>...</thought> または <think>...</think>)
        text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", text, flags=re.DOTALL).strip()

        # 2. 外側の ```markdown ... ``` のみで全体が囲まれている場合は中身を展開
        match = re.match(r"^```(?:markdown|md)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # 3. 冒頭の会話的な前置き除去
        lines = text.splitlines()
        while lines:
            first = lines[0].strip()
            if not first or first == "---":
                lines.pop(0)
                continue
            if re.match(r"^(承知|かしこまり|了解|はい、|以下に|提供された|ご提示|分析データに基づき)", first):
                lines.pop(0)
                continue
            break
        text = "\n".join(lines).strip()

        # 4. テンプレート内の注釈行 `（※ ...）` がそのまま出力されてしまった場合に除去
        text = re.sub(r"^\s*[（(]※[^）)\n]*[）)]\s*\n?", "", text, flags=re.MULTILINE)

        # 5. よくあるLLMの誤字・見出し番号欠落・二重括弧の補正
        text = text.replace("言語タイムスタンプ", "言及タイムスタンプ")
        text = re.sub(r"^##\s*\.\s*(アクションアイテム|改善アクション|執行アクション)", r"## 3. \1", text, flags=re.MULTILINE)
        text = re.sub(r"（([^（）]+)）（\1）", r"（\1）", text)
        text = re.sub(r"\(([^()]+)\)\(\1\)", r"(\1)", text)

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
            "### 議題ごとの簡潔化ルール（必ず適用）\n"
            "- 各議題の審議・協議セクションには、確定した決定事項と、その背景・理由だけを簡潔に記載してください。\n"
            "- 決定事項は分析データの decisions、背景・理由は rationale を優先し、議題ごとに最大2項目を目安にしてください。\n"
            "- 詳細な発言、意見の応酬、時系列の説明、長い議論要約は本文に含めないでください。これらはフォームの [補足事項] に出力します。\n"
            "- 決定がない議題は決定がないと明記し、検討中・保留の内容を決定事項として書かないでください。\n"
            "- 背景・理由が分析データにない場合は推測で補わず、省略してください。\n\n"
            f"=== 抽出済み議事録分析データ (Minute Analysis JSON) ===\n\n"
            f"{analysis_json_str}"
        )

        # 入力プロンプト + 出力上限から必要な num_ctx を算出
        estimated_tokens = int(len(user_content) * 1.5) + config.stage2_num_predict
        if estimated_tokens <= config.ctx_threshold_standard:
            effective_num_ctx = config.num_ctx
        elif estimated_tokens <= config.ctx_threshold_extended:
            effective_num_ctx = 49152
        else:
            effective_num_ctx = config.max_num_ctx

        messages = [
            {
                "role": "user",
                "content": user_content,
            }
        ]

        logger.info(
            f"[Composer] Calling Ollama for Stage 2 with model '{self.client.model}' "
            f"(template='{template_name}', num_ctx={effective_num_ctx}, content_len={len(user_content)} chars)..."
        )
        content, thinking = self.client.chat(
            messages=messages,
            temperature=config.stage2_temperature,
            num_ctx=effective_num_ctx,
            format_json=False,
            keep_alive="0",  # Stage 2 完了と同時に Ollama 側で VRAM を即時解放
            think=config.stage2_think,
            num_predict=config.stage2_num_predict,
        )

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
