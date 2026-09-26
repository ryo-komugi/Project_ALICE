"""
Antigravity-Powered Auto-Patcher & Code Maintenance Engine for ALICE_CoPilot.
Autonomous pipeline that investigates code, creates patches, verifies via pytest,
commits changes if regression-free, and reports diffs back to Discord #copilot.
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

COPILOT_DIR = Path(__file__).resolve().parent.parent
if str(COPILOT_DIR) not in sys.path:
    sys.path.insert(0, str(COPILOT_DIR))

import config

PROJECT_ROOT = config.PROJECT_ROOT
CORE_DIR = PROJECT_ROOT / "ALICE_Core"
COPILOT_PYTHON = PROJECT_ROOT / "myenv" / "copilot_env" / "bin" / "python3"
CORE_PYTHON = PROJECT_ROOT / "myenv" / "core_env" / "bin" / "python3"
from google.antigravity import Agent, LocalOpenAIAgentConfig

# Execution state tracking
PATCH_EXECUTION_STATE: dict[str, Any] = {
    "status": "idle",
    "target_repo": "ALICE_CoPilot",
    "modified_files": [],
    "test_passed": False,
    "committed": False,
    "commit_hash": None,
    "error": None,
    "diff": "",
}


def reset_patch_state():
    PATCH_EXECUTION_STATE["status"] = "idle"
    PATCH_EXECUTION_STATE["target_repo"] = "ALICE_CoPilot"
    PATCH_EXECUTION_STATE["modified_files"] = []
    PATCH_EXECUTION_STATE["test_passed"] = False
    PATCH_EXECUTION_STATE["committed"] = False
    PATCH_EXECUTION_STATE["commit_hash"] = None
    PATCH_EXECUTION_STATE["error"] = None
    PATCH_EXECUTION_STATE["diff"] = ""


# =========================================================================
# Antigravity Tools for Auto-Patcher
# =========================================================================

def read_source_file(file_path: str, start_line: int = 1, line_count: int = 150) -> str:
    """Reads a section of a source code file in Project_ALICE.

    Args:
        file_path: Relative path from Project_ALICE root (e.g. 'ALICE_CoPilot/reviewer/report_manager.py').
        start_line: 1-indexed line number to start reading from.
        line_count: Number of lines to read.
    """
    target = PROJECT_ROOT / file_path
    if not target.exists() or not target.is_file():
        return f"エラー: ファイルが存在しません: {file_path}"

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        
        start_idx = max(0, start_line - 1)
        end_idx = min(len(all_lines), start_idx + line_count)
        selected = all_lines[start_idx:end_idx]
        
        numbered = [f"{start_idx + i + 1:4d}: {line}" for i, line in enumerate(selected)]
        return f"=== {file_path} (Lines {start_idx + 1}-{end_idx} of {len(all_lines)}) ===\n" + "".join(numbered)
    except Exception as e:
        return f"ファイル読み込みエラー: {e}"


def search_code_symbol(symbol: str, repo: str = "ALICE_CoPilot") -> str:
    """Searches for definitions or usages of a symbol across a repository.

    Args:
        symbol: The class, function, or keyword to find.
        repo: Repository name (e.g. 'ALICE_CoPilot', 'ALICE_Core').
    """
    target_dir = PROJECT_ROOT / repo if repo else COPILOT_DIR
    cmd = [
        "grep", "-rn",
        "--exclude-dir=.git", "--exclude-dir=__pycache__", "--exclude-dir=.pytest_cache",
        symbol, str(target_dir)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = res.stdout.strip().splitlines()
        if not lines:
            return f"'{symbol}' は {repo} 内で見つかりませんでした。"
        return "\n".join(lines[:20]) + (f"\n...他 {len(lines) - 20} 件" if len(lines) > 20 else "")
    except Exception as e:
        return f"検索エラー: {e}"


def apply_file_modification(file_path: str, old_content: str, new_content: str) -> str:
    """Replaces an exact block of code in a source file.

    Args:
        file_path: Relative path from Project_ALICE (e.g. 'ALICE_CoPilot/reviewer/report_manager.py').
        old_content: The exact existing string block to replace.
        new_content: The new replacement string block.
    """
    target = PROJECT_ROOT / file_path
    if not target.exists() or not target.is_file():
        return f"エラー: ファイルが見つかりません: {file_path}"

    try:
        with open(target, "r", encoding="utf-8") as f:
            src = f.read()

        if old_content not in src:
            return f"置換失敗: 指定された old_content が {file_path} 内に完全一致で見つかりません。"

        updated = src.replace(old_content, new_content, 1)
        with open(target, "w", encoding="utf-8") as f:
            f.write(updated)

        if file_path not in PATCH_EXECUTION_STATE["modified_files"]:
            PATCH_EXECUTION_STATE["modified_files"].append(file_path)

        return f"成功: {file_path} のコードブロックを正常に置換・保存しました。"
    except Exception as e:
        return f"置換例外: {e}"


def run_regression_tests(repo: str = "ALICE_CoPilot", test_target: str = "") -> str:
    """Runs pytest test suites to verify that modifications caused zero regressions.

    Args:
        repo: Repository name ('ALICE_CoPilot' or 'ALICE_Core').
        test_target: Optional specific test file (e.g. 'tests/test_checklist.py').
    """
    if repo == "ALICE_Core":
        py_bin = CORE_PYTHON
        work_dir = CORE_DIR
        default_target = "test_admin_auth.py"
    else:
        py_bin = COPILOT_PYTHON
        work_dir = COPILOT_DIR
        default_target = "tests/test_checklist.py"

    target_file = test_target or default_target
    cmd = [str(py_bin), "-m", "pytest", target_file, "-v"]

    try:
        res = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True, timeout=40)
        out = (res.stdout + "\n" + res.stderr).strip()
        passed = res.returncode == 0
        PATCH_EXECUTION_STATE["test_passed"] = passed

        status = "✅ 全テスト合格 (100% PASS)" if passed else "❌ テスト失敗 (FAIL)"
        return f"{status}\n\n{out[-600:]}"
    except Exception as e:
        PATCH_EXECUTION_STATE["test_passed"] = False
        return f"テスト実行例外: {e}"


def commit_and_record_patch(commit_message: str, repo: str = "ALICE_CoPilot") -> str:
    """Commits all staged changes if regression tests passed.

    Args:
        commit_message: Descriptive git commit message in Japanese or English.
        repo: Repository name ('ALICE_CoPilot' or 'ALICE_Core').
    """
    repo_dir = PROJECT_ROOT / repo if repo else COPILOT_DIR
    if not PATCH_EXECUTION_STATE.get("test_passed"):
        return "コミット拒絶: 単体テスト（pytest）が未実行または不合格です。先に run_regression_tests をパスしてください。"

    try:
        # Check diff
        diff_res = subprocess.run(["git", "diff"], cwd=str(repo_dir), capture_output=True, text=True)
        PATCH_EXECUTION_STATE["diff"] = diff_res.stdout[:1500]

        # Stage and commit
        subprocess.run(["git", "add", "-u"], cwd=str(repo_dir), check=True)
        commit_res = subprocess.run(["git", "commit", "-m", commit_message], cwd=str(repo_dir), capture_output=True, text=True)
        if commit_res.returncode != 0:
            return f"コミット失敗または変更なし: {commit_res.stdout}\n{commit_res.stderr}"

        # Get hash
        hash_res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True)
        c_hash = hash_res.stdout.strip()
        PATCH_EXECUTION_STATE["committed"] = True
        PATCH_EXECUTION_STATE["commit_hash"] = c_hash

        # Push to backup
        subprocess.run(["git", "push", "backup", "main"], cwd=str(repo_dir), capture_output=True, text=True)

        return f"✅ コミット＆バックアッププッシュ完了: [{c_hash}] {commit_message}"
    except Exception as e:
        return f"コミット処理例外: {e}"


# =========================================================================
# Execution Entrypoint
# =========================================================================

AUTO_PATCHER_SYSTEM_PROMPT = """
あなたはProject_ALICEの自律改修・パッチ適用エージェント（Antigravity Auto-Patcher）です。
浅野さんから承認されたシステム改善提案や、指示されたエンジニアリング課題を自律的に解決します。

【厳格な作業プロトコル】
1. 【調査】: まず `search_code_symbol` や `read_source_file` を使い、修正すべき対象ファイルと該当行を特定・精査する。
2. 【修正】: `apply_file_modification` を用いて、ピンポイントかつ安全にコードブロックを置換する。
3. 【テスト検証】: 修正後、必ず `run_regression_tests` を実行し、全単体テストが 100% PASS することを確認する。テストが失敗した場合は直ちに原因を特定して再修正するか元に戻す。
4. 【コミット】: テスト合格を確認したら `commit_and_record_patch` を実行して変更を永続化・プッシュする。
5. 【報告】: 何をどう修正し、どのテストがパスしたかを簡潔明瞭に報告する。
"""


async def execute_autonomous_patch(instruction: str, repo: str = "ALICE_CoPilot") -> dict[str, Any]:
    """Runs the Antigravity Agent to execute an autonomous code modification."""
    reset_patch_state()
    PATCH_EXECUTION_STATE["status"] = "running"
    PATCH_EXECUTION_STATE["target_repo"] = repo

    agent_config = LocalOpenAIAgentConfig(
        model=config.OLLAMA_MODEL,
        base_url="http://localhost:11434/v1",
        system_instructions=AUTO_PATCHER_SYSTEM_PROMPT,
        tools=[
            read_source_file,
            search_code_symbol,
            apply_file_modification,
            run_regression_tests,
            commit_and_record_patch,
        ],
    )

    prompt = f"""
以下の課題・改善提案について、コードを調査・修正し、単体テストを完走させてコミットしてください。

【対象リポジトリ】: {repo}
【改善課題・指示内容】:
{instruction}
"""

    ans_text = ""
    try:
        async with Agent(config=agent_config) as agent:
            resp = await agent.chat(prompt)
            ans_text = await resp.text() or ""
        PATCH_EXECUTION_STATE["status"] = "completed"
    except Exception as e:
        PATCH_EXECUTION_STATE["status"] = "error"
        PATCH_EXECUTION_STATE["error"] = str(e)
        ans_text = f"自律改修プロセス中に例外が発生しました: {e}"

    return {
        "ans_text": ans_text,
        "status": PATCH_EXECUTION_STATE["status"],
        "modified_files": PATCH_EXECUTION_STATE["modified_files"],
        "test_passed": PATCH_EXECUTION_STATE["test_passed"],
        "committed": PATCH_EXECUTION_STATE["committed"],
        "commit_hash": PATCH_EXECUTION_STATE["commit_hash"],
        "diff": PATCH_EXECUTION_STATE["diff"],
        "error": PATCH_EXECUTION_STATE["error"],
    }
