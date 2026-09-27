"""
[Facade / Compatibility Shim]
This module has been relocated to `infrastructure.ip_monitor`.
Importing from `core.ip_monitor` is maintained for backward compatibility.
"""
from infrastructure.ip_monitor import *  # noqa: F401, F403
from infrastructure.ip_monitor import (
    ip_monitor_loop,
    check_and_notify_ip_change,
    fetch_current_global_ip,
    get_cached_global_ip,
    save_cached_global_ip,
)
