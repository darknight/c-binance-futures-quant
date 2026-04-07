import json
import time

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlmodel import select

from app.models.income_history_take import IncomeHistoryTake
from app.models.machine_status import TradeMachineStatus
from app.models.position_record import PositionRecord
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_dashboard_summary")
def get_dashboard_summary(request: Request):
    state = request.app.state.app_state
    now = int(time.time())

    if now - state.dashboard_summary_update_ts < 10 and state.dashboard_summary_data:
        return state.dashboard_summary_data

    # Balance + position value from latest PositionRecord per symbol
    all_balance = 0
    all_position = 0
    with state.infra_client.get_session() as session:
        subq = select(func.max(PositionRecord.id)).group_by(PositionRecord.symbol).scalar_subquery()
        position_record_data = session.exec(
            select(PositionRecord).where(PositionRecord.id.in_(subq))
        ).all()
    for row in position_record_data:
        all_position += (row.position_value or 0)
        all_balance += (row.balance or 0)

    # Today's profit/commission from income_obj (populated by /get_income_obj)
    today_profit = state.income_obj.get("today", {}).get("p", 0)
    today_commission = state.income_obj.get("today", {}).get("c", 0)
    today_vol = today_commission  # oneDayVol in old frontend = today's commission

    # System status from TradeMachineStatus
    system_status = ""
    system_update_ts = 0
    run_time = 0
    if now - state.update_trade_machine_status_data_ts > 60:
        state.update_trade_machine_status_data_ts = now
        with state.infra_client.get_session() as session:
            state.trade_machine_status_data = session.exec(
                select(TradeMachineStatus).order_by(TradeMachineStatus.update_ts.asc())
            ).all()
        all_run_time = 0
        for item in state.trade_machine_status_data:
            all_run_time += (item.run_time or 0)
        if len(state.trade_machine_status_data) > 0:
            state.average_run_time = int(all_run_time / len(state.trade_machine_status_data))

    if len(state.trade_machine_status_data) > 0:
        system_update_ts = state.trade_machine_status_data[0].update_ts
        system_status = state.trade_machine_status_data[0].status
        run_time = state.average_run_time

    state.dashboard_summary_data = {
        "s": "ok",
        "balance": all_balance,
        "positionValue": all_position,
        "oneDayVol": today_vol,
        "oneDayProfit": today_profit,
        "systemStatus": system_status,
        "systemUpdateTs": system_update_ts,
        "runTime": run_time,
        "t": now,
    }
    state.dashboard_summary_update_ts = now

    return json.loads(json_dumps(state.dashboard_summary_data))


@router.post("/get_profit_by_symbol")
def get_profit_by_symbol(request: Request):
    state = request.app.state.app_state
    now = int(time.time())

    # Calculate today's midnight timestamp (UTC) in milliseconds
    today_ts = (now - now % 86400) * 1000

    # Return cache if within 5min TTL and same day
    if (
        now - state.profit_by_symbol_update_ts < 300
        and state.profit_by_symbol_today_ts == today_ts
        and state.profit_by_symbol_data
    ):
        return state.profit_by_symbol_data

    with state.infra_client.get_session() as session:
        income_rows = session.exec(
            select(IncomeHistoryTake).where(IncomeHistoryTake.binance_ts < today_ts)
        ).all()

    p = {}  # profit by symbol
    c = {}  # commission by symbol
    v = {}  # BNB volume by symbol

    one_day_ago = today_ts - 86400 * 1000
    seven_days_ago = today_ts - 7 * 86400 * 1000
    thirty_days_ago = today_ts - 30 * 86400 * 1000

    for row in income_rows:
        income = float(row.income) if row.income is not None else 0
        binance_ts = row.binance_ts
        income_type = row.income_type
        bnb_price = float(row.bnb_price) if row.bnb_price is not None else 0
        asset = row.asset
        symbol = row.symbol

        if not symbol:
            continue

        if symbol not in p:
            p[symbol] = [0, 0, 0, 0]
        if symbol not in c:
            c[symbol] = [0, 0, 0, 0]
        if symbol not in v:
            v[symbol] = [0, 0, 0, 0]

        real_income = income * bnb_price if asset == "BNB" else income

        if income_type == "COMMISSION":
            commission_value = real_income * 0.6
            if binance_ts >= one_day_ago:
                c[symbol][0] += commission_value
                p[symbol][0] += commission_value
                if asset == "BNB":
                    v[symbol][0] += income * 0.6
            if binance_ts >= seven_days_ago:
                c[symbol][1] += commission_value
                p[symbol][1] += commission_value
                if asset == "BNB":
                    v[symbol][1] += income * 0.6
            if binance_ts >= thirty_days_ago:
                c[symbol][2] += commission_value
                p[symbol][2] += commission_value
                if asset == "BNB":
                    v[symbol][2] += income * 0.6
            c[symbol][3] += commission_value
            p[symbol][3] += commission_value
            if asset == "BNB":
                v[symbol][3] += income * 0.6

        elif income_type in ("REALIZED_PNL", "FUNDING_FEE"):
            if binance_ts >= one_day_ago:
                p[symbol][0] += real_income
            if binance_ts >= seven_days_ago:
                p[symbol][1] += real_income
            if binance_ts >= thirty_days_ago:
                p[symbol][2] += real_income
            p[symbol][3] += real_income

    # Aggregate "all" row
    for d in (p, c, v):
        d["all"] = [0, 0, 0, 0]
        for key in d:
            if key != "all":
                for i in range(4):
                    d["all"][i] += d[key][i]

    state.profit_by_symbol_data = {"s": "ok", "p": p, "c": c, "v": v, "t": today_ts}
    state.profit_by_symbol_update_ts = now
    state.profit_by_symbol_today_ts = today_ts

    return state.profit_by_symbol_data
