#!/usr/bin/env python3
"""
ALICE_Minute CLI Adapter.
Entry point for ALICE_Core integration.
Delegates execution to core.pipeline.MinutePipeline.
"""
import argparse
import logging
from pathlib import Path
import sys

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config import config
from core.pipeline import MinutePipeline
from version import FULL_VERSION

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ALICE_Minute")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{FULL_VERSION} - Workspace Meeting Minutes Generator")
    parser.add_argument(
        "--workspace",
        type=str,
        required=True,
        help="Path to the Job Workspace directory (e.g., /data/runtime/workspaces/job_xxx)",
    )
    parser.add_argument(
        "--template",
        type=str,
        default=config.default_template,
        choices=["standard", "interview", "executive", "consultation"],
        help=f"Minutes template to use (choices: standard, interview, executive, consultation. default: {config.default_template})",
    )
    parser.add_argument(
        "--stage2-only",
        action="store_true",
        help="Skip Stage 1 and compose minutes directly from existing analysis.json",
    )
    parser.add_argument(
        "--force-stage1",
        action="store_true",
        help="Force re-running Stage 1 even if analysis.json already exists",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Ollama model name to use (default: {config.model_name})",
    )
    return parser.parse_args()


def run_pipeline(
    workspace_dir: Path | str,
    template_name: str = "standard",
    stage2_only: bool = False,
    force_stage1: bool = False,
    model_override: str | None = None,
) -> int:
    """後方互換ラッパー関数: MinutePipeline を実行し終了コード (0: 成功, 1: 失敗) を返す"""
    try:
        pipeline = MinutePipeline(model=model_override)
        pipeline.run(
            workspace_dir=workspace_dir,
            template_name=template_name,
            stage2_only=stage2_only,
            force_stage1=force_stage1,
        )
        return 0
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return 1


def main() -> None:
    args = parse_args()
    workspace_path = Path(args.workspace).resolve()

    if not workspace_path.exists():
        logger.error(f"Workspace directory does not exist: {workspace_path}")
        sys.exit(1)

    exit_code = run_pipeline(
        workspace_dir=workspace_path,
        template_name=args.template,
        stage2_only=args.stage2_only,
        force_stage1=args.force_stage1,
        model_override=args.model,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
