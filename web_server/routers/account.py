import json
import time
import datetime

import requests
from fastapi import APIRouter, Form, Request
from sqlalchemy import func
from sqlmodel import select

from binance_f.requestclient import RequestClient
from app.models.position_record import PositionRecord
from app.models.loss_limit_time import LossLimitTime
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_all_acount_info")
def get_all_acount_info(request: Request):
    state = request.app.state.app_state
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
    return {"s": "ok", "b": all_balance, "p": all_position, "t": int(time.time())}


@router.post("/get_all_open_orders_b")
def get_all_open_orders_b(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/get_position")
def get_position(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    positions_arr = []
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_account_information()
    result = json.loads(result)
    for i in range(len(result["positions"])):
        if float(result["positions"][i]["positionAmt"]) != 0:
            positions_arr.append(result["positions"][i])
    return {"s": "ok", "r": positions_arr, "t": int(time.time())}


@router.post("/get_trade_record")
def get_trade_record(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_account_trades(symbol)
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/get_second_open_position")
def get_second_open_position():
    BINANCE_API_KEY = "bJpPkJe9kW8USXKDQuP2WKeSVaEIOM5wKT7Uta1ir2wmlAxNHN9hwrZDhjJCYcEd"
    this_ip = "172.24.207.4"
    url = f"http://{this_ip}/{BINANCE_API_KEY[0:10]}.json"
    result = requests.request("GET", url, timeout=(0.5, 0.5)).json()
    return {"s": "ok", "t": int(time.time()), "r": result}


@router.post("/update_loss_limit_time")
def update_loss_limit_time(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now_time = state.infra_client.turn_ts_to_time(int(time.time()))
    now_time_str = str(now_time) if not isinstance(now_time, str) else now_time
    with state.infra_client.get_session() as session:
        row = session.exec(select(LossLimitTime).where(LossLimitTime.symbol == symbol)).first()
        if row:
            row.limit_time = now_time_str
            session.add(row)
            session.commit()
    # Refresh cache
    _get_loss_limit_time_data(state, True)
    return {"s": "ok", "t": int(time.time())}


def _get_loss_limit_time_data(state, force_update):
    """Refresh loss limit time cache."""
    now = int(time.time())
    if (now - state.get_loss_limit_time_data_ts > 60) or force_update:
        state.get_loss_limit_time_data_ts = now
        with state.infra_client.get_session() as session:
            loss_limit_time_data = session.exec(select(LossLimitTime)).all()
        state.loss_limit_time_data_arr = []
        for row in loss_limit_time_data:
            state.loss_limit_time_data_arr.append({
                "symbol": row.symbol,
                "limitTime": row.limit_time,
            })


def _update_binance_data(state):
    """Fetch ETH/BTC kline + all tickers."""
    now = int(time.time())
    if now - state.update_binance_data_ts >= 1:
        state.update_binance_data_ts = now
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=ETHUSDT&interval=1m&limit=99"
            eth_kline = requests.request("GET", url, timeout=(1, 1)).json()
            if len(eth_kline) == 99:
                state.eth_1m_kline_arr = eth_kline
        except Exception as e:
            print(e)
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=99"
            btc_kline = requests.request("GET", url, timeout=(1, 1)).json()
            if len(btc_kline) == 99:
                state.btc_1m_kline_arr = btc_kline
        except Exception as e:
            print(e)
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            tick_arr = requests.request("GET", url, timeout=(1, 1)).json()
            if len(tick_arr) > 100:
                state.tick_arr = tick_arr
        except Exception as e:
            print(e)


def _update_turn_price(state):
    """Update ETH/BTC turn price from position records."""
    now = int(time.time())
    if now - state.turn_price_update_ts > 60:
        state.turn_price_update_ts = now
        with state.infra_client.get_session() as session:
            for symbol_name, price_attr, ts_attr in [
                ("ETHUSDT", "eth_turn_price", "eth_turn_ts"),
                ("BTCUSDT", "btc_turn_price", "btc_turn_ts"),
            ]:
                latest = session.exec(
                    select(PositionRecord).where(PositionRecord.symbol == symbol_name).order_by(PositionRecord.id.desc()).limit(1)
                ).first()
                if latest:
                    position_amt = latest.position_amt or 0
                    if position_amt > 0:
                        last_turn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == symbol_name, PositionRecord.position_amt < 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                    else:
                        last_turn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == symbol_name, PositionRecord.position_amt > 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                    if last_turn:
                        setattr(state, price_attr, 0)
                        setattr(state, ts_attr, last_turn.ts)


def _update_trade_server_status_data(state):
    """Imported from status router logic — duplicated here to avoid circular imports."""
    from web_server.routers.status import _update_trade_server_status_data as _update
    _update(state)


@router.post("/get_watch_info")
def get_watch_info(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.watch_info_update_ts >= 60:
        state.watch_info_update_ts = now
        _update_binance_data(state)
        all_position_arr = []
        _update_trade_server_status_data(state)
        _update_turn_price(state)

        for key in state.new_api_obj:
            day_begin_balance_update_time = state.infra_client.turn_ts_to_day_time(now)
            if day_begin_balance_update_time != state.new_api_obj[key]["dayBeginBalaneUpdateTime"]:
                zero_point = state.infra_client.turn_ts_to_time(day_begin_balance_update_time)
                with state.infra_client.get_session() as session:
                    first_row = session.exec(
                        select(PositionRecord).where(PositionRecord.ts >= zero_point).order_by(PositionRecord.id.asc()).limit(1)
                    ).first()
                if first_row:
                    state.new_api_obj[key]["dayBeginBalane"] = first_row.balance
                    state.new_api_obj[key]["dayBeginBalaneUpdateTime"] = day_begin_balance_update_time

            this_ip = state.new_api_obj[key]["positionIP"]
            this_key = state.new_api_obj[key]["apiKey"]
            my_symbol = state.new_api_obj[key]["mySymbol"]
            day_begin_balance = state.new_api_obj[key]["dayBeginBalane"]
            symbol = state.new_api_obj[key]["symbol"]

            _get_loss_limit_time_data(state, False)
            this_loss_limit_time = ""
            for item in state.loss_limit_time_data_arr:
                if item["symbol"] == symbol:
                    this_loss_limit_time = item["limitTime"]
                    break
            if this_loss_limit_time == "":
                with state.infra_client.get_session() as session:
                    session.add(LossLimitTime(symbol=symbol, limit_time="2023-03-28 01:00:00"))
                    session.commit()
                _get_loss_limit_time_data(state, True)

            url = f"http://{this_ip}/{this_key[0:10]}.json"
            result = requests.request("GET", url, timeout=(0.25, 0.25)).json()
            account_balance_value = result["balance"]

            for a in range(len(result["positionArr"])):
                this_price = 0
                for b in range(len(state.tick_arr)):
                    if state.tick_arr[b]["symbol"] == result["positionArr"][a]["symbol"]:
                        this_price = float(state.tick_arr[b]["price"])
                result["positionArr"][a]["balance"] = account_balance_value
                result["positionArr"][a]["mySymbol"] = my_symbol
                if my_symbol == "OTHER":
                    result["positionArr"][a]["mySymbol"] = result["positionArr"][a]["symbol"] + "_BINANCE"
                result["positionArr"][a]["price"] = this_price
                result["positionArr"][a]["dayBeginBalane"] = day_begin_balance
                result["positionArr"][a]["updateTime"] = int(time.time() * 1000)
                result["positionArr"][a]["tradeType"] = str(result["positionArr"][a]["entryPrice"])[-1]
                result["positionArr"][a]["entryPrice"] = 0
                result["positionArr"][a]["unrealizedProfit"] = 0
                result["positionArr"][a]["profitPercent"] = 0
                all_position_arr.append(result["positionArr"][a])

        state.watch_info_obj = {
            "s": "ok",
            "balance": account_balance_value if state.new_api_obj else 0,
            "ethP": state.eth_turn_price,
            "btcP": state.btc_turn_price,
            "ethT": state.eth_turn_ts,
            "btcT": state.btc_turn_ts,
            "eth": state.eth_1m_kline_arr,
            "btc": state.btc_1m_kline_arr,
            "e": state.loss_limit_time_data_arr,
            "d": state.trade_server_status_data,
            "a": all_position_arr,
            "t": int(time.time()),
        }

    return json.loads(json_dumps(state.watch_info_obj))


@router.post("/get_one_day_rate")
def get_one_day_rate(request: Request):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.update_one_day_rate_ts >= 30 * 1000:
        binance_response = []
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            binance_response = requests.request("GET", url, timeout=(3, 3)).json()
            binance_response.sort(key=lambda elem: float(elem['quoteVolume']), reverse=True)
        except Exception as e:
            print(e)
        if len(binance_response) >= 100:
            state.symbol_data_obj = {}
            for i in range(len(binance_response)):
                vol_index = 1
                if i <= 15:
                    vol_index = 1.5
                elif i <= 30:
                    vol_index = 1.4
                elif i <= 45:
                    vol_index = 1.3
                elif i <= 60:
                    vol_index = 1.2
                elif i <= 75:
                    vol_index = 1.1
                state.symbol_data_obj[binance_response[i]["symbol"]] = {
                    "oneDayWave": int(state.infra_client.get_percent_num(
                        float(binance_response[i]["highPrice"]) - float(binance_response[i]["lowPrice"]),
                        float(binance_response[i]["lowPrice"]),
                    )),
                    "volRank": i,
                    "volIndex": vol_index,
                    "vol": float(binance_response[i]["quoteVolume"]),
                    "highPrice": float(binance_response[i]["highPrice"]),
                    "lowPrice": float(binance_response[i]["lowPrice"]),
                }
        state.update_one_day_rate_ts = now
    return {"s": "ok", "d": state.symbol_data_obj}
