"""
System Telemetry & Metrics Collection for ALICE_Core Cockpit.
Collects CPU, RAM, GPU, Disk usage, and systemd service statuses with zero external dependencies.
"""
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger("ALICE_Core.Telemetry")

# Ensure standard system binary paths are present in PATH for systemd environment
for _sys_p in ["/usr/bin", "/bin", "/usr/local/bin"]:
    if _sys_p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{_sys_p}"

NVIDIA_SMI_BIN = shutil.which("nvidia-smi") or "/usr/bin/nvidia-smi"
SYSTEMCTL_BIN = shutil.which("systemctl") or "/usr/bin/systemctl"


def _get_cpu_temp() -> float | None:
    """Read CPU package or thermal zone temperature in Celsius."""
    try:
        for tz in ["thermal_zone3", "thermal_zone1", "thermal_zone2", "thermal_zone0"]:
            p = Path(f"/sys/class/thermal/{tz}")
            if p.exists():
                type_file = p / "type"
                temp_file = p / "temp"
                if type_file.exists() and temp_file.exists():
                    t_type = type_file.read_text().strip().lower()
                    if any(k in t_type for k in ["x86_pkg", "tcpu", "core", "package", "cpu"]):
                        raw = float(temp_file.read_text().strip())
                        return round(raw / 1000.0, 1) if raw > 1000 else round(raw, 1)
    except Exception:
        pass

    try:
        import glob
        for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_p = Path(h) / "name"
            if name_p.exists() and "coretemp" in name_p.read_text().lower():
                temp_p = Path(h) / "temp1_input"
                if temp_p.exists():
                    raw = float(temp_p.read_text().strip())
                    return round(raw / 1000.0, 1) if raw > 1000 else round(raw, 1)
    except Exception:
        pass
    return None


def _get_cpu_usage() -> dict[str, Any]:
    """Read CPU usage, core count, and package temperature."""
    cores = os.cpu_count() or 1
    cpu_percent = 0.0
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        fields = [float(x) for x in line.split()[1:]]
        idle_time = fields[3] + fields[4]
        total_time = sum(fields)
        with open("/proc/loadavg", "r") as f:
            load_1m = float(f.read().split()[0])
        cpu_percent = min(100.0, round((load_1m / cores) * 100, 1))
    except Exception as e:
        logger.debug(f"[Admin] Failed to read CPU: {e}")

    return {
        "cores": cores,
        "percent": cpu_percent,
        "temp": _get_cpu_temp(),
    }


def _get_memory_usage() -> dict[str, Any]:
    """Read RAM usage from /proc/meminfo."""
    total_kb = 0
    available_kb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
    except Exception as e:
        logger.debug(f"[Admin] Failed to read Mem: {e}")

    used_kb = max(0, total_kb - available_kb)
    percent = round((used_kb / total_kb * 100), 1) if total_kb > 0 else 0.0

    return {
        "total_gb": round(total_kb / (1024 * 1024), 2),
        "used_gb": round(used_kb / (1024 * 1024), 2),
        "percent": percent,
    }


_last_gpu_usage: dict[str, Any] | None = None
_last_gpu_time: float = 0.0


def _get_gpu_usage() -> dict[str, Any]:
    """Query NVIDIA GPU, VRAM usage, core utilization, and temperature via nvidia-smi with 1.0s caching."""
    global _last_gpu_usage, _last_gpu_time
    now = time.time()
    if _last_gpu_usage is not None and (now - _last_gpu_time) < 1.0:
        return _last_gpu_usage

    try:
        cmd = [
            NVIDIA_SMI_BIN,
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, timeout=2.0).decode("utf-8").strip()
        parts = [p.strip() for p in out.split(",")]
        name = parts[0]
        total_mb = float(parts[1])
        used_mb = float(parts[2])
        gpu_util = float(parts[3])
        gpu_temp = float(parts[4]) if len(parts) > 4 else None
        vram_percent = round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0.0

        res = {
            "available": True,
            "name": name,
            "total_mb": int(total_mb),
            "used_mb": int(used_mb),
            "total_gb": round(total_mb / 1024, 2),
            "used_gb": round(used_mb / 1024, 2),
            "vram_percent": vram_percent,
            "gpu_util_percent": gpu_util,
            "temp": gpu_temp,
        }
        _last_gpu_usage = res
        _last_gpu_time = now
        return res
    except Exception:
        fallback = {
            "available": False,
            "name": "N/A",
            "total_gb": 0,
            "used_gb": 0,
            "vram_percent": 0.0,
            "gpu_util_percent": 0.0,
            "temp": None,
        }
        _last_gpu_usage = fallback
        _last_gpu_time = now
        return fallback


def _get_disk_usage() -> dict[str, Any]:
    """Get disk usage of /data and root / runtimes."""
    drives = []
    # 1. System Root (/)
    try:
        u_root = shutil.disk_usage("/")
        root_tot = round(u_root.total / (1024**3), 2)
        root_used = round(u_root.used / (1024**3), 2)
        root_pct = round((u_root.used / u_root.total) * 100, 1)
        drives.append({
            "mount": "/",
            "name": "System (/)",
            "total_gb": root_tot,
            "used_gb": root_used,
            "percent": root_pct,
        })
    except Exception:
        pass

    # 2. Workspaces (/data)
    data_stat = {"total_gb": 0, "used_gb": 0, "percent": 0.0}
    try:
        u_data = shutil.disk_usage("/data")
        data_tot = round(u_data.total / (1024**3), 2)
        data_used = round(u_data.used / (1024**3), 2)
        data_pct = round((u_data.used / u_data.total) * 100, 1)
        data_stat = {"total_gb": data_tot, "used_gb": data_used, "percent": data_pct}
        drives.append({
            "mount": "/data",
            "name": "Workspaces (/data)",
            "total_gb": data_tot,
            "used_gb": data_used,
            "percent": data_pct,
        })
    except Exception:
        pass

    return {
        "total_gb": data_stat["total_gb"],
        "used_gb": data_stat["used_gb"],
        "percent": data_stat["percent"],
        "drives": drives,
    }


def _get_service_status() -> dict[str, str]:
    """Check systemd service active status with process fallback."""
    services = {
        "core": "alice-core.service",
        "copilot": "alice-copilot.service",
        "ollama": "ollama.service",
    }
    result = {}
    for key, svc in services.items():
        try:
            cmd = [SYSTEMCTL_BIN, "is-active", svc]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            status_text = (res.stdout or res.stderr or "").strip().lower()
            if status_text in ("active", "activating", "reloading"):
                result[key] = "active"
            elif status_text in ("inactive", "deactivating"):
                result[key] = "inactive"
            elif status_text in ("failed",):
                result[key] = "failed"
            else:
                result[key] = status_text or "unknown"
        except Exception:
            result[key] = "unknown"

    # CoPilot 手動稼働プロセス（ALICE_CoPilot/main.py）のフォールバック検知
    if result.get("copilot") != "active":
        try:
            p_check = subprocess.run(["pgrep", "-f", "ALICE_CoPilot/main.py"], capture_output=True, text=True, timeout=1.0)
            if p_check.returncode == 0 and p_check.stdout.strip():
                result["copilot"] = "active"
        except Exception:
            pass

    # LINE Gateway status (Active when Core is active)
    result["line"] = "active" if result.get("core") == "active" else "inactive"

    return result
