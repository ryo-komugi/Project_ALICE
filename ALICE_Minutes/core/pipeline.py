"""
Pipeline Orchestrator for ALICE_Minute.
Executes two-stage meeting minutes generation:
  Stage 1: Transcript (+ Summary Outline) -> analysis.json (Structuring)
  Stage 2: analysis.json + Template -> minutes.md / minutes.txt (Composition)
"""
from datetime import datetime
import gc
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

    def run(
        self,
        workspace_dir: Path | str,
        template_name: str = "standard",
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
            f"Target model: {self.target_model}, template: '{template_name}', "
            f"stage2_only: {stage2_only}, force_stage1: {force_stage1}"
        )

        analysis_result: Optional[MinuteAnalysisResult] = None
        stage1_elapsed: float = 0.0

        try:
            minutes_dir = WorkspaceIO.get_minutes_dir(workspace_path)
            analysis_path = minutes_dir / "analysis.json"

            # ----------------------------------------------------
            # Stage 1: Conversation Understanding & Structuring
            # ----------------------------------------------------
            if stage2_only:
                logger.info("Skipping Stage 1 (--stage2-only). Loading existing analysis.json...")
                analysis_result = WorkspaceIO.load_stage1_analysis(workspace_path)
            elif analysis_path.exists() and not force_stage1:
                logger.info(f"Found existing {analysis_path}. Reusing Stage 1 analysis (use --force-stage1 to re-run)...")
                analysis_result = WorkspaceIO.load_stage1_analysis(workspace_path)
            else:
                logger.info("Loading transcript.json...")
                segments = WorkspaceIO.load_transcript(workspace_path)
                logger.info(f"Loaded {len(segments)} segments.")

                summary_analysis = WorkspaceIO.load_summary_analysis(workspace_path)
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

            # ----------------------------------------------------
            # Stage 2: Human-Readable Minutes Generation
            # ----------------------------------------------------
            logger.info(f"Executing Stage 2 (Composer: Minutes Generation with template '{template_name}')...")
            composer = MinuteComposer(client=self.client)
            markdown_content, stage2_elapsed = composer.run(
                analysis=analysis_result,
                template_name=template_name,
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
                "template": template_name,
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
                template_name=template_name,
            )
            raise
        finally:
            try:
                self.client.unload_model()
            except Exception:
                pass
            _free_memory()
