from fastapi.testclient import TestClient
from web_server.app import create_app
from web_server.state import AppState


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_cors_headers():
    app = create_app()
    client = TestClient(app)
    resp = client.options("/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_app_state_defaults():
    state = AppState()
    assert state.price_decimal_obj == {}
    assert state.order_id_index >= 1
    assert state.income_obj["15m"]["c"] == 0
    assert len(state.position_arr) == 10


def test_app_state_next_order_id():
    state = AppState()
    first = state.order_id_index
    result = state.next_order_id()
    assert result == first + 1
    assert state.order_id_index == first + 1


from web_server.binance_helpers import json_dumps, UTCEncoder
from datetime import datetime


def test_utc_encoder_datetime():
    dt = datetime(2024, 1, 15, 12, 0, 0)
    result = json_dumps({"time": dt})
    assert "2024-01-15T12:00:00" in result


def test_utc_encoder_non_datetime():
    result = json_dumps({"value": 42})
    assert '"value": 42' in result


import os
import tempfile
from unittest.mock import patch


def test_get_config():
    app = create_app()
    client = TestClient(app)
    with patch("web_server.routers.config.settings") as mock_settings:
        mock_settings.binance_api_arr = '[{"apiKey":"abc","apiSecret":"secret123","apiDescribe":"test"}]'
        resp = client.post("/get_config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["s"] == "ok"
    assert data["binanceApiArr"][0]["apiSecret"] == ""
    assert data["binanceApiArr"][0]["apiKey"] == "abc"


def test_modify_hot_key():
    app = create_app()
    client = TestClient(app)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{}')
        temp_path = f.name
    try:
        with patch("web_server.routers.config.USER_CONFIG_PATH", temp_path):
            resp = client.post("/modify_hot_key", data={"newHotKeyConfigObj": '{"key1":"value1"}'})
        assert resp.status_code == 200
        assert resp.json()["newHotKeyConfigObj"] == {"key1": "value1"}
    finally:
        os.unlink(temp_path)


def test_get_state_config():
    app = create_app()
    client = TestClient(app)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        import json as _json
        _json.dump({"state_config_obj": {"mode": "test"}}, f)
        temp_path = f.name
    try:
        with patch("web_server.routers.config.USER_CONFIG_PATH", temp_path):
            resp = client.post("/get_state_config")
        assert resp.status_code == 200
        assert resp.json()["stateConfigObj"] == {"mode": "test"}
    finally:
        os.unlink(temp_path)
