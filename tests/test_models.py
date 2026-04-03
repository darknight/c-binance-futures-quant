from decimal import Decimal
from sqlmodel import SQLModel, Session, create_engine, select
import pytest

# Import models before create_all so SQLModel.metadata is populated
from app.models.trade_symbol import TradeSymbol
from app.models.order import Order
from app.models.trade import Trade
from app.models.trade_record import TradeRecord
from app.models.position_record import PositionRecord
from app.models.income import Income
from app.models.income_day import IncomeDay
from app.models.commission import Commission
from app.models.machine_status import MachineStatus, TradeMachineStatus
from app.models.trade_server_status import TradeServerStatus
from app.models.loss_limit_time import LossLimitTime


@pytest.fixture
def session():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_trade_symbol_create(session):

    symbol = TradeSymbol(
        symbol="BTCUSDT",
        coin="BTC",
        quote="USDT",
        status="yes",
        onboard_date="2020-01-01",
        index=0,
        default_show=True,
        onboard_ts=1577836800,
    )
    session.add(symbol)
    session.commit()
    session.refresh(symbol)
    assert symbol.id is not None
    assert symbol.symbol == "BTCUSDT"


def test_trade_symbol_unique_symbol(session):
    s1 = TradeSymbol(symbol="ETHUSDT", coin="ETH", quote="USDT", status="yes")
    s2 = TradeSymbol(symbol="ETHUSDT", coin="ETH", quote="USDT", status="yes")
    session.add(s1)
    session.commit()
    session.add(s2)
    with pytest.raises(Exception):
        session.commit()




def test_order_create(session):
    o = Order(
        symbol="BTCUSDT",
        order_id=123456,
        client_order_id="test_order_1",
        side="BUY",
        position_side="LONG",
        status="NEW",
        price=Decimal("50000.00"),
        orig_qty=Decimal("0.01"),
        binance_ts=1704067200000,
    )
    session.add(o)
    session.commit()
    assert o.id is not None
    assert o.symbol == "BTCUSDT"


def test_trade_create(session):
    t = Trade(
        symbol="BTCUSDT",
        binance_id=789,
        order_id=123456,
        price=Decimal("50000.00"),
        qty=Decimal("0.01"),
        quote_qty=Decimal("500.00"),
        realized_pnl=Decimal("0.00"),
        commission=Decimal("0.20"),
        side="BUY",
        position_side="LONG",
        buyer=True,
        maker=False,
        ts=1704067200000,
    )
    session.add(t)
    session.commit()
    assert t.id is not None


def test_trade_record_create(session):
    tr = TradeRecord(
        symbol="ETHUSDT",
        direction="longs",
        status="tradeBegin",
        begin_ts=1704067200000,
        balance=Decimal("10000.00"),
    )
    session.add(tr)
    session.commit()
    assert tr.id is not None


def test_position_record_create(session):
    pr = PositionRecord(
        symbol="BTCUSDT",
        unrealized_profit=Decimal("100.50"),
        position_amt=Decimal("0.5"),
        ts=1704067200000,
        time="2026-01-01 00:00:00",
        position_value=Decimal("25000.00"),
        balance=Decimal("10000.00"),
    )
    session.add(pr)
    session.commit()
    assert pr.id is not None


def test_income_create(session):
    i = Income(
        access_token="abc123",
        income_type="REALIZED_PNL",
        income=Decimal("50.5"),
        asset="USDT",
        symbol="BTCUSDT",
        binance_ts=1704067200000,
    )
    session.add(i)
    session.commit()
    assert i.id is not None


def test_income_day_create(session):
    d = IncomeDay(
        api_key="key123",
        day_begin_time="2026-01-01 00:00:00",
        day_end_time="2026-01-02 00:00:00",
        binance_commission=Decimal("10.0"),
        pnl=Decimal("100.0"),
    )
    session.add(d)
    session.commit()
    assert d.id is not None


def test_commission_create(session):
    c = Commission(
        machine_index=0,
        income_type="COMMISSION",
        income=Decimal("-0.5"),
        symbol="ETHUSDT",
        binance_ts=1704067200000,
    )
    session.add(c)
    session.commit()
    assert c.id is not None


def test_machine_status_create(session):
    ms = MachineStatus(
        private_ip="10.0.0.1",
        insert_ts=1704067200000,
        update_ts=1704067200000,
        symbol="BTCUSDT",
    )
    session.add(ms)
    session.commit()
    assert ms.id is not None

    tms = TradeMachineStatus(
        private_ip="10.0.0.2",
        insert_ts=1704067200000,
        update_ts=1704067200000,
        status="running",
        run_time=3600,
    )
    session.add(tms)
    session.commit()
    assert tms.id is not None


def test_trade_server_status_create(session):
    ts = TradeServerStatus(
        private_ip="10.0.0.3",
        name="trade_server_1",
        symbol="BTCUSDT",
    )
    session.add(ts)
    session.commit()
    assert ts.id is not None


def test_loss_limit_time_create(session):
    llt = LossLimitTime(symbol="BTCUSDT", limit_time=3600)
    session.add(llt)
    session.commit()
    assert llt.id is not None
