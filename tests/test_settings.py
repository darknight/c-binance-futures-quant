import os
import pytest


def test_settings_has_server_name():
    """server_name field exists and defaults to empty string."""
    os.environ.pop("SERVER_NAME", None)
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.Settings(_env_file=None)
    assert s.server_name == ""


def test_settings_has_machine_index():
    """machine_index field exists and defaults to 0."""
    s = _make_settings()
    assert s.machine_index == 0


def test_settings_has_service_host_fields():
    """Service host fields exist with correct defaults."""
    s = _make_settings()
    assert s.tick_instance_count == 1
    assert s.vol_rate_host_a == ""
    assert s.vol_rate_host_b == ""
    assert s.second_open_hosts == "[]"


def test_settings_no_aliyun_fields():
    """Aliyun fields should no longer exist."""
    s = _make_settings()
    assert not hasattr(s, "aliyun_api_key")
    assert not hasattr(s, "aliyun_api_secret")
    assert not hasattr(s, "aliyun_point")


def _make_settings():
    from settings import Settings
    return Settings(_env_file=None)
