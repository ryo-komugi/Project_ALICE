"""
[Facade / Compatibility Shim]
This module has been relocated to `infrastructure.system_settings`.
Importing from `core.system_settings` is maintained for backward compatibility.
"""
from infrastructure.system_settings import *  # noqa: F401, F403
from infrastructure.system_settings import (
    is_maintenance_active,
    get_maintenance_message,
    is_admin_bypass_allowed,
    update_system_settings,
    get_system_settings,
)
