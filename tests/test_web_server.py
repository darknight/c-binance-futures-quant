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
