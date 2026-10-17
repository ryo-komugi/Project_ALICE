"""
Pipeline Orchestrator for ALICE_Minute.
Executes two-stage meeting minutes generation:
  Stage 1: Transcript (+ Summary Outline) -> analysis.json (Structuring)
  Stage 2: analysis.json + Template -> minutes.md / minutes.txt (Composition)
"""
from datetime import datetime
import gc
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional

from config import config
from core.analyzer import MinuteAnalyzer
from core.composer import MinuteComposer
from core.models import MinuteAnalysisResult
from core.ollama_client import OllamaClient
from core.workspace_io import WorkspaceIO
from version import FULL_VERSION

logger = logging.getLogger(__name__)


def _free_memory() -> None:
    """CPU/GPU メモリを明示的に解放"""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


class MinutePipeline:
    VALID_TEMPLATES = ("standard", "interview", "executive", "consultation")

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        model: Optional[str] = None,
    ):
        self.target_model = model or config.model_name
        self.client = client or OllamaClient(
            host=config.ollama_host,
            model=self.target_model,
            timeout=config.timeout_seconds,
            fallback_model=config.fallback_model,
        )

    @classmethod
    def resolve_template_name(
        cls,
        requested_template: str,
        analysis_result: Optional[MinuteAnalysisResult] = None,
        summary_analysis: Optional[Dict[str, Any]] = None,
        workspace_path: Optional[Path] = None,
    ) -> str:
        """
        template_name が 'auto' の場合、Summary のメタデータおよび Stage 1 の meeting_type・参加者構成から
        最適なテンプレート（standard / interview / consultation / executive）を自動決定する。
        """
        if requested_template and requested_template != "auto" and requested_template in cls.VALID_TEMPLATES:
            return requested_template

        # 1. summary/metadata.json または summary/analysis.json の判定結果を確認
        if isinstance(summary_analysis, dict):
            meta = summary_analysis.get("metadata", {})
            if isinstance(meta, dict):
                # 対象者不在の会議なら standard (meeting)
                if meta.get("is_target_present") is False:
                    return "standard"
                cat = str(meta.get("conversation_category", "")).strip().lower()
                if cat == "interview":
                    return "interview"
                elif cat == "consultation":
                    return "consultation"
                elif cat == "meeting":
                    return "standard"

        if workspace_path:
            sum_meta_path = workspace_path / "summary" / "metadata.json"
            if sum_meta_path.exists():
                try:
                    sum_meta = json.loads(sum_meta_path.read_text(encoding="utf-8-sig"))
                    c_type = str(sum_meta.get("conversation_type", "")).strip().lower()
                    if c_type == "interview":
                        return "interview"
                    elif c_type == "consultation":
                        return "consultation"
                    elif c_type == "meeting":
                        return "standard"
                except Exception:
                    pass

        # 2. Stage 1 の MinuteAnalysisResult.meeting_overview.meeting_type から判定
        if analysis_result and analysis_result.meeting_overview:
            m_type = str(analysis_result.meeting_overview.meeting_type or "").lower()
            title = str(analysis_result.meeting_overview.title or "").lower()
            combined = f"{m_type} {title}"
            if any(k in combined for k in ["役員", "経営", "取締役", "executive"]):
                return "executive"
            if any(k in combined for k in ["相談", "壁打ち", "consultation"]):
                return "consultation"
            if any(k in combined for k in ["面談", "1on1", "ヒアリング", "interview"]):
                # 会議・定例が含まれている場合は standard を優先
                if not any(m in combined for m in ["会議", "定例", "打ち合わせ", "ミーティング"]):
                    return "interview"

        return "standard"

    def run(
        self,
        workspace_dir: Path | str,
        template_name: str = "auto",
        stage2_only: bool = False,
        force_stage1: bool = False,
    ) -> Dict[str, Any]:
        """
        議事録パイプラインの実行。
        戻り値: 生成された成果物情報と実行メトリクス
        """
        workspace_path = Path(workspace_dir).resolve()
        start_total_time = time.time()

        logger.info(f"Starting {FULL_VERSION} pipeline for workspace: {workspace_path}")
        logger.info(
            f"Target model: {self.target_model}, requested_template: '{template_name}', "
            f"stage2_only: {stage2_only}, force_stage1: {force_stage1}"
        )

        analysis_result: Optional[MinuteAnalysisResult] = None
        stage1_elapsed: float = 0.0
        resolved_template = template_name if template_name != "auto" else "standard"

        try:
            minutes_dir = WorkspaceIO.get_minutes_dir(workspace_path)
            analysis_path = minutes_dir / "analysis.json"
            summary_analysis_path = WorkspaceIO.get_summary_analysis_path(workspace_path)
            summary_analysis = WorkspaceIO.load_summary_analysis(workspace_path)

            # 既存の minutes/analysis.json よりも新しい summary/analysis.json が存在する場合はキャッシュ無効化
            cache_stale = False
            if analysis_path.exists() and summary_analysis_path.exists():
                try:
                    if summary_analysis_path.stat().st_mtime > analysis_path.stat().st_mtime:
                        logger.info(
                            f"Detected newer {summary_analysis_path} than {analysis_path}. "
                            f"Invalidating cached Stage 1 analysis to incorporate Summary outline."
                        )
                        cache_stale = True
                except Exception:
                    pass

            # ----------------------------------------------------
            # Stage 1: Conversation Understanding & Structuring
            # ----------------------------------------------------
            if stage2_only:
                logger.info("Skipping Stage 1 (--stage2-only). Loading existing analysis.json...")
                analysis_result = WorkspaceIO.load_stage1_analysis(workspace_path)
            elif analysis_path.exists() and not force_stage1 and not cache_stale:
                logger.info(f"Found existing {analysis_path}. Reusing Stage 1 analysis (use --force-stage1 to re-run)...")
                analysis_result = WorkspaceIO.load_stage1_analysis(workspace_path)
            else:
                logger.info("Loading transcript.json...")
                segments = WorkspaceIO.load_transcript(workspace_path)
                logger.info(f"Loaded {len(segments)} segments.")

                if summary_analysis:
                    logger.info("Summary outline found! Using hybrid guidance for Stage 1.")
                else:
                    logger.info("No summary outline found. Running Stage 1 from raw transcript.")

                logger.info("Executing Stage 1 (Analyzer: Meeting Minutes Structuring)...")
                analyzer = MinuteAnalyzer(client=self.client)
                analysis_result, stage1_elapsed = analyzer.run(
                    segments=segments,
                    summary_analysis=summary_analysis,
                )

                logger.info(f"Stage 1 completed in {stage1_elapsed:.2f}s. Saving analysis.json...")
                saved_analysis_path = WorkspaceIO.save_stage1_analysis(workspace_path, analysis_result)
                logger.info(f"Saved: {saved_analysis_path}")

            # テンプレート自動解決
            resolved_template = self.resolve_template_name(
                requested_template=template_name,
                analysis_result=analysis_result,
                summary_analysis=summary_analysis,
                workspace_path=workspace_path,
            )
            logger.info(f"Resolved template: '{resolved_template}' (requested: '{template_name}')")

            # ----------------------------------------------------
            # Stage 2: Human-Readable Minutes Generation
            # ----------------------------------------------------
            logger.info(f"Executing Stage 2 (Composer: Minutes Generation with template '{resolved_template}')...")
            composer = MinuteComposer(client=self.client)
            markdown_content, stage2_elapsed = composer.run(
                analysis=analysis_result,
                template_name=resolved_template,
            )

            total_elapsed = time.time() - start_total_time
            logger.info(f"Stage 2 completed in {stage2_elapsed:.2f}s. Saving minutes.md and minutes.txt...")

            is_complete = bool(re.search(r"（以上）|以上\s*$", markdown_content.strip()))
            if not is_complete:
                logger.warning("[ALICE_Minute] Generated minutes does not end with '（以上）'. Truncation may have occurred.")

            metadata = {
                "module": "ALICE_Minute",
                "version": "0.2.0",
                "status": "COMPLETED",
                "model": self.target_model,
                "template": resolved_template,
                "requested_template": template_name,
                "summary_guidance_used": bool(summary_analysis),
                "created_at": datetime.now().isoformat(),
                "is_complete": is_complete,
                "execution_time": {
                    "stage1_seconds": round(stage1_elapsed, 2),
                    "stage2_seconds": round(stage2_elapsed, 2),
                    "total_seconds": round(total_elapsed, 2),
                },
                "metrics": {
                    "agenda_count": len(analysis_result.agenda_items),
                    "action_item_count": len(analysis_result.action_items),
                    "decision_count": len(analysis_result.confirmed_decisions),
                    "pending_topic_count": len(analysis_result.pending_and_next_topics),
                },
            }

            saved_files = WorkspaceIO.save_stage2_artifacts(
                workspace_dir=workspace_path,
                markdown_text=markdown_content,
                metadata=metadata,
            )

            for key, p in saved_files.items():
                logger.info(f"Saved: {p}")

            logger.info(f"{FULL_VERSION} pipeline finished successfully in {total_elapsed:.2f}s")
            return {
                "status": "SUCCESS",
                "artifacts": saved_files,
                "metadata": metadata,
                "total_elapsed": total_elapsed,
            }

        except Exception as e:
            logger.exception(f"Error in {FULL_VERSION} pipeline: {e}")
            # エラー時メタデータを保存
            WorkspaceIO.save_failure_metadata(
                workspace_dir=workspace_path,
                error_message=str(e),
                target_model=self.target_model,
                template_name=resolved_template,
            )
            try:
                self.client.unload_model()
            except Exception:
                pass
            raise
        finally:
            _free_memory()
