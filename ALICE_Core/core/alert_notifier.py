"""
ALICE_Core Discord Alert Notifier.
Sends structured incident alerts directly to Discord (#alerts) via Webhook.
"""
import logging
import os
import requests
from datetime import datetime
from typing import Any

import config
from models.job import Job

logger = logging.getLogger("ALICE_Core.AlertNotifier")


def send_discord_alert(
    job: Job,
    error_type: str = "JOB_EXECUTION_FAILURE",
    message: str = "Unknown error occurred",
    level: str = "ERROR",
    extra_fields: dict[str, str] | None = None,
    webhook_url: str | None = None,
) -> bool:
    """Send structured incident alert for a Job to Discord Webhook.

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    target_url = webhook_url if webhook_url is not None else getattr(config, "DISCORD_ALERT_WEBHOOK_URL", "")
    if not target_url:
        logger.debug("[AlertNotifier] DISCORD_ALERT_WEBHOOK_URL is not set. Skipping Discord alert.")
        return False

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = 0xE74C3C if level.upper() == "ERROR" else 0xF39C12  # Red or Orange

    title = f"[{level.upper()}] {error_type}"
    original_filename = getattr(job, "original_filename", "") or (
        job.input_metadata.get("original_filename") if hasattr(job, "input_metadata") and job.input_metadata else "N/A"
    )

    failed_step = job.current_step or (
        job.error_detail.get("failed_step") if hasattr(job, "error_detail") and job.error_detail else "N/A"
    )

    # Clean multi-line message as quote block
    clean_message = "\n".join(f"> {line}" for line in (message or "No details").splitlines())
    if len(clean_message) > 1000:
        clean_message = clean_message[:995] + "..."

    fields = [
        {"name": "Job ID", "value": f"`{job.job_id}`", "inline": True},
        {"name": "User ID", "value": f"`{job.user_id}`", "inline": True},
        {"name": "対象ファイル", "value": f"`{original_filename}`", "inline": False},
        {"name": "失敗ステップ", "value": f"`{failed_step}`", "inline": True},
        {"name": "ワークフロー", "value": f"`{job.workflow}`", "inline": True},
        {"name": "エラー詳細", "value": clean_message, "inline": False},
    ]

    log_file = (
        job.error_detail.get("log_file")
        if hasattr(job, "error_detail") and job.error_detail
        else None
    )
    if log_file:
        fields.append({"name": "ログファイル", "value": f"`{log_file}`", "inline": False})

    if extra_fields:
        for k, v in extra_fields.items():
            fields.append({"name": k, "value": f"`{v}`", "inline": True})

    payload = {
        "embeds": [
            {
                "title": title,
                "color": color,
                "fields": fields,
                "footer": {"text": f"ALICE Core Alert System | {now_str}"},
            }
        ]
    }

    try:
        resp = requests.post(target_url, json=payload, timeout=5.0)
        if resp.status_code in (200, 204):
            logger.info(f"[AlertNotifier] Successfully dispatched Discord alert for job {job.job_id}")
            return True
        else:
            logger.warning(f"[AlertNotifier] Discord webhook returned status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"[AlertNotifier] Failed to send Discord alert: {e}")
        return False


def send_system_alert(
    title: str,
    message: str,
    level: str = "WARN",
    extra_fields: dict[str, str] | None = None,
    webhook_url: str | None = None,
) -> bool:
    """Send system-level alert (not bound to a single Job) to Discord Webhook."""
    target_url = webhook_url if webhook_url is not None else getattr(config, "DISCORD_ALERT_WEBHOOK_URL", "")
    if not target_url:
        logger.debug("[AlertNotifier] DISCORD_ALERT_WEBHOOK_URL is not set. Skipping Discord alert.")
        return False

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = 0xE74C3C if level.upper() == "ERROR" else 0xF39C12

    clean_message = "\n".join(f"> {line}" for line in message.splitlines())
    fields = [
        {"name": "詳細", "value": clean_message, "inline": False},
    ]
    if extra_fields:
        for k, v in extra_fields.items():
            fields.append({"name": k, "value": f"`{v}`", "inline": True})

    payload = {
        "embeds": [
            {
                "title": f"[{level.upper()}] {title}",
                "color": color,
                "fields": fields,
                "footer": {"text": f"ALICE Core Alert System | {now_str}"},
            }
        ]
    }

    try:
        resp = requests.post(target_url, json=payload, timeout=5.0)
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.warning(f"[AlertNotifier] Failed to send system alert: {e}")
        return False


def send_mfa_approval_alert(
    request_id: str,
    approval_token: str,
    client_ip: str,
    user_agent: str,
    expires_in_minutes: int = 5,
    webhook_url: str | None = None,
) -> bool:
    """Send an MFA approval request to Discord (#alerts) with a one-tap approval URL."""
    target_url = webhook_url if webhook_url is not None else getattr(config, "DISCORD_ALERT_WEBHOOK_URL", "")
    if not target_url:
        logger.debug("[AlertNotifier] DISCORD_ALERT_WEBHOOK_URL is not set. Skipping Discord MFA alert.")
        return False

    public_url = getattr(config, "PUBLIC_URL", "https://project-alice.net").rstrip("/")
    approval_url = f"{public_url}/admin/api/mfa/approve-link?token={approval_token}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = 0xF1C40F  # Bright Gold / Alert Yellow

    device_desc = user_agent or "Unknown Device"
    if "iPhone" in device_desc:
        device_desc = "iPhone (Safari/App)"
    elif "Android" in device_desc:
        device_desc = "Android (Mobile)"
    elif "Windows" in device_desc:
        device_desc = "Windows PC"
    elif "Macintosh" in device_desc or "Mac OS" in device_desc:
        device_desc = "Mac PC"

    fields = [
        {"name": "接続元 IP", "value": f"`{client_ip}`", "inline": True},
        {"name": "アクセス端末", "value": f"`{device_desc}`", "inline": True},
        {"name": "有効期限", "value": f"{expires_in_minutes}分間", "inline": True},
        {
            "name": "ワンタップ承認リンク",
            "value": f"**[👉 ここをタップしてログインを承認する]({approval_url})**\n*(※心当たりがない場合は無視してください。アクセスは自動的に破棄されます)*",
            "inline": False,
        },
    ]

    payload = {
        "embeds": [
            {
                "title": "🚨 [MFA / ログイン承認要求] 外部端末からのアクセス検知",
                "description": "外部ネットワークから管理コックピット（`/admin`）へのログイン試行がありました。\n心当たりがある場合は、以下のリンクをタップしてログインを承認してください。",
                "color": color,
                "fields": fields,
                "footer": {"text": f"ALICE Core Security Gateway | {now_str}"},
            }
        ]
    }

    try:
        resp = requests.post(target_url, json=payload, timeout=5.0)
        if resp.status_code in (200, 204):
            logger.info(f"[AlertNotifier] Successfully sent MFA approval alert to Discord for request {request_id}")
            return True
        else:
            logger.warning(f"[AlertNotifier] Discord webhook returned status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"[AlertNotifier] Failed to send MFA approval alert: {e}")
        return False
