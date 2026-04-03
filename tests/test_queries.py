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
