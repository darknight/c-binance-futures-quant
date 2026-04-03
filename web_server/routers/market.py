import json
import time

import requests
from fastapi import APIRouter, Form, Request

from web_server.binance_helpers import get_kline

router = APIRouter()


@router.post("/get_depth")
def get_depth(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.depth_update_ts > 100:
        state.depth_update_ts = now
        url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=50"
        binance_response = requests.request("GET", url, timeout=(0.5, 0.5)).json()
        state.last_binance_response_obj = binance_response

    return {
        "s": "ok",
        "r": state.last_binance_response_obj,
        "i": symbol,
        "p": state.price_decimal_amount_obj[symbol],
        "a": state.amount_decimal_amount_obj[symbol],
    }


@router.post("/get_one_min_select_kline")
def get_one_min_select_kline(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.one_min_update_ts >= 100:
        state.one_min_update_ts = now
        kline_arr = get_kline(symbol, "1m", 3)
        state.one_min_kline = kline_arr
    return {"s": "ok", "k": state.one_min_kline}
