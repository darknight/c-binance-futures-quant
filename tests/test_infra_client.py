import os
import pytest


def test_infra_client_has_no_aliyun_imports():
    """infra_client.py should not import any aliyun SDK modules."""
    import inspect
    import infra_client as mod
    source = inspect.getsource(mod)
    assert "aliyunsdkcore" not in source
    assert "aliyunsdkecs" not in source
    assert "AcsClient" not in source
    assert "DescribeInstancesRequest" not in source


def test_infra_client_has_no_ecs_methods():
    """InfraClient should not have ECS discovery methods."""
    from infra_client import InfraClient
    assert not hasattr(InfraClient, "getServerName")
    assert not hasattr(InfraClient, "get_aliyun_private_ip_arr_by_name")
    assert not hasattr(InfraClient, "get_aliyun_public_ip_arr_by_name")


def test_infra_client_reads_server_name_from_settings(monkeypatch):
    """InfraClient.__init__ should read serverName from settings, not ECS API."""
    monkeypatch.setenv("SERVER_NAME", "test_machine_42")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    # Reload settings and infra_client to pick up env
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    import infra_client as infra_mod
    importlib.reload(infra_mod)
    client = infra_mod.InfraClient(larkMsgSymbol="test")
    assert client.serverName == "test_machine_42"
