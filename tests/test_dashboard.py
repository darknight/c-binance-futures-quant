import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.models.income_history_take import IncomeHistoryTake
from app.models.machine_status import TradeMachineStatus  # noqa: F401 – needed for create_all
from app.models.position_record import PositionRecord
from web_server.state import AppState


def _make_app_with_state(state: AppState):
    from fastapi import FastAPI
    from web_server.routers import dashboard

    app = FastAPI()
    app.include_router(dashboard.router)
    app.state.app_state = state
    return app


def _create_test_state() -> AppState:
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    state = AppState()
    infra = MagicMock()

    @contextmanager
    def mock_get_session():
        with Session(engine) as session:
            yield session

    infra.get_session = mock_get_session
    state.infra_client = infra

    # Seed position records
    with Session(engine) as session:
        now_ts = int(time.time())
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        session.add(
            PositionRecord(
                symbol="BTCUSDT",
                position_amt=Decimal("0.5"),
                position_value=Decimal("15000"),
                balance=Decimal("20000"),
                time=now_dt,
                ts=now_ts,
                profit=Decimal("100"),
                commission=Decimal("10"),
                maker_commission=Decimal("5"),
                unrealized_profit=Decimal("50"),
            )
        )
        session.add(
            PositionRecord(
                symbol="ETHUSDT",
                position_amt=Decimal("5"),
                position_value=Decimal("8000"),
                balance=Decimal("20000"),
                time=now_dt,
                ts=now_ts,
                profit=Decimal("50"),
                commission=Decimal("5"),
                maker_commission=Decimal("2"),
                unrealized_profit=Decimal("20"),
            )
        )

        # Seed income history — use timestamp from 2 days ago (in ms)
        yesterday_ms = int(time.time() * 1000) - 2 * 86400 * 1000
        session.add(
            IncomeHistoryTake(
                income_type="REALIZED_PNL",
                income=Decimal("100.0"),
                bnb_price=Decimal("600.0"),
                asset="USDT",
                symbol="BTCUSDT",
                binance_ts=yesterday_ms,
                trade_id="1",
                api_key="test",
            )
        )
        session.add(
            IncomeHistoryTake(
                income_type="COMMISSION",
                income=Decimal("-0.5"),
                bnb_price=Decimal("600.0"),
                asset="BNB",
                symbol="BTCUSDT",
                binance_ts=yesterday_ms,
                trade_id="2",
                api_key="test",
            )
        )
        session.add(
            IncomeHistoryTake(
                income_type="FUNDING_FEE",
                income=Decimal("5.0"),
                bnb_price=Decimal("600.0"),
                asset="USDT",
                symbol="ETHUSDT",
                binance_ts=yesterday_ms,
                trade_id="3",
                api_key="test",
            )
        )
        session.commit()

    return state


def test_get_dashboard_summary():
    state = _create_test_state()
    state.income_obj = {
        "today": {"c": -50.0, "p": 200.0, "s": 10.0},
        "15m": {"c": 0, "p": 0, "s": 0},
        "30m": {"c": 0, "p": 0, "s": 0},
        "1h": {"c": 0, "p": 0, "s": 0},
        "4h": {"c": 0, "p": 0, "s": 0},
        "oneDay": {"c": 0, "p": 0, "s": 0},
    }
    app = _make_app_with_state(state)
    client = TestClient(app)
    resp = client.post("/get_dashboard_summary")
    data = resp.json()
    assert data["s"] == "ok"
    assert data["balance"] == 40000
    assert data["positionValue"] == 23000
    assert data["oneDayProfit"] == 200.0
    assert data["oneDayVol"] == -50.0


def test_get_profit_by_symbol():
    state = _create_test_state()
    app = _make_app_with_state(state)
    client = TestClient(app)
    resp = client.post("/get_profit_by_symbol")
    data = resp.json()
    assert data["s"] == "ok"
    assert "BTCUSDT" in data["p"]
    assert "ETHUSDT" in data["p"]
    assert "all" in data["p"]
    # BTCUSDT profit: REALIZED_PNL 100 (USDT, real_income=100)
    #               + COMMISSION -0.5 * 600 * 0.6 = -180 (BNB commission_value)
    btc_profit_all = data["p"]["BTCUSDT"][3]
    assert abs(btc_profit_all - (100 + (-0.5 * 600 * 0.6))) < 0.01
    # ETHUSDT profit: FUNDING_FEE 5.0 (USDT, real_income=5)
    eth_profit_all = data["p"]["ETHUSDT"][3]
    assert abs(eth_profit_all - 5.0) < 0.01
    # BTCUSDT BNB volume: income * 0.6 = -0.5 * 0.6 = -0.3
    btc_vol_all = data["v"]["BTCUSDT"][3]
    assert abs(btc_vol_all - (-0.5 * 0.6)) < 0.01


def test_get_profit_by_symbol_cache():
    state = _create_test_state()
    app = _make_app_with_state(state)
    client = TestClient(app)
    resp1 = client.post("/get_profit_by_symbol")
    resp2 = client.post("/get_profit_by_symbol")
    assert resp1.json() == resp2.json()
    assert state.profit_by_symbol_update_ts > 0
