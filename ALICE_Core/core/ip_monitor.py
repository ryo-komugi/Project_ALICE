"""
ALICE_Core Global IP Change Monitor.
Monitors home residential global IP changes and notifies Discord #alerts
so that Cloudflare Zero Trust (Access) 'Bypass Home' IP policies can be updated.
"""
import asyncio
import ipaddress
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

import config
from core.alert_notifier import send_system_alert

logger = logging.getLogger("ALICE_Core.IPMonitor")

DEFAULT_IP_CACHE_PATH = Path(getattr(config, "DIR_CORE_RUNTIME", "/data/runtime/core")) / "last_global_ip.txt"

# Reliable plain-text IP resolution providers
IP_PROVIDERS = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
]


def fetch_current_global_ip(timeout: float = 3.5) -> Optional[str]:
    """Fetch current external global IP using reliable providers with fallback."""
    for url in IP_PROVIDERS:
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "curl/7.88.1"})
            if resp.status_code == 200:
                raw_ip = resp.text.strip()
                # Validate that it is a valid IP address
                ip_obj = ipaddress.ip_address(raw_ip)
                if not ip_obj.is_loopback and not ip_obj.is_multicast:
                    return str(ip_obj)
        except Exception as e:
            logger.debug(f"[IPMonitor] Failed to fetch IP from {url}: {e}")
            continue

    logger.warning("[IPMonitor] All external IP resolution providers failed.")
    return None


def get_cached_global_ip(cache_file: Path | str = DEFAULT_IP_CACHE_PATH) -> Optional[str]:
    """Read cached global IP from disk if exists."""
    path = Path(cache_file)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            # Validate IP format
            ipaddress.ip_address(content)
            return content
    except Exception as e:
        logger.warning(f"[IPMonitor] Could not read valid IP from cache file {path}: {e}")
    return None


def save_cached_global_ip(ip_str: str, cache_file: Path | str = DEFAULT_IP_CACHE_PATH) -> bool:
    """Save detected global IP to cache file."""
    path = Path(cache_file)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ip_str, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"[IPMonitor] Failed to write cache file {path}: {e}")
        return False


def check_and_notify_ip_change(
    cache_file: Path | str = DEFAULT_IP_CACHE_PATH,
    force_alert: bool = False,
) -> dict[str, Any]:
    """
    Check current global IP against cached value.
    If IP changed (or force_alert=True), dispatch Discord #alerts notification and update cache.
    """
    current_ip = fetch_current_global_ip()
    if not current_ip:
        return {"status": "error", "message": "Failed to resolve external global IP"}

    cached_ip = get_cached_global_ip(cache_file)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. First run / No cached IP: Initialize baseline silently
    if not cached_ip:
        save_cached_global_ip(current_ip, cache_file)
        logger.info(f"[IPMonitor] Initialized baseline global IP: {current_ip}")
        return {
            "status": "initialized",
            "current_ip": current_ip,
            "previous_ip": None,
            "alert_sent": False,
        }

    # 2. IP changed or forced check
    if current_ip != cached_ip or force_alert:
        logger.warning(f"[IPMonitor] Detected global IP change: {cached_ip} -> {current_ip}")

        extra_fields = {
            "旧IP (Previous)": cached_ip,
            "新IP (Current)": current_ip,
            "検知日時": now_str,
            "対応手順": "Cloudflare Zero Trust ➔ Access ➔ Policies ➔「Bypass Home」の IP ranges を新IPに変更",
            "ダッシュボードURL": "https://one.dash.cloudflare.com/",
        }

        alert_sent = send_system_alert(
            title="【自宅IP変更検知】Cloudflare Zero Trust の更新が必要です",
            message=(
                "自宅のグローバルIPアドレスの変更を検知しました。\n"
                "Cloudflare Zero Trust の「Bypass Home」ポリシーの更新が必要です。\n"
                "※更新するまで、自宅PCからのアクセス時に15分ワンタイムPINが要求されます。"
            ),
            level="WARN",
            extra_fields=extra_fields,
        )

        save_cached_global_ip(current_ip, cache_file)

        return {
            "status": "changed" if current_ip != cached_ip else "forced",
            "current_ip": current_ip,
            "previous_ip": cached_ip,
            "alert_sent": alert_sent,
        }

    # 3. IP unchanged
    logger.debug(f"[IPMonitor] Global IP unchanged: {current_ip}")
    return {
        "status": "unchanged",
        "current_ip": current_ip,
        "previous_ip": cached_ip,
        "alert_sent": False,
    }


async def ip_monitor_loop(
    interval_seconds: int = 1800,
    cache_file: Path | str = DEFAULT_IP_CACHE_PATH,
    startup_delay: float = 10.0,
):
    """Background loop checking global IP every interval_seconds (default: 30 minutes)."""
    logger.info(f"[IPMonitor] Background loop scheduled (interval: {interval_seconds}s)")
    if startup_delay > 0:
        await asyncio.sleep(startup_delay)

    while True:
        try:
            res = check_and_notify_ip_change(cache_file)
            if res.get("status") in ("changed", "initialized"):
                logger.info(f"[IPMonitor] Check result: {res}")
        except asyncio.CancelledError:
            logger.info("[IPMonitor] Loop cancelled.")
            break
        except Exception as e:
            logger.warning(f"[IPMonitor] Unexpected exception in loop: {e}")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[IPMonitor] Loop cancelled during sleep.")
            break
