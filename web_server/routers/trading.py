import _thread
import decimal
import json
import math
import time
import traceback

from fastapi import APIRouter, Form, Request

from binance_f.requestclient import RequestClient
from binance_f.model.constant import *
from web_server.binance_helpers import (
    get_future_depth_by_symbol,
    get_pole_price,
    get_spot_now_price_by_depth,
    get_stop_loss_price_by_time,
    get_stop_profit_price_by_time,
)

router = APIRouter()


def _buy_bnb(state, api_key, buy_bnb_amount, bnb_price, asset_type):
    """Buy BNB via spot, transfer to futures. Throttled to once per 60s."""
    now = int(time.time())
    symbol = "BNB" + asset_type
    print("buyBNB")
    if now - state.buy_bnb_ts > 60:
        state.buy_bnb_ts = now
        from binance_f.requestclient import SpotRequestClient
        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("UMFUTURE_MAIN", asset_type, bnb_price * buy_bnb_amount * 1.05)
        result = json.loads(result)

        amount = buy_bnb_amount
        amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (amount))
        bet_price = decimal.Decimal("%.1f" % (bnb_price * 1.005))

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.post_order(
            symbol=symbol, quantity=amount, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
            price=bet_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        time.sleep(1)

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.get_account_information()
        result = json.loads(result)
        result = result['balances']
        bnb_balance = 0
        usdt_balance = 0
        for i in range(len(result)):
            if result[i]['asset'] == asset_type:
                usdt_balance = float(result[i]['free'])
            if result[i]['asset'] == "BNB":
                bnb_balance = float(result[i]['free'])

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("MAIN_UMFUTURE", "BNB", bnb_balance)
        result = json.loads(result)
        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("MAIN_UMFUTURE", asset_type, usdt_balance)
        result = json.loads(result)
        return True
    return False


def _take_longs_order(state, longs_price, quantity, trade_type, symbol, key, secret):
    """Place a limit long order."""
    longs_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (longs_price)))
    oid = state.next_order_id()
    new_client_order_id = f"{state.order_id_symbol}_{trade_type}_{oid}"
    result = {}
    try:
        request_client = RequestClient(api_key=key, secret_key=secret)
        result = request_client.post_order(
            newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
            quantity=quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
            price=longs_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        if "code" in result and result['code'] == -1001:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
                price=longs_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
            result = json.loads(result)
        if "code" in result and result['code'] not in (-5022, -1001):
            _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"longs order error:{result},{quantity}",))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"longsM:{e}",))
    return result


def _take_shorts_order(state, shorts_price, quantity, trade_type, symbol, key, secret):
    """Place a limit short order."""
    shorts_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (shorts_price)))
    oid = state.next_order_id()
    new_client_order_id = f"{state.order_id_symbol}_{trade_type}_{oid}"
    result = {}
    try:
        request_client = RequestClient(api_key=key, secret_key=secret)
        result = request_client.post_order(
            newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
            quantity=quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
            price=shorts_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        if "code" in result and result['code'] == -1001:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
                price=shorts_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
            result = json.loads(result)
        if "code" in result and result['code'] not in (-5022, -1001, -2022):
            _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"shorts order error:{result},{quantity}",))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"shortsM:{e}",))
    return result


@router.post("/open_position")
def open_position(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    money: float = Form(),
    tradeType: str = Form(),
    nowPrice: float = Form(),
    paraArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    para_arr = json.loads(paraArr)
    market_max_size = state.market_max_size_obj[symbol]
    result_arr = []
    trade_coin_quantity = 0

    def _timeout_resp():
        return {"s": "timeout", "t": tradeType, "i": symbol}

    def _data_error_resp():
        return {"s": "dataError", "t": tradeType, "i": symbol}

    if tradeType == "openLongsByMarket":
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"marketOpenLongs_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.MARKET,
                positionSide="BOTH", price="0",
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType == "openShortsByMarket":
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"marketOpenShorts_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.MARKET,
                positionSide="BOTH", price="0",
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByDepth", "openShortsByDepth"):
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()
        depth_type = para_arr[0]
        price = 0
        if depth_type == "mid":
            price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "buy":
            price = float(depth_obj["bids"][int(para_arr[1]) - 1][0])
        elif depth_type == "sell":
            price = float(depth_obj["asks"][int(para_arr[1]) - 1][0])

        price = price * float(para_arr[2])
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        new_client_order_id = f"depthOpenLongs_s{oid}" if tradeType == "openLongsByDepth" else f"depthOpenShorts_s{oid}"
        time_in_force = TimeInForce.GTX if para_arr[4] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.BUY if tradeType == "openLongsByDepth" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=time_in_force,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByLeft", "openShortsByLeft"):
        mins = int(para_arr[0])
        price_index = float(para_arr[1])
        price_arr = get_pole_price(symbol, mins)
        high_price = price_arr[0]
        if high_price == 0:
            return _data_error_resp()
        low_price = price_arr[1]
        price = low_price * price_index if tradeType == "openLongsByLeft" else high_price * price_index

        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        new_client_order_id = f"leftOpenLongs_s{oid}" if tradeType == "openLongsByLeft" else f"leftOpenShortss_s{oid}"
        order_side = OrderSide.BUY if tradeType == "openLongsByLeft" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByRight", "openShortsByRight"):
        mins = int(para_arr[0])
        price_index = float(para_arr[1])
        price_arr = get_pole_price(symbol, mins)
        high_price = price_arr[0]
        if high_price == 0:
            return _data_error_resp()
        low_price = price_arr[1]
        if tradeType == "openLongsByRight":
            price = high_price * price_index
            stop_price = high_price
        else:
            price = low_price * price_index
            stop_price = low_price

        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / stop_price))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        new_client_order_id = f"rightOpenLongs_s{oid}" if tradeType == "openLongsByRight" else f"rightOpenShorts_s{oid}"
        order_side = OrderSide.BUY if tradeType == "openLongsByRight" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_auto_order_with_price(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.STOP,
                stopPrice=stop_price, price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByBatch", "openShortsByBatch"):
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()
        depth_type = para_arr[0]
        basic_price = 0
        if depth_type == "mid":
            basic_price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "buy":
            basic_price = float(depth_obj["bids"][int(para_arr[1]) - 1][0])
        elif depth_type == "sell":
            basic_price = float(depth_obj["asks"][int(para_arr[1]) - 1][0])

        basic_price = basic_price * float(para_arr[2])
        add_price_percent = float(para_arr[4])
        order_count = int(para_arr[5])
        price_arr = []
        if add_price_percent == 0:
            basic_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (basic_price)))
            for i in range(order_count):
                if tradeType == "openLongsByBatch":
                    price_arr.append(basic_price - state.price_tick_obj[symbol] * i)
                else:
                    price_arr.append(basic_price + state.price_tick_obj[symbol] * i)
        else:
            for i in range(order_count):
                if tradeType == "openLongsByBatch":
                    price_arr.append(basic_price * (1 - add_price_percent * i / 100))
                else:
                    price_arr.append(basic_price * (1 + add_price_percent * i / 100))

        time_in_force = TimeInForce.GTX if para_arr[6] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.BUY if tradeType == "openLongsByBatch" else OrderSide.SELL
        for i in range(len(price_arr)):
            price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price_arr[i])))
            coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice / order_count))
            if coin_quantity > market_max_size:
                coin_quantity = market_max_size
                trade_coin_quantity = market_max_size

            oid = state.next_order_id()
            new_client_order_id = f"depthOpenLongs_s{oid}" if tradeType == "openLongsByBatch" else f"depthOpenShorts_s{oid}"

            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                    price=price, positionSide="BOTH", timeInForce=time_in_force,
                )
            except Exception:
                return _timeout_resp()
            result = json.loads(result)
            result_arr.append(result)

    elif tradeType == "openLongsByPrice":
        price = float(para_arr[0])
        client_id_prefix = "rightOpenLongs" if price > nowPrice else "leftOpenLongs"
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"{client_id_prefix}_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            if client_id_prefix == "leftOpenLongs":
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
                    positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC,
                )
            else:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.STOP_MARKET,
                    stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType == "openShortsByPrice":
        price = float(para_arr[0])
        client_id_prefix = "rightOpenShorts" if price < nowPrice else "leftOpenShorts"
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"{client_id_prefix}_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            if client_id_prefix == "leftOpenShorts":
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
                    positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC,
                )
            else:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.STOP_MARKET,
                    stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
        except Exception as e:
            print(e)
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    return {
        "s": "ok",
        "resultArr": result_arr,
        "tradeCoinQuantity": trade_coin_quantity,
        "money": money,
        "symbol": symbol,
        "tradeType": tradeType,
    }


@router.post("/close_position")
def close_position(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    money: float = Form(),
    tradeType: str = Form(),
    nowPrice: float = Form(),
    direction: str = Form(),
    paraArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    para_arr = json.loads(paraArr)
    market_max_size = state.market_max_size_obj[symbol]
    trade_coin_quantity = 0
    result_arr = []

    def _timeout_resp():
        return {"s": "timeout", "t": tradeType, "i": symbol}

    def _data_error_resp():
        return {"s": "dataError", "t": tradeType, "i": symbol}

    if tradeType == "selectCoinCloseByMarket":
        oid = state.next_order_id()
        new_client_order_id = f"marketCloseLongs_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=market_max_size, side=order_side, ordertype=OrderType.MARKET,
                price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result_arr.append(json.loads(result))

    elif tradeType == "selectCoinCloseByDepth":
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()

        money = money * float(para_arr[0])
        depth_type = para_arr[1]
        depth_number = int(para_arr[2]) - 1
        price = 0
        if depth_type == "mid":
            price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "reverse":
            price = float(depth_obj["bids"][depth_number][0]) if direction == "longs" else float(depth_obj["asks"][depth_number][0])
        elif depth_type == "positive":
            price = float(depth_obj["asks"][depth_number][0]) if direction == "longs" else float(depth_obj["bids"][depth_number][0])

        price_index = float(para_arr[3]) if direction == "longs" else float(para_arr[4])
        price = price * price_index
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        coin_quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        new_client_order_id = f"depthLongsClose_s{oid}" if direction == "longs" else f"depthShortsClose_s{oid}"
        time_in_force = TimeInForce.GTX if para_arr[5] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=time_in_force,
            )
        except Exception:
            return _timeout_resp()
        result_arr.append(json.loads(result))

    elif tradeType == "selectCoinCloseByBatch":
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()

        money = money * float(para_arr[0])
        depth_type = para_arr[1]
        depth_number = int(para_arr[2]) - 1
        basic_price = 0
        if depth_type == "mid":
            basic_price = (float(depth_obj["asks"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "reverse":
            basic_price = float(depth_obj["bids"][depth_number][0]) if direction == "longs" else float(depth_obj["asks"][depth_number][0])
        elif depth_type == "positive":
            basic_price = float(depth_obj["asks"][depth_number][0]) if direction == "longs" else float(depth_obj["bids"][depth_number][0])

        price_index = float(para_arr[3]) if direction == "longs" else float(para_arr[4])
        basic_price = basic_price * price_index
        add_price_percent = float(para_arr[5])
        order_count = int(para_arr[6])
        price_arr = []
        if add_price_percent == 0:
            basic_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (basic_price)))
            for i in range(order_count):
                if direction == "longs":
                    price_arr.append(basic_price + state.price_tick_obj[symbol] * i)
                else:
                    price_arr.append(basic_price - state.price_tick_obj[symbol] * i)
        else:
            for i in range(order_count):
                if direction == "longs":
                    price_arr.append(basic_price * (1 + add_price_percent * i / 100))
                else:
                    price_arr.append(basic_price * (1 - add_price_percent * i / 100))

        time_in_force = TimeInForce.GTX if para_arr[7] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY
        for i in range(len(price_arr)):
            price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price_arr[i])))
            coin_quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice / order_count)))
            if coin_quantity > market_max_size:
                coin_quantity = market_max_size
                trade_coin_quantity = market_max_size

            oid = state.next_order_id()
            new_client_order_id = f"batchLongsClose_s{oid}" if direction == "longs" else f"batchShortsClose_s{oid}"

            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                    price=price, positionSide="BOTH", timeInForce=time_in_force,
                )
            except Exception:
                return _timeout_resp()
            result_arr.append(json.loads(result))

    return {
        "s": "ok",
        "resultArr": result_arr,
        "tradeCoinQuantity": trade_coin_quantity,
        "marketMaxSize": market_max_size,
        "symbol": symbol,
        "tradeType": tradeType,
    }


@router.post("/stop_loss_batch")
def stop_loss_batch(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    positionDirection: str = Form(),
    stopLossPriceArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_loss_price_arr = json.loads(stopLossPriceArr)
    market_max_size = state.market_max_size_obj[symbol]
    stop_loss_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_loss_price_arr)))

    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    some_order_timeout = False

    for i in range(len(stop_loss_price_arr)):
        stop_loss_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_loss_price_arr[i]))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        if i == len(stop_loss_price_arr) - 1:
            remaining = coinAmount - float(decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_loss_price_arr)))) * (len(stop_loss_price_arr) - 1)
            stop_loss_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (remaining))
        try:
            result = request_client.post_auto_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=stop_loss_coin_quantity, side=position_side, ordertype=OrderType.STOP_MARKET,
                stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            some_order_timeout = True
        result = json.loads(result)
        order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "someOrderTimeOut": some_order_timeout}


@router.post("/stop_loss_once")
def stop_loss_once(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    stopLossType: str = Form(),
    stopLossParaArr: str = Form(),
    positionDirection: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_loss_para_arr = json.loads(stopLossParaArr)
    market_max_size = state.market_max_size_obj[symbol]

    stop_loss_price = 0
    if stopLossType == "time":
        time_index = stop_loss_para_arr[1]
        stop_loss_price = get_stop_loss_price_by_time(symbol, stop_loss_para_arr[0], positionDirection) * time_index
    elif stopLossType == "price":
        stop_loss_price = float(stop_loss_para_arr[0])

    stop_loss_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_loss_price))
    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    order_count = math.ceil(coinAmount / market_max_size)

    if order_count > 10:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    if order_count == 1:
        coin_amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_auto_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_amount, side=position_side, ordertype=OrderType.STOP_MARKET,
                stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return {"s": "timeout", "t": stopLossType, "i": symbol}
        result = json.loads(result)
        order_result_arr.append(result)
    else:
        for i in range(order_count):
            oid = state.next_order_id()
            new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=market_max_size, side=position_side, ordertype=OrderType.STOP_MARKET,
                    stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
            except Exception:
                return {"s": "timeout", "t": stopLossType, "i": symbol}
            result = json.loads(result)
            order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "stopLossType": stopLossType}


@router.post("/stop_profit_batch")
def stop_profit_batch(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    positionDirection: str = Form(),
    stopProfitPriceArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_profit_price_arr = json.loads(stopProfitPriceArr)
    market_max_size = state.market_max_size_obj[symbol]

    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stop_profit_order_id_arr = []
    for i in range(len(result)):
        client_order_id = result[i]['clientOrderId']
        order_type_symbol = client_order_id.split("_")[0]
        if order_type_symbol in ("shortsStopProfit", "longsStopProfit"):
            stop_profit_order_id_arr.append(client_order_id)

    for cid in stop_profit_order_id_arr:
        for _ in range(2):
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                request_client.cancel_order(symbol=symbol, orderId=cid)
                break
            except Exception as e:
                print(e)

    stop_profit_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_profit_price_arr)))
    if stop_profit_coin_quantity > market_max_size:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    some_order_timeout = False

    for i in range(len(stop_profit_price_arr)):
        stop_profit_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_profit_price_arr[i]))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        if i == len(stop_profit_price_arr) - 1:
            remaining = coinAmount - float(decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_profit_price_arr)))) * (len(stop_profit_price_arr) - 1)
            stop_profit_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (remaining))
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=stop_profit_coin_quantity, side=position_side, ordertype=OrderType.LIMIT,
                price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
            )
        except Exception:
            some_order_timeout = True
        result = json.loads(result)
        order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "someOrderTimeOut": some_order_timeout}


@router.post("/stop_profit_once")
def stop_profit_once(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    stopProfitType: str = Form(),
    stopProfitParaArr: str = Form(),
    positionDirection: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_profit_para_arr = json.loads(stopProfitParaArr)
    market_max_size = state.market_max_size_obj[symbol]

    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stop_profit_order_id_arr = []
    for i in range(len(result)):
        client_order_id = result[i]['clientOrderId']
        order_type_symbol = client_order_id.split("_")[0]
        if order_type_symbol in ("shortsStopProfit", "longsStopProfit"):
            stop_profit_order_id_arr.append(client_order_id)

    for cid in stop_profit_order_id_arr:
        for _ in range(2):
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                request_client.cancel_order(symbol=symbol, orderId=cid)
                break
            except Exception as e:
                print(e)

    stop_profit_price = 0
    if stopProfitType == "time":
        time_index = stop_profit_para_arr[1]
        stop_profit_price = get_stop_profit_price_by_time(symbol, stop_profit_para_arr[0], positionDirection) * time_index
    elif stopProfitType == "price":
        stop_profit_price = float(stop_profit_para_arr[0])

    stop_profit_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_profit_price))
    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    order_count = math.ceil(coinAmount / market_max_size)

    if order_count > 10:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    if order_count == 1:
        coin_amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_amount, side=position_side, ordertype=OrderType.LIMIT,
                price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
            )
        except Exception:
            return {"s": "timeout", "t": stopProfitType, "i": symbol}
        result = json.loads(result)
        order_result_arr.append(result)
    else:
        for i in range(order_count):
            oid = state.next_order_id()
            new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=market_max_size, side=position_side, ordertype=OrderType.LIMIT,
                    price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
                )
            except Exception:
                return {"s": "timeout", "t": stopProfitType, "i": symbol}
            result = json.loads(result)
            order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "stopProfitType": stopProfitType}


@router.post("/take_open")
def take_open(
    request: Request,
    key: str = Form(),
    secret: str = Form(),
    symbol: str = Form(),
    direction: str = Form(),
    price: float = Form(),
    openTime: int = Form(),
    positionValue: float = Form(),
    volMultiple: float = Form(),
):
    state = request.app.state.app_state
    try:
        now = int(time.time() * 1000)
        should_trade = (
            (positionValue == 0 and symbol in state.take_open_obj and now - state.take_open_obj[symbol]["ts"] > 60000 * 15)
            or (symbol in state.take_open_obj and state.take_open_obj[symbol]["status"] == "end")
            or (symbol in state.take_open_obj and openTime > state.take_open_obj[symbol]["openTime"])
            or (symbol not in state.take_open_obj)
        )
        if should_trade:
            state.take_open_obj[symbol] = {"ts": now, "openTime": openTime, "status": "trading"}
            if direction == "longs":
                value = 100
                quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (value / price)))
                _take_longs_order(state, price, quantity, "T", symbol, key, secret)
                state.infra_client.send_notify_limit_one_min(f"{symbol} take longs")
            if direction == "shorts":
                value = 100
                quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (value / price)))
                _take_shorts_order(state, price, quantity, "T", symbol, key, secret)
                state.infra_client.send_notify_limit_one_min(f"{symbol} take shorts")
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
    return {"s": "ok"}


@router.post("/end_open")
def end_open(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    try:
        if symbol in state.take_open_obj and state.take_open_obj[symbol]["status"] != "end":
            state.take_open_obj[symbol]["status"] = "end"
            state.infra_client.send_notify_limit_one_min(f"{symbol} end trade")
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
    return {"s": "ok"}
