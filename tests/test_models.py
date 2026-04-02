from decimal import Decimal
from sqlmodel import SQLModel, Session, create_engine, select
import pytest

# Import models before create_all so SQLModel.metadata is populated
from app.models.trade_symbol import TradeSymbol
from app.models.user import User
from app.models.visitor import Visitor
from app.models.chat import Chat
from app.models.order import Order
from app.models.trade import Trade
from app.models.trade_record import TradeRecord
from app.models.position_record import PositionRecord


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


def test_user_create(session):
    user = User(
        account="test@example.com",
        password="hashed_pw",
        name="tester",
        register_ip="127.0.0.1",
        register_time="2026-01-01 00:00:00",
        access_token="abc123",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None


def test_visitor_create(session):
    v = Visitor(ip="1.2.3.4", time="2026-01-01 00:00:00", page="/home")
    session.add(v)
    session.commit()
    assert v.id is not None


def test_chat_create(session):
    c = Chat(
        access_token="abc123",
        name="tester",
        time="2026-01-01 00:00:00",
        ts=1704067200,
        content="hello",
    )
    session.add(c)
    session.commit()
    assert c.id is not None


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
