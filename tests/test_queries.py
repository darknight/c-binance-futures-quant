import json
from datetime import datetime, timezone
from decimal import Decimal
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import func, asc
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
from app.models.trades import Trades
from app.models.begin_trade_record import BeginTradeRecord


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


# ---------------------------------------------------------------------------
# Helpers for MachineStatus / TradeMachineStatus
# ---------------------------------------------------------------------------

def _make_machine_status(session, *, private_ip="10.0.1.1", symbol="BTCUSDT",
                          insert_ts=1000, update_ts=1000) -> MachineStatus:
    """Insert a MachineStatus row and return the refreshed object."""
    row = MachineStatus(
        private_ip=private_ip,
        symbol=symbol,
        insert_ts=insert_ts,
        update_ts=update_ts,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _make_trade_machine_status(session, *, private_ip="10.0.2.1", status="running",
                                insert_ts=2000, update_ts=2000,
                                run_time=100) -> TradeMachineStatus:
    """Insert a TradeMachineStatus row and return the refreshed object."""
    row = TradeMachineStatus(
        private_ip=private_ip,
        status=status,
        insert_ts=insert_ts,
        update_ts=update_ts,
        run_time=run_time,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# update_machine_status — SELECT by private_ip, INSERT if not exists, UPDATE if exists
# ---------------------------------------------------------------------------

def test_machine_status_select_by_ip_absent(session):
    """SELECT by private_ip returns empty list when no matching row exists."""
    rows = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == "10.0.1.99")
    ).all()
    assert rows == []


def test_machine_status_select_by_ip_present(session):
    """SELECT by private_ip returns exactly the matching row."""
    _make_machine_status(session, private_ip="10.0.1.2")

    rows = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == "10.0.1.2")
    ).all()
    assert len(rows) == 1
    assert rows[0].private_ip == "10.0.1.2"


def test_machine_status_insert_when_not_found(session):
    """INSERT a new MachineStatus row when none exists for the given IP."""
    private_ip = "10.0.1.3"
    existing = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == private_ip)
    ).all()
    assert existing == []

    update_ts = 1700000001
    new_row = MachineStatus(
        private_ip=private_ip,
        insert_ts=update_ts,
        update_ts=update_ts,
        symbol="ETHUSDT",
    )
    session.add(new_row)
    session.commit()

    inserted = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == private_ip)
    ).all()
    assert len(inserted) == 1
    assert inserted[0].symbol == "ETHUSDT"
    assert inserted[0].update_ts == update_ts


def test_machine_status_update_when_found(session):
    """UPDATE update_ts for an existing MachineStatus row."""
    _make_machine_status(session, private_ip="10.0.1.4", update_ts=1000)

    new_ts = 9999999
    db_row = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == "10.0.1.4")
    ).one()
    db_row.update_ts = new_ts
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.update_ts == new_ts


def test_machine_status_update_does_not_affect_other_rows(session):
    """Updating one MachineStatus row leaves sibling rows untouched."""
    _make_machine_status(session, private_ip="10.0.1.5", update_ts=1000)
    _make_machine_status(session, private_ip="10.0.1.6", update_ts=1000)

    target = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == "10.0.1.5")
    ).one()
    target.update_ts = 8888888
    session.add(target)
    session.commit()

    other = session.exec(
        select(MachineStatus).where(MachineStatus.private_ip == "10.0.1.6")
    ).one()
    assert other.update_ts == 1000


# ---------------------------------------------------------------------------
# update_trade_status — SELECT by private_ip, INSERT if not exists, UPDATE if exists
# ---------------------------------------------------------------------------

def test_trade_machine_status_select_by_ip_absent(session):
    """SELECT by private_ip returns empty list when no row exists."""
    rows = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == "10.0.2.99")
    ).all()
    assert rows == []


def test_trade_machine_status_select_by_ip_present(session):
    """SELECT by private_ip returns exactly the matching row."""
    _make_trade_machine_status(session, private_ip="10.0.2.2")

    rows = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == "10.0.2.2")
    ).all()
    assert len(rows) == 1
    assert rows[0].private_ip == "10.0.2.2"


def test_trade_machine_status_insert_when_not_found(session):
    """INSERT a new TradeMachineStatus row when none exists for the given IP."""
    private_ip = "10.0.2.3"
    existing = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == private_ip)
    ).all()
    assert existing == []

    update_ts = 1700000002
    new_row = TradeMachineStatus(
        private_ip=private_ip,
        insert_ts=update_ts,
        update_ts=update_ts,
        status="idle",
    )
    session.add(new_row)
    session.commit()

    inserted = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == private_ip)
    ).all()
    assert len(inserted) == 1
    assert inserted[0].status == "idle"
    assert inserted[0].update_ts == update_ts


def test_trade_machine_status_update_when_found(session):
    """UPDATE status, update_ts, and run_time for an existing TradeMachineStatus row."""
    _make_trade_machine_status(session, private_ip="10.0.2.4",
                                status="idle", update_ts=2000, run_time=50)

    new_ts = 9999999
    db_row = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == "10.0.2.4")
    ).one()
    db_row.status = "running"
    db_row.update_ts = new_ts
    db_row.run_time = 200
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.status == "running"
    assert db_row.update_ts == new_ts
    assert db_row.run_time == 200


def test_trade_machine_status_update_does_not_affect_other_rows(session):
    """Updating one TradeMachineStatus row leaves sibling rows untouched."""
    _make_trade_machine_status(session, private_ip="10.0.2.5", status="idle")
    _make_trade_machine_status(session, private_ip="10.0.2.6", status="idle")

    target = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == "10.0.2.5")
    ).one()
    target.status = "running"
    session.add(target)
    session.commit()

    other = session.exec(
        select(TradeMachineStatus).where(TradeMachineStatus.private_ip == "10.0.2.6")
    ).one()
    assert other.status == "idle"


# ---------------------------------------------------------------------------
# get_trade_status — SELECT all TradeMachineStatus ordered by update_ts asc
# ---------------------------------------------------------------------------

def test_trade_machine_status_select_all_ordered_asc(session):
    """SELECT all TradeMachineStatus rows ordered by update_ts ascending."""
    _make_trade_machine_status(session, private_ip="10.0.3.1",
                                update_ts=3000, status="a", run_time=10)
    _make_trade_machine_status(session, private_ip="10.0.3.2",
                                update_ts=1000, status="b", run_time=20)
    _make_trade_machine_status(session, private_ip="10.0.3.3",
                                update_ts=2000, status="c", run_time=30)

    from sqlalchemy import asc
    rows = session.exec(
        select(TradeMachineStatus).order_by(asc(TradeMachineStatus.update_ts))
    ).all()

    assert len(rows) == 3
    assert rows[0].update_ts == 1000
    assert rows[1].update_ts == 2000
    assert rows[2].update_ts == 3000


def test_trade_machine_status_first_row_fields(session):
    """The first row (lowest update_ts) exposes status, update_ts, run_time correctly."""
    _make_trade_machine_status(session, private_ip="10.0.4.1",
                                update_ts=500, status="ok", run_time=77)
    _make_trade_machine_status(session, private_ip="10.0.4.2",
                                update_ts=900, status="err", run_time=88)

    from sqlalchemy import asc
    rows = session.exec(
        select(TradeMachineStatus).order_by(asc(TradeMachineStatus.update_ts))
    ).all()

    first = rows[0]
    assert first.status == "ok"
    assert first.update_ts == 500
    assert first.run_time == 77


def test_trade_machine_status_average_run_time(session):
    """Average run_time can be computed from all returned rows."""
    _make_trade_machine_status(session, private_ip="10.0.5.1", run_time=100)
    _make_trade_machine_status(session, private_ip="10.0.5.2", run_time=200)
    _make_trade_machine_status(session, private_ip="10.0.5.3", run_time=300)

    from sqlalchemy import asc
    rows = session.exec(
        select(TradeMachineStatus).order_by(asc(TradeMachineStatus.update_ts))
    ).all()

    total = sum(r.run_time for r in rows)
    avg = int(total / len(rows))
    assert avg == 200


# ---------------------------------------------------------------------------
# Helpers for Income / IncomeDay
# ---------------------------------------------------------------------------

def _make_income(session, *, access_token="ak_test", income_type="COMMISSION",
                 income_val="0.001", bnb_price="300.0", asset="BNB",
                 trade_id="123", binance_ts=1700000000000, symbol="BTCUSDT",
                 api_key="ak_test", commission="0.01") -> Income:
    """Insert an Income row and return the refreshed object."""
    from decimal import Decimal
    row = Income(
        access_token=access_token,
        income_type=income_type,
        income=Decimal(income_val),
        bnb_price=Decimal(bnb_price),
        asset=asset,
        trade_id=trade_id,
        binance_ts=binance_ts,
        symbol=symbol,
        api_key=api_key,
        commission=Decimal(commission),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _make_income_day(session, *, api_key="ak_test",
                     day_begin_time=None, day_end_time=None,
                     binance_commission="1.5", zjy_commission="0.3",
                     pnl="10.0") -> IncomeDay:
    """Insert an IncomeDay row and return the refreshed object."""
    from decimal import Decimal
    row = IncomeDay(
        api_key=api_key,
        day_begin_time=day_begin_time or datetime(2026, 1, 1, tzinfo=timezone.utc),
        day_end_time=day_end_time or datetime(2026, 1, 2, tzinfo=timezone.utc),
        binance_commission=Decimal(binance_commission),
        zjy_commission=Decimal(zjy_commission),
        pnl=Decimal(pnl),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Income: SELECT WHERE binance_ts > X ORDER BY id DESC
# ---------------------------------------------------------------------------

def test_income_select_by_binance_ts_order_desc(session):
    """SELECT Income WHERE binance_ts > threshold ORDER BY id DESC."""
    _make_income(session, binance_ts=1000, symbol="BTCUSDT")
    _make_income(session, binance_ts=2000, symbol="ETHUSDT")
    _make_income(session, binance_ts=3000, symbol="SOLUSDT")

    rows = session.exec(
        select(Income).where(Income.binance_ts > 1500).order_by(Income.id.desc())
    ).all()
    assert len(rows) == 2
    # DESC order: highest id first
    assert rows[0].symbol == "SOLUSDT"
    assert rows[1].symbol == "ETHUSDT"


def test_income_select_by_binance_ts_empty(session):
    """SELECT Income with threshold above all rows returns empty."""
    _make_income(session, binance_ts=1000)

    rows = session.exec(
        select(Income).where(Income.binance_ts > 9999).order_by(Income.id.desc())
    ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# Income: SELECT WHERE api_key = X ORDER BY id DESC LIMIT 100
# ---------------------------------------------------------------------------

def test_income_select_by_api_key_with_limit(session):
    """SELECT Income WHERE api_key = X ORDER BY id DESC LIMIT 100."""
    for i in range(5):
        _make_income(session, api_key="key_a", binance_ts=1000 + i, symbol=f"SYM{i}")
    _make_income(session, api_key="key_b", binance_ts=9000, symbol="OTHER")

    rows = session.exec(
        select(Income)
        .where(Income.api_key == "key_a")
        .order_by(Income.id.desc())
        .limit(100)
    ).all()
    assert len(rows) == 5
    assert all(r.api_key == "key_a" for r in rows)
    # DESC: last inserted first
    assert rows[0].symbol == "SYM4"


def test_income_select_by_api_key_limit_caps_results(session):
    """LIMIT actually caps the number of returned rows."""
    for i in range(5):
        _make_income(session, api_key="key_c", binance_ts=1000 + i, symbol=f"S{i}")

    rows = session.exec(
        select(Income)
        .where(Income.api_key == "key_c")
        .order_by(Income.id.desc())
        .limit(3)
    ).all()
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# Income: INSERT
# ---------------------------------------------------------------------------

def test_income_insert(session):
    """INSERT a new Income record via session.add()."""
    from decimal import Decimal
    row = Income(
        access_token="tok",
        income_type="REALIZED_PNL",
        income=Decimal("5.5"),
        bnb_price=Decimal("310.0"),
        asset="USDT",
        trade_id="999",
        binance_ts=1700000000000,
        symbol="ETHUSDT",
        api_key="ak1",
        commission=Decimal("0.0"),
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.id is not None
    fetched = session.exec(select(Income).where(Income.id == row.id)).one()
    assert fetched.income_type == "REALIZED_PNL"
    assert fetched.income == Decimal("5.5")


# ---------------------------------------------------------------------------
# Income: SELECT WHERE binance_ts BETWEEN range (aggregation)
# ---------------------------------------------------------------------------

def test_income_select_binance_ts_range(session):
    """SELECT Income WHERE binance_ts > begin AND binance_ts <= end."""
    _make_income(session, binance_ts=1000, income_type="COMMISSION", income_val="0.5")
    _make_income(session, binance_ts=2000, income_type="REALIZED_PNL", income_val="10.0")
    _make_income(session, binance_ts=3000, income_type="COMMISSION", income_val="0.3")
    _make_income(session, binance_ts=4000, income_type="REALIZED_PNL", income_val="20.0")

    rows = session.exec(
        select(Income)
        .where(Income.binance_ts > 1500)
        .where(Income.binance_ts <= 3500)
    ).all()
    assert len(rows) == 2
    types = {r.income_type for r in rows}
    assert types == {"REALIZED_PNL", "COMMISSION"}


def test_income_aggregation_logic(session):
    """Verify aggregation logic matching updateDayIncome pattern."""
    from decimal import Decimal
    _make_income(session, binance_ts=2000, income_type="COMMISSION",
                 asset="BNB", income_val="0.01", bnb_price="300.0", commission="0.3")
    _make_income(session, binance_ts=2500, income_type="COMMISSION",
                 asset="USDT", income_val="1.5", bnb_price="0", commission="0.15")
    _make_income(session, binance_ts=3000, income_type="REALIZED_PNL",
                 asset="USDT", income_val="50.0", bnb_price="0", commission="0.0")

    rows = session.exec(
        select(Income).where(Income.binance_ts > 1000).where(Income.binance_ts <= 4000)
    ).all()

    day_binance_commission = 0
    day_pnl = 0
    day_zjy_commission = 0
    for item in rows:
        if item.income_type == "COMMISSION":
            if item.asset == "BNB":
                day_binance_commission += item.income * item.bnb_price
            elif item.asset in ("USDT", "BUSD"):
                day_binance_commission += item.income
        elif item.income_type == "REALIZED_PNL":
            if item.asset in ("USDT", "BUSD"):
                day_pnl += item.income
        day_zjy_commission += item.commission

    assert day_binance_commission == Decimal("0.01") * Decimal("300.0") + Decimal("1.5")
    assert day_pnl == Decimal("50.0")
    assert day_zjy_commission == Decimal("0.3") + Decimal("0.15") + Decimal("0.0")


# ---------------------------------------------------------------------------
# IncomeDay: SELECT ORDER BY id DESC LIMIT 1 (latest)
# ---------------------------------------------------------------------------

def test_income_day_select_latest(session):
    """SELECT IncomeDay ORDER BY id DESC LIMIT 1 returns the most recent row."""
    _make_income_day(session, day_begin_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 1, 2, tzinfo=timezone.utc))
    _make_income_day(session, day_begin_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 1, 3, tzinfo=timezone.utc))

    latest = session.exec(
        select(IncomeDay).order_by(IncomeDay.id.desc()).limit(1)
    ).first()
    assert latest is not None
    # SQLite strips tzinfo
    assert latest.day_begin_time == datetime(2026, 1, 2, tzinfo=timezone.utc).replace(tzinfo=None)


def test_income_day_select_latest_empty(session):
    """SELECT latest IncomeDay from empty table returns None."""
    latest = session.exec(
        select(IncomeDay).order_by(IncomeDay.id.desc()).limit(1)
    ).first()
    assert latest is None


# ---------------------------------------------------------------------------
# IncomeDay: SELECT ORDER BY id ASC (all, chronological)
# ---------------------------------------------------------------------------

def test_income_day_select_all_asc(session):
    """SELECT IncomeDay ORDER BY id ASC returns rows in chronological order."""
    _make_income_day(session, day_begin_time=datetime(2026, 1, 3, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 1, 4, tzinfo=timezone.utc), pnl="30.0")
    _make_income_day(session, day_begin_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 1, 2, tzinfo=timezone.utc), pnl="10.0")

    rows = session.exec(
        select(IncomeDay).order_by(IncomeDay.id.asc())
    ).all()
    assert len(rows) == 2
    # ASC by id: first inserted comes first
    assert rows[0].day_begin_time == datetime(2026, 1, 3, tzinfo=timezone.utc).replace(tzinfo=None)
    assert rows[1].day_begin_time == datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# IncomeDay: INSERT
# ---------------------------------------------------------------------------

def test_income_day_insert(session):
    """INSERT a new IncomeDay record via session.add()."""
    from decimal import Decimal
    row = IncomeDay(
        api_key="ak_day",
        day_begin_time=datetime(2026, 2, 1, tzinfo=timezone.utc),
        day_end_time=datetime(2026, 2, 2, tzinfo=timezone.utc),
        binance_commission=Decimal("2.0"),
        zjy_commission=Decimal("0.5"),
        pnl=Decimal("15.0"),
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.id is not None
    fetched = session.exec(select(IncomeDay).where(IncomeDay.id == row.id)).one()
    assert fetched.pnl == Decimal("15.0")


# ---------------------------------------------------------------------------
# IncomeDay: UPDATE by day_end_time
# ---------------------------------------------------------------------------

def test_income_day_update_by_day_end_time(session):
    """UPDATE IncomeDay fields by matching day_end_time."""
    from decimal import Decimal
    _make_income_day(session, day_begin_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 3, 2, tzinfo=timezone.utc),
                     binance_commission="1.0", pnl="5.0", zjy_commission="0.2")

    target_end = datetime(2026, 3, 2, tzinfo=timezone.utc).replace(tzinfo=None)
    db_row = session.exec(
        select(IncomeDay).where(IncomeDay.day_end_time == target_end)
    ).one()
    db_row.binance_commission = Decimal("2.0")
    db_row.pnl = Decimal("12.0")
    db_row.zjy_commission = Decimal("0.6")
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.binance_commission == Decimal("2.0")
    assert db_row.pnl == Decimal("12.0")
    assert db_row.zjy_commission == Decimal("0.6")


def test_income_day_update_does_not_affect_other_rows(session):
    """Updating one IncomeDay row leaves other rows untouched."""
    from decimal import Decimal
    _make_income_day(session, day_begin_time=datetime(2026, 4, 1, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 4, 2, tzinfo=timezone.utc), pnl="10.0")
    _make_income_day(session, day_begin_time=datetime(2026, 4, 2, tzinfo=timezone.utc),
                     day_end_time=datetime(2026, 4, 3, tzinfo=timezone.utc), pnl="20.0")

    target_end = datetime(2026, 4, 2, tzinfo=timezone.utc).replace(tzinfo=None)
    db_row = session.exec(
        select(IncomeDay).where(IncomeDay.day_end_time == target_end)
    ).one()
    db_row.pnl = Decimal("99.0")
    session.add(db_row)
    session.commit()

    other_end = datetime(2026, 4, 3, tzinfo=timezone.utc).replace(tzinfo=None)
    other = session.exec(
        select(IncomeDay).where(IncomeDay.day_end_time == other_end)
    ).one()
    assert other.pnl == Decimal("20.0")


# ---------------------------------------------------------------------------
# TradeSymbol: SELECT WHERE status='yes' ORDER BY id ASC
# ---------------------------------------------------------------------------

def _make_trade_symbol(session, *, symbol="BTCUSDT", coin="BTC", quote="USDT",
                       status="yes", index=1, default_show=True,
                       link_symbol_arr=None) -> TradeSymbol:
    row = TradeSymbol(
        symbol=symbol, coin=coin, quote=quote, status=status,
        index=index, default_show=default_show,
        link_symbol_arr=link_symbol_arr or [],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_trade_symbol_select_active_ordered(session):
    """SELECT TradeSymbol WHERE status='yes' ORDER BY id ASC."""
    _make_trade_symbol(session, symbol="ETHUSDT", coin="ETH", status="yes", index=2)
    _make_trade_symbol(session, symbol="BTCUSDT", coin="BTC", status="yes", index=1)
    _make_trade_symbol(session, symbol="SOLUSDT", coin="SOL", status="no", index=3)

    rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    assert len(rows) == 2
    assert rows[0].symbol == "ETHUSDT"
    assert rows[1].symbol == "BTCUSDT"


def test_trade_symbol_maps_to_dict(session):
    """Simulate the mapping performed by getSymbolIndex()."""
    _make_trade_symbol(session, symbol="BTCUSDT", coin="BTC", quote="USDT",
                       index=0, default_show=True, link_symbol_arr=["ETHUSDT"])

    rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    row = rows[0]
    link_data = row.link_symbol_arr if isinstance(row.link_symbol_arr, (list, dict)) else json.loads(row.link_symbol_arr or "[]")
    mapped = {
        "symbol": row.symbol,
        "coin": row.coin,
        "symbolIndex": row.index,
        "quote": row.quote,
        "linkSymbolArr": link_data,
        "defaultShow": row.default_show,
        "weight": 0,
    }
    assert mapped["symbol"] == "BTCUSDT"
    assert mapped["linkSymbolArr"] == ["ETHUSDT"]
    assert mapped["defaultShow"] is True


def test_trade_symbol_no_active_returns_empty(session):
    """SELECT with no status='yes' rows returns empty."""
    _make_trade_symbol(session, symbol="BTCUSDT", status="no")

    rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# PositionRecord: SELECT with ts range + optional symbol filter
# ---------------------------------------------------------------------------

def _make_position_record(session, *, symbol="BTCUSDT", ts=1000,
                          position_amt=None, position_value=None,
                          balance=None, profit=None, commission=None,
                          maker_commission=None, unrealized_profit=None,
                          time_val=None) -> PositionRecord:
    row = PositionRecord(
        symbol=symbol, ts=ts,
        position_amt=position_amt, position_value=position_value,
        balance=balance, profit=profit, commission=commission,
        maker_commission=maker_commission, unrealized_profit=unrealized_profit,
        time=time_val,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_position_record_select_by_ts_range_all(session):
    """SELECT PositionRecord WHERE ts > begin AND ts < end (ALL symbols)."""
    _make_position_record(session, symbol="BTCUSDT", ts=500)
    _make_position_record(session, symbol="ETHUSDT", ts=1500)
    _make_position_record(session, symbol="SOLUSDT", ts=2500)

    rows = session.exec(
        select(PositionRecord).where(PositionRecord.ts > 1000, PositionRecord.ts < 2000)
    ).all()
    assert len(rows) == 1
    assert rows[0].symbol == "ETHUSDT"


def test_position_record_select_by_ts_range_with_symbol(session):
    """SELECT PositionRecord WHERE ts range AND symbol filter."""
    _make_position_record(session, symbol="BTCUSDT", ts=1500)
    _make_position_record(session, symbol="ETHUSDT", ts=1500)

    stmt = select(PositionRecord).where(
        PositionRecord.ts > 1000, PositionRecord.ts < 2000
    ).where(PositionRecord.symbol == "ETHUSDT")
    rows = session.exec(stmt).all()
    assert len(rows) == 1
    assert rows[0].symbol == "ETHUSDT"


def test_position_record_maps_to_dict(session):
    """Simulate the mapping from get_position_record()."""
    _make_position_record(session, symbol="BTCUSDT", ts=1500,
                          position_amt=Decimal("0.5"), position_value=Decimal("15000"),
                          balance=Decimal("10000"), profit=Decimal("100"),
                          commission=Decimal("5"), maker_commission=Decimal("2"),
                          unrealized_profit=Decimal("50"))

    rows = session.exec(
        select(PositionRecord).where(PositionRecord.ts > 1000, PositionRecord.ts < 2000)
    ).all()
    row = rows[0]
    mapped = {
        "positionAmt": row.position_amt,
        "price": None,
        "positionValue": row.position_value,
        "balance": row.balance,
        "time": row.time,
        "profit": row.profit,
        "commission": row.commission,
        "makerCommission": row.maker_commission,
        "entryPrice": None,
        "unrealizedProfit": row.unrealized_profit,
        "maintMargin": None,
    }
    assert mapped["positionAmt"] == Decimal("0.5")
    assert mapped["balance"] == Decimal("10000")
    assert mapped["unrealizedProfit"] == Decimal("50")


# ---------------------------------------------------------------------------
# PositionRecord: SELECT latest per symbol (get_all_acount_info)
# ---------------------------------------------------------------------------

def test_position_record_latest_per_symbol(session):
    """SELECT latest PositionRecord per symbol using subquery."""
    _make_position_record(session, symbol="BTCUSDT", ts=1000,
                          position_value=Decimal("1000"), balance=Decimal("5000"))
    _make_position_record(session, symbol="BTCUSDT", ts=2000,
                          position_value=Decimal("2000"), balance=Decimal("6000"))
    _make_position_record(session, symbol="ETHUSDT", ts=1500,
                          position_value=Decimal("500"), balance=Decimal("3000"))

    subq = select(func.max(PositionRecord.id)).group_by(PositionRecord.symbol).scalar_subquery()
    rows = session.exec(
        select(PositionRecord).where(PositionRecord.id.in_(subq))
    ).all()

    assert len(rows) == 2
    all_position = sum(row.position_value or 0 for row in rows)
    all_balance = sum(row.balance or 0 for row in rows)
    assert all_position == Decimal("2500")
    assert all_balance == Decimal("9000")


# ---------------------------------------------------------------------------
# PositionRecord: SELECT latest by symbol ORDER BY id DESC LIMIT 1 (updateTurnPrice)
# ---------------------------------------------------------------------------

def test_position_record_latest_by_symbol(session):
    """SELECT latest PositionRecord for a specific symbol."""
    _make_position_record(session, symbol="ETHUSDT", ts=1000, position_amt=Decimal("1.0"))
    _make_position_record(session, symbol="ETHUSDT", ts=2000, position_amt=Decimal("-0.5"))

    latest = session.exec(
        select(PositionRecord).where(PositionRecord.symbol == "ETHUSDT")
        .order_by(PositionRecord.id.desc()).limit(1)
    ).first()
    assert latest is not None
    assert latest.position_amt == Decimal("-0.5")


def test_position_record_turn_price_negative_amt(session):
    """SELECT last record where position_amt > 0 (turn price logic for negative current)."""
    _make_position_record(session, symbol="ETHUSDT", ts=1000, position_amt=Decimal("1.0"))
    _make_position_record(session, symbol="ETHUSDT", ts=2000, position_amt=Decimal("-0.5"))
    _make_position_record(session, symbol="ETHUSDT", ts=3000, position_amt=Decimal("-0.3"))

    last_positive = session.exec(
        select(PositionRecord)
        .where(PositionRecord.symbol == "ETHUSDT", PositionRecord.position_amt > 0)
        .order_by(PositionRecord.id.desc()).limit(1)
    ).first()
    assert last_positive is not None
    assert last_positive.ts == 1000


# ---------------------------------------------------------------------------
# PositionRecord: SELECT balance WHERE ts >= zeroPoint ORDER BY id ASC LIMIT 1
# ---------------------------------------------------------------------------

def test_position_record_first_after_timestamp(session):
    """SELECT first PositionRecord after a given ts (day begin balance)."""
    _make_position_record(session, ts=500, balance=Decimal("9000"))
    _make_position_record(session, ts=1000, balance=Decimal("10000"))
    _make_position_record(session, ts=1500, balance=Decimal("11000"))

    first_row = session.exec(
        select(PositionRecord).where(PositionRecord.ts >= 800)
        .order_by(PositionRecord.id.asc()).limit(1)
    ).first()
    assert first_row is not None
    assert first_row.balance == Decimal("10000")


def test_position_record_first_after_timestamp_none(session):
    """SELECT first PositionRecord when no records match returns None."""
    _make_position_record(session, ts=500, balance=Decimal("9000"))

    first_row = session.exec(
        select(PositionRecord).where(PositionRecord.ts >= 9999)
        .order_by(PositionRecord.id.asc()).limit(1)
    ).first()
    assert first_row is None


# ---------------------------------------------------------------------------
# LossLimitTime: SELECT all, INSERT, UPDATE
# ---------------------------------------------------------------------------

def _make_loss_limit_time(session, *, symbol="BTCUSDT",
                          limit_time="2023-03-28 01:00:00") -> LossLimitTime:
    row = LossLimitTime(symbol=symbol, limit_time=limit_time)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_loss_limit_time_select_all(session):
    """SELECT all LossLimitTime rows."""
    _make_loss_limit_time(session, symbol="BTCUSDT")
    _make_loss_limit_time(session, symbol="ETHUSDT", limit_time="2024-01-01 00:00:00")

    rows = session.exec(select(LossLimitTime)).all()
    assert len(rows) == 2
    symbols = {r.symbol for r in rows}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


def test_loss_limit_time_select_all_maps_to_dict(session):
    """Simulate getLossLimitTimeData mapping."""
    _make_loss_limit_time(session, symbol="BTCUSDT", limit_time="2023-03-28 01:00:00")

    rows = session.exec(select(LossLimitTime)).all()
    arr = [{"symbol": r.symbol, "limitTime": r.limit_time} for r in rows]
    assert arr[0]["symbol"] == "BTCUSDT"
    assert arr[0]["limitTime"] == "2023-03-28 01:00:00"


def test_loss_limit_time_insert(session):
    """INSERT a new LossLimitTime row."""
    new_row = LossLimitTime(symbol="SOLUSDT", limit_time="2023-03-28 01:00:00")
    session.add(new_row)
    session.commit()

    rows = session.exec(select(LossLimitTime).where(LossLimitTime.symbol == "SOLUSDT")).all()
    assert len(rows) == 1
    assert rows[0].limit_time == "2023-03-28 01:00:00"


def test_loss_limit_time_update(session):
    """UPDATE limit_time WHERE symbol."""
    _make_loss_limit_time(session, symbol="BTCUSDT", limit_time="2023-03-28 01:00:00")

    row = session.exec(
        select(LossLimitTime).where(LossLimitTime.symbol == "BTCUSDT")
    ).first()
    assert row is not None
    row.limit_time = "2026-04-03 12:00:00"
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.limit_time == "2026-04-03 12:00:00"


def test_loss_limit_time_update_does_not_affect_other(session):
    """UPDATE one LossLimitTime leaves others unchanged."""
    _make_loss_limit_time(session, symbol="BTCUSDT", limit_time="old")
    _make_loss_limit_time(session, symbol="ETHUSDT", limit_time="old")

    row = session.exec(
        select(LossLimitTime).where(LossLimitTime.symbol == "BTCUSDT")
    ).first()
    row.limit_time = "new"
    session.add(row)
    session.commit()

    other = session.exec(
        select(LossLimitTime).where(LossLimitTime.symbol == "ETHUSDT")
    ).one()
    assert other.limit_time == "old"


# ---------------------------------------------------------------------------
# TradeRecord: SELECT WHERE profit_percent_by_balance <= -0.15 ORDER BY id DESC
# ---------------------------------------------------------------------------

def _make_trade_record(session, *, symbol="BTCUSDT", end_ts=1000,
                       profit=None, profit_percent_by_balance=None) -> TradeRecord:
    row = TradeRecord(
        symbol=symbol, end_ts=end_ts,
        profit=profit, profit_percent_by_balance=profit_percent_by_balance,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_trade_record_big_loss_filter(session):
    """SELECT TradeRecord WHERE profit_percent_by_balance <= -0.15 ORDER BY id DESC."""
    _make_trade_record(session, symbol="BTCUSDT", end_ts=1000,
                       profit=Decimal("-50"), profit_percent_by_balance=Decimal("-0.20"))
    _make_trade_record(session, symbol="ETHUSDT", end_ts=2000,
                       profit=Decimal("-10"), profit_percent_by_balance=Decimal("-0.10"))
    _make_trade_record(session, symbol="SOLUSDT", end_ts=3000,
                       profit=Decimal("-30"), profit_percent_by_balance=Decimal("-0.15"))

    rows = session.exec(
        select(TradeRecord)
        .where(TradeRecord.profit_percent_by_balance <= Decimal("-0.15"))
        .order_by(TradeRecord.id.desc())
    ).all()
    assert len(rows) == 2
    # DESC order: SOLUSDT first (highest id)
    assert rows[0].symbol == "SOLUSDT"
    assert rows[1].symbol == "BTCUSDT"


def test_trade_record_big_loss_empty(session):
    """No rows match the big loss filter."""
    _make_trade_record(session, profit_percent_by_balance=Decimal("-0.05"))

    rows = session.exec(
        select(TradeRecord)
        .where(TradeRecord.profit_percent_by_balance <= Decimal("-0.15"))
        .order_by(TradeRecord.id.desc())
    ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# TradesTake: SELECT WHERE symbol AND status='tradeBegin', INSERT
# ---------------------------------------------------------------------------

def test_trades_take_select_by_symbol_and_status(session):
    """SELECT TradesTake WHERE symbol AND status='tradeBegin'."""
    row = TradesTake(symbol="BTCUSDT", status="tradeBegin", version=3, begin_ts=1000)
    session.add(row)
    session.commit()

    rows = session.exec(
        select(TradesTake).where(TradesTake.symbol == "BTCUSDT", TradesTake.status == "tradeBegin")
    ).all()
    assert len(rows) == 1


def test_trades_take_select_no_match(session):
    """SELECT TradesTake with non-matching symbol returns empty."""
    row = TradesTake(symbol="BTCUSDT", status="tradeBegin", version=3)
    session.add(row)
    session.commit()

    rows = session.exec(
        select(TradesTake).where(TradesTake.symbol == "ETHUSDT", TradesTake.status == "tradeBegin")
    ).all()
    assert rows == []


def test_trades_take_insert(session):
    """INSERT a new TradesTake row with all trade begin fields."""
    new_row = TradesTake(
        status="tradeBegin", version=3,
        vol_multiple=Decimal("1.5"), standard_rate=Decimal("0.01"),
        symbol="BTCUSDT", kline_arr="[[1,2,3]]",
        now_open_rate=Decimal("0.005"), begin_machine_number="machine1",
        direction="longs", longs_condition_a=1,
        shorts_condition_a=0, shorts_condition_b=0,
        btc_now_open_rate=Decimal("0.003"), eth_now_open_rate=Decimal("0.004"),
        begin_ts=1700000000000, end_ts=1700000000000,
        trade_type="open", update_ts=1700000000000,
        client_begin_price=Decimal("42000"), client_end_price=Decimal("42100"),
    )
    session.add(new_row)
    session.commit()
    session.refresh(new_row)

    assert new_row.id is not None
    fetched = session.exec(select(TradesTake).where(TradesTake.id == new_row.id)).one()
    assert fetched.symbol == "BTCUSDT"
    assert fetched.status == "tradeBegin"
    assert fetched.version == 3
    assert fetched.direction == "longs"
    assert fetched.begin_ts == 1700000000000


def test_trades_take_skip_insert_when_exists(session):
    """Do not insert if a tradeBegin row already exists for the symbol."""
    existing = TradesTake(symbol="BTCUSDT", status="tradeBegin", version=3)
    session.add(existing)
    session.commit()

    rows = session.exec(
        select(TradesTake).where(TradesTake.symbol == "BTCUSDT", TradesTake.status == "tradeBegin")
    ).all()
    # Simulate: if len(tradesData)==0 -> insert; else skip
    if len(rows) == 0:
        session.add(TradesTake(symbol="BTCUSDT", status="tradeBegin", version=3))
        session.commit()

    all_rows = session.exec(select(TradesTake)).all()
    assert len(all_rows) == 1


# ---------------------------------------------------------------------------
# BeginTradeRecord: SELECT WHERE symbol AND ts range ORDER BY id DESC LIMIT 5000
# ---------------------------------------------------------------------------

def _make_begin_trade_record(session, *, symbol="BTCUSDT", ts=1000,
                              time_val="2026-01-01 00:00:00",
                              direction="longs") -> BeginTradeRecord:
    row = BeginTradeRecord(
        symbol=symbol, ts=ts, time=time_val, direction=direction,
        asks_depth_arr="[]", bids_depth_arr="[]", orders_result="{}",
        now_open_rate=Decimal("0.01"), machine_number="m1",
        my_trade_type="open", now_price=Decimal("42000"),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_begin_trade_record_select_by_symbol_and_ts(session):
    """SELECT BeginTradeRecord WHERE symbol AND ts range ORDER BY id DESC."""
    _make_begin_trade_record(session, symbol="BTCUSDT", ts=1000)
    _make_begin_trade_record(session, symbol="BTCUSDT", ts=2000)
    _make_begin_trade_record(session, symbol="ETHUSDT", ts=1500)

    rows = session.exec(
        select(BeginTradeRecord)
        .where(BeginTradeRecord.symbol == "BTCUSDT",
               BeginTradeRecord.ts > 500, BeginTradeRecord.ts < 2500)
        .order_by(BeginTradeRecord.id.desc())
        .limit(5000)
    ).all()
    assert len(rows) == 2
    # DESC: highest id first
    assert rows[0].ts == 2000
    assert rows[1].ts == 1000


def test_begin_trade_record_maps_to_dict(session):
    """Simulate get_order_result_arr mapping."""
    _make_begin_trade_record(session, symbol="BTCUSDT", ts=1500,
                              time_val="2026-01-01 12:00:00", direction="shorts")

    rows = session.exec(
        select(BeginTradeRecord)
        .where(BeginTradeRecord.symbol == "BTCUSDT",
               BeginTradeRecord.ts > 1000, BeginTradeRecord.ts < 2000)
        .order_by(BeginTradeRecord.id.desc()).limit(5000)
    ).all()
    row = rows[0]
    mapped = {
        "symbol": row.symbol,
        "time": row.time,
        "asksDepthArr": json.loads(row.asks_depth_arr or "[]"),
        "bidsDepthArr": json.loads(row.bids_depth_arr or "[]"),
        "ordersResult": json.loads(row.orders_result or "{}"),
        "direction": row.direction,
        "nowOpenRate": row.now_open_rate,
        "machineNumber": row.machine_number,
        "ts": row.ts,
        "myTradeType": row.my_trade_type,
        "nowPrice": row.now_price,
    }
    assert mapped["symbol"] == "BTCUSDT"
    assert mapped["direction"] == "shorts"
    assert mapped["asksDepthArr"] == []


# ---------------------------------------------------------------------------
# Trades: SELECT WHERE status + beginTs + version ORDER BY id DESC
# ---------------------------------------------------------------------------

def _make_trades(session, *, symbol="BTCUSDT", status="updateProfit",
                 version=2, begin_ts=1000, **kwargs) -> Trades:
    row = Trades(
        symbol=symbol, status=status, version=version, begin_ts=begin_ts,
        direction=kwargs.get("direction", "longs"),
        profit=kwargs.get("profit", Decimal("10")),
        value=kwargs.get("value", Decimal("1000")),
        cost=kwargs.get("cost", Decimal("500")),
        vol_info=kwargs.get("vol_info", "{}"),
        open_type=kwargs.get("open_type", "normal"),
        open_time=kwargs.get("open_time", 1),
        add_time=kwargs.get("add_time", 0),
        close_time=kwargs.get("close_time", 1),
        open_gtx_time=kwargs.get("open_gtx_time", 0),
        add_gtx_time=kwargs.get("add_gtx_time", 0),
        close_gtx_time=kwargs.get("close_gtx_time", 0),
        now_open_rate=kwargs.get("now_open_rate", Decimal("0.01")),
        standard_rate=kwargs.get("standard_rate", Decimal("0.005")),
        take_time=kwargs.get("take_time", 60),
        begin_boll_up=kwargs.get("begin_boll_up", Decimal("100")),
        begin_boll_down=kwargs.get("begin_boll_down", Decimal("80")),
        take_value=kwargs.get("take_value", Decimal("200")),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_trades_select_update_profit(session):
    """SELECT Trades WHERE status='updateProfit' AND beginTs > X AND version=2."""
    _make_trades(session, symbol="BTCUSDT", begin_ts=2000)
    _make_trades(session, symbol="ETHUSDT", begin_ts=500)
    _make_trades(session, symbol="SOLUSDT", begin_ts=2000, status="tradeBegin")

    rows = session.exec(
        select(Trades)
        .where(Trades.status == "updateProfit", Trades.begin_ts > 1000, Trades.version == 2)
        .order_by(Trades.id.desc())
    ).all()
    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSDT"


def test_trades_select_update_profit_fail(session):
    """SELECT Trades WHERE status='updateProfitFail' AND beginTs > X."""
    _make_trades(session, status="updateProfitFail", begin_ts=2000)
    _make_trades(session, status="updateProfitFail", begin_ts=500)
    _make_trades(session, status="updateProfit", begin_ts=2000)

    rows = session.exec(
        select(Trades).where(
            Trades.status == "updateProfitFail", Trades.begin_ts > 1000, Trades.version == 2
        )
    ).all()
    assert len(rows) == 1


def test_trades_vol_info_parsing(session):
    """vol_info stored as JSON string can be parsed back."""
    vol_data = {"qty": 10, "price": 42000}
    _make_trades(session, vol_info=json.dumps(vol_data))

    rows = session.exec(
        select(Trades).where(Trades.status == "updateProfit", Trades.version == 2)
    ).all()
    parsed = json.loads(rows[0].vol_info) if isinstance(rows[0].vol_info, str) else rows[0].vol_info
    assert parsed == vol_data


def test_trades_boll_percent_calculation(session):
    """Verify begin_boll_up - begin_boll_down percentage calculation."""
    _make_trades(session, begin_boll_up=Decimal("110"), begin_boll_down=Decimal("100"))

    rows = session.exec(
        select(Trades).where(Trades.status == "updateProfit", Trades.version == 2)
    ).all()
    row = rows[0]
    boll_up = row.begin_boll_up or 0
    boll_down = row.begin_boll_down or 0
    diff = boll_up - boll_down
    assert diff == Decimal("10")
    assert boll_down == Decimal("100")

# ---------------------------------------------------------------------------
# commission.py: Income — DELETE old, SELECT all order by id DESC
# ---------------------------------------------------------------------------

def _make_income_simple(session, *, symbol="BTCUSDT", binance_ts=1000000000000,
                         income_val="1.5", trade_id="tid1") -> Income:
    row = Income(
        symbol=symbol,
        binance_ts=binance_ts,
        income=Decimal(income_val),
        trade_id=trade_id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_income_delete_old_rows(session):
    """DELETE Income WHERE binance_ts < threshold removes only old rows."""
    from sqlalchemy import delete as sa_delete
    _make_income_simple(session, binance_ts=500, trade_id="old")
    _make_income_simple(session, binance_ts=1500, trade_id="new")

    session.exec(sa_delete(Income).where(Income.binance_ts < 1000))
    session.commit()

    rows = session.exec(select(Income)).all()
    assert len(rows) == 1
    assert rows[0].trade_id == "new"


def test_income_delete_old_rows_none_deleted(session):
    """DELETE Income WHERE binance_ts < very-low threshold deletes nothing."""
    from sqlalchemy import delete as sa_delete
    _make_income_simple(session, binance_ts=9000, trade_id="keep")

    session.exec(sa_delete(Income).where(Income.binance_ts < 1))
    session.commit()

    rows = session.exec(select(Income)).all()
    assert len(rows) == 1


def test_income_select_all_ordered_desc(session):
    """SELECT Income ORDER BY id DESC returns rows in descending id order."""
    _make_income_simple(session, binance_ts=1000, trade_id="a")
    _make_income_simple(session, binance_ts=2000, trade_id="b")
    _make_income_simple(session, binance_ts=3000, trade_id="c")

    rows = session.exec(select(Income).order_by(Income.id.desc())).all()
    assert len(rows) == 3
    assert rows[0].trade_id == "c"
    assert rows[2].trade_id == "a"


def test_income_insert_without_access_token(session):
    """INSERT Income without access_token uses default empty string."""
    row = Income(
        income=Decimal("2.0"),
        trade_id="t999",
        binance_ts=1700000000000,
        symbol="SOLUSDT",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.id is not None
    assert row.access_token == ""


# ---------------------------------------------------------------------------
# commission.py: IncomeHistoryTake — SELECT limit 2000, INSERT batch
# ---------------------------------------------------------------------------

def _make_income_history_take(session, *, symbol="BTCUSDT",
                               binance_ts=1000000000000,
                               income_type="REALIZED_PNL",
                               income_val="10.0", asset="USDT",
                               trade_id="htid1") -> IncomeHistoryTake:
    row = IncomeHistoryTake(
        symbol=symbol,
        binance_ts=binance_ts,
        income_type=income_type,
        income=Decimal(income_val),
        asset=asset,
        trade_id=trade_id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_income_history_take_select_desc_limit(session):
    """SELECT IncomeHistoryTake ORDER BY id DESC LIMIT 2000."""
    for i in range(5):
        _make_income_history_take(session, trade_id=f"h{i}", binance_ts=1000 + i)

    rows = session.exec(
        select(IncomeHistoryTake).order_by(IncomeHistoryTake.id.desc()).limit(2000)
    ).all()
    assert len(rows) == 5
    # Highest id first
    assert rows[0].trade_id == "h4"


def test_income_history_take_insert_batch(session):
    """session.add_all inserts multiple IncomeHistoryTake rows in one commit."""
    new_rows = [
        IncomeHistoryTake(symbol="BTCUSDT", income=Decimal("5"), trade_id="b1",
                          binance_ts=1000, income_type="REALIZED_PNL", asset="USDT"),
        IncomeHistoryTake(symbol="ETHUSDT", income=Decimal("3"), trade_id="b2",
                          binance_ts=2000, income_type="COMMISSION", asset="BNB"),
    ]
    session.add_all(new_rows)
    session.commit()

    rows = session.exec(select(IncomeHistoryTake)).all()
    assert len(rows) == 2
    symbols = {r.symbol for r in rows}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


# ---------------------------------------------------------------------------
# binanceOrdersRecord.py: Order — SELECT by symbol, INSERT, UPDATE
# ---------------------------------------------------------------------------

def _make_order(session, *, symbol="BTCUSDT", order_id=12345,
                status="NEW", binance_ts=1700000000000,
                update_time=1700000001000, my_ts=1700000000) -> Order:
    row = Order(
        symbol=symbol,
        order_id=order_id,
        status=status,
        binance_ts=binance_ts,
        update_time=update_time,
        my_ts=my_ts,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_order_select_by_symbol_ordered_desc(session):
    """SELECT Order WHERE symbol ORDER BY id DESC LIMIT 1000."""
    _make_order(session, symbol="BTCUSDT", order_id=1, binance_ts=1000)
    _make_order(session, symbol="BTCUSDT", order_id=2, binance_ts=2000)
    _make_order(session, symbol="ETHUSDT", order_id=3, binance_ts=1500)

    rows = session.exec(
        select(Order).where(Order.symbol == "BTCUSDT")
        .order_by(Order.id.desc()).limit(1000)
    ).all()
    assert len(rows) == 2
    # Highest id first
    assert rows[0].order_id == 2
    assert rows[1].order_id == 1


def test_order_insert_all_fields(session):
    """INSERT Order with all 22 columns maps correctly to model fields."""
    row = Order(
        avg_price=Decimal("42000"),
        client_order_id="cid_abc",
        cum_quote=Decimal("42"),
        executed_qty=Decimal("0.001"),
        order_id=99999,
        orig_qty=Decimal("0.001"),
        orig_type="LIMIT",
        price=Decimal("42000"),
        reduce_only="False",
        side="BUY",
        position_side="LONG",
        status="FILLED",
        stop_price=Decimal("0"),
        close_position="False",
        symbol="BTCUSDT",
        time_in_force="GTC",
        order_type="LIMIT",
        update_time=1700000001000,
        working_type="CONTRACT_PRICE",
        price_protect="False",
        binance_ts=1700000000000,
        my_ts=1700000000,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.id is not None
    fetched = session.exec(select(Order).where(Order.order_id == 99999)).one()
    assert fetched.client_order_id == "cid_abc"
    assert fetched.side == "BUY"
    assert fetched.status == "FILLED"


def test_order_update_status(session):
    """UPDATE Order status and my_ts by id."""
    row = _make_order(session, status="NEW", my_ts=1000)

    db_row = session.get(Order, row.id)
    db_row.status = "noExit"
    db_row.my_ts = 9999
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.status == "noExit"
    assert db_row.my_ts == 9999


def test_order_select_new_status_with_my_ts_filter(session):
    """SELECT Order WHERE status='NEW' AND my_ts < threshold."""
    _make_order(session, status="NEW", my_ts=500)
    _make_order(session, status="NEW", my_ts=9000)
    _make_order(session, status="FILLED", my_ts=500)

    rows = session.exec(
        select(Order).where(Order.status == "NEW", Order.my_ts < 3600)
    ).all()
    assert len(rows) == 1
    assert rows[0].my_ts == 500


# ---------------------------------------------------------------------------
# binanceTradesRecord.py: Trade — SELECT by symbol, INSERT batch
# ---------------------------------------------------------------------------

def _make_trade(session, *, symbol="BTCUSDT", binance_id=55555,
                ts=1700000000000, my_ts=1700000000) -> Trade:
    row = Trade(
        symbol=symbol,
        binance_id=binance_id,
        ts=ts,
        my_ts=my_ts,
        buyer=True,
        maker=False,
        order_id=12345,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_trade_select_by_symbol_ordered_desc(session):
    """SELECT Trade WHERE symbol ORDER BY id DESC LIMIT 1000."""
    _make_trade(session, symbol="BTCUSDT", binance_id=1, ts=1000)
    _make_trade(session, symbol="BTCUSDT", binance_id=2, ts=2000)
    _make_trade(session, symbol="ETHUSDT", binance_id=3, ts=1500)

    rows = session.exec(
        select(Trade).where(Trade.symbol == "BTCUSDT")
        .order_by(Trade.id.desc()).limit(1000)
    ).all()
    assert len(rows) == 2
    assert rows[0].binance_id == 2


def test_trade_insert_batch(session):
    """session.add_all inserts multiple Trade rows."""
    new_rows = [
        Trade(symbol="BTCUSDT", binance_id=10, ts=1000, my_ts=1, buyer=True, maker=False, order_id=1),
        Trade(symbol="ETHUSDT", binance_id=20, ts=2000, my_ts=2, buyer=False, maker=True, order_id=2),
    ]
    session.add_all(new_rows)
    session.commit()

    rows = session.exec(select(Trade)).all()
    assert len(rows) == 2
    ids = {r.binance_id for r in rows}
    assert ids == {10, 20}


def test_trade_skip_duplicate_binance_id(session):
    """Simulate dedup: skip insert if binance_id already in existing records."""
    existing = _make_trade(session, symbol="BTCUSDT", binance_id=777)

    loaded = session.exec(
        select(Trade).where(Trade.symbol == "BTCUSDT").order_by(Trade.id.desc()).limit(1000)
    ).all()

    insert_flag = True
    for row in loaded:
        if int(row.binance_id) == 777:
            insert_flag = False
            break

    assert insert_flag is False
    count = session.exec(select(Trade)).all()
    assert len(count) == 1


# ---------------------------------------------------------------------------
# updateTradeSymbol.py: TradeSymbol — TRUNCATE, INSERT batch, UPDATE fields
# ---------------------------------------------------------------------------

def test_trade_symbol_truncate(session):
    """DELETE all TradeSymbol rows simulates TRUNCATE."""
    from sqlalchemy import delete as sa_delete
    _make_trade_symbol(session, symbol="BTCUSDT")
    _make_trade_symbol(session, symbol="ETHUSDT")

    session.exec(sa_delete(TradeSymbol))
    session.commit()

    rows = session.exec(select(TradeSymbol)).all()
    assert rows == []


def test_trade_symbol_insert_batch(session):
    """session.add_all inserts multiple TradeSymbol rows."""
    new_rows = [
        TradeSymbol(symbol="BTCUSDT", coin="BTC", quote="USDT", status="yes",
                    index=0, default_show=False, link_symbol_arr=[]),
        TradeSymbol(symbol="ETHUSDT", coin="ETH", quote="USDT", status="yes",
                    index=1, default_show=False, link_symbol_arr=[]),
    ]
    session.add_all(new_rows)
    session.commit()

    rows = session.exec(select(TradeSymbol)).all()
    assert len(rows) == 2


def test_trade_symbol_update_quote_volume(session):
    """UPDATE quote_volume by symbol."""
    _make_trade_symbol(session, symbol="BTCUSDT")

    row = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCUSDT")).first()
    row.quote_volume = Decimal("999999.5")
    session.add(row)
    session.commit()
    session.refresh(row)

    assert row.quote_volume == Decimal("999999.5")


def test_trade_symbol_update_index(session):
    """UPDATE index by id (batch re-index operation)."""
    r1 = _make_trade_symbol(session, symbol="BTCUSDT", index=0, status="yes")
    r2 = _make_trade_symbol(session, symbol="ETHUSDT", index=0, status="yes")

    active = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    for i, r in enumerate(active):
        r.index = i
        session.add(r)
    session.commit()

    rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    assert rows[0].index == 0
    assert rows[1].index == 1


def test_trade_symbol_update_default_show(session):
    """UPDATE default_show — highest quoteVolume gets True, others False."""
    _make_trade_symbol(session, symbol="BTCUSDT", coin="BTC")
    _make_trade_symbol(session, symbol="BTCPERP", coin="BTC")

    # Set quote volumes to determine ordering
    r1 = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCUSDT")).first()
    r2 = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCPERP")).first()
    r1.quote_volume = Decimal("1000")
    r2.quote_volume = Decimal("50")
    session.add(r1)
    session.add(r2)
    session.commit()

    coin_rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.coin == "BTC")
        .order_by(TradeSymbol.quote_volume.desc())
    ).all()
    for b, row in enumerate(coin_rows):
        row.default_show = (b == 0)
        session.add(row)
    session.commit()

    btcusdt = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCUSDT")).first()
    btcperp = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCPERP")).first()
    assert btcusdt.default_show is True
    assert btcperp.default_show is False


def test_trade_symbol_update_link_symbol_arr(session):
    """UPDATE link_symbol_arr with list of symbols sharing the same coin."""
    _make_trade_symbol(session, symbol="BTCUSDT", coin="BTC")
    _make_trade_symbol(session, symbol="BTCBUSD", coin="BTC")
    _make_trade_symbol(session, symbol="ETHUSDT", coin="ETH")

    all_rows = session.exec(select(TradeSymbol).order_by(TradeSymbol.id.asc())).all()
    for row in all_rows:
        link_rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.coin == row.coin)
        ).all()
        row.link_symbol_arr = [r.symbol for r in link_rows]
        session.add(row)
    session.commit()

    btcusdt = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "BTCUSDT")).first()
    ethusdt = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == "ETHUSDT")).first()
    assert set(btcusdt.link_symbol_arr) == {"BTCUSDT", "BTCBUSD"}
    assert ethusdt.link_symbol_arr == ["ETHUSDT"]


# ---------------------------------------------------------------------------
# positionRecord.py — record_position() INSERT pattern
# ---------------------------------------------------------------------------

def test_position_record_insert_all_symbol(session):
    """INSERT PositionRecord for 'all' symbol as done in record_position()."""
    from decimal import Decimal
    from datetime import datetime, timezone
    now = 1700000000
    record = PositionRecord(
        symbol="all",
        unrealized_profit=Decimal("12.5"),
        position_amt=Decimal("1.0"),
        ts=now,
        time=datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
        position_value=Decimal("42000"),
        balance=Decimal("10000"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    assert record.id is not None
    fetched = session.exec(
        select(PositionRecord).where(PositionRecord.symbol == "all")
    ).first()
    assert fetched is not None
    assert fetched.unrealized_profit == Decimal("12.5")
    assert fetched.ts == now
    assert fetched.update_profit_and_commission is False


# ---------------------------------------------------------------------------
# positionRecord.py — updateProfitAndCommission() SELECT patterns
# ---------------------------------------------------------------------------

def test_position_record_select_pending_update(session):
    """SELECT PositionRecord WHERE ts < threshold AND update_profit_and_commission=False."""
    from decimal import Decimal
    _make_position_record(session, symbol="all", ts=1000)
    _make_position_record(session, symbol="all", ts=2000)
    _make_position_record(session, symbol="all", ts=5000)

    threshold = 3000
    rows = session.exec(
        select(PositionRecord)
        .where(PositionRecord.ts < threshold)
        .where(PositionRecord.update_profit_and_commission == False)
        .order_by(PositionRecord.id.desc())
    ).all()
    assert len(rows) == 2
    # DESC: highest id first
    assert rows[0].ts == 2000
    assert rows[1].ts == 1000


def test_position_record_select_max_id_before(session):
    """SELECT PositionRecord with highest id < given id (previous record lookup)."""
    from decimal import Decimal
    r1 = _make_position_record(session, symbol="all", ts=1000)
    r2 = _make_position_record(session, symbol="all", ts=2000)
    r3 = _make_position_record(session, symbol="all", ts=3000)

    # Find the record immediately before r3
    prev = session.exec(
        select(PositionRecord)
        .where(PositionRecord.id < r3.id)
        .order_by(PositionRecord.id.desc())
        .limit(1)
    ).first()
    assert prev is not None
    assert prev.ts == 2000


def test_position_record_update_profit_commission(session):
    """UPDATE PositionRecord profit, commission, maker_commission, update_profit_and_commission by id."""
    from decimal import Decimal
    record = _make_position_record(session, symbol="all", ts=1000)
    assert record.update_profit_and_commission is False

    db_row = session.exec(
        select(PositionRecord).where(PositionRecord.id == record.id)
    ).one()
    db_row.profit = Decimal("100.5")
    db_row.commission = Decimal("-5.2")
    db_row.maker_commission = Decimal("2.1")
    db_row.update_profit_and_commission = True
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.profit == Decimal("100.5")
    assert db_row.commission == Decimal("-5.2")
    assert db_row.maker_commission == Decimal("2.1")
    assert db_row.update_profit_and_commission is True


# ---------------------------------------------------------------------------
# tradesUpdate.py — update() SELECT + UPDATE patterns
# ---------------------------------------------------------------------------

def test_trades_take_select_trade_begin_status(session):
    """SELECT TradesTake WHERE status='tradeBegin' returns only matching rows."""
    TradesTake.__table__  # ensure table registered
    row1 = TradesTake(symbol="BTCUSDT", status="tradeBegin", begin_ts=1000)
    row2 = TradesTake(symbol="ETHUSDT", status="tradeEnd", begin_ts=2000)
    row3 = TradesTake(symbol="SOLUSDT", status="tradeBegin", begin_ts=3000)
    session.add(row1)
    session.add(row2)
    session.add(row3)
    session.commit()

    rows = session.exec(
        select(TradesTake).where(TradesTake.status == "tradeBegin")
    ).all()
    assert len(rows) == 2
    symbols = {r.symbol for r in rows}
    assert symbols == {"BTCUSDT", "SOLUSDT"}


def test_trades_take_update_trade_end_fields(session):
    """UPDATE TradesTake value, amount, cost, balance, end_ts, status='tradeEnd' by id."""
    from decimal import Decimal
    row = TradesTake(symbol="BTCUSDT", status="tradeBegin", begin_ts=1000)
    session.add(row)
    session.commit()
    session.refresh(row)

    db_row = session.exec(
        select(TradesTake).where(TradesTake.id == row.id)
    ).one()
    db_row.value = Decimal("50000")
    db_row.amount = Decimal("1.2")
    db_row.cost = Decimal("41666")
    db_row.balance = Decimal("10000")
    db_row.end_ts = 2000
    db_row.status = "tradeEnd"
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.value == Decimal("50000")
    assert db_row.amount == Decimal("1.2")
    assert db_row.status == "tradeEnd"
    assert db_row.end_ts == 2000


# ---------------------------------------------------------------------------
# tradesUpdate.py — updateProfit() SELECT + UPDATE patterns
# ---------------------------------------------------------------------------

def test_income_history_take_select_latest_by_id(session):
    """SELECT IncomeHistoryTake ORDER BY id DESC LIMIT 1 returns the latest row."""
    r1 = IncomeHistoryTake(symbol="BTCUSDT", binance_ts=1000, income_type="COMMISSION")
    r2 = IncomeHistoryTake(symbol="ETHUSDT", binance_ts=2000, income_type="REALIZED_PNL")
    session.add(r1)
    session.add(r2)
    session.commit()

    latest = session.exec(
        select(IncomeHistoryTake).order_by(IncomeHistoryTake.id.desc()).limit(1)
    ).first()
    assert latest is not None
    assert latest.symbol == "ETHUSDT"
    assert latest.binance_ts == 2000


def test_trades_take_select_trade_end_before_ts(session):
    """SELECT TradesTake WHERE status='tradeEnd' AND end_ts < threshold."""
    from decimal import Decimal
    r1 = TradesTake(symbol="BTCUSDT", status="tradeEnd", end_ts=1000)
    r2 = TradesTake(symbol="ETHUSDT", status="tradeEnd", end_ts=5000)
    r3 = TradesTake(symbol="SOLUSDT", status="tradeBegin", end_ts=500)
    session.add(r1)
    session.add(r2)
    session.add(r3)
    session.commit()

    threshold = 3000
    rows = session.exec(
        select(TradesTake)
        .where(TradesTake.status == "tradeEnd")
        .where(TradesTake.end_ts < threshold)
    ).all()
    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSDT"


def test_income_history_take_select_in_range_by_symbol(session):
    """SELECT IncomeHistoryTake WHERE binance_ts IN range AND symbol matches."""
    from decimal import Decimal
    r1 = IncomeHistoryTake(symbol="BTCUSDT", binance_ts=1000,
                            income_type="COMMISSION", income=Decimal("0.01"),
                            bnb_price=Decimal("300"), asset="BNB")
    r2 = IncomeHistoryTake(symbol="BTCUSDT", binance_ts=3000,
                            income_type="REALIZED_PNL", income=Decimal("50"),
                            bnb_price=Decimal("0"), asset="USDT")
    r3 = IncomeHistoryTake(symbol="ETHUSDT", binance_ts=2000,
                            income_type="COMMISSION", income=Decimal("0.005"),
                            bnb_price=Decimal("300"), asset="BNB")
    r4 = IncomeHistoryTake(symbol="BTCUSDT", binance_ts=9000,
                            income_type="COMMISSION", income=Decimal("1"),
                            bnb_price=Decimal("0"), asset="USDT")
    for r in [r1, r2, r3, r4]:
        session.add(r)
    session.commit()

    rows = session.exec(
        select(IncomeHistoryTake)
        .where(IncomeHistoryTake.binance_ts >= 500)
        .where(IncomeHistoryTake.binance_ts <= 5000)
        .where(IncomeHistoryTake.symbol == "BTCUSDT")
    ).all()
    assert len(rows) == 2
    types = {r.income_type for r in rows}
    assert types == {"COMMISSION", "REALIZED_PNL"}


def test_trades_take_update_profit_fields(session):
    """UPDATE TradesTake profit, commission, status, profitPercentByBalance, vol_info, extra_info."""
    from decimal import Decimal
    row = TradesTake(symbol="BTCUSDT", status="tradeEnd", begin_ts=1000, end_ts=2000)
    session.add(row)
    session.commit()
    session.refresh(row)

    db_row = session.exec(
        select(TradesTake).where(TradesTake.id == row.id)
    ).one()
    db_row.profit = Decimal("75.5")
    db_row.commission = Decimal("-3.2")
    db_row.status = "updateProfit"
    db_row.profit_percent_by_balance = Decimal("0.75")
    db_row.vol_info = {"binanceHoursVolArr": [100, 200], "okexHoursVolArr": [], "bybitHoursVolArr": []}
    db_row.extra_info = {"priceRate": 2.5}
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.profit == Decimal("75.5")
    assert db_row.status == "updateProfit"
    assert db_row.vol_info["binanceHoursVolArr"] == [100, 200]
    assert db_row.extra_info["priceRate"] == 2.5


def test_trades_take_update_status_fail(session):
    """UPDATE TradesTake status='updateProfitFail' when no income data found."""
    row = TradesTake(symbol="BTCUSDT", status="tradeEnd", begin_ts=1000, end_ts=2000)
    session.add(row)
    session.commit()
    session.refresh(row)

    db_row = session.exec(
        select(TradesTake).where(TradesTake.id == row.id)
    ).one()
    db_row.status = "updateProfitFail"
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.status == "updateProfitFail"


# ---------------------------------------------------------------------------
# webOssUpdate.py — IncomeHistoryTakeDay patterns
# ---------------------------------------------------------------------------

def _make_income_history_take_day(session, *, day_begin_time="2023-07-20 00:00:00",
                                   day_end_time="2023-07-21 00:00:00",
                                   commission=None, profit=None) -> IncomeHistoryTakeDay:
    from decimal import Decimal
    row = IncomeHistoryTakeDay(
        day_begin_time=day_begin_time,
        day_end_time=day_end_time,
        commission=Decimal(str(commission)) if commission is not None else None,
        profit=Decimal(str(profit)) if profit is not None else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_income_history_take_day_select_latest(session):
    """SELECT IncomeHistoryTakeDay ORDER BY id DESC LIMIT 1 returns the most recent row."""
    _make_income_history_take_day(session, day_begin_time="2023-07-20 00:00:00")
    _make_income_history_take_day(session, day_begin_time="2023-07-21 00:00:00")

    latest = session.exec(
        select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.desc()).limit(1)
    ).first()
    assert latest is not None
    assert latest.day_begin_time == "2023-07-21 00:00:00"


def test_income_history_take_day_select_latest_empty(session):
    """SELECT latest IncomeHistoryTakeDay from empty table returns None."""
    latest = session.exec(
        select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.desc()).limit(1)
    ).first()
    assert latest is None


def test_income_history_take_day_select_by_day_begin_time(session):
    """SELECT IncomeHistoryTakeDay WHERE day_begin_time = X."""
    _make_income_history_take_day(session, day_begin_time="2023-07-20 00:00:00")
    _make_income_history_take_day(session, day_begin_time="2023-07-21 00:00:00")

    row = session.exec(
        select(IncomeHistoryTakeDay)
        .where(IncomeHistoryTakeDay.day_begin_time == "2023-07-20 00:00:00")
    ).first()
    assert row is not None
    assert row.day_begin_time == "2023-07-20 00:00:00"


def test_income_history_take_day_select_by_day_begin_time_none(session):
    """SELECT IncomeHistoryTakeDay WHERE non-existent day_begin_time returns None."""
    row = session.exec(
        select(IncomeHistoryTakeDay)
        .where(IncomeHistoryTakeDay.day_begin_time == "2099-01-01 00:00:00")
    ).first()
    assert row is None


def test_income_history_take_day_insert(session):
    """INSERT IncomeHistoryTakeDay as done in updateDayIncome()."""
    from decimal import Decimal
    new_row = IncomeHistoryTakeDay(
        day_begin_time="2023-08-01 00:00:00",
        day_end_time="2023-08-02 00:00:00",
        commission=Decimal("1.5"),
        profit=Decimal("25.0"),
    )
    session.add(new_row)
    session.commit()
    session.refresh(new_row)

    assert new_row.id is not None
    fetched = session.exec(
        select(IncomeHistoryTakeDay).where(IncomeHistoryTakeDay.id == new_row.id)
    ).one()
    assert fetched.commission == Decimal("1.5")
    assert fetched.profit == Decimal("25.0")


def test_income_history_take_day_update_by_day_end_time(session):
    """UPDATE IncomeHistoryTakeDay commission, profit WHERE day_end_time = X."""
    from decimal import Decimal
    _make_income_history_take_day(
        session,
        day_begin_time="2023-07-20 00:00:00",
        day_end_time="2023-07-21 00:00:00",
        commission=1.0, profit=10.0,
    )

    db_row = session.exec(
        select(IncomeHistoryTakeDay)
        .where(IncomeHistoryTakeDay.day_end_time == "2023-07-21 00:00:00")
    ).first()
    assert db_row is not None
    db_row.commission = Decimal("2.5")
    db_row.profit = Decimal("50.0")
    session.add(db_row)
    session.commit()
    session.refresh(db_row)

    assert db_row.commission == Decimal("2.5")
    assert db_row.profit == Decimal("50.0")


def test_income_history_take_day_update_does_not_affect_other_rows(session):
    """Updating one IncomeHistoryTakeDay row leaves sibling rows untouched."""
    from decimal import Decimal
    _make_income_history_take_day(
        session, day_begin_time="2023-07-20 00:00:00",
        day_end_time="2023-07-21 00:00:00", profit=10.0,
    )
    _make_income_history_take_day(
        session, day_begin_time="2023-07-21 00:00:00",
        day_end_time="2023-07-22 00:00:00", profit=20.0,
    )

    db_row = session.exec(
        select(IncomeHistoryTakeDay)
        .where(IncomeHistoryTakeDay.day_end_time == "2023-07-21 00:00:00")
    ).first()
    db_row.profit = Decimal("99.0")
    session.add(db_row)
    session.commit()

    other = session.exec(
        select(IncomeHistoryTakeDay)
        .where(IncomeHistoryTakeDay.day_end_time == "2023-07-22 00:00:00")
    ).first()
    assert other.profit == Decimal("20.0")


def test_income_history_take_day_select_all_ordered_asc(session):
    """SELECT IncomeHistoryTakeDay ORDER BY id ASC returns rows in insert order."""
    from decimal import Decimal
    _make_income_history_take_day(session, day_begin_time="2023-07-20 00:00:00", profit=10.0)
    _make_income_history_take_day(session, day_begin_time="2023-07-21 00:00:00", profit=20.0)
    _make_income_history_take_day(session, day_begin_time="2023-07-22 00:00:00", profit=30.0)

    rows = session.exec(
        select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.asc())
    ).all()
    assert len(rows) == 3
    assert rows[0].day_begin_time == "2023-07-20 00:00:00"
    assert rows[1].day_begin_time == "2023-07-21 00:00:00"
    assert rows[2].day_begin_time == "2023-07-22 00:00:00"
    assert [float(r.profit) for r in rows] == [10.0, 20.0, 30.0]


def test_income_history_take_day_day_income_arr_building(session):
    """Verify day income arr building pattern from updateDayIncome()."""
    from decimal import Decimal
    _make_income_history_take_day(session, day_begin_time="2023-07-20 00:00:00",
                                   day_end_time="2023-07-21 00:00:00", profit=15.0)
    _make_income_history_take_day(session, day_begin_time="2023-07-21 00:00:00",
                                   day_end_time="2023-07-22 00:00:00", profit=25.0)

    rows = session.exec(
        select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.asc())
    ).all()
    day_income_arr = [[r.day_begin_time, float(r.profit)] for r in rows]

    assert len(day_income_arr) == 2
    assert day_income_arr[0] == ["2023-07-20 00:00:00", 15.0]
    assert day_income_arr[1] == ["2023-07-21 00:00:00", 25.0]


# ---------------------------------------------------------------------------
# webOssUpdate.py — generateObj() SELECT TradeMachineStatus + TradesTake patterns
# ---------------------------------------------------------------------------

def test_trade_machine_status_sum_run_time(session):
    """Compute systemAverageRunTime from all TradeMachineStatus rows."""
    _make_trade_machine_status(session, private_ip="10.6.0.1", update_ts=1000, run_time=100)
    _make_trade_machine_status(session, private_ip="10.6.0.2", update_ts=2000, run_time=200)
    _make_trade_machine_status(session, private_ip="10.6.0.3", update_ts=3000, run_time=300)

    rows = session.exec(
        select(TradeMachineStatus).order_by(asc(TradeMachineStatus.update_ts))
    ).all()

    all_run_time = sum(r.run_time or 0 for r in rows)
    system_average_run_time = int(all_run_time / len(rows))
    system_update_ts = rows[0].update_ts
    system_status = rows[0].status

    assert all_run_time == 600
    assert system_average_run_time == 200
    assert system_update_ts == 1000


def test_trades_take_select_update_profit_limit_1000(session):
    """SELECT TradesTake WHERE status='updateProfit' ORDER BY id ASC LIMIT 1000."""
    for i in range(5):
        row = TradesTake(symbol=f"SYM{i}USDT", status="updateProfit",
                         begin_ts=i * 1000, end_ts=i * 2000)
        session.add(row)
    row_other = TradesTake(symbol="XYZUSDT", status="tradeEnd", begin_ts=0)
    session.add(row_other)
    session.commit()

    rows = session.exec(
        select(TradesTake)
        .where(TradesTake.status == "updateProfit")
        .order_by(TradesTake.id.asc())
        .limit(1000)
    ).all()
    assert len(rows) == 5
    assert all(r.status == "updateProfit" for r in rows)
    # ASC: first inserted first
    assert rows[0].symbol == "SYM0USDT"
