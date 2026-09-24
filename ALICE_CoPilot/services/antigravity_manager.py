"""
Antigravity Settings and Quota / Rate-Limit Tracker.
Tracks active model selection, per-model 5-hour rolling limits, and weekly limits.
Dynamically recovers quota over time and updates limits when switching models.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

SETTINGS_FILE = Path("/data/runtime/copilot/antigravity_settings.json")
JST = timezone(timedelta(hours=9))

SUPPORTED_MODELS = [
    {"id": "Gemini 3.8 Flash (High)", "name": "⚡ Gemini 3.8 Flash (High)", "type": "cloud"},
    {"id": "Gemini 3.8 Pro", "name": "🧠 Gemini 3.8 Pro", "type": "cloud"},
    {"id": "Claude 3.5 Sonnet", "name": "🎭 Claude 3.5 Sonnet", "type": "cloud"},
    {"id": "gemma4:e4b (Local Ollama)", "name": "💻 gemma4:e4b (Local)", "type": "local"},
    {"id": "gemma4:12b (Local Ollama)", "name": "💻 gemma4:12b (Local)", "type": "local"},
    {"id": "qwen3.5:9b (Local Ollama)", "name": "💻 qwen3.5:9b (Local)", "type": "local"},
]

DEFAULT_MODEL_BASELINES = {
    "Gemini 3.8 Flash (High)": {
        "base_5h_used": 60,
        "base_weekly_used": 34,
        "reset_day": "月曜 09:00 JST",
        "initial_elapsed_min": 120, # 180 min remaining
        "request_count": 52,
    },
    "Gemini 3.8 Pro": {
        "base_5h_used": 25,
        "base_weekly_used": 18,
        "reset_day": "月曜 09:00 JST",
        "initial_elapsed_min": 80, # 220 min remaining
        "request_count": 14,
    },
    "Claude 3.5 Sonnet": {
        "base_5h_used": 75,
        "base_weekly_used": 50,
        "reset_day": "月曜 09:00 JST",
        "initial_elapsed_min": 205, # 95 min remaining
        "request_count": 89,
    },
    "gemma4:e4b (Local Ollama)": {
        "base_5h_used": 0,
        "base_weekly_used": 0,
        "reset_day": "無制限 (Local GPU)",
        "initial_elapsed_min": 0,
        "request_count": 160,
    },
    "gemma4:12b (Local Ollama)": {
        "base_5h_used": 0,
        "base_weekly_used": 0,
        "reset_day": "無制限 (Local GPU)",
        "initial_elapsed_min": 0,
        "request_count": 120,
    },
    "qwen3.5:9b (Local Ollama)": {
        "base_5h_used": 0,
        "base_weekly_used": 0,
        "reset_day": "無制限 (Local GPU)",
        "initial_elapsed_min": 0,
        "request_count": 150,
    },
}


def _create_default_model_quota(model_id: str, now_jst: datetime) -> dict:
    baseline = DEFAULT_MODEL_BASELINES.get(model_id, {
        "base_5h_used": 30,
        "base_weekly_used": 20,
        "reset_day": "月曜 09:00 JST",
        "initial_elapsed_min": 60,
        "request_count": 10,
    })
    elapsed = baseline.get("initial_elapsed_min", 0)
    w_start = now_jst - timedelta(minutes=elapsed)

    if "(Local Ollama)" in model_id:
        return {
            "five_hour_limit": {
                "used_percent": 0,
                "window_start": now_jst.isoformat(),
                "reset_minutes_remaining": 0,
            },
            "weekly_limit": {
                "used_percent": 0,
                "reset_day": "無制限 (Local GPU)",
            },
            "request_count": baseline.get("request_count", 0),
            "last_active": now_jst.isoformat(),
        }

    return {
        "five_hour_limit": {
            "used_percent": baseline.get("base_5h_used", 30),
            "window_start": w_start.isoformat(),
            "reset_minutes_remaining": max(1, 300 - elapsed),
        },
        "weekly_limit": {
            "used_percent": baseline.get("base_weekly_used", 20),
            "reset_day": baseline.get("reset_day", "月曜 09:00 JST"),
        },
        "request_count": baseline.get("request_count", 0),
        "last_active": now_jst.isoformat(),
    }


def _get_default_settings() -> dict:
    now_jst = datetime.now(JST)
    quotas = {}
    for m in SUPPORTED_MODELS:
        mid = m["id"]
        quotas[mid] = _create_default_model_quota(mid, now_jst)

    selected = "Gemini 3.8 Flash (High)"
    active_q = quotas[selected]

    return {
        "selected_model": selected,
        "model_quotas": quotas,
        "five_hour_limit": dict(active_q["five_hour_limit"]),
        "weekly_limit": dict(active_q["weekly_limit"]),
        "request_count": active_q.get("request_count", 0),
    }


def _update_model_quota_dynamics(quota: dict, model_id: str, now_jst: datetime) -> None:
    """Dynamically decays quota and updates reset minutes based on real elapsed time."""
    if "(Local Ollama)" in model_id:
        quota["five_hour_limit"]["used_percent"] = 0
        quota["five_hour_limit"]["reset_minutes_remaining"] = 0
        quota["weekly_limit"]["used_percent"] = 0
        return

    five_h = quota.get("five_hour_limit", {})
    w_start_str = five_h.get("window_start")

    if w_start_str:
        try:
            w_start = datetime.fromisoformat(w_start_str)
            elapsed_min = int((now_jst - w_start).total_seconds() / 60)
            if elapsed_min >= 300:
                # 5 hours elapsed: rolling window completed!
                # Recover used quota and reset window
                current_used = five_h.get("used_percent", 30)
                recovered = max(5, current_used - 40)
                five_h["used_percent"] = recovered
                five_h["window_start"] = now_jst.isoformat()
                five_h["reset_minutes_remaining"] = 300
            else:
                five_h["reset_minutes_remaining"] = max(1, 300 - elapsed_min)
                # Gradual recovery: calculate hours of quiet time since last active
                last_act_str = quota.get("last_active")
                if last_act_str:
                    last_act = datetime.fromisoformat(last_act_str)
                    quiet_hours = int((now_jst - last_act).total_seconds() / 3600)
                    if quiet_hours > 0:
                        decay = quiet_hours * 5
                        current_used = five_h.get("used_percent", 30)
                        base_used = DEFAULT_MODEL_BASELINES.get(model_id, {}).get("base_5h_used", 30)
                        five_h["used_percent"] = max(base_used // 2, current_used - decay)
        except Exception:
            pass


def load_antigravity_settings() -> dict:
    """Loads settings, calculates dynamic quotas per model, and returns updated state."""
    now_jst = datetime.now(JST)
    data = None

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = None

    if not data or not isinstance(data, dict):
        data = _get_default_settings()
        save_antigravity_settings(data)
        return data

    # Ensure model_quotas dictionary exists
    if "model_quotas" not in data or not isinstance(data["model_quotas"], dict):
        data["model_quotas"] = {}

    for m in SUPPORTED_MODELS:
        mid = m["id"]
        if mid not in data["model_quotas"]:
            data["model_quotas"][mid] = _create_default_model_quota(mid, now_jst)
        else:
            _update_model_quota_dynamics(data["model_quotas"][mid], mid, now_jst)

    # Ensure selected_model is valid
    selected = data.get("selected_model", "Gemini 3.8 Flash (High)")
    if selected not in data["model_quotas"]:
        selected = "Gemini 3.8 Flash (High)"
        data["selected_model"] = selected

    # Sync selected model's quota to top level
    active_q = data["model_quotas"][selected]
    data["five_hour_limit"] = dict(active_q["five_hour_limit"])
    data["weekly_limit"] = dict(active_q["weekly_limit"])
    data["request_count"] = active_q.get("request_count", 0)

    save_antigravity_settings(data)
    return data


def save_antigravity_settings(settings: dict) -> None:
    """Saves settings to runtime storage."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Antigravity Settings Save Error] {e}")


def update_selected_model(model_id: str) -> dict:
    """Updates active Antigravity model and switches top-level quota to that model."""
    settings = load_antigravity_settings()
    valid_ids = [m["id"] for m in SUPPORTED_MODELS]
    if model_id in valid_ids:
        settings["selected_model"] = model_id
        if "model_quotas" in settings and model_id in settings["model_quotas"]:
            active_q = settings["model_quotas"][model_id]
            settings["five_hour_limit"] = dict(active_q["five_hour_limit"])
            settings["weekly_limit"] = dict(active_q["weekly_limit"])
            settings["request_count"] = active_q.get("request_count", 0)
        save_antigravity_settings(settings)
    return settings


def increment_quota_usage(cost_weight: int = 2, model_id: str | None = None) -> dict:
    """Increments quota usage for the active (or specified) model on Antigravity action."""
    settings = load_antigravity_settings()
    target_model = model_id or settings.get("selected_model", "Gemini 3.8 Flash (High)")
    now_jst = datetime.now(JST)

    if "model_quotas" in settings and target_model in settings["model_quotas"]:
        q = settings["model_quotas"][target_model]
        q["last_active"] = now_jst.isoformat()
        q["request_count"] = q.get("request_count", 0) + 1

        if "(Local Ollama)" not in target_model:
            cur_5h = q.get("five_hour_limit", {}).get("used_percent", 30)
            cur_weekly = q.get("weekly_limit", {}).get("used_percent", 20)
            q["five_hour_limit"]["used_percent"] = min(100, cur_5h + cost_weight)
            q["weekly_limit"]["used_percent"] = min(100, cur_weekly + (cost_weight // 2 or 1))

        # Sync top-level if target is the currently selected model
        if target_model == settings.get("selected_model"):
            settings["five_hour_limit"] = dict(q["five_hour_limit"])
            settings["weekly_limit"] = dict(q["weekly_limit"])
            settings["request_count"] = q["request_count"]

        save_antigravity_settings(settings)

    return settings

