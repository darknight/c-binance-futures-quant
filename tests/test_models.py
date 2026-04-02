from sqlmodel import SQLModel, Session, create_engine, select
import pytest

# Import models before create_all so SQLModel.metadata is populated
from app.models.trade_symbol import TradeSymbol
from app.models.user import User
from app.models.visitor import Visitor
from app.models.chat import Chat


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
