# ==========================================
# ALICE_Transcript CLI Interface (Adapter)
# ==========================================
import sys
import argparse
from pathlib import Path

# Add Project_ALICE and ALICE_Transcript root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import config
from core.pipeline import TranscriptPipeline


def parse_args():
    parser = argparse.ArgumentParser(description="ALICE_Transcript CLI Adapter v0.2.1")
    parser.add_argument(
        "--workspace",
        required=True,
        type=str,
        help="Path to the Job Workspace directory",
    )
    parser.add_argument(
        "--model",
        default=getattr(config, "MODEL_NAME", "deepdml/faster-whisper-large-v3-turbo-ct2"),
        type=str,
        help="Whisper model name or path (default: from config)",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        type=str,
        help="Execution device: cuda or cpu (default: cuda)",
    )
    parser.add_argument(
        "--language",
        default="ja",
        type=str,
        help="Transcription language code (default: ja)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    workspace_path = Path(args.workspace)
    if not workspace_path.exists():
        print(f"[Error] Workspace directory does not exist: {workspace_path}", file=sys.stderr)
        sys.exit(1)

    try:
        pipeline = TranscriptPipeline(model_name=args.model, device=args.device, language=args.language)
        pipeline.run(workspace_path)
        sys.exit(0)
    except Exception as e:
        print(f"[Error] CLI execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
