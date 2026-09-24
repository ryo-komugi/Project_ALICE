"""
System inspection and job monitoring tools for ALICE_CoPilot.
Zero external pip dependencies: uses /proc, /sys, shutil, os, sqlite3, and nvidia-smi.
"""
import json
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
import config

logger = logging.getLogger("ALICE_CoPilot.Tools.System")

DB_PATH = Path("/data/runtime/search/alice_index.db")
WORKSPACES_ROOT = Path("/data/runtime/workspaces")
STATS_PATH = Path("/data/runtime/copilot/system_daily_stats.json")


def get_cpu_temp_c() -> float | None:
    """Read CPU temperature from /sys/class/hwmon (e.g. coretemp)."""
    hwmon_root = Path("/sys/class/hwmon")
    if not hwmon_root.exists():
        return None

    try:
        for hwmon in hwmon_root.iterdir():
            name_file = hwmon / "name"
            if name_file.exists():
                name = name_file.read_text(encoding="utf-8").strip()
                if "coretemp" in name:
                    temp_file = hwmon / "temp1_input"
                    if temp_file.exists():
                        milli_c = int(temp_file.read_text(encoding="utf-8").strip())
                        return round(milli_c / 1000.0, 1)
    except Exception as e:
        logger.debug(f"[get_cpu_temp_c] Error reading CPU temp: {e}")
    return None


def get_gpu_metrics() -> dict[str, Any] | None:
    """Read GPU metrics from nvidia-smi."""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 5:
                used_mb = int(parts[1])
                total_mb = int(parts[2])
                return {
                    "name": parts[0],
                    "memory_used_mb": used_mb,
                    "memory_total_mb": total_mb,
                    "memory_percent": round((used_mb / total_mb) * 100, 1) if total_mb else 0,
                    "utilization_percent": int(parts[3]),
                    "temperature_c": int(parts[4]),
                }
    except Exception as e:
        logger.debug(f"[get_gpu_metrics] Error reading GPU metrics: {e}")
    return None


def get_ram_metrics() -> dict[str, Any]:
    """Read RAM and swap metrics from /proc/meminfo."""
    mem_total_kb, mem_avail_kb, swap_total_kb, swap_free_kb = 0, 0, 0, 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(parts[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(parts[1])
                elif line.startswith("SwapTotal:"):
                    swap_total_kb = int(parts[1])
                elif line.startswith("SwapFree:"):
                    swap_free_kb = int(parts[1])
    except Exception as e:
        logger.debug(f"[get_ram_metrics] Error reading /proc/meminfo: {e}")

    ram_total_gb = round(mem_total_kb / (1024 * 1024), 1)
    ram_used_gb = round((mem_total_kb - mem_avail_kb) / (1024 * 1024), 1)
    ram_percent = round((ram_used_gb / ram_total_gb) * 100, 1) if ram_total_gb else 0

    swap_total_gb = round(swap_total_kb / (1024 * 1024), 1)
    swap_used_gb = round((swap_total_kb - swap_free_kb) / (1024 * 1024), 1)

    return {
        "used_gb": ram_used_gb,
        "total_gb": ram_total_gb,
        "percent": ram_percent,
        "swap_used_gb": swap_used_gb,
        "swap_total_gb": swap_total_gb,
    }


def get_storage_metrics() -> dict[str, Any]:
    """Read disk usage for /data and root partitions."""
    disks = {}
    for mount_point, key in [("/data", "data_partition"), ("/", "root_partition")]:
        try:
            du = shutil.disk_usage(mount_point)
            disks[key] = {
                "mount": mount_point,
                "used_gb": round(du.used / (1024**3), 1),
                "total_gb": round(du.total / (1024**3), 1),
                "percent": round((du.used / du.total) * 100, 1),
            }
        except Exception:
            pass
    return disks


def get_services_status() -> dict[str, str]:
    """Check status of ALICE related services via systemctl."""
    services = ["alice-core.service", "alice-copilot.service", "ollama.service"]
    status_map = {}
    for s in services:
        try:
            res = subprocess.run(
                ["systemctl", "is-active", s],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            status_map[s] = res.stdout.strip()
        except Exception:
            status_map[s] = "unknown"
    return status_map


def update_daily_peaks(
    gpu: dict[str, Any] | None = None,
    cpu_temp: float | None = None,
    ram: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update and persist today's peak metrics atomically into STATS_PATH.
    If date changes, previous peaks reset for the new day.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    if gpu is None:
        gpu = get_gpu_metrics() or {}
    if cpu_temp is None:
        cpu_temp = get_cpu_temp_c()
    if ram is None:
        ram = get_ram_metrics()

    stats = {
        "date": today,
        "vram_peak_mb": 0,
        "vram_peak_time": now_time,
        "vram_peak_percent": 0.0,
        "gpu_util_peak_percent": 0,
        "gpu_temp_peak_c": 0,
        "cpu_temp_peak_c": 0.0,
        "ram_peak_gb": 0.0,
    }

    if STATS_PATH.exists():
        try:
            with open(STATS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("date") == today:
                    stats = saved
        except Exception:
            pass

    cur_vram = gpu.get("memory_used_mb", 0)
    if cur_vram > stats.get("vram_peak_mb", 0):
        stats["vram_peak_mb"] = cur_vram
        stats["vram_peak_time"] = now_time
        stats["vram_peak_percent"] = gpu.get("memory_percent", 0.0)

    cur_gpu_util = gpu.get("utilization_percent", 0)
    if cur_gpu_util > stats.get("gpu_util_peak_percent", 0):
        stats["gpu_util_peak_percent"] = cur_gpu_util

    cur_gpu_temp = gpu.get("temperature_c", 0)
    if cur_gpu_temp > stats.get("gpu_temp_peak_c", 0):
        stats["gpu_temp_peak_c"] = cur_gpu_temp

    if cpu_temp is not None and cpu_temp > stats.get("cpu_temp_peak_c", 0.0):
        stats["cpu_temp_peak_c"] = cpu_temp

    cur_ram = ram.get("used_gb", 0.0)
    if cur_ram > stats.get("ram_peak_gb", 0.0):
        stats["ram_peak_gb"] = cur_ram

    try:
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = STATS_PATH.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        tmp_path.replace(STATS_PATH)
    except Exception as e:
        logger.error(f"[update_daily_peaks] Error saving stats: {e}")

    return stats


def get_system_status() -> dict[str, Any]:
    """
    Get current server resource usage (GPU, CPU, RAM, Disk, Services)
    along with today's peak metrics.
    """
    gpu = get_gpu_metrics() or {}
    cpu_temp = get_cpu_temp_c()
    ram = get_ram_metrics()

    cpu_info: dict[str, Any] = {}
    try:
        load1, load5, load15 = os.getloadavg()
        cpu_info["load_1m"] = round(load1, 2)
        cpu_info["load_5m"] = round(load5, 2)
        cpu_info["load_15m"] = round(load15, 2)
    except Exception:
        pass
    if cpu_temp is not None:
        cpu_info["temperature_c"] = cpu_temp

    storage = get_storage_metrics()
    services = get_services_status()

    # Update peaks with current values
    today_peaks = update_daily_peaks(gpu=gpu, cpu_temp=cpu_temp, ram=ram)

    return {
        "current": {
            "gpu": gpu,
            "cpu": cpu_info,
            "ram": ram,
            "storage": storage,
            "services": services,
        },
        "today_peaks": today_peaks,
    }


def get_recent_jobs(limit: int = 5, status_filter: str | None = None) -> list[dict[str, Any]]:
    """
    Get recent audio jobs processed by ALICE for the owner.

    Args:
        limit: Number of jobs to return (default 5)
        status_filter: Optional filter ('COMPLETED', 'FAILED', etc.)

    Returns:
        list[dict]: List of jobs with status, filename, created_at, and error details if failed.
    """
    if not DB_PATH.exists():
        return []

    owner_id = getattr(config, "OWNER_CORE_USER_ID", "U794535d58fb802ac996f4a86ce119ad2")
    jobs = []

    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            sql = """
                SELECT job_id, user_id, status, workflow, original_filename, created_at
                FROM jobs_metadata
                WHERE user_id = ?
            """
            params: list[Any] = [owner_id]
            if status_filter:
                sql += " AND status = ?"
                params.append(status_filter.upper().strip())
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                job_id, user_id, status, workflow, original_name, created_at = r
                job_info: dict[str, Any] = {
                    "job_id": job_id,
                    "status": status,
                    "workflow": workflow,
                    "original_filename": original_name or job_id,
                    "created_at": created_at[:16].replace("T", " ") if created_at else "日時不明",
                }

                if status == "FAILED":
                    job_json_path = WORKSPACES_ROOT / job_id / "job.json"
                    if job_json_path.exists():
                        try:
                            with open(job_json_path, "r", encoding="utf-8") as f:
                                jdata = json.load(f)
                                job_info["error_message"] = jdata.get("error_message")
                                error_detail = jdata.get("error_detail")
                                if error_detail:
                                    job_info["failed_step"] = error_detail.get("failed_step")
                                    job_info["error_detail_message"] = error_detail.get("message")
                        except Exception:
                            pass

                jobs.append(job_info)
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[get_recent_jobs] Error: {e}")

    return jobs
