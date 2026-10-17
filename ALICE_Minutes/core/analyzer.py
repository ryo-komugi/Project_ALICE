"""
Stage 1 Analyzer for ALICE_Minute.
Structures conversation transcript into MinuteAnalysisResult using hybrid input:
Summary outline (agenda/timeline) + raw transcript facts.
"""
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import config
from core.models import MinuteAnalysisResult, Participant
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
        with open(self.prompt_path, "r", encoding="utf-8-sig") as f:
            return f.read().strip()

    def _determine_num_ctx(self, text_length: int, num_predict: int | None = None) -> int:
        """文字数と出力トークン上限から安全なコンテキスト長（num_ctx）を動的決定"""
        predict_margin = num_predict if num_predict is not None else config.stage1_num_predict
        # 日本語 1 文字 ≒ 1.5 トークン換算 + 出力トークン上限
        estimated_tokens = int(text_length * 1.5) + predict_margin
        if estimated_tokens <= config.ctx_threshold_standard:
            return config.num_ctx  # 32768
        elif estimated_tokens <= config.ctx_threshold_extended:
            return 49152
        else:
            return config.max_num_ctx  # 65536

    @staticmethod
    def _format_summary_guidance(summary_data: Dict[str, Any]) -> str:
        """ALICE_Summary の Stage 1 分析結果から議事録用の見取り図テキストを構築（全重要フィールドを活用）"""
        lines = ["### 先行モジュールによる会議見取り図 (Summary Outline):"]

        meta = summary_data.get("metadata", {})
        if isinstance(meta, dict):
            conv_type = meta.get("conversation_type")
            conv_cat = meta.get("conversation_category")
            is_target = meta.get("is_target_present")
            if conv_type:
                lines.append(f"- **会話種別**: {conv_type} (category={conv_cat}, is_target_present={is_target})")

        overview = summary_data.get("conversation_overview", {})
        if isinstance(overview, dict):
            if overview.get("purpose"):
                lines.append(f"- **会議目的**: {overview['purpose']}")
            if overview.get("background"):
                lines.append(f"- **背景**: {overview['background']}")

        speakers = summary_data.get("speakers_analysis", [])
        if speakers:
            lines.append("- **出席者と推定役割**:")
            for spk in speakers:
                if isinstance(spk, dict):
                    lines.append(
                        f"  - {spk.get('speaker_label')}: {spk.get('estimated_role', '不明')} "
                        f"({spk.get('basis', '')})"
                    )

        timeline = summary_data.get("timeline_sections", [])
        if timeline:
            lines.append("- **特定された時系列アジェンダ・セクション一覧**:")
            for idx, sec in enumerate(timeline, start=1):
                if not isinstance(sec, dict):
                    continue
                start = WorkspaceIO.normalize_timestamp_str(sec.get("start_time", "00:00"))
                end = WorkspaceIO.normalize_timestamp_str(sec.get("end_time", "00:00"))
                title = sec.get("section_title", f"議題 {idx}")
                lines.append(f"  {idx}. [{start} - {end}] {title}")
                if sec.get("interviewer_inquiry"):
                    lines.append(f"     ・問題提起/問いかけ: {sec['interviewer_inquiry']}")
                if sec.get("participant_initial_statement"):
                    lines.append(f"     ・回答/意見: {sec['participant_initial_statement']}")
                for c in sec.get("contradictions_and_evidence", []) or []:
                    lines.append(f"     ・指摘/客観事実: {c}")
                for u in sec.get("uncovered_facts_confession", []) or []:
                    lines.append(f"     ・判明した事実/実態: {u}")
                for d in sec.get("agreed_rules_and_decisions", []) or []:
                    lines.append(f"     ・合意方針: {d}")

        conclusions = summary_data.get("conclusions_and_actions", {})
        if isinstance(conclusions, dict):
            decisions = conclusions.get("decisions", []) or []
            if decisions:
                lines.append("- **Summary側で特定された全体決定事項**:")
                for d in decisions:
                    lines.append(f"  - {d}")
            next_actions = conclusions.get("next_actions", []) or []
            if next_actions:
                lines.append("- **Summary側で特定されたネクストアクション候補**:")
                for na in next_actions:
                    if isinstance(na, dict):
                        lines.append(
                            f"  - 担当: {na.get('actor', '関係者')} | 内容: {na.get('action', '')} "
                            f"| 期限/条件: {na.get('deadline_or_condition', '指定なし')}"
                        )

        uncertain = summary_data.get("uncertain_or_ambiguous_points", []) or []
        if uncertain:
            lines.append("- **未確定・保留・曖昧な点**:")
            for u in uncertain:
                lines.append(f"  - {u}")

        return "\n".join(lines)

    @staticmethod
    def post_process_analysis(
        result: MinuteAnalysisResult,
        segments: List[Dict[str, Any]],
        summary_analysis: Optional[Dict[str, Any]] = None,
    ) -> MinuteAnalysisResult:
        """
        Stage 1 出力後のプログラム検証・正規化:
        1. 実際に発話している SPEAKER_XX が participants から漏れている場合（面談対象者 SPEAKER_00 の脱落等）に補完
        2. display_name の重複解消（同名の参加者が複数いる場合は A, B 等を付与）および二重括弧の防止
        3. 本文・opinion・task・assignee に残存する生の SPEAKER_XX を display_name に自動置換
        4. タイムスタンプ文字列を累積 MM:SS に正規化
        """
        speaker_stats = WorkspaceIO.summarize_speakers(segments)
        summary_speaker_map: Dict[str, Dict[str, str]] = {}
        if isinstance(summary_analysis, dict):
            for sp in summary_analysis.get("speakers_analysis", []) or []:
                if isinstance(sp, dict) and sp.get("speaker_label"):
                    summary_speaker_map[str(sp["speaker_label"]).strip()] = {
                        "role": str(sp.get("estimated_role", "参加者")).strip(),
                        "basis": str(sp.get("basis", "音声発話より確認")).strip(),
                    }

        # 既知の SPEAKER_XX ラベルを収集
        covered_labels = set()
        for p in result.participants:
            for lbl in re.findall(r"SPEAKER_\d+", str(p.speaker_label)):
                covered_labels.add(lbl)

        # 発話が2回以上または5秒以上ある話者で participants に未登録の話者を補完
        for sp_label, st in sorted(speaker_stats.items()):
            if sp_label not in covered_labels and (st["count"] >= 2 or st["duration"] >= 5.0):
                sum_info = summary_speaker_map.get(sp_label, {})
                role = sum_info.get("role") or "参加者・発言者"
                basis = sum_info.get("basis") or f"計{st['count']}回（{st['duration']:.1f}秒）の発話を確認"
                result.participants.append(
                    Participant(
                        speaker_label=sp_label,
                        display_name=role.split("・")[0].split("（")[0].strip() or sp_label,
                        estimated_role=role,
                        basis=basis,
                    )
                )

        # display_name の整形と重複排除
        name_counts: Dict[str, int] = {}
        for p in result.participants:
            raw_name = (p.display_name or "").strip()
            if not raw_name or re.fullmatch(r"SPEAKER_\d+", raw_name):
                role_clean = re.sub(r"[（(].*?[）)]", "", p.estimated_role or "参加者").strip()
                raw_name = role_clean.split("・")[0].strip() or p.speaker_label
            # 既に括弧が含まれている場合は外す（テンプレート側の（{estimated_role}）との二重括弧を防止）
            raw_name = re.sub(r"[（(].*?[）)]", "", raw_name).strip() or raw_name
            p.display_name = raw_name
            name_counts[raw_name] = name_counts.get(raw_name, 0) + 1

        seen_counts: Dict[str, int] = {}
        label_to_name: Dict[str, str] = {}
        for p in result.participants:
            base_name = p.display_name or p.speaker_label
            if name_counts.get(base_name, 0) > 1:
                idx = seen_counts.get(base_name, 0)
                seen_counts[base_name] = idx + 1
                suffix = chr(ord("A") + idx) if idx < 26 else str(idx + 1)
                p.display_name = f"{base_name}{suffix}"
            # estimated_role 内の外側の括弧も除去して二重括弧を防ぐ
            if p.estimated_role:
                p.estimated_role = re.sub(r"^[（(](.*)[）)]$", r"\1", p.estimated_role.strip())

            for lbl in re.findall(r"SPEAKER_\d+", str(p.speaker_label)):
                label_to_name[lbl] = p.display_name

        def replace_speaker_labels(text: Optional[str]) -> Optional[str]:
            if not text:
                return text
            out = str(text)
            for lbl, disp in label_to_name.items():
                # "SPEAKER_01（指導担当者）" -> "指導担当者"
                out = re.sub(rf"{lbl}\s*[（(][^）)]*[）)]", disp, out)
                out = re.sub(rf"\b{lbl}\b", disp, out)
            return out

        # 各フィールドの SPEAKER_XX 置換 & タイムスタンプ正規化
        for ag in result.agenda_items:
            ag.agenda_title = replace_speaker_labels(ag.agenda_title) or ag.agenda_title
            ag.discussion_summary = replace_speaker_labels(ag.discussion_summary) or ag.discussion_summary
            ag.rationale = replace_speaker_labels(ag.rationale)
            if ag.time_range:
                parts = re.split(r"\s*[-〜~]\s*", ag.time_range.strip())
                if len(parts) == 2:
                    ag.time_range = f"{WorkspaceIO.normalize_timestamp_str(parts[0])} - {WorkspaceIO.normalize_timestamp_str(parts[1])}"
            ag.decisions = [replace_speaker_labels(d) or d for d in ag.decisions]
            for ko in ag.key_opinions:
                ko.speaker = replace_speaker_labels(ko.speaker) or ko.speaker
                ko.opinion = replace_speaker_labels(ko.opinion) or ko.opinion
                if ko.time_anchor:
                    ko.time_anchor = WorkspaceIO.normalize_timestamp_str(ko.time_anchor)

        for ai in result.action_items:
            ai.task = replace_speaker_labels(ai.task) or ai.task
            ai.assignee = replace_speaker_labels(ai.assignee) or ai.assignee
            ai.deliverable_or_condition = replace_speaker_labels(ai.deliverable_or_condition)
            if ai.time_context:
                ai.time_context = WorkspaceIO.normalize_timestamp_str(ai.time_context)

        result.confirmed_decisions = [replace_speaker_labels(d) or d for d in result.confirmed_decisions]
        for pt in result.pending_and_next_topics:
            pt.topic = replace_speaker_labels(pt.topic) or pt.topic
            pt.reason = replace_speaker_labels(pt.reason) or pt.reason
            pt.next_action = replace_speaker_labels(pt.next_action)

        return result

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
        speaker_stats = WorkspaceIO.summarize_speakers(segments)

        context_parts = [prompt_template]

        if speaker_stats:
            sp_lines = ["\n### 音声内で発話が確認された全話者統計（全員漏れなく participants に含めるか統合すること）:"]
            for sp_lbl, st in sorted(speaker_stats.items()):
                sp_lines.append(f"- {sp_lbl}: 発話 {st['count']}回（計 {st['duration']:.1f}秒） 例: 「{st['sample']}...」")
            context_parts.append("\n".join(sp_lines))

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
        num_ctx = self._determine_num_ctx(len(user_content), num_predict=config.stage1_num_predict)

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

        result = self.post_process_analysis(result, segments=segments, summary_analysis=summary_analysis)

        elapsed = time.time() - t0
        logger.info(f"[Analyzer] Stage 1 Ollama response received in {elapsed:.2f}s")
        return result, elapsed
