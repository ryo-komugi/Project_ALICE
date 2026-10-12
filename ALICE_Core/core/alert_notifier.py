"""
[Facade / Compatibility Shim]
This module has been relocated to `infrastructure.alert_notifier`.
Importing from `core.alert_notifier` is maintained for backward compatibility.
"""
from infrastructure.alert_notifier import *  # noqa: F401, F403
from infrastructure.alert_notifier import send_discord_alert, send_system_alert
