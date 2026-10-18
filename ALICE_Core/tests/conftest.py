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
def setup_test_users():
    """テスト用ダミーユーザー (U_TEST_DUMMY_USER_001) を自動登録・初期化"""
    try:
        from repository.user_repository import UserRepository
        from auth.user import User
        from auth.user_status import UserStatus

        repo = UserRepository()
        dummy_id = "U_TEST_DUMMY_USER_001"
        existing = repo.find(dummy_id)
        if not existing:
            repo.create(User(user_id=dummy_id, display_name="Test User", status=UserStatus.READY))
        elif existing.status != UserStatus.READY:
            repo.update_status(dummy_id, UserStatus.READY)
    except Exception as e:
        print(f"[conftest] Warning: failed to ensure test user: {e}")


@pytest.fixture(scope="session", autouse=True)
def auto_cleanup_test_workspaces():
    """
    テスト実行前後のワークスペース自動クリーンアップ。
    1. テスト開始前に残存しているテスト用Job（user_test*, test_*）を安全に削除
    2. テストセッション開始時点のワークスペース一覧を記録
    3. テスト終了後、テスト中に新規作成されたワークスペースディレクトリを自動削除
    """
    import config
    ws_dir = Path(config.DIR_WORKSPACES)
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
