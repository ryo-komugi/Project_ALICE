"""
Test Infrastructure and Core Facade Compatibility.
Verifies that all infrastructure modules are importable directly and via backward-compatible core facades.
"""
import pytest

def test_infrastructure_and_core_facade_logger():
    import infrastructure.logger as infra_log
    import core.logger as core_log

    assert infra_log.initialize_logger is core_log.initialize_logger
    assert infra_log.cleanup_logs is core_log.cleanup_logs
    assert infra_log.ARCHIVE_DIR == core_log.ARCHIVE_DIR
    assert infra_log.LOG_FILE == core_log.LOG_FILE

def test_infrastructure_and_core_facade_alert_notifier():
    import infrastructure.alert_notifier as infra_alert
    import core.alert_notifier as core_alert

    assert infra_alert.send_discord_alert is core_alert.send_discord_alert
    assert infra_alert.send_system_alert is core_alert.send_system_alert

def test_infrastructure_and_core_facade_ip_monitor():
    import infrastructure.ip_monitor as infra_ip
    import core.ip_monitor as core_ip

    assert infra_ip.ip_monitor_loop is core_ip.ip_monitor_loop
    assert infra_ip.check_and_notify_ip_change is core_ip.check_and_notify_ip_change
    assert infra_ip.fetch_current_global_ip is core_ip.fetch_current_global_ip

def test_infrastructure_and_core_facade_system_settings():
    import infrastructure.system_settings as infra_settings
    import core.system_settings as core_settings

    assert infra_settings.is_maintenance_active is core_settings.is_maintenance_active
    assert infra_settings.get_maintenance_message is core_settings.get_maintenance_message
    assert infra_settings.is_admin_bypass_allowed is core_settings.is_admin_bypass_allowed
    assert infra_settings.update_system_settings is core_settings.update_system_settings
    assert infra_settings.get_system_settings is core_settings.get_system_settings
