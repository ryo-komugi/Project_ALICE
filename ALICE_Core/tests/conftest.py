import sys
import shutil
import json
from pathlib import Path
import pytest

CORE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = CORE_ROOT.parent

for p in [str(CORE_ROOT), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(scope="session", autouse=True)
def auto_cleanup_test_workspaces():
    """
    テスト実行前後のワークスペース自動クリーンアップ。
    1. テスト開始前に残存しているテスト用Job（user_test*, test_*）を安全に削除
    2. テストセッション開始時点のワークスペース一覧を記録
    3. テスト終了後、テスト中に新規作成されたワークスペースディレクトリを自動削除
    """
    ws_dir = Path("/data/runtime/workspaces")
    if not ws_dir.exists():
        yield
        return

    # テスト開始前の既存ディレクトリをスナップショット
    before_dirs = set(ws_dir.iterdir())

    # 開始前に残っているテスト用Job（test_プレフィックス等）があれば事前にクリーンアップ
    test_user_prefixes = ("user_test", "test_", "user_rec_")
    for d in before_dirs:
        if d.is_dir() and (d / "job.json").exists():
            try:
                with open(d / "job.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    user_id = data.get("user_id", "")
                    if any(user_id.startswith(pfx) for pfx in test_user_prefixes):
                        shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass

    # 本番Jobのみとなった状態で再度スナップショット
    before_dirs = set(ws_dir.iterdir())

    yield

    # テストセッション終了後：テスト実行中に増えたディレクトリを全自動クリーンアップ
    if ws_dir.exists():
        after_dirs = set(ws_dir.iterdir())
        created_dirs = after_dirs - before_dirs
        for d in created_dirs:
            if d.is_dir() and d.name.startswith("job_"):
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass
