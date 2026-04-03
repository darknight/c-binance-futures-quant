import json
import time

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from binance_f.requestclient import RequestClient
from web_server.binance_helpers import get_spot_now_price_by_depth
from app.models.trade_server_status import TradeServerStatus
from app.models.machine_status import MachineStatus, TradeMachineStatus

router = APIRouter()


def _update_trade_server_status_data(state):
    """Refresh trade server status cache."""
    now = int(time.time())
    if now - state.update_trade_server_status_data_ts > 5:
        state.update_trade_server_status_data_ts = now
        with state.infra_client.get_session() as session:
            rows = session.exec(select(TradeServerStatus)).all()
        state.trade_server_status_data = []
        for item in rows:
            extra_para = json.loads(item.extra_para) if item.extra_para else {}
            state.trade_server_status_data.append({
                "extraPara": extra_para,
                "runInfo": json.loads(item.run_info) if item.run_info else {},
                "symbol": item.symbol,
                "privateIP": item.private_ip,
                "name": item.name,
                "mySymbol": item.my_symbol,
                "updateTs": item.update_ts,
                "updateTime": item.update_time,
                "customizeDangerousData": extra_para,
            })


@router.post("/ping")
def ping(
    request: Request,
    apiKey: str = Form(),
    apiIndex: int = Form(),
    timestamp: int = Form(),
    autoBuyBnbConfigArr: str = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    auto_buy_config = json.loads(autoBuyBnbConfigArr)
    auto_buy_bnb = auto_buy_config[2]
    begin_min_bnb_money = auto_buy_config[0]
    buy_bnb_money = auto_buy_config[1]

    state.update_api_obj(apiKey)
    now = int(time.time() * 1000)

    # getBinanceAccountInfo logic
    buy_bnb_result = False
    if now - state.account_info_update_ts > 60000:
        positions_arr = []
        assets_arr = []
        try:
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            result = request_client.get_account_information()
            result = json.loads(result)
            for i in range(len(result["positions"])):
                if float(result["positions"][i]["positionAmt"]) != 0:
                    positions_arr.append(result["positions"][i])
            assets_arr = result["assets"]
            bnb_amount = -1
            usdt_amount = -1
            busd_amount = -1
            for i in range(len(assets_arr)):
                if assets_arr[i]['asset'] == "BNB":
                    bnb_amount = float(assets_arr[i]['marginBalance'])
                if assets_arr[i]['asset'] == "USDT":
                    usdt_amount = float(assets_arr[i]['marginBalance'])
                if assets_arr[i]['asset'] == "BUSD":
                    busd_amount = float(assets_arr[i]['marginBalance'])
            state.bnb_price = get_spot_now_price_by_depth("BNBUSDT")
            # Auto BNB buy logic omitted for safety — preserved in trading router's _buy_bnb
            state.position_arr[apiIndex] = positions_arr
            state.assets_arr[apiIndex] = assets_arr
        except Exception as e:
            print(e)
        state.account_info_update_ts = now

    return {
        "s": "ok",
        "p": state.position_arr,
        "t": state.assets_arr,
        "r": buy_bnb_result,
        "n": now,
        "b": state.bnb_price,
        "l": timestamp,
    }


@router.post("/check_maker_server_in_data")
def check_maker_server_in_data(
    request: Request,
    name: str = Form(),
    privateIP: str = Form(),
    symbol: str = Form(),
    mySymbol: str = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            extra_para = {"customizeDangerous": 0}
            new_row = TradeServerStatus(
                private_ip=privateIP,
                name=name,
                extra_para=json.dumps(extra_para),
                symbol=symbol,
                my_symbol=mySymbol,
            )
            session.add(new_row)
            session.commit()
    return {"s": "ok"}


@router.post("/update_maker_server_run_info")
def update_maker_server_run_info(
    request: Request,
    privateIP: str = Form(),
    dangerousClass: str = Form(),
    dangerousName: str = Form(),
    direction: str = Form(),
    longsOnceTradeValue: float = Form(),
    shortsOnceTradeValue: float = Form(),
    longsBollTimeAmount: float = Form(),
    shortsBollTimeAmount: float = Form(),
    positionValue: float = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    run_info = {
        "dangerousClass": dangerousClass,
        "dangerousName": dangerousName,
        "longsOnceTradeValue": longsOnceTradeValue,
        "shortsOnceTradeValue": shortsOnceTradeValue,
        "longsBollTimeAmount": longsBollTimeAmount,
        "shortsBollTimeAmount": shortsBollTimeAmount,
        "positionValue": positionValue,
        "direction": direction,
    }
    now = int(time.time())
    with state.infra_client.get_session() as session:
        db_row = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).first()
        if db_row is not None:
            db_row.run_info = json.dumps(run_info)
            db_row.update_ts = now
            db_row.update_time = state.infra_client.turn_ts_to_time(now)
            session.add(db_row)
            session.commit()

    _update_trade_server_status_data(state)
    customize_dangerous_data = {"customizeDangerous": 0}
    for a in range(len(state.trade_server_status_data)):
        if state.trade_server_status_data[a]["privateIP"] == privateIP:
            customize_dangerous_data = state.trade_server_status_data[a]["customizeDangerousData"]
            break

    return {"s": "ok", "customizeDangerous": customize_dangerous_data["customizeDangerous"]}


@router.post("/get_customize_dangerous")
def get_customize_dangerous(request: Request):
    state = request.app.state.app_state
    SYMBOL_ARR = ["ETHUSDT", "BTCUSDT"]
    now = int(time.time())
    _update_trade_server_status_data(state)

    if now - state.customize_dangerous_data_arr_update_ts > 5:
        state.customize_dangerous_data_arr_update_ts = now
        result = []
        for sym in SYMBOL_ARR:
            for item in state.trade_server_status_data:
                if item["symbol"] == sym:
                    result.append({
                        "customizeDangerous": item["customizeDangerousData"]["customizeDangerous"],
                        "dangerousName": item["runInfo"]["dangerousName"],
                        "dangerousClass": item["runInfo"]["dangerousClass"],
                        "symbol": item["symbol"],
                    })
        state.customize_dangerous_data_arr = result

    return {"s": "ok", "customizeDangerousDataArr": state.customize_dangerous_data_arr}


@router.post("/update_customize_dangerous")
def update_customize_dangerous(
    request: Request,
    customizeDangerous: int = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    extra_info = json.dumps({"customizeDangerous": customizeDangerous})
    with state.infra_client.get_session() as session:
        if symbol == "all":
            rows = session.exec(select(TradeServerStatus)).all()
        else:
            rows = session.exec(
                select(TradeServerStatus).where(TradeServerStatus.symbol == symbol)
            ).all()
        for row in rows:
            row.extra_para = extra_info
            session.add(row)
        session.commit()
    return {"s": "ok"}


@router.post("/update_machine_status")
def update_machine_status(request: Request, privateIP: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    update_ts = int(time.time())
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(MachineStatus).where(MachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = MachineStatus(private_ip=privateIP, insert_ts=update_ts, update_ts=update_ts, symbol=symbol)
            session.add(row)
        else:
            existing[0].update_ts = update_ts
            session.add(existing[0])
        session.commit()
    return {"s": "ok"}


@router.post("/update_trade_status")
def update_trade_status(request: Request, privateIP: str = Form(), status: str = Form(), runTime: str = Form()):
    state = request.app.state.app_state
    update_ts = int(time.time())
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(TradeMachineStatus).where(TradeMachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = TradeMachineStatus(private_ip=privateIP, insert_ts=update_ts, update_ts=update_ts, status=status)
            session.add(row)
        else:
            existing[0].status = status
            existing[0].update_ts = update_ts
            existing[0].run_time = int(runTime)
            session.add(existing[0])
        session.commit()
    return {"s": "ok"}


@router.post("/get_trade_status")
def get_trade_status(request: Request):
    state = request.app.state.app_state
    from sqlalchemy import asc as _asc
    now = int(time.time())
    if now - state.update_trade_machine_status_data_ts > 60:
        state.update_trade_machine_status_data_ts = now
        with state.infra_client.get_session() as session:
            state.trade_machine_status_data = session.exec(
                select(TradeMachineStatus).order_by(_asc(TradeMachineStatus.update_ts))
            ).all()
        all_run_time = 0
        for item in state.trade_machine_status_data:
            all_run_time += (item.run_time or 0)
        if len(state.trade_machine_status_data) > 0:
            state.average_run_time = int(all_run_time / len(state.trade_machine_status_data))

    if len(state.trade_machine_status_data) > 0:
        return {
            "s": "ok",
            "updateTs": state.trade_machine_status_data[0].update_ts,
            "status": state.trade_machine_status_data[0].status,
            "runTime": state.average_run_time,
        }
    return {"s": "ok", "updateTs": 0, "status": "", "runTime": 0}
