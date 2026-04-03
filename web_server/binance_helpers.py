import json
import time
import requests
from datetime import datetime as _dt

from settings import settings


class UTCEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, _dt):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj):
    return json.dumps(obj, cls=UTCEncoder)


def update_symbol_info(state):
    """Fetch Binance exchange info and populate symbol precision data on state."""
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.request("GET", url, timeout=(3, 7)).json()
    symbols = response['symbols']
    for i in range(len(symbols)):
        this_instrument_id = symbols[i]['symbol']
        price_tick = 0
        price_decimal = ""
        amount_decimal = ""
        price_decimal_amount = ""
        amount_decimal_amount = ""
        for c in range(len(symbols[i]['filters'])):
            if symbols[i]['filters'][c]['filterType'] == "PRICE_FILTER":
                price_tick = float(symbols[i]['filters'][c]['tickSize'])
                this_decimal = 0
                init_para = 10
                for d in range(20):
                    this_decimal = this_decimal + 1
                    init_para = round(init_para / 10, 10)
                    if init_para == float(symbols[i]['filters'][c]['tickSize']):
                        break
                price_decimal = "%." + str(this_decimal - 1) + "f"
                price_decimal_amount = str(this_decimal - 1)
            if symbols[i]['filters'][c]['filterType'] == "LOT_SIZE":
                this_decimal = 0
                init_para = 10
                for d in range(20):
                    this_decimal = this_decimal + 1
                    init_para = round(init_para / 10, 10)
                    if init_para == float(symbols[i]['filters'][c]['stepSize']):
                        break
                amount_decimal = "%." + str(this_decimal - 1) + "f"
                amount_decimal_amount = str(this_decimal - 1)
            if symbols[i]['filters'][c]['filterType'] == "MARKET_LOT_SIZE":
                state.market_max_size_obj[this_instrument_id] = float(symbols[i]['filters'][c]['maxQty'])
                state.market_min_size_obj[this_instrument_id] = float(symbols[i]['filters'][c]['minQty'])
        state.price_decimal_obj[this_instrument_id] = price_decimal
        state.amount_decimal_obj[this_instrument_id] = amount_decimal
        state.price_tick_obj[this_instrument_id] = price_tick
        state.price_decimal_amount_obj[this_instrument_id] = price_decimal_amount
        if amount_decimal_amount != "":
            state.amount_decimal_amount_obj[this_instrument_id] = int(amount_decimal_amount)


def get_future_depth_by_symbol(symbol, limit):
    """Fetch futures order book depth with retry."""
    response = {}
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=50"
            response = requests.request("GET", url, timeout=timeout).json()
            return response
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return response


def get_kline(symbol, interval, limit):
    """Fetch kline data with retry."""
    kline_data_arr = []
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
            kline_data_arr = requests.request("GET", url, timeout=timeout).json()
            kline_data_arr.sort(key=lambda elem: float(elem[0]), reverse=False)
            return kline_data_arr
        except Exception as e:
            print(e)
    return kline_data_arr


def get_future_now_price_by_depth(symbol):
    """Get current futures mid-price from depth with retry."""
    now_price = 0
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=5"
            response = requests.request("GET", url, timeout=timeout).json()
            now_price = (float(response['asks'][0][0]) + float(response['bids'][0][0])) / 2
            return now_price
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return now_price


def get_spot_now_price_by_depth(symbol):
    """Get current spot mid-price from depth with retry."""
    now_price = 0
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://api.binance.com/api/v1/depth?symbol={symbol}&limit=5"
            response = requests.request("GET", url, timeout=timeout).json()
            now_price = (float(response['asks'][0][0]) + float(response['bids'][0][0])) / 2
            return now_price
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return now_price


def get_pole_price(symbol, mins):
    """Get high/low price over a time range using appropriate kline interval."""
    mins = int(mins)
    high_price = 0
    low_price = 99999999
    kline_arr = []
    if mins < 500:
        kline_arr = get_kline(symbol, "1m", mins)
    elif mins < 7500:
        kline_arr = get_kline(symbol, "15m", int(mins / 15))
    elif mins < 30000:
        kline_arr = get_kline(symbol, "1h", int(mins / 60))
    elif mins < 120000:
        kline_arr = get_kline(symbol, "4h", int(mins / 240))
    elif mins < 720000:
        kline_arr = get_kline(symbol, "1d", int(mins / 1440))

    for i in range(len(kline_arr)):
        if float(kline_arr[i][2]) > high_price:
            high_price = float(kline_arr[i][2])
        if float(kline_arr[i][3]) < low_price:
            low_price = float(kline_arr[i][3])
    return [high_price, low_price]


def get_stop_loss_price_by_time(symbol, stop_loss_para, position_direction):
    """Calculate stop loss price based on time window high/low."""
    price_arr = get_pole_price(symbol, int(stop_loss_para))
    if position_direction == "longs":
        return price_arr[1]
    if position_direction == "shorts":
        return price_arr[0]
    return 0


def get_stop_profit_price_by_time(symbol, stop_profit_para, position_direction):
    """Calculate stop profit price based on time window high/low."""
    price_arr = get_pole_price(symbol, int(stop_profit_para))
    if position_direction == "shorts":
        return price_arr[1]
    if position_direction == "longs":
        return price_arr[0]
    return 0
