# ==========================================
# ALICE_Summary CLI Interface (Adapter)
# ==========================================
import sys
import argparse
import logging
from pathlib import Path

# Add ALICE_Summary directory to sys.path
MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from config import DEFAULT_CONFIG
from core.pipeline import SummaryPipeline

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ALICE_Summary")


def parse_args():
    parser = argparse.ArgumentParser(description="ALICE_Summary CLI Module v0.2.0")
    parser.add_argument(
        "--workspace",
        required=True,
        type=str,
        help="Path to the Job Workspace directory",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CONFIG.default_model,
        type=str,
        help=f"Ollama model name (default: {DEFAULT_CONFIG.default_model})",
    )
    parser.add_argument(
        "--stage2-only",
        action="store_true",
        help="Skip Stage 1 and resume from existing analysis.json",
    )
    parser.add_argument(
        "--stage3-only",
        action="store_true",
        help="Skip Stage 1 & 2 and resume Stage 3 consistency check from existing draft_summary.md",
    )
    parser.add_argument(
        "--skip-stage3",
        action="store_true",
        help="Skip Stage 3 consistency check and use Stage 2 draft as final summary",
    )
    parser.add_argument(
        "--force-stage1",
        action="store_true",
        help="Force re-running Stage 1 even if analysis.json exists",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Force re-running all stages from scratch",
    )
    parser.add_argument(
        "--type",
        default="auto",
        choices=["auto", "interview", "meeting", "consultation", "general"],
        help="Conversation template type (default: auto)",
    )
    return parser.parse_args()


def run_pipeline(workspace_path, model_name=None, **kwargs):
    """Backward compatibility wrapper for existing tests or direct callers"""
    pipeline = SummaryPipeline()
    return pipeline.run(workspace_path=workspace_path, model_name=model_name, **kwargs)


def main():
    args = parse_args()
    workspace_path = Path(args.workspace).resolve()

    if not workspace_path.exists():
        logger.error(f"Workspace directory does not exist: {workspace_path}")
        print(f"[Error] Workspace does not exist: {workspace_path}", file=sys.stderr)
        sys.exit(1)

    try:
        pipeline = SummaryPipeline()
        pipeline.run(
            workspace_path=workspace_path,
            model_name=args.model,
            stage2_only=args.stage2_only,
            stage3_only=args.stage3_only,
            skip_stage3=args.skip_stage3,
            force_stage1=args.force_stage1,
            force_all=args.force_all,
            conv_type=args.type,
        )
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        print(f"[Error] Summary generation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
