import decimal
import json
import time
import datetime

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from binance_f.requestclient import RequestClient
from app.models.income import Income
from app.models.income_day import IncomeDay
from web_server.binance_helpers import get_future_now_price_by_depth, json_dumps

router = APIRouter()


@router.post("/get_income_obj")
def get_income_obj(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.last_update_income_ts >= 9:
        if now - state.last_update_income_ts >= 60 or (not state.income_lock):
            state.last_update_income_ts = now
            state.income_lock = True

            today_time = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " 00:00:00"
            today_ts = state.infra_client.turn_ts_to_time(today_time)

            today_limit_ts = today_ts * 1000
            fifteen_mins_limit_ts = int(time.time() * 1000) - 900000
            thirty_mins_limit_ts = int(time.time() * 1000) - 1800000
            one_hour_limit_ts = int(time.time() * 1000) - 3600000
            four_hours_limit_ts = int(time.time() * 1000) - 14400000
            one_day_limit_ts = int(time.time() * 1000) - 86400000
            limit_ts = int(time.time() * 1000) - 86400000

            with state.infra_client.get_session() as session:
                data = session.exec(
                    select(Income).where(Income.binance_ts > limit_ts).order_by(Income.id.desc())
                ).all()

            if len(data) > 0:
                state.income_obj = {
                    "15m": {"c": 0, "p": 0, "s": 0},
                    "30m": {"c": 0, "p": 0, "s": 0},
                    "1h": {"c": 0, "p": 0, "s": 0},
                    "4h": {"c": 0, "p": 0, "s": 0},
                    "oneDay": {"c": 0, "p": 0, "s": 0},
                    "today": {"c": 0, "p": 0, "s": 0},
                }

            symbol_income_obj = {}
            for row in data:
                sym = row.symbol
                binance_ts = row.binance_ts
                value = row.income
                commission = row.commission
                if sym not in symbol_income_obj:
                    symbol_income_obj[sym] = {
                        "15m": {"p": 0, "c": 0}, "30m": {"p": 0, "c": 0},
                        "1h": {"p": 0, "c": 0}, "4h": {"p": 0, "c": 0},
                        "oneDay": {"p": 0, "c": 0}, "today": {"p": 0, "c": 0},
                    }

                if row.asset == "BNB":
                    value = row.income * row.bnb_price

                time_buckets = [
                    ("15m", fifteen_mins_limit_ts), ("30m", thirty_mins_limit_ts),
                    ("1h", one_hour_limit_ts), ("4h", four_hours_limit_ts),
                    ("oneDay", one_day_limit_ts), ("today", today_limit_ts),
                ]

                if row.income_type == "COMMISSION":
                    for bucket, limit in time_buckets:
                        if binance_ts >= limit:
                            state.income_obj[bucket]["c"] += value
                            state.income_obj[bucket]["s"] += commission
                            symbol_income_obj[sym][bucket]["c"] += value
                if row.income_type == "REALIZED_PNL":
                    for bucket, limit in time_buckets:
                        if binance_ts >= limit:
                            state.income_obj[bucket]["p"] += value
                            symbol_income_obj[sym][bucket]["p"] += value

            state.symbol_income_obj = symbol_income_obj
            state.income_lock = False

    return json.loads(json_dumps({
        "s": "ok", "i": state.income_obj, "n": int(time.time()), "d": state.symbol_income_obj,
    }))


def _update_day_income(state):
    """Update income_day table with aggregated daily data."""
    now = int(time.time())
    if now - state.update_day_income_ts > 30:
        state.update_day_income_ts = now

        with state.infra_client.get_session() as session:
            latest_day = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.desc()).limit(1)
            ).first()

        init_income_day_time = "2022-11-20 00:00:00"
        init_income_day_ts = state.infra_client.turn_ts_to_time(init_income_day_time)
        last_income_day_ts = 0
        if latest_day is not None:
            last_income_day_ts = state.infra_client.turn_ts_to_time(latest_day.day_begin_time)
        if last_income_day_ts == 0:
            last_income_day_ts = init_income_day_ts
        now_ts = int(time.time())
        today_ts = now_ts - now_ts % 86400

        need_insert_day = int((today_ts - last_income_day_ts) / 86400)
        for i in range(need_insert_day):
            end_day_ts = last_income_day_ts + 86400 * (i + 1)
            begin_day_ts = last_income_day_ts + 86400 * i
            with state.infra_client.get_session() as session:
                income_data = session.exec(
                    select(Income)
                    .where(Income.binance_ts > begin_day_ts * 1000)
                    .where(Income.binance_ts <= end_day_ts * 1000)
                ).all()
            day_binance_commission = 0
            day_zjy_commission = 0
            day_pnl = 0
            for item in income_data:
                if item.income_type == "COMMISSION":
                    if item.asset == "BNB":
                        day_binance_commission += item.income * item.bnb_price
                    elif item.asset in ("USDT", "BUSD"):
                        day_binance_commission += item.income
                elif item.income_type == "REALIZED_PNL":
                    if item.asset == "BNB":
                        day_pnl += item.income * item.bnb_price
                    elif item.asset in ("USDT", "BUSD"):
                        day_pnl += item.income
                day_zjy_commission += item.commission

            with state.infra_client.get_session() as session:
                existing_day = session.exec(
                    select(IncomeDay).where(IncomeDay.day_begin_time == state.infra_client.turn_ts_to_time(begin_day_ts))
                ).first()
                if existing_day is None:
                    new_day = IncomeDay(
                        api_key="",
                        day_begin_time=state.infra_client.turn_ts_to_time(begin_day_ts),
                        day_end_time=state.infra_client.turn_ts_to_time(end_day_ts),
                        binance_commission=day_binance_commission,
                        pnl=day_pnl,
                        zjy_commission=day_zjy_commission,
                    )
                    session.add(new_day)
                    session.commit()
                else:
                    existing_day.binance_commission = day_binance_commission
                    existing_day.pnl = day_pnl
                    existing_day.zjy_commission = day_zjy_commission
                    session.add(existing_day)
                    session.commit()


@router.post("/get_day_income")
def get_day_income(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    today_time = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " 00:00:00"
    today_ts = state.infra_client.turn_ts_to_time(today_time)
    is_update = 0

    if now - state.get_day_income_ts > 300 or state.get_day_income_today_ts != today_ts:
        _update_day_income(state)
        is_update = 1
        state.get_day_income_today_ts = today_ts
        state.get_day_income_ts = now
        with state.infra_client.get_session() as session:
            day_income_data = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.asc())
            ).all()
        state.day_income_data = []
        for item in day_income_data:
            if state.infra_client.turn_ts_to_time(item.day_begin_time) != today_ts:
                state.day_income_data.append({
                    "allNetProfit": 0,
                    "dayBeginTime": item.day_begin_time,
                    "dayEndTime": item.day_end_time,
                    "binanceCommission": item.binance_commission,
                    "netProfit": item.pnl + item.binance_commission,
                    "profit": item.pnl,
                    "zjyCommission": item.zjy_commission,
                })

    if state.infra_client.turn_ts_to_time(state.day_income_data[len(state.day_income_data) - 1]["dayBeginTime"]) != today_ts:
        state.day_income_data.append({
            "allNetProfit": 0,
            "dayBeginTime": state.infra_client.turn_ts_to_time(today_ts),
            "dayEndTime": state.infra_client.turn_ts_to_time(today_ts + 86400),
            "binanceCommission": state.income_obj["today"]["c"],
            "netProfit": state.income_obj["today"]["c"] + state.income_obj["today"]["p"],
            "profit": state.income_obj["today"]["p"],
            "zjyCommission": state.income_obj["today"]["s"],
        })
    else:
        state.day_income_data[len(state.day_income_data) - 1] = {
            "allNetProfit": 0,
            "dayBeginTime": state.infra_client.turn_ts_to_time(today_ts),
            "dayEndTime": state.infra_client.turn_ts_to_time(today_ts + 86400),
            "binanceCommission": state.income_obj["today"]["c"],
            "netProfit": state.income_obj["today"]["c"] + state.income_obj["today"]["p"],
            "profit": state.income_obj["today"]["p"],
            "zjyCommission": state.income_obj["today"]["s"],
        }

    return json.loads(json_dumps({"s": "ok", "d": state.day_income_data, "u": is_update}))


@router.post("/r")
def record_income(request: Request, apiKey: str = Form()):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.last_record_ts >= 9:
        if now - state.last_record_ts >= 300 or (not state.record_lock):
            state.record_lock = True
            state.last_record_ts = now
            state.update_api_obj(apiKey)

            with state.infra_client.get_session() as session:
                last_binance_ts_data = session.exec(
                    select(Income)
                    .where(Income.api_key == apiKey)
                    .order_by(Income.id.desc())
                    .limit(100)
                ).all()

            last_binance_ts = 0
            if len(last_binance_ts_data) > 0:
                last_binance_ts = last_binance_ts_data[0].binance_ts

            result = []
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)
            except Exception:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)

            result.sort(key=lambda elem: float(elem["time"]), reverse=False)
            bnb_price = get_future_now_price_by_depth("BNBUSDT")

            for i in range(len(result)):
                trade_id = str(result[i]['tradeId'])
                binance_ts = str(result[i]['time'])
                income_type = str(result[i]['incomeType'])
                income = str(result[i]['income'])
                asset = str(result[i]['asset'])
                sym = str(result[i]['symbol'])

                if income_type in ("COMMISSION", "REALIZED_PNL"):
                    is_exit = False
                    for b in range(len(last_binance_ts_data)):
                        if (
                            int(result[i]['time']) < last_binance_ts
                            or (
                                str(int(last_binance_ts_data[b].binance_ts)) == str(int(binance_ts))
                                and str(last_binance_ts_data[b].income_type) == str(income_type)
                                and format(float(last_binance_ts_data[b].income), '.8f') == format(float(income), '.8f')
                                and str(last_binance_ts_data[b].asset) == str(asset)
                                and str(last_binance_ts_data[b].trade_id) == str(trade_id)
                            )
                        ):
                            is_exit = True
                    if not is_exit:
                        commission = 0
                        if income_type == "COMMISSION":
                            if asset == "BNB":
                                commission = abs(float(income) * bnb_price * 0.1) if float(income) < 0 else abs(float(income) * bnb_price * 0.05)
                            else:
                                commission = abs(float(income) * 0.1) if float(income) < 0 else abs(float(income) * 0.05)

                        with state.infra_client.get_session() as session:
                            new_income = Income(
                                access_token=str(apiKey),
                                api_key=str(apiKey),
                                income_type=str(income_type),
                                income=decimal.Decimal(str(income)),
                                asset=str(asset),
                                trade_id=trade_id,
                                binance_ts=int(binance_ts),
                                symbol=sym,
                                bnb_price=decimal.Decimal(str(bnb_price)),
                                commission=decimal.Decimal(str(commission)),
                            )
                            session.add(new_income)
                            session.commit()
            state.record_lock = False
    return {"s": "ok"}


@router.post("/get_invest_percent")
def get_invest_percent():
    invest_percent_obj_arr = [
        {'name': '吴钊庆', 'time': '2023-05-19 14:59:00', 'percent': 12.206461839330702, 'initValue': 2800, 'assetsWhileJoin': 20138.67, 'investType': 'longs'},
        {'name': '一零二四', 'time': '2023-05-19 13:36:00', 'percent': 21.81179905448812, 'initValue': 5000, 'assetsWhileJoin': 15125.24, 'investType': 'longs'},
        {'name': '李', 'time': '2023-05-16 21:52:00', 'percent': 8.808005636839024, 'initValue': 2000, 'assetsWhileJoin': 12982.22, 'investType': 'longs'},
        {'name': 'michael', 'time': '2023-05-12 20:28:00', 'percent': 52.16531441742779, 'initValue': 10000, 'assetsWhileJoin': 959, 'investType': 'longs'},
        {'name': 'ming', 'time': '2023-05-09 00:00:00', 'percent': 5.008419051914373, 'initValue': 750, 'assetsWhileJoin': 0, 'investType': 'longs'},
    ]
    for item in invest_percent_obj_arr:
        item["percent"] = int(item["percent"] * 10000) / 10000
    return {"s": "ok", "t": int(time.time()), "r": invest_percent_obj_arr}
