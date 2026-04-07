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
