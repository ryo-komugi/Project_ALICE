import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 保存先: /data/runtime/core/system_settings.json
# フォールバック: database/system_settings.json
PRIMARY_PATH = Path("/data/runtime/core/system_settings.json")
FALLBACK_PATH = Path(__file__).resolve().parent.parent / "database" / "system_settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "maintenance_mode": False,
    "maintenance_message": (
        "只今システムメンテナンスおよびアップデート作業を行っております。\n"
        "ご不便をおかけしますが、再開までしばらくお待ちください。\n"
        "（作業完了次第、自動的に通常応答へ復帰いたします）"
    ),
    "admin_bypass": True,
    "updated_at": "",
    "updated_by": "",
}


def _get_settings_file() -> Path:
    try:
        PRIMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        return PRIMARY_PATH
    except Exception:
        FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        return FALLBACK_PATH


def get_system_settings() -> dict[str, Any]:
    """設定ファイルからシステム設定を読み込む。存在しない場合はデフォルトを返す。"""
    path = _get_settings_file()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # デフォルトキーをマージして安全性を確保
            settings = dict(DEFAULT_SETTINGS)
            settings.update(data)
            return settings
    except Exception as e:
        logger.warning(f"[SystemSettings] Failed to read settings from {path}: {e}")
        return dict(DEFAULT_SETTINGS)


def update_system_settings(new_settings: dict[str, Any]) -> dict[str, Any]:
    """システム設定を更新して永続化する。"""
    current = get_system_settings()
    for key in ("maintenance_mode", "maintenance_message", "admin_bypass", "updated_at", "updated_by"):
        if key in new_settings:
            current[key] = new_settings[key]

    path = _get_settings_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        logger.info(f"[SystemSettings] Updated system settings in {path}")
    except Exception as e:
        logger.error(f"[SystemSettings] Failed to write settings to {path}: {e}")
        raise

    return current


def is_maintenance_active() -> bool:
    """現在メンテナンスモードが有効かどうかを取得する。"""
    return bool(get_system_settings().get("maintenance_mode", False))


def get_maintenance_message() -> str:
    """メンテナンス時の案内メッセージを取得する。"""
    msg = get_system_settings().get("maintenance_message")
    if not msg or not msg.strip():
        return DEFAULT_SETTINGS["maintenance_message"]
    return msg.strip()


def is_admin_bypass_allowed() -> bool:
    """メンテナンスモード中も管理者のバイパスを許可するかどうかを取得する。"""
    return bool(get_system_settings().get("admin_bypass", True))
