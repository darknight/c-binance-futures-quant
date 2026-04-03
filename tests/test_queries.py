import json
from datetime import datetime, timezone
from sqlmodel import SQLModel, Session, create_engine, select
import pytest

# Import all models so SQLModel.metadata is fully populated before create_all
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
from app.models.trades_take import TradesTake
from app.models.income_history_take import IncomeHistoryTake
from app.models.income_history_take_day import IncomeHistoryTakeDay
from app.models.commission_temp_income import CommissionTempIncome


@pytest.fixture
def session():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(session, *, private_ip="10.0.0.1", name="server_1",
              symbol="BTCUSDT", my_symbol="BTC",
              extra_para=None, run_info=None,
              update_ts=None, update_time=None) -> TradeServerStatus:
    """Insert a TradeServerStatus row and return the refreshed object."""
    row = TradeServerStatus(
        private_ip=private_ip,
        name=name,
        symbol=symbol,
        my_symbol=my_symbol,
        extra_para=json.dumps(extra_para or {"customizeDangerous": 0}),
        run_info=json.dumps(run_info or {}),
        update_ts=update_ts,
        update_time=update_time,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# updateTradeServerStatusData — SELECT all rows
# ---------------------------------------------------------------------------

def test_select_all_rows_empty(session):
    """SELECT all rows returns an empty list when the table is empty."""
    rows = session.exec(select(TradeServerStatus)).all()
    assert rows == []


def test_select_all_rows_returns_every_record(session):
    """SELECT all rows returns one entry per inserted row."""
    _make_row(session, private_ip="10.0.0.1", symbol="BTCUSDT")
    _make_row(session, private_ip="10.0.0.2", symbol="ETHUSDT")

    rows = session.exec(select(TradeServerStatus)).all()
    assert len(rows) == 2

    ips = {r.private_ip for r in rows}
    assert ips == {"10.0.0.1", "10.0.0.2"}


def test_select_all_rows_json_fields_are_parseable(session):
    """extra_para and run_info stored as JSON strings can be parsed back."""
    extra = {"customizeDangerous": 1}
    info = {"dangerousClass": "A", "positionValue": 100.0}
    _make_row(session, extra_para=extra, run_info=info)

    rows = session.exec(select(TradeServerStatus)).all()
    assert len(rows) == 1
    assert json.loads(rows[0].extra_para) == extra
    assert json.loads(rows[0].run_info) == info


def test_select_all_rows_maps_to_dict_correctly(session):
    """Simulate the mapping performed by updateTradeServerStatusData()."""
    extra = {"customizeDangerous": 0}
    info = {"dangerousName": "x", "dangerousClass": "B"}
    row = _make_row(session, extra_para=extra, run_info=info,
                    symbol="ETHUSDT", private_ip="10.0.0.3",
                    name="srv", my_symbol="ETH", update_ts=1000)

    rows = session.exec(select(TradeServerStatus)).all()
    item = rows[0]

    parsed_extra = json.loads(item.extra_para)
    mapped = {
        "extraPara": parsed_extra,
        "runInfo": json.loads(item.run_info),
        "symbol": item.symbol,
        "privateIP": item.private_ip,
        "name": item.name,
        "mySymbol": item.my_symbol,
        "updateTs": item.update_ts,
        "updateTime": item.update_time,
        "customizeDangerousData": parsed_extra,
    }

    assert mapped["extraPara"] == extra
    assert mapped["privateIP"] == "10.0.0.3"
    assert mapped["symbol"] == "ETHUSDT"
    assert mapped["updateTs"] == 1000


# ---------------------------------------------------------------------------
# check_maker_server_in_data — SELECT by privateIP, INSERT if not found
# ---------------------------------------------------------------------------

def test_select_by_ip_returns_nothing_when_absent(session):
    """Querying by a non-existent IP returns no rows."""
    rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.99")
    ).all()
    assert rows == []


def test_select_by_ip_returns_row_when_present(session):
    """Querying by an existing IP returns exactly that row."""
    _make_row(session, private_ip="10.0.0.5")

    rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.5")
    ).all()
    assert len(rows) == 1
    assert rows[0].private_ip == "10.0.0.5"


def test_insert_when_ip_not_found(session):
    """If no row exists for an IP, inserting one succeeds."""
    private_ip = "10.0.0.7"
    existing = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == private_ip)
    ).all()
    assert existing == []

    extra_para = {"customizeDangerous": 0}
    new_row = TradeServerStatus(
        private_ip=private_ip,
        name="new_server",
        extra_para=json.dumps(extra_para),
        symbol="BTCUSDT",
        my_symbol="BTC",
    )
    session.add(new_row)
    session.commit()

    inserted = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == private_ip)
    ).all()
    assert len(inserted) == 1
    assert json.loads(inserted[0].extra_para) == extra_para


def test_no_duplicate_insert_when_ip_exists(session):
    """When a row already exists for an IP, no second insert is performed."""
    _make_row(session, private_ip="10.0.0.8")

    existing = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.8")
    ).all()
    # Row found — skip the INSERT (matching the len(data)==0 guard in webServer.py)
    if not existing:
        session.add(TradeServerStatus(private_ip="10.0.0.8"))
        session.commit()

    all_rows = session.exec(select(TradeServerStatus)).all()
    assert len(all_rows) == 1


# ---------------------------------------------------------------------------
# update_maker_server_run_info — UPDATE runInfo, updateTs, updateTime by IP
# ---------------------------------------------------------------------------

def test_update_run_info_by_ip(session):
    """UPDATE run_info, update_ts, update_time for a specific private_ip."""
    row = _make_row(session, private_ip="10.0.0.10")
    assert json.loads(row.run_info) == {}

    new_run_info = {
        "dangerousClass": "C",
        "dangerousName": "test",
        "longsOnceTradeValue": 50.0,
        "shortsOnceTradeValue": 50.0,
        "longsBollTimeAmount": 1.0,
        "shortsBollTimeAmount": 1.0,
        "positionValue": 200.0,
        "direction": "longs",
    }
    now_ts = 1700000000
    now_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    db_row = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.10")
    ).one()
    db_row.run_info = json.dumps(new_run_info)
    db_row.update_ts = now_ts
    db_row.update_time = now_time
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert json.loads(db_row.run_info) == new_run_info
    assert db_row.update_ts == now_ts
    # SQLite strips tzinfo on round-trip; compare the naive datetime equivalent
    assert db_row.update_time == now_time.replace(tzinfo=None)


def test_update_run_info_only_affects_target_ip(session):
    """Updating run_info for one IP does not alter other rows."""
    _make_row(session, private_ip="10.0.0.11", symbol="BTCUSDT")
    _make_row(session, private_ip="10.0.0.12", symbol="ETHUSDT")

    target = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.11")
    ).one()
    target.run_info = json.dumps({"dangerousClass": "X"})
    session.add(target)
    session.commit()

    other = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.12")
    ).one()
    assert json.loads(other.run_info) == {}


# ---------------------------------------------------------------------------
# update_customize_dangerous — UPDATE extraPara for all rows or by symbol
# ---------------------------------------------------------------------------

def test_update_extra_para_for_all_rows(session):
    """UPDATE extra_para for every row (symbol == 'all' branch)."""
    _make_row(session, private_ip="10.0.0.20", symbol="BTCUSDT")
    _make_row(session, private_ip="10.0.0.21", symbol="ETHUSDT")

    new_extra = json.dumps({"customizeDangerous": 1})

    all_rows = session.exec(select(TradeServerStatus)).all()
    for r in all_rows:
        r.extra_para = new_extra
        session.add(r)
    session.commit()

    updated = session.exec(select(TradeServerStatus)).all()
    for r in updated:
        assert json.loads(r.extra_para)["customizeDangerous"] == 1


def test_update_extra_para_by_symbol(session):
    """UPDATE extra_para only for rows matching a specific symbol."""
    _make_row(session, private_ip="10.0.0.30", symbol="BTCUSDT",
              extra_para={"customizeDangerous": 0})
    _make_row(session, private_ip="10.0.0.31", symbol="ETHUSDT",
              extra_para={"customizeDangerous": 0})

    new_extra = json.dumps({"customizeDangerous": 1})

    target_rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "BTCUSDT")
    ).all()
    for r in target_rows:
        r.extra_para = new_extra
        session.add(r)
    session.commit()

    btc_rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "BTCUSDT")
    ).all()
    eth_rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "ETHUSDT")
    ).all()

    assert all(json.loads(r.extra_para)["customizeDangerous"] == 1 for r in btc_rows)
    assert all(json.loads(r.extra_para)["customizeDangerous"] == 0 for r in eth_rows)


def test_update_extra_para_by_symbol_no_match(session):
    """UPDATE by symbol with no matching rows leaves the table unchanged."""
    _make_row(session, private_ip="10.0.0.40", symbol="BTCUSDT",
              extra_para={"customizeDangerous": 0})

    new_extra = json.dumps({"customizeDangerous": 99})
    target_rows = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "SOLUSDT")
    ).all()
    for r in target_rows:
        r.extra_para = new_extra
        session.add(r)
    session.commit()

    all_rows = session.exec(select(TradeServerStatus)).all()
    assert all(json.loads(r.extra_para)["customizeDangerous"] == 0 for r in all_rows)
