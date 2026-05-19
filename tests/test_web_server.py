from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from web_server.state import AppState
from web_server.routers import config, market, orders, trading, income, records, status, account, dashboard


def _make_test_app():
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(config.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


def test_health_endpoint():
    app = _make_test_app()
    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_cors_headers():
    app = _make_test_app()
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
    app = _make_test_app()
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
    app = _make_test_app()
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
    app = _make_test_app()
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


def _create_test_app():
    """Create a test app with mocked lifespan (no Binance/DB calls).

    This mirrors the production router registration in web_server.app.
    Dashboard endpoint behavior is covered separately in test_dashboard.py.
    """
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    state = AppState()
    state.infra_client = MagicMock()
    state.infra_client.get_session = MagicMock()
    app.state.app_state = state

    app.include_router(config.router)
    app.include_router(market.router)
    app.include_router(orders.router)
    app.include_router(trading.router)
    app.include_router(income.router)
    app.include_router(records.router)
    app.include_router(status.router)
    app.include_router(account.router)
    app.include_router(dashboard.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


def test_health_with_mocked_app():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_get_invest_percent():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/get_invest_percent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["s"] == "ok"
    assert len(data["r"]) == 5


def test_end_open_unknown_symbol():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/end_open", data={"symbol": "UNKNOWN"})
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_all_routes_registered():
    """Verify all expected routes are registered on the app."""
    app = _create_test_app()
    routes = [route.path for route in app.routes if hasattr(route, "path")]
    expected_endpoints = [
        "/health",
        "/get_config",
        "/get_symbol_index",
        "/modify_hot_key",
        "/get_state_config",
        "/modify_state_config",
        "/get_depth",
        "/get_one_min_select_kline",
        "/change_leverage",
        "/cancel_orders",
        "/cancel_order",
        "/get_all_open_orders",
        "/cancel_binance_orders",
        "/cancel_binance_order",
        "/get_commission_rate",
        "/open_position",
        "/close_position",
        "/stop_loss_batch",
        "/stop_loss_once",
        "/stop_profit_batch",
        "/stop_profit_once",
        "/take_open",
        "/end_open",
        "/get_income_obj",
        "/r",
        "/get_day_income",
        "/get_invest_percent",
        "/get_position_record",
        "/get_history_position_record",
        "/get_big_loss_trades",
        "/begin_trade_record",
        "/get_order_result_arr",
        "/get_trades_result_arr",
        "/ping",
        "/check_maker_server_in_data",
        "/update_maker_server_run_info",
        "/get_customize_dangerous",
        "/update_customize_dangerous",
        "/update_machine_status",
        "/update_trade_status",
        "/get_trade_status",
        "/get_all_acount_info",
        "/get_all_open_orders_b",
        "/get_position",
        "/get_trade_record",
        "/get_second_open_position",
        "/update_loss_limit_time",
        "/get_watch_info",
        "/get_one_day_rate",
        "/get_dashboard_summary",
        "/get_profit_by_symbol",
    ]
    for ep in expected_endpoints:
        assert ep in routes, f"Missing route: {ep}"
