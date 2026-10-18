# ==========================================
# Core Module Runners Definition (Registry & Artifact Contract)
# ==========================================
import os
import sys
from pathlib import Path
import config


def _resolve_python_bin(env_var: str, relative_subpath: str) -> str:
    """環境変数、プロジェクト相対パス、共有環境パス、sys.executable から有効な Python バイナリを解決"""
    # 1. 明示的な環境変数
    custom_bin = os.getenv(env_var)
    if custom_bin and Path(custom_bin).is_file():
        return custom_bin

    # 2. プロジェクト内仮想環境
    candidates = [
        config.PROJECT_ROOT / "myenv" / relative_subpath / "bin" / "python",
        Path(f"/home/takuya/Project_ALICE/myenv/{relative_subpath}/bin/python"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)

    # 3. 指定環境変数の値（ファイル未存在でも指定があれば優先）
    if custom_bin:
        return custom_bin

    # 4. カレントプロセスの Python
    return sys.executable


WHISPER_PYTHON_BIN = _resolve_python_bin("WHISPER_PYTHON_BIN", "whisper_env")
CORE_PYTHON_BIN = _resolve_python_bin("CORE_PYTHON_BIN", "core_env")

MODULE_RUNNERS = {
    "transcript": {
        "python_bin": WHISPER_PYTHON_BIN,
        "cli_path": str(config.PROJECT_ROOT / "ALICE_Transcript" / "cli.py"),
        "module_cwd": str(config.PROJECT_ROOT / "ALICE_Transcript"),
        "artifact_dir": "transcript",
        "primary_artifact": "transcript.txt",
        "contract_artifacts": ["transcript.json", "transcript.txt", "metadata.json"],
    },
    "summary": {
        "python_bin": CORE_PYTHON_BIN,
        "cli_path": str(config.PROJECT_ROOT / "ALICE_Summary" / "cli.py"),
        "module_cwd": str(config.PROJECT_ROOT / "ALICE_Summary"),
        "artifact_dir": "summary",
        "primary_artifact": "summary.txt",
        "contract_artifacts": ["summary.md", "summary.txt", "analysis.json", "metadata.json"],
    },
    "minutes": {
        "python_bin": CORE_PYTHON_BIN,
        "cli_path": str(config.PROJECT_ROOT / "ALICE_Minutes" / "cli.py"),
        "module_cwd": str(config.PROJECT_ROOT / "ALICE_Minutes"),
        "artifact_dir": "minutes",
        "primary_artifact": "minutes.md",
        "contract_artifacts": ["minutes.txt", "minutes.md", "analysis.json", "metadata.json"],
    },
}
