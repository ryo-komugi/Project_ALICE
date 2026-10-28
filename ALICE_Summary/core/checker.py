import time
import re
import logging
from pathlib import Path
from typing import Tuple
from core.ollama_client import OllamaClient, OllamaResponse
from core.workspace_io import WorkspaceIO
from config import SummaryConfig

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """Stage 3: 原文文字起こしとドラフト要約の整合性検証・精密監査・修正を担当するエンジン"""

    def __init__(self, config: SummaryConfig, client: OllamaClient):
        self.config = config
        self.client = client
        self.prompt_template_base = Path(__file__).resolve().parent.parent / "prompts" / "stage3_consistency"

    TYPE_SPECIFIC_CRITERIA = {
        "interview": [
            "【評価と事実の混同】: 面談者の主観的指導・評価や仮定の質問が、対象者本人の発言や客観的事実として書かれていないか。",
            "【対象者と面談者の発言バランス】: 面談側の発言だけでなく、対象者本人の説明・意見・合意内容も公平に反映されているか。",
        ],
        "meeting": [
            "【決定事項の厳格性】: 会議で合意・承認されていない個人の意見や提案が「決定事項」として書かれていないか。",
            "【タスク・担当者・期限の正確性】: ネクストアクション（誰が・何を・いつまでに）の担当者名や期限が原文発言と一致しているか。",
            "【参加者意見の帰属】: 参加者の意見・懸念が正しくその発言者に紐付いているか。",
        ],
        "consultation": [
            "【相談課題と助言の峻別】: 相談者が抱える課題・悩みと、助言者が提案したアイデアが明確に区別されているか。",
            "【アイデアの決定化防止】: ブレストや検討段階のアイデアが確定方針のように書かれていないか。",
        ],
        "general": [
            "【全体文脈の維持】: 会話の背景・論点・次回予定が偏りなく客観的に要約されているか。",
        ],
    }

    def _load_prompt_template(self, conv_type: str = "general") -> str:
        base_template = WorkspaceIO.read_prompt_file(self.prompt_template_base)

        criteria = self.TYPE_SPECIFIC_CRITERIA.get(conv_type, self.TYPE_SPECIFIC_CRITERIA["general"])
        extra_criteria_text = "\n".join([f"{idx}. {c}" for idx, c in enumerate(criteria, start=7)])
        if "{extra_criteria}" in base_template:
            return base_template.replace("{extra_criteria}", extra_criteria_text)
        if "6. 【雑談やたとえ話の混入】:" in base_template:
            return re.sub(
                r"(6\.\s*【雑談やたとえ話の混入】:[^\n]*\n\s*-\s*[^\n]*)",
                r"\1\n" + extra_criteria_text,
                base_template,
                count=1,
            )
        return base_template + "\n" + extra_criteria_text

    def check_and_refine(
        self,
        formatted_transcript: str,
        draft_summary: str,
        model_name: str,
        num_ctx: int | None = None,
        conv_type: str = "general",
        keep_alive: str | int | None = None,
    ) -> Tuple[str, str, OllamaResponse]:
        """元の文字起こしとドラフト要約を対照し、(final_summary_md, report_md, response) を返す"""
        template = self._load_prompt_template(conv_type=conv_type)
        prompt = template.replace("{draft_summary}", draft_summary.strip()).replace(
            "{transcript}", formatted_transcript.strip()
        )

        required_ctx = WorkspaceIO.calculate_dynamic_num_ctx(
            prompt, base_margin=self.config.num_predict_stage3 + 1024
        )
        effective_num_ctx = max(num_ctx or self.config.num_ctx, required_ctx)
        effective_keep_alive = keep_alive if keep_alive is not None else self.config.keep_alive

        messages = [
            {
                "role": "system",
                "content": "あなたは要約文書の正確性と原文整合性を担保する最高品質の校正・監査専門AIです。元の文字起こしと照合し、事実の歪曲や重要事項の欠落を厳格にチェックしてください。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        logger.info(f"[ConsistencyChecker] Calling Ollama for Stage 3 with model '{model_name}' (num_ctx={effective_num_ctx})...")
        t0 = time.time()
        fallback = self.config.fallback_model if self.config.enable_fallback else None
        resp = self.client.chat(
            model=model_name,
            messages=messages,
            format_json=False,
            temperature=self.config.temperature_stage3,
            num_ctx=effective_num_ctx,
            num_predict=self.config.num_predict_stage3,
            repeat_penalty=self.config.repeat_penalty,
            timeout_sec=self.config.timeout_sec,
            keep_alive=effective_keep_alive,
            max_retries=self.config.max_retries,
            retry_delay=self.config.retry_delay,
            backoff_factor=self.config.backoff_factor,
            fallback_model=fallback,
            think=self.config.think_stage3,
        )
        elapsed = time.time() - t0
        logger.info(f"[ConsistencyChecker] Stage 3 Ollama response received in {elapsed:.2f}s")

        raw_content = resp.content.strip()

        # レポート部分と最終修正版要約部分を分離
        final_summary, report = self.parse_checker_output(raw_content, fallback_draft=draft_summary)

        return final_summary, report, resp

    @staticmethod
    def _has_no_factual_issues(report_part: str) -> bool:
        """検証レポートに『重大な不整合なし』『修正不要』と明記され、実質的な修正指摘がないか判定する"""
        if not report_part:
            return False
        # 発見された不整合・修正点 の行を抽出
        m = re.search(r"発見された不整合・修正点\s*[:：]\s*([^\n]+)", report_part)
        if m:
            finding_line = m.group(1).strip()
            if any(kw in finding_line for kw in ["重大な不整合なし", "不整合なし", "修正点なし", "特になし", "問題なし", "修正不要"]):
                # 他に「要修正」「誤り」「捏造」等の指摘がなければドラフト無修正採用が可能
                if not any(err in report_part for err in ["要修正", "修正しました", "削除しました", "訂正しました"]):
                    return True
        return False

    @classmethod
    def parse_checker_output(cls, raw_output: str, fallback_draft: str) -> Tuple[str, str]:
        """チェッカーの出力から『整合性検証レポート』と『最終修正版要約』を分離する"""
        text = raw_output.strip()

        # コードブロックで囲まれている場合の剥離
        if text.startswith("```markdown") and text.endswith("```"):
            text = text[len("```markdown") : -3].strip()
        elif text.startswith("```md") and text.endswith("```"):
            text = text[len("```md") : -3].strip()
        elif text.startswith("```") and text.endswith("```"):
            text = text[3:-3].strip()

        # 「# 最終修正版要約」または類似見出しの位置を探索
        split_patterns = [
            r"#+\s*最終修正版要約",
            r"#+\s*最終修正要約",
            r"#+\s*修正後の要約",
            r"#+\s*最終版要約",
        ]

        split_idx = -1
        matched_span = (0, 0)
        for pattern in split_patterns:
            m = re.search(pattern, text)
            if m:
                split_idx = m.start()
                matched_span = m.span()
                break

        if split_idx != -1:
            report_part = text[:split_idx].strip()
            summary_part = text[matched_span[1] :].strip()

            # 要約冒頭の「※ドラフトの完成度が高いため...」等の注釈行や区切り線があれば整頓
            lines = summary_part.splitlines()
            while lines:
                first = lines[0].strip()
                if not first or first == "---" or first.startswith("※") or first.startswith("（"):
                    lines.pop(0)
                else:
                    break
            summary_part = WorkspaceIO.clean_markdown_output("\n".join(lines))

            # 重大な不整合なし（修正不要）と判定された場合は、Stage 2 ドラフトをそのまま採用して再生成劣化を防ぐ
            if fallback_draft and cls._has_no_factual_issues(report_part):
                logger.info("[ConsistencyChecker] Report indicates no factual issues; preserving draft_summary without regeneration drift.")
                return fallback_draft, report_part

            # 「変更なし」「同上」等の省略出力または極端に短い場合は fallback_draft をそのまま維持
            if len(summary_part) < 300 or (fallback_draft and len(summary_part) < len(fallback_draft) * 0.5):
                logger.info("[ConsistencyChecker] Summary part omitted or shorter than threshold; preserving draft_summary.")
                return fallback_draft, report_part

            return summary_part, report_part
        else:
            # 分割見出しが見つからない場合（レポートのみ出力された場合を含む）
            logger.info("[ConsistencyChecker] No split header found; preserving draft_summary and saving output as report.")
            return fallback_draft, text
