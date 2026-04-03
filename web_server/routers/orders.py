import json
import time

from fastapi import APIRouter, Form, Request

from binance_f.requestclient import RequestClient
from binance_f.model.constant import *

router = APIRouter()


@router.post("/change_leverage")
def change_leverage(request: Request, symbol: str = Form(), leverage: int = Form(), apiKey: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.change_initial_leverage(symbol, leverage)
    result = json.loads(result)
    return {"s": "ok", "result": result}


@router.post("/cancel_orders")
def cancel_orders(request: Request, apiKey: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    result = {}
    try:
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
    except Exception as e:
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
        print(e)
    return {"s": "ok"}


@router.post("/cancel_order")
def cancel_order(request: Request, apiKey: str = Form(), symbol: str = Form(), clientOrderId: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.cancel_order(symbol=symbol, orderId=clientOrderId)
    return {"s": "ok"}


@router.post("/get_all_open_orders")
def get_all_open_orders(key: str = Form(), secret: str = Form()):
    request_client = RequestClient(api_key=key, secret_key=secret)
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/cancel_binance_orders")
def cancel_binance_orders(request: Request, key: str = Form(), secret: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    need_cancel = True
    if symbol in state.symbol_cancel_orders_ts_obj:
        if now - state.symbol_cancel_orders_ts_obj[symbol] <= 3000:
            need_cancel = False

    if need_cancel:
        for _ in range(3):
            try:
                request_client = RequestClient(api_key=key, secret_key=secret)
                result = request_client.cancel_all_orders(symbol=symbol)
            except Exception as e:
                print(e)
        state.symbol_cancel_orders_ts_obj[symbol] = now

    return {"s": "ok"}


@router.post("/cancel_binance_order")
def cancel_binance_order(
    request: Request,
    key: str = Form(),
    secret: str = Form(),
    symbol: str = Form(),
    clientOrderId: str = Form(),
):
    state = request.app.state.app_state
    for attempt in range(3):
        try:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.cancel_order(symbol=symbol, orderId=clientOrderId)
            break
        except Exception as e:
            if attempt == 2:
                state.infra_client.send_notify_limit_one_min(
                    f"【cancel order error】，{key},{symbol},{clientOrderId},{e}"
                )
            print(e)
    return {"s": "ok"}


@router.post("/get_commission_rate")
def get_commission_rate(key: str = Form(), secret: str = Form(), symbol: str = Form()):
    request_client = RequestClient(api_key=key, secret_key=secret)
    result = request_client.get_commission_rate(symbol=symbol)
    result = json.loads(result)
    return {"s": "ok", "d": result}
