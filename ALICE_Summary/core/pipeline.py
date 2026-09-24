import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from config import DEFAULT_CONFIG, SummaryConfig
from core.workspace_io import WorkspaceIO
from core.ollama_client import OllamaClient
from core.analyzer import Analyzer
from core.composer import Composer
from core.commentator import Commentator
from core.checker import ConsistencyChecker

logger = logging.getLogger("ALICE_Summary.Pipeline")


class SummaryPipeline:
    """ALICE_Summary 3-Stage 要約・講評パイプライン統括エンジン"""

    def __init__(self, config: Optional[SummaryConfig] = None, client: Optional[OllamaClient] = None):
        self.config = config or DEFAULT_CONFIG
        self.client = client or OllamaClient(base_url=self.config.ollama_url)
        self.analyzer = Analyzer(config=self.config, client=self.client)
        self.composer = Composer(config=self.config, client=self.client)
        self.commentator = Commentator(config=self.config, client=self.client)
        self.checker = ConsistencyChecker(config=self.config, client=self.client)

    def run(
        self,
        workspace_path: Path,
        model_name: Optional[str] = None,
        stage2_only: bool = False,
        stage3_only: bool = False,
        skip_stage3: bool = False,
        force_stage1: bool = False,
        force_all: bool = False,
        conv_type: str = "auto",
    ) -> Dict[str, Any]:
        t_start = time.time()
        target_model = model_name or self.config.default_model
        workspace_path = workspace_path.resolve()

        logger.info(f"Starting ALICE_Summary pipeline for workspace: {workspace_path}")
        logger.info(f"Target model: {target_model}, type: {conv_type}, stage2_only={stage2_only}, stage3_only={stage3_only}, skip_stage3={skip_stage3}")

        summary_dir = WorkspaceIO.get_summary_dir(workspace_path)
        analysis_path = summary_dir / "analysis.json"
        draft_path = summary_dir / "draft_summary.md"

        stage1_time = 0.0
        stage2_time = 0.0
        stage3_time = 0.0
        commentary_time = 0.0

        stage1_resp = None
        stage2_resp = None
        stage3_resp = None
        commentary_resp = None

        analysis_data = None
        draft_summary_md = ""
        final_summary_md = ""
        consistency_report_md = ""
        commentary_md = ""

        try:
            # 1. Transcript 読み込み & フォーマット & 動的コンテキスト長算出
            logger.info("Loading transcript.json...")
            segments = WorkspaceIO.load_transcript(workspace_path)
            input_segments_count = len(segments)
            formatted_transcript = WorkspaceIO.format_transcript_for_prompt(segments)
            if not formatted_transcript.strip():
                raise ValueError("Formatted transcript text is empty")

            dynamic_num_ctx = WorkspaceIO.calculate_dynamic_num_ctx(formatted_transcript)
            logger.info(
                f"Transcript loaded: {input_segments_count} segments ({len(formatted_transcript)} chars). "
                f"Dynamically determined num_ctx: {dynamic_num_ctx}"
            )

            # ==========================================
            # Stage 1: 会話理解・話者役割推定・構造化
            # ==========================================
            valid_existing_analysis = False
            if analysis_path.exists() and not (force_stage1 or force_all):
                try:
                    analysis_data = WorkspaceIO.load_analysis_json(workspace_path)
                    if analysis_data and isinstance(analysis_data, dict) and analysis_data.get("conversation_overview"):
                        valid_existing_analysis = True
                except Exception as e:
                    logger.warning(f"Existing {analysis_path} is corrupted or invalid ({e}). Will re-generate.")

            if stage3_only:
                logger.info("Stage 3 only mode requested. Skipping Stage 1.")
            elif stage2_only:
                logger.info(f"Stage 2 only mode requested. Loading existing {analysis_path}...")
                analysis_data = WorkspaceIO.load_analysis_json(workspace_path)
            elif valid_existing_analysis:
                logger.info(f"Found valid existing {analysis_path}. Skipping Stage 1 (use --force-stage1 to re-run).")
            else:
                logger.info("Executing Stage 1 (Analyzer: Conversation Understanding & Structuring)...")
                t_stage1_start = time.time()
                analysis_data, stage1_resp = self.analyzer.analyze(
                    formatted_transcript, model_name=target_model, num_ctx=dynamic_num_ctx
                )
                stage1_time = time.time() - t_stage1_start
                logger.info(f"Stage 1 completed in {stage1_time:.2f}s. Saving analysis.json...")
                WorkspaceIO.save_analysis_json(workspace_path, analysis_data)
                logger.info(f"Saved: {analysis_path}")

            # ==========================================
            # Stage 2: ドラフト要約文章化
            # ==========================================
            valid_existing_draft = False
            if draft_path.exists() and not (force_stage1 or force_all) and not stage2_only:
                try:
                    draft_summary_md = WorkspaceIO.load_draft_summary(workspace_path)
                    if draft_summary_md and len(draft_summary_md.strip()) > 50:
                        valid_existing_draft = True
                except Exception as e:
                    logger.warning(f"Existing {draft_path} is corrupted or empty ({e}). Will re-generate.")

            applied_type = "interview"
            if stage3_only:
                logger.info("Stage 3 only mode requested. Loading existing draft summary...")
                draft_summary_md = WorkspaceIO.load_draft_summary(workspace_path)
            elif valid_existing_draft:
                logger.info(f"Found valid existing {draft_path}. Loading draft summary...")
                draft_summary_md = WorkspaceIO.load_draft_summary(workspace_path)
                applied_type = Composer.detect_conversation_type(analysis_data) if analysis_data else "interview"
            else:
                logger.info("Executing Stage 2 (Composer: Draft Summary Generation)...")
                t_stage2_start = time.time()
                s2_keep_alive = self.config.final_keep_alive if skip_stage3 else self.config.keep_alive
                draft_summary_md, stage2_resp, applied_type = self.composer.compose(
                    analysis_data,
                    model_name=target_model,
                    num_ctx=min(dynamic_num_ctx, 32768),
                    keep_alive=s2_keep_alive,
                    conv_type=conv_type,
                )
                stage2_time = time.time() - t_stage2_start
                logger.info(f"Stage 2 completed in {stage2_time:.2f}s. Saving draft_summary.md...")
                WorkspaceIO.save_draft_summary(workspace_path, draft_summary_md)
                logger.info(f"Saved: {draft_path}")

            # ==========================================
            # Stage 3: 原文照合・整合性チェック & 精密修正
            # ==========================================
            if skip_stage3:
                logger.info("Skip Stage 3 requested. Adopting Stage 2 draft as final summary...")
                final_summary_md = draft_summary_md
                self.client.unload_model(target_model)
            else:
                logger.info("Executing Stage 3 (ConsistencyChecker: Audit & Refine against Transcript)...")
                t_stage3_start = time.time()
                final_summary_md, consistency_report_md, stage3_resp = self.checker.check_and_refine(
                    formatted_transcript=formatted_transcript,
                    draft_summary=draft_summary_md,
                    model_name=target_model,
                    num_ctx=dynamic_num_ctx,
                    conv_type=applied_type,
                )
                stage3_time = time.time() - t_stage3_start
                logger.info(f"Stage 3 completed in {stage3_time:.2f}s. Saving consistency_report.md...")
                report_path = WorkspaceIO.save_consistency_report(workspace_path, consistency_report_md)
                logger.info(f"Saved: {report_path}")

            # 最終成果物の保存 (summary.md, summary.txt)
            md_path, txt_path = WorkspaceIO.save_summary_documents(workspace_path, final_summary_md)
            logger.info(f"Saved final summary: {md_path}")
            logger.info(f"Saved plain text summary: {txt_path}")

            # ==========================================
            # Commentary 生成（面談・会議の総括および人物・指導講評）
            # ==========================================
            if analysis_data:
                logger.info("Generating Commentary (Analysis & Evaluation Report)...")
                t_comm_start = time.time()
                commentary_md, commentary_resp = self.commentator.generate_commentary(
                    analysis_data=analysis_data,
                    draft_summary=final_summary_md or draft_summary_md,
                    model_name=target_model,
                    num_ctx=min(dynamic_num_ctx, 32768),
                    keep_alive=self.config.final_keep_alive,
                    conv_type=applied_type,
                )
                commentary_time = time.time() - t_comm_start
                comm_md_path, comm_txt_path = WorkspaceIO.save_commentary_documents(workspace_path, commentary_md)
                logger.info(f"Saved commentary: {comm_md_path}")
                logger.info(f"Saved plain text commentary: {comm_txt_path}")

            total_time = time.time() - t_start

            # Metadata 作成
            token_metrics: Dict[str, Any] = {
                "stage1_prompt_tokens": stage1_resp.prompt_eval_count if stage1_resp else None,
                "stage1_eval_tokens": stage1_resp.eval_count if stage1_resp else None,
                "stage2_prompt_tokens": stage2_resp.prompt_eval_count if stage2_resp else None,
                "stage2_eval_tokens": stage2_resp.eval_count if stage2_resp else None,
                "stage3_prompt_tokens": stage3_resp.prompt_eval_count if stage3_resp else None,
                "stage3_eval_tokens": stage3_resp.eval_count if stage3_resp else None,
                "commentary_prompt_tokens": commentary_resp.prompt_eval_count if commentary_resp else None,
                "commentary_eval_tokens": commentary_resp.eval_count if commentary_resp else None,
            }
            total_tokens = sum(v for v in token_metrics.values() if isinstance(v, int))
            token_metrics["total_tokens"] = total_tokens

            actual_models = list(dict.fromkeys(
                r.actual_model for r in [stage1_resp, stage2_resp, stage3_resp, commentary_resp] if r and getattr(r, "actual_model", None)
            ))
            fallback_used = any(m != target_model for m in actual_models)

            metadata = {
                "workspace": str(workspace_path),
                "status": "COMPLETED",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": target_model,
                "actual_models": actual_models or [target_model],
                "fallback_used": fallback_used,
                "conversation_type": applied_type,
                "num_ctx": dynamic_num_ctx,
                "execution_time_sec": {
                    "stage1": round(stage1_time, 2),
                    "stage2": round(stage2_time, 2),
                    "stage3": round(stage3_time, 2),
                    "commentary": round(commentary_time, 2),
                    "total": round(total_time, 2),
                },
                "token_metrics": token_metrics,
                "input_segments_count": input_segments_count,
                "stage3_executed": not skip_stage3,
                "commentary_executed": bool(commentary_md),
            }

            metadata_path = WorkspaceIO.save_metadata(workspace_path, metadata)
            logger.info(f"Saved: {metadata_path}")
            logger.info(f"ALICE_Summary pipeline finished successfully in {total_time:.2f}s")
            return metadata

        except Exception as e:
            logger.exception(f"Pipeline execution failed: {e}")
            try:
                self.client.unload_model(target_model)
            except Exception:
                pass
            raise
