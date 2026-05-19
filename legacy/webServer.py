# DEPRECATED: This file is kept as reference only.
# The active web server is now web_server/app.py (FastAPI).
# Entry point: run_web_server.py
#!/usr/bin/env python3
# coding=utf-8
import _thread
import sys
from bottle import run, get, post, request,response
import json
from datetime import datetime as _dt
import random
import time
import requests
import mysql.connector
import oss2
import socket
import decimal
import datetime
import math
import traceback
from multiprocessing import Pool
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import connect
from binance_f.requestclient import RequestClient
from binance_f.constant.test import *
from binance_f.base.printobject import *
from binance_f.model.constant import *
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.acs_exception.exceptions import ClientException
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest
from aliyunsdkecs.request.v20140526.StartInstancesRequest import StartInstancesRequest
from aliyunsdkecs.request.v20140526.StopInstancesRequest import StopInstancesRequest
from settings import settings
from infra_client import InfraClient
from sqlmodel import select
from app.models.trade_server_status import TradeServerStatus
from app.models.machine_status import MachineStatus, TradeMachineStatus
from app.models.income import Income
from app.models.income_day import IncomeDay
from app.models.loss_limit_time import LossLimitTime
from app.models.position_record import PositionRecord
from app.models.trade_symbol import TradeSymbol
from app.models.trades_take import TradesTake
from app.models.trade_record import TradeRecord
from app.models.trades import Trades
from app.models.begin_trade_record import BeginTradeRecord

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="webServer",connectMysqlPool=True)

USER_CONFIG_PATH = "user_config.json"

def load_user_config():
    try:
        with open(USER_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"hot_key_config_obj": {}, "state_config_obj": {}}

def save_user_config(config):
    with open(USER_CONFIG_PATH, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

class UTCEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, _dt):
            return obj.isoformat()
        return super().default(obj)

def json_dumps(obj):
    return json.dumps(obj, cls=UTCEncoder)



ORDER_ID_SYMBOL = "wTake"


PRIVATE_IP = FUNCTION_CLIENT.get_private_ip()

ORDER_ID_INDEX  = random.randint(1,100000)


PRICE_DECIMAL_OBJ = {}

AMOUNT_DECIMAL_OBJ = {}

PRICE_TICK_OBJ = {}

PRICE_DECIMAL_AMOUNT_OBJ = {}

AMOUNT_DECIMAL_AMOUNT_OBJ = {}

MARKET_MAX_SIZE_OBJ = {}


MARKET_MIN_SIZE_OBJ = {}

def updateSymbolInfo():
    global PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,PRICE_DECIMAL_AMOUNT_OBJ,AMOUNT_DECIMAL_AMOUNT_OBJ,PRICE_TICK_OBJ,MARKET_MAX_SIZE_OBJ,MARKET_MIN_SIZE_OBJ
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.request("GET", url,timeout=(3,7)).json()
    symbols = response['symbols']
    for i in range(len(symbols)):
        thisInstrumentID = symbols[i]['symbol']
        priceTick = 0
        priceDecimal = ""
        amountDecimal = ""
        priceDecimalAmount = ""
        amountDecimalAmount = ""
        for c in range(len(symbols[i]['filters'])):
            if symbols[i]['filters'][c]['filterType']=="PRICE_FILTER":
                priceTick=float(symbols[i]['filters'][c]['tickSize'])
                thisDecimal = 0
                initPara = 10
                for d in range(20):
                    thisDecimal = thisDecimal+1
                    initPara = round(initPara/10,10)
                    if initPara==float(symbols[i]['filters'][c]['tickSize']):
                        break
                priceDecimal = "%."+str(thisDecimal-1)+"f"
                priceDecimalAmount= str(thisDecimal-1)
            if symbols[i]['filters'][c]['filterType']=="LOT_SIZE":
                thisDecimal = 0
                initPara = 10
                for d in range(20):
                    thisDecimal = thisDecimal+1
                    initPara = round(initPara/10,10)
                    if initPara==float(symbols[i]['filters'][c]['stepSize']):
                        break
                amountDecimal = "%."+str(thisDecimal-1)+"f"
                amountDecimalAmount = str(thisDecimal-1)
            if symbols[i]['filters'][c]['filterType']=="MARKET_LOT_SIZE":
                MARKET_MAX_SIZE_OBJ[thisInstrumentID] = float(symbols[i]['filters'][c]['maxQty'])
                MARKET_MIN_SIZE_OBJ[thisInstrumentID] = float(symbols[i]['filters'][c]['minQty'])
        PRICE_DECIMAL_OBJ[thisInstrumentID] = priceDecimal
        AMOUNT_DECIMAL_OBJ[thisInstrumentID] = amountDecimal
        PRICE_TICK_OBJ[thisInstrumentID] = priceTick
        PRICE_DECIMAL_AMOUNT_OBJ[thisInstrumentID] = priceDecimalAmount
        if amountDecimalAmount!="":
            AMOUNT_DECIMAL_AMOUNT_OBJ[thisInstrumentID] = int(amountDecimalAmount)

updateSymbolInfo()

while not "BTCUSDT" in PRICE_DECIMAL_OBJ:
    FUNCTION_CLIENT.send_notify("mainConsole updateSymbolInfo")
    updateSymbolInfo()
    time.sleep(1)

def takeElemZero(elem):
    return float(elem[0])

def getFutureDepthBySymbol(symbol,limit):
    response = {}
    try:
        url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=50"
        response = requests.request("GET", url,timeout=(0.5,0.5)).json()
    except Exception as e:
        try:
            url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=50"
            response = requests.request("GET", url,timeout=(1,1)).json()
        except Exception as e:
            try:
                url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=50"
                response = requests.request("GET", url,timeout=(2,2)).json()
            except Exception as e:
                print(e)
    return response

def getKline(symbol,interval,limit):
    nowPrice = 0
    klineDataArr = []
    try:
        url = "https://fapi.binance.com/fapi/v1/klines?symbol="+symbol+"&interval="+interval+"&limit="+str(limit)
        klineDataArr = requests.request("GET", url,timeout=(0.5,0.5)).json()
        klineDataArr.sort(key=takeElemZero,reverse=False)
    except Exception as e:
        print(e)
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol="+symbol+"&interval="+interval+"&limit="+str(limit)
            klineDataArr = requests.request("GET", url,timeout=(1,1)).json()
            klineDataArr.sort(key=takeElemZero,reverse=False)
        except Exception as e:
            print(e)
            try:
                url = "https://fapi.binance.com/fapi/v1/klines?symbol="+symbol+"&interval="+interval+"&limit="+str(limit)
                klineDataArr = requests.request("GET", url,timeout=(2,2)).json()
                klineDataArr.sort(key=takeElemZero,reverse=False)
            except Exception as e:
                print(e)
    return klineDataArr

def getFutureNowPriceByDepth(symbol):
    nowPrice = 0
    try:
        url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=5"
        response = requests.request("GET", url,timeout=(0.5,0.5)).json()
        nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
    except Exception as e:
        try:
            url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=5"
            response = requests.request("GET", url,timeout=(1,1)).json()
            nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
        except Exception as e:
            try:
                url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=5"
                response = requests.request("GET", url,timeout=(2,2)).json()
                nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
            except Exception as e:
                print(e)
    return nowPrice

def getSpotNowPriceByDepth(symbol):
    nowPrice = 0
    try:
        url = "https://api.binance.com/api/v1/depth?symbol="+symbol+"&limit=5"
        response = requests.request("GET", url,timeout=(0.5,0.5)).json()
        nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
    except Exception as e:
        try:
            url = "https://api.binance.com/api/v1/depth?symbol="+symbol+"&limit=5"
            response = requests.request("GET", url,timeout=(1,1)).json()
            nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
        except Exception as e:
            try:
                url = "https://api.binance.com/api/v1/depth?symbol="+symbol+"&limit=5"
                response = requests.request("GET", url,timeout=(2,2)).json()
                nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
            except Exception as e:
                print(e)
    return nowPrice


BUY_BNB_TS = False
def buyBNB(apiKey,buyBNBAmount,bnbPrice,assetType):
    global BUY_BNB_TS,API_OBJ,AMOUNT_DECIMAL_OBJ
    now = int(time.time())
    symbol = "BNB"+assetType
    print("buyBNB")
    if now-BUY_BNB_TS>60:
        BUY_BNB_TS = now
        

        spot_request_client = SpotRequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = spot_request_client.transfer("UMFUTURE_MAIN",assetType,bnbPrice*buyBNBAmount*1.05)
        result = json.loads(result)



        amount = buyBNBAmount
        amount =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (amount ))
        betPrice =  decimal.Decimal("%.1f"% (bnbPrice*1.005))

        spot_request_client = SpotRequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = spot_request_client.post_order(symbol=symbol, quantity=amount,side=OrderSide.BUY, ordertype=OrderType.LIMIT, price=betPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        result = json.loads(result)

        time.sleep(1)

        spot_request_client = SpotRequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = spot_request_client.get_account_information()
        result = json.loads(result)

        result = result['balances']
        bnbBalance = 0
        usdtBalance = 0
        for i in range(len(result)):
            if result[i]['asset']==assetType:
               usdtBalance = float(result[i]['free'])
            if result[i]['asset']=="BNB":
               bnbBalance = float(result[i]['free'])

        spot_request_client = spot_request_client = SpotRequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = spot_request_client.transfer("MAIN_UMFUTURE","BNB",bnbBalance)
        result = json.loads(result)
        spot_request_client = spot_request_client = SpotRequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = spot_request_client.transfer("MAIN_UMFUTURE",assetType,usdtBalance)
        result = json.loads(result)
        return True




INCOME_OBJ = {
    "15m":{"c":0,"p":0,'s':0},
    "30m":{"c":0,"p":0,'s':0},
    "1h":{"c":0,"p":0,'s':0},
    "4h":{"c":0,"p":0,'s':0},
    "oneDay":{"c":0,"p":0,'s':0},
    "today":{"c":0,"p":0,'s':0}
}

SYMBOL_INCOME_OBJ= {
}

LAST_UPDATE_INCOME_TS = 0
INCOME_LOCK = False
@post('/get_income_obj', methods='POST')
def getIncomeObj():
    global INCOME_OBJ,LAST_UPDATE_INCOME_TS,INCOME_LOCK,SYMBOL_INCOME_OBJ
    now = int(time.time())
    if now - LAST_UPDATE_INCOME_TS>=9:
        if now - LAST_UPDATE_INCOME_TS>=60 or (not INCOME_LOCK):
            LAST_UPDATE_INCOME_TS = now
            INCOME_LOCK= True

            todayTime = datetime.datetime.utcnow().strftime("%Y-%m-%d")+" 00:00:00"
            todayeTs  = FUNCTION_CLIENT.turn_ts_to_time(todayTime)

            todayeLimitTs = todayeTs*1000
            fifteenMinsLimitTs = int(time.time()*1000)-900000
            thirtyMinsLimitTs = int(time.time()*1000)-1800000
            oneHourLimitTs = int(time.time()*1000)-3600000
            fourHoursLimitTs = int(time.time()*1000)-14400000
            oneDayLimitTs = int(time.time()*1000)-86400000
            limitTs = int(time.time()*1000)-86400000
            with FUNCTION_CLIENT.get_session() as session:
                data = session.exec(
                    select(Income).where(Income.binance_ts > limitTs).order_by(Income.id.desc())
                ).all()
            print("len(data):"+str(len(data)))
            if len(data)>0:
                INCOME_OBJ = {
                    "15m":{"c":0,"p":0,'s':0},
                    "30m":{"c":0,"p":0,'s':0},
                    "1h":{"c":0,"p":0,'s':0},
                    "4h":{"c":0,"p":0,'s':0},
                    "oneDay":{"c":0,"p":0,'s':0},
                    "today":{"c":0,"p":0,'s':0}
                }

            symbolIncomeObj = {}
            for row in data:
                symbol = row.symbol
                binanceTs = row.binance_ts
                value = row.income
                commission = row.commission
                if not (symbol in symbolIncomeObj):
                    symbolIncomeObj[symbol] = {
                    "15m":{"p":0,"c":0},
                    "30m":{"p":0,"c":0},
                    "1h":{"p":0,"c":0},
                    "4h":{"p":0,"c":0},
                    "oneDay":{"p":0,"c":0},
                    "today":{"p":0,"c":0}
                }

                if  row.asset=="BNB":
                    value = row.income*row.bnb_price

                if row.income_type=="COMMISSION":
                    if binanceTs>=fifteenMinsLimitTs:
                        INCOME_OBJ["15m"]["c"] = INCOME_OBJ["15m"]["c"]+value
                        INCOME_OBJ["15m"]["s"] = INCOME_OBJ["15m"]["s"]+commission
                        symbolIncomeObj[symbol]["15m"]["c"] = symbolIncomeObj[symbol]["15m"]["c"]+value
                    if binanceTs>=thirtyMinsLimitTs:
                        INCOME_OBJ["30m"]["c"] = INCOME_OBJ["30m"]["c"]+value
                        INCOME_OBJ["30m"]["s"] = INCOME_OBJ["30m"]["s"]+commission
                        symbolIncomeObj[symbol]["30m"]["c"] = symbolIncomeObj[symbol]["30m"]["c"]+value
                    if binanceTs>=oneHourLimitTs:
                        INCOME_OBJ["1h"]["c"] = INCOME_OBJ["1h"]["c"]+value
                        INCOME_OBJ["1h"]["s"] = INCOME_OBJ["1h"]["s"]+commission
                        symbolIncomeObj[symbol]["1h"]["c"] = symbolIncomeObj[symbol]["1h"]["c"]+value
                    if binanceTs>=fourHoursLimitTs:
                        INCOME_OBJ["4h"]["c"] = INCOME_OBJ["4h"]["c"]+value
                        INCOME_OBJ["4h"]["s"] = INCOME_OBJ["4h"]["s"]+commission
                        symbolIncomeObj[symbol]["4h"]["c"] = symbolIncomeObj[symbol]["4h"]["c"]+value
                    if binanceTs>=oneDayLimitTs:
                        INCOME_OBJ["oneDay"]["c"] = INCOME_OBJ["oneDay"]["c"]+value
                        INCOME_OBJ["oneDay"]["s"] = INCOME_OBJ["oneDay"]["s"]+commission
                        symbolIncomeObj[symbol]["oneDay"]["c"] = symbolIncomeObj[symbol]["oneDay"]["c"]+value
                    if binanceTs>=todayeLimitTs:
                        INCOME_OBJ["today"]["c"] = INCOME_OBJ["today"]["c"]+value
                        INCOME_OBJ["today"]["s"] = INCOME_OBJ["today"]["s"]+commission
                        symbolIncomeObj[symbol]["today"]["c"] = symbolIncomeObj[symbol]["today"]["c"]+value
                if row.income_type=="REALIZED_PNL":
                    if binanceTs>=fifteenMinsLimitTs:
                        INCOME_OBJ["15m"]["p"] = INCOME_OBJ["15m"]["p"]+value
                        symbolIncomeObj[symbol]["15m"]["p"] = symbolIncomeObj[symbol]["15m"]["p"]+value
                    if binanceTs>=thirtyMinsLimitTs:
                        INCOME_OBJ["30m"]["p"] = INCOME_OBJ["30m"]["p"]+value
                        symbolIncomeObj[symbol]["30m"]["p"] = symbolIncomeObj[symbol]["30m"]["p"]+value
                    if binanceTs>=oneHourLimitTs:
                        INCOME_OBJ["1h"]["p"] = INCOME_OBJ["1h"]["p"]+value
                        symbolIncomeObj[symbol]["1h"]["p"] = symbolIncomeObj[symbol]["1h"]["p"]+value
                    if binanceTs>=fourHoursLimitTs:
                        INCOME_OBJ["4h"]["p"] = INCOME_OBJ["4h"]["p"]+value
                        symbolIncomeObj[symbol]["4h"]["p"] = symbolIncomeObj[symbol]["4h"]["p"]+value
                    if binanceTs>=oneDayLimitTs:
                        INCOME_OBJ["oneDay"]["p"] = INCOME_OBJ["oneDay"]["p"]+value
                        symbolIncomeObj[symbol]["oneDay"]["p"] = symbolIncomeObj[symbol]["oneDay"]["p"]+value
                    if binanceTs>=todayeLimitTs:
                        INCOME_OBJ["today"]["p"] = INCOME_OBJ["today"]["p"]+value
                        symbolIncomeObj[symbol]["today"]["p"] = symbolIncomeObj[symbol]["today"]["p"]+value
            SYMBOL_INCOME_OBJ = symbolIncomeObj

            INCOME_LOCK= False
    resp = json.dumps({'s':'ok','i':INCOME_OBJ,'n':int(time.time()),'d':SYMBOL_INCOME_OBJ})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


ACCOUNT_INFO_UPDATE_TS = 0
BNB_PRICE = 0
POSITION_ARR = []
ASSETS_ARR = []
for i in range(10):
    POSITION_ARR.append([])
    ASSETS_ARR.append([])


def getBinanceAccountInfo(apiIndex,apiKey,autoBuyBnb,beginMinBnbMoney,buyBNBMoney):
    global ACCOUNT_INFO_UPDATE_TS,POSITION_ARR,ASSETS_ARR,BNB_PRICE
    now = int(time.time()*1000)
    buyBNBResult = False
    if now - ACCOUNT_INFO_UPDATE_TS>60000:
        positionsArr = []
        assetsArr = []
        result = {}
        bnbAmount = -1
        usdtAmount = -1
        busdAmount =-1
        try:
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            result = request_client.get_account_information()
            result = json.loads(result)
            for i in range(len(result["positions"])):
                if float(result["positions"][i]["positionAmt"])!=0:
                    positionsArr.append(result["positions"][i])

            # positionsArr = result["positions"]
            assetsArr = result["assets"]
            for i in range(len(assetsArr)):
                if assetsArr[i]['asset'] == "BNB":
                    bnbAmount = float(assetsArr[i]['marginBalance'])
                if assetsArr[i]['asset'] == "USDT":
                    usdtAmount = float(assetsArr[i]['marginBalance'])
                if assetsArr[i]['asset'] == "BUSD":
                    busdAmount = float(assetsArr[i]['marginBalance'])
            BNB_PRICE = getSpotNowPriceByDepth("BNBUSDT")
            beginMinBnbAmount = beginMinBnbMoney/BNB_PRICE
            buyBNBAmount = buyBNBMoney/BNB_PRICE
            if autoBuyBnb and bnbAmount!=-1 and bnbAmount<beginMinBnbAmount and usdtAmount>=buyBNBMoney*1.1:
                buyAsset= "USDT"
                buyBNBResult = buyBNB(apiKey,buyBNBAmount,BNB_PRICE,buyAsset)
            elif autoBuyBnb and bnbAmount!=-1 and bnbAmount<beginMinBnbAmount and busdAmount>=buyBNBMoney*1.1:
                buyAsset= "BUSD"
                buyBNBResult = buyBNB(apiKey,buyBNBAmount,BNB_PRICE,buyAsset)
            POSITION_ARR[apiIndex] = positionsArr
            ASSETS_ARR[apiIndex] = assetsArr

        except Exception as e:
            print(e)
        ACCOUNT_INFO_UPDATE_TS = now
    return [POSITION_ARR,ASSETS_ARR,buyBNBResult,BNB_PRICE]

@post('/ping', methods='POST')
def ping():
    global PRIVATE_IP_OBJ,API_OBJ,UPDATE_POSITION_TS
    apiKey = str(request.forms.get('apiKey'))
    apiIndex = int(request.forms.get('apiIndex'))
    timestamp = int(request.forms.get('timestamp'))
    autoBuyBnbConfigArr = json.loads(request.forms.get('autoBuyBnbConfigArr'))

    autoBuyBnb = autoBuyBnbConfigArr[2]
    beginMinBnbMoney = autoBuyBnbConfigArr[0]
    buyBNBMoney = autoBuyBnbConfigArr[1]

    print(autoBuyBnb)
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    now = int(time.time()*1000)
    binanceInfoArr = getBinanceAccountInfo(apiIndex,apiKey,autoBuyBnb,beginMinBnbMoney,buyBNBMoney)
    resp = json.dumps({'s':'ok','p':binanceInfoArr[0],'t':binanceInfoArr[1],'r':binanceInfoArr[2],'n':now,'b':binanceInfoArr[3],"l":timestamp})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_symbol_index', methods='POST')
def getSymbolIndex():
    with FUNCTION_CLIENT.get_session() as session:
        rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
        ).all()

    tradeSymbolArr = []
    for i in range(len(rows)):
        symbolIndex = i
        link_data = rows[i].link_symbol_arr if isinstance(rows[i].link_symbol_arr, (list, dict)) else json.loads(rows[i].link_symbol_arr or "[]")
        tradeSymbolArr.append({
                "symbol":rows[i].symbol,
                "coin":rows[i].coin,
                "symbolIndex":rows[i].index,
                "quote":rows[i].quote,
                "linkSymbolArr":link_data,
                "defaultShow":rows[i].default_show,
                "weight":0
            })


    resp = json.dumps({'s':'ok','d':tradeSymbolArr})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_config', methods='POST')
def get_config():
    config = load_user_config()
    binanceApiArr = json.loads(settings.binance_api_arr)
    for item in binanceApiArr:
        item["apiSecret"] = ""
    resp = json.dumps({
        's': 'ok',
        'binanceApiArr': binanceApiArr,
        'hotKeyConfigObj': config.get("hot_key_config_obj", {}),
        'stateConfigObj': config.get("state_config_obj", {})
    })
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/change_leverage', methods='POST')
def change_leverage():
    global API_OBJ
    symbol = str(request.forms.get('symbol'))
    leverage = int(request.forms.get('leverage'))
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    result = request_client.change_initial_leverage(symbol,leverage)
    result = json.loads(result)
    resp = json.dumps({'s':'ok','result':result})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp



@post('/modify_hot_key', methods='POST')
def modify_hot_key():
    newHotKeyConfigObj = json.loads(request.forms.get('newHotKeyConfigObj'))
    config = load_user_config()
    config["hot_key_config_obj"] = newHotKeyConfigObj
    save_user_config(config)
    resp = json.dumps({'s':'ok',"newHotKeyConfigObj":newHotKeyConfigObj})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_state_config', methods='POST')
def get_state_config():
    config = load_user_config()
    stateConfigObj = config.get("state_config_obj", {})
    resp = json.dumps({'s':'ok',"stateConfigObj":stateConfigObj})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/modify_state_config', methods='POST')
def modify_state_config():
    stateConfigObj = json.loads(request.forms.get('stateConfigObj'))
    config = load_user_config()
    config["state_config_obj"] = stateConfigObj
    save_user_config(config)
    resp = json.dumps({'s':'ok','stateConfigObj':stateConfigObj})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

DEPTH_UPDATE_TS = 0
LAST_BINANCE_RESPONSE_OBJ = {}
@post('/get_depth', methods='POST')
def get_depth():
    global PRICE_DECIMAL_AMOUNT_OBJ,AMOUNT_DECIMAL_AMOUNT_OBJ,DEPTH_UPDATE_TS,LAST_BINANCE_RESPONSE_OBJ
    symbol = str(request.forms.get('symbol'))
    now = int(time.time()*1000)
    if now - DEPTH_UPDATE_TS>100:
        DEPTH_UPDATE_TS = now
        url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit=50"
        binanceResponse = requests.request("GET", url,timeout=(0.5,0.5)).json()
        LAST_BINANCE_RESPONSE_OBJ = binanceResponse

    resp = json.dumps({'s':'ok','r':LAST_BINANCE_RESPONSE_OBJ,"i":symbol,"p":PRICE_DECIMAL_AMOUNT_OBJ[symbol],"a":AMOUNT_DECIMAL_AMOUNT_OBJ[symbol]})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

API_OBJ = {}

def updateAPIObj(apiKey):
    global API_OBJ
    if apiKey in API_OBJ:
        return
    binanceApiArr = json.loads(settings.binance_api_arr)
    for item in binanceApiArr:
        if apiKey == item["apiKey"]:
            API_OBJ[item["apiKey"]] = item["apiSecret"]
            break

def cancelBinanceOrder(symbol,apiKey):
    global API_OBJ
    result= {}
    try:
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
    except Exception as e:
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
        print(e)
    resp = json.dumps({'s':'ok','result':result})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/cancel_orders', methods='POST')
def cancel_orders():
    global API_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    cancelBinanceOrder(symbol,apiKey)
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/cancel_order', methods='POST')
def cancel_order():
    global API_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    clientOrderId = str(request.forms.get('clientOrderId'))
    request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    result = request_client.cancel_order(symbol=symbol,orderId=clientOrderId)
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp



ALL_OPEN_ORDERS_ARR_UPDATE_TS = 0
ALL_OPEN_ORDERS_ARR = []
@post('/get_all_open_orders', methods='POST')
def get_all_open_orders():
    global API_OBJ,ALL_OPEN_ORDERS_ARR,ALL_OPEN_ORDERS_ARR_UPDATE_TS
    key = str(request.forms.get('key'))
    secret = str(request.forms.get('secret'))
    request_client = RequestClient(api_key=key,secret_key=secret)
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    resp = json.dumps({'s':'ok','r':result,'t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

def getStopLossPriceByTime(symbol,stopLossPara,positionDirection):
    stopLossPrice = 0
    stopLossTime = int(stopLossPara)
    highPrice = 0
    lowPrice = 99999999
    if stopLossTime<500:
        klineArr = getKline(symbol,"1m",stopLossTime)
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopLossTime<7500:
        klineArr = getKline(symbol,"15m",int(stopLossTime/15))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopLossTime<30000:
        klineArr = getKline(symbol,"1h",int(stopLossTime/60))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopLossTime<120000:
        klineArr = getKline(symbol,"4h",int(stopLossTime/240))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopLossTime<720000:
        klineArr = getKline(symbol,"1d",int(stopLossTime/1440))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])

    if positionDirection =="longs":
        stopLossPrice = lowPrice
    if positionDirection =="shorts":
        stopLossPrice = highPrice

    return stopLossPrice

def getPolePrice(symbol,mins):
    stopLossPrice = 0
    mins = int(mins)
    highPrice = 0
    lowPrice = 99999999
    if mins<500:
        klineArr = getKline(symbol,"1m",mins)
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif mins<7500:
        klineArr = getKline(symbol,"15m",int(mins/15))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif mins<30000:
        klineArr = getKline(symbol,"1h",int(mins/60))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif mins<120000:
        klineArr = getKline(symbol,"4h",int(mins/240))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif mins<720000:
        klineArr = getKline(symbol,"1d",int(mins/1440))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])

    return [highPrice,lowPrice]

def getStopProfitPriceByTime(symbol,stopProfitPara,positionDirection):
    stopProfitPrice = 0
    stopProfitTime = int(stopProfitPara)
    highPrice = 0
    lowPrice = 99999999
    if stopProfitTime<500:
        klineArr = getKline(symbol,"1m",stopProfitTime)
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopProfitTime<7500:
        klineArr = getKline(symbol,"15m",int(stopProfitTime/15))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopProfitTime<30000:
        klineArr = getKline(symbol,"1h",int(stopProfitTime/60))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopProfitTime<120000:
        klineArr = getKline(symbol,"4h",int(stopProfitTime/240))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])
    elif stopProfitTime<720000:
        klineArr = getKline(symbol,"1d",int(stopProfitTime/1440))
        for i in range(len(klineArr)):
            if float(klineArr[i][2])>highPrice:
                highPrice = float(klineArr[i][2])
            if float(klineArr[i][3])<lowPrice:
                lowPrice = float(klineArr[i][3])

    if positionDirection =="shorts":
        stopProfitPrice = lowPrice
    if positionDirection =="longs":
        stopProfitPrice = highPrice

    return stopProfitPrice

@post('/open_position', methods='POST')
def open_position():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX,MARKET_MAX_SIZE_OBJ,PRICE_TICK_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    money = float(request.forms.get('money'))
    tradeType = str(request.forms.get('tradeType'))
    nowPrice = float(request.forms.get('nowPrice'))
    paraArr = json.loads(request.forms.get('paraArr'))

    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]
    now = int(time.time())
    resultArr= []
    result = {}
    direction = ""
    tradeCoinQuantity = 0
    if tradeType=="openLongsByMarket":
        direction = "longs"
        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice ))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = "marketOpenLongs_s"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_market_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.BUY, ordertype=OrderType.MARKET, positionSide="BOTH", price="0")
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        resultArr.append(result)
    elif tradeType=="openShortsByMarket":
        direction = "shorts"
        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice ))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize

        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = "marketOpenShorts_s"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_market_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.SELL, ordertype=OrderType.MARKET, positionSide="BOTH", price="0")
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        resultArr.append(result)


    elif tradeType=="openLongsByDepth" or tradeType=="openShortsByDepth":
        depthObj = getFutureDepthBySymbol(symbol,50)
        if not ("bids" in depthObj):
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        depthType = paraArr[0]
        price = 0
        if depthType=="mid":
            price = (float(depthObj["bids"][0][0])+float(depthObj["bids"][0][0]))/2
        elif depthType=="buy":
            depthNumber = int(paraArr[1])-1
            price = float(depthObj["bids"][depthNumber][0])
        elif depthType=="sell":
            depthNumber = int(paraArr[1])-1
            price = float(depthObj["asks"][depthNumber][0])

        priceIndex = float(paraArr[2])
        price = price*priceIndex
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))
        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice ))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize

        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = ""
        if tradeType =="openLongsByDepth":
            newClientOrderId ="depthOpenLongs_s"+str(ORDER_ID_INDEX)
        if tradeType =="openShortsByDepth":
            newClientOrderId = "depthOpenShorts_s"+str(ORDER_ID_INDEX)

        timeInForce = ""
        if paraArr[4]=="GTX":
            timeInForce = TimeInForce.GTX
        if paraArr[4]=="GTC":
            timeInForce = TimeInForce.GTC

        orderSide = ""
        if tradeType =="openLongsByDepth":
            orderSide = OrderSide.BUY
        if tradeType =="openShortsByDepth":
            orderSide = OrderSide.SELL
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.LIMIT, price=price, positionSide="BOTH", timeInForce=timeInForce)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        resultArr.append(result)

    elif tradeType=="openLongsByLeft" or tradeType=="openShortsByLeft":

        mins = int(paraArr[0])
        priceIndex = float(paraArr[1])
        priceArr = getPolePrice(symbol,mins)
        highPrice = priceArr[0]
        if highPrice==0:
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        lowPirce = priceArr[1]
        price = 0
        if tradeType=="openLongsByLeft":
            price = lowPirce*priceIndex
        if tradeType=="openShortsByLeft":
            price = highPrice*priceIndex

        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/price ))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize

        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))

        newClientOrderId = ""
        if tradeType =="openLongsByLeft":
            newClientOrderId ="leftOpenLongs_s"+str(ORDER_ID_INDEX)
        if tradeType =="openShortsByLeft":
            newClientOrderId = "leftOpenShortss_s"+str(ORDER_ID_INDEX)

        orderSide = ""
        if tradeType =="openLongsByLeft":
            orderSide = OrderSide.BUY
        if tradeType =="openShortsByLeft":
            orderSide = OrderSide.SELL
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.LIMIT, price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        resultArr.append(result)
    elif tradeType=="openLongsByRight" or tradeType=="openShortsByRight":

        mins = int(paraArr[0])
        priceIndex = float(paraArr[1])
        priceArr = getPolePrice(symbol,mins)
        highPrice = priceArr[0]
        if highPrice==0:
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        lowPirce = priceArr[1]
        price = 0
        stopPrice = 0
        if tradeType=="openLongsByRight":
            price = highPrice*priceIndex
            stopPrice = highPrice
        if tradeType=="openShortsByRight":
            price = lowPirce*priceIndex
            stopPrice = lowPirce

        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/stopPrice ))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize


        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))

        newClientOrderId = ""
        if tradeType =="openLongsByRight":
            newClientOrderId ="rightOpenLongs_s"+str(ORDER_ID_INDEX)
        if tradeType =="openShortsByRight":
            newClientOrderId = "rightOpenShorts_s"+str(ORDER_ID_INDEX)

        orderSide = ""
        if tradeType =="openLongsByRight":
            orderSide = OrderSide.BUY
        if tradeType =="openShortsByRight":
            orderSide = OrderSide.SELL
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_auto_order_with_price(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.STOP,stopPrice=stopPrice, price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        resultArr.append(result)
    elif tradeType=="openLongsByBatch" or tradeType=="openShortsByBatch":
        depthObj = getFutureDepthBySymbol(symbol,50)
        if not ("bids" in depthObj):
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        depthType = paraArr[0]
        basicPrice = 0
        if depthType=="mid":
            basicPrice = (float(depthObj["bids"][0][0])+float(depthObj["bids"][0][0]))/2
        elif depthType=="buy":
            depthNumber = int(paraArr[1])-1
            basicPrice = float(depthObj["bids"][depthNumber][0])
        elif depthType=="sell":
            depthNumber = int(paraArr[1])-1
            basicPrice = float(depthObj["asks"][depthNumber][0])

        priceIndex = float(paraArr[2])
        basicPrice = basicPrice*priceIndex

        addPricePercent = float(paraArr[4])
        orderCount = int(paraArr[5])
        priceArr = []
        if addPricePercent==0:
            basicPrice =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (basicPrice)))
            for i in range(orderCount):
                if tradeType=="openLongsByBatch":
                    priceArr.append(basicPrice-PRICE_TICK_OBJ[symbol]*i)
                if tradeType=="openShortsByBatch":
                    priceArr.append(basicPrice+PRICE_TICK_OBJ[symbol]*i)
        else:
            for i in range(orderCount):
                if tradeType=="openLongsByBatch":
                    priceArr.append(basicPrice*(1-addPricePercent*i/100))
                if tradeType=="openShortsByBatch":
                    priceArr.append(basicPrice*(1+addPricePercent*i/100))

        for i in range(len(priceArr)):
            price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (priceArr[i])))

            coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice/orderCount ))
            if coinQuantity>marketMaxSize:
                coinQuantity = marketMaxSize
                tradeCoinQuantity = marketMaxSize

            timeInForce = ""
            if paraArr[6]=="GTX":
                timeInForce = TimeInForce.GTX
            if paraArr[6]=="GTC":
                timeInForce = TimeInForce.GTC

            ORDER_ID_INDEX = ORDER_ID_INDEX+1
            newClientOrderId = ""
            if tradeType =="openLongsByBatch":
                newClientOrderId ="depthOpenLongs_s"+str(ORDER_ID_INDEX)
            if tradeType =="openShortsByBatch":
                newClientOrderId = "depthOpenShorts_s"+str(ORDER_ID_INDEX)


            orderSide = ""
            if tradeType =="openLongsByBatch":
                orderSide = OrderSide.BUY
            if tradeType =="openShortsByBatch":
                orderSide = OrderSide.SELL
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            try:
                result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.LIMIT, price=price, positionSide="BOTH", timeInForce=timeInForce)
            except Exception as e:
                resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
                response.set_header('Access-Control-Allow-Origin', '*')
                return resp
            result = json.loads(result)
            resultArr.append(result)
    elif tradeType=="openLongsByPrice":
        price = float(paraArr[0])
        clientIDPrefix = ""
        if price>nowPrice:
            clientIDPrefix = "rightOpenLongs"
        if price<=nowPrice:
            clientIDPrefix = "leftOpenLongs"

        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/price ))
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = clientIDPrefix+"_s"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])

        try:
            if clientIDPrefix=="leftOpenLongs":
                result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.BUY, ordertype=OrderType.LIMIT, positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC)
            if clientIDPrefix=="rightOpenLongs":
                result = request_client.post_auto_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.BUY, ordertype=OrderType.STOP_MARKET, stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp

        result = json.loads(result)
        resultArr.append(result)
    elif tradeType=="openShortsByPrice":
        price = float(paraArr[0])
        clientIDPrefix = ""
        if price<nowPrice:
            clientIDPrefix = "rightOpenShorts"
        if price>=nowPrice:
            clientIDPrefix = "leftOpenShorts"

        coinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/price ))
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = clientIDPrefix+"_s"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])

        try:
            if clientIDPrefix=="leftOpenShorts":
                result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.SELL, ordertype=OrderType.LIMIT, positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC)
            if clientIDPrefix=="rightOpenShorts":
                result = request_client.post_auto_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.SELL, ordertype=OrderType.STOP_MARKET, stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            print(e)
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp

        result = json.loads(result)
        resultArr.append(result)

    resp = json.dumps({'s':'ok','resultArr':resultArr,'tradeCoinQuantity':tradeCoinQuantity,'money':money,'symbol':symbol,"tradeType":tradeType})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/close_position', methods='POST')
def close_position():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    money = float(request.forms.get('money'))
    tradeType = str(request.forms.get('tradeType'))
    nowPrice = float(request.forms.get('nowPrice'))
    direction = str(request.forms.get('direction'))
    paraArr = json.loads(request.forms.get('paraArr'))
    now = int(time.time())
    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]
    tradeCoinQuantity = 0
    resultArr = []
    if tradeType=="selectCoinCloseByMarket":

        newClientOrderId = "marketCloseLongs_s"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        orderSide = ""
        if direction=="longs":
            orderSide = OrderSide.SELL
        if direction=="shorts":
            orderSide = OrderSide.BUY

        try:
            result = request_client.post_market_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=marketMaxSize,side=orderSide, ordertype=OrderType.MARKET, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp

        resultArr.append(json.loads(result))
        coinQuantity = decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice ))


    elif tradeType=="selectCoinCloseByDepth":
        depthObj = getFutureDepthBySymbol(symbol,50)
        if not ("bids" in depthObj):
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp

        moneyIndex = float(paraArr[0])
        money = money*moneyIndex

        depthType = paraArr[1]
        price = 0
        depthNumber = int(paraArr[2])-1
        if depthType=="mid":
            price = (float(depthObj["bids"][0][0])+float(depthObj["bids"][0][0]))/2
        elif depthType=="reverse":
            if direction=="longs":
                price = float(depthObj["bids"][depthNumber][0])
            if direction=="shorts":
                price = float(depthObj["asks"][depthNumber][0])
        elif depthType=="positive":
            if direction=="longs":
                price = float(depthObj["asks"][depthNumber][0])
            if direction=="shorts":
                price = float(depthObj["bids"][depthNumber][0])

        priceIndex = 0
        if direction =="longs":
            priceIndex = float(paraArr[3])
        if direction =="shorts":
            priceIndex = float(paraArr[4])

        price = price*priceIndex
        price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (price)))
        coinQuantity =  float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice )))
        if coinQuantity>marketMaxSize:
            coinQuantity = marketMaxSize
            tradeCoinQuantity = marketMaxSize

        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = ""
        if direction =="longs":
            newClientOrderId ="depthLongsClose_s"+str(ORDER_ID_INDEX)
        if direction =="shorts":
            newClientOrderId = "depthShortsClose_s"+str(ORDER_ID_INDEX)
        print(newClientOrderId)
        timeInForce = ""
        if paraArr[5]=="GTX":
            timeInForce = TimeInForce.GTX
        if paraArr[5]=="GTC":
            timeInForce = TimeInForce.GTC

        orderSide = ""
        if direction =="longs":
            orderSide = OrderSide.SELL
        if direction =="shorts":
            orderSide = OrderSide.BUY
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.LIMIT, price=price, positionSide="BOTH", timeInForce=timeInForce)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        resultArr.append(json.loads(result))

    elif tradeType=="selectCoinCloseByBatch":
        depthObj = getFutureDepthBySymbol(symbol,50)
        if not ("bids" in depthObj):
            resp = json.dumps({'s':'dataError','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp

        moneyIndex = float(paraArr[0])
        money = money*moneyIndex

        depthType = paraArr[1]
        basicPrice = 0
        depthNumber = int(paraArr[2])-1
        if depthType=="mid":
            basicPrice = (float(depthObj["asks"][0][0])+float(depthObj["bids"][0][0]))/2
        elif depthType=="reverse":
            if direction=="longs":
                basicPrice = float(depthObj["bids"][depthNumber][0])
            if direction=="shorts":
                basicPrice = float(depthObj["asks"][depthNumber][0])
        elif depthType=="positive":
            if direction=="longs":
                basicPrice = float(depthObj["asks"][depthNumber][0])
            if direction=="shorts":
                basicPrice = float(depthObj["bids"][depthNumber][0])

        priceIndex = 0
        if direction =="longs":
            priceIndex = float(paraArr[3])
        if direction =="shorts":
            priceIndex = float(paraArr[4])

        basicPrice = basicPrice*priceIndex

        priceArr = []



        addPricePercent = float(paraArr[5])
        orderCount = int(paraArr[6])
        if addPricePercent==0:
            basicPrice =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (basicPrice)))
            for i in range(orderCount):
                if direction=="longs":
                    priceArr.append(basicPrice+PRICE_TICK_OBJ[symbol]*i)
                if direction=="shorts":
                    priceArr.append(basicPrice-PRICE_TICK_OBJ[symbol]*i)
        else:
            for i in range(orderCount):
                if direction=="longs":
                    priceArr.append(basicPrice*(1+addPricePercent*i/100))
                if direction=="shorts":
                    priceArr.append(basicPrice*(1-addPricePercent*i/100))

        for i in range(len(priceArr)):
            price =  float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (priceArr[i])))
            coinQuantity =  float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (money/nowPrice/orderCount )))
            if coinQuantity>marketMaxSize:
                coinQuantity = marketMaxSize
                tradeCoinQuantity = marketMaxSize

            ORDER_ID_INDEX = ORDER_ID_INDEX+1
            newClientOrderId = ""
            if direction =="longs":
                newClientOrderId ="batchLongsClose_s"+str(ORDER_ID_INDEX)
            if direction =="shorts":
                newClientOrderId = "batchShortsClose_s"+str(ORDER_ID_INDEX)

            timeInForce = ""
            if paraArr[7]=="GTX":
                timeInForce = TimeInForce.GTX
            if paraArr[7]=="GTC":
                timeInForce = TimeInForce.GTC

            orderSide = ""
            if direction =="longs":
                orderSide = OrderSide.SELL
            if direction =="shorts":
                orderSide = OrderSide.BUY
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            try:
                result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=coinQuantity,side=orderSide, ordertype=OrderType.LIMIT, price=price, positionSide="BOTH", timeInForce=timeInForce)
            except Exception as e:
                resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
                response.set_header('Access-Control-Allow-Origin', '*')
                return resp
            resultArr.append(json.loads(result))
    resp = json.dumps({'s':'ok','resultArr':resultArr,'tradeCoinQuantity':tradeCoinQuantity,'marketMaxSize':marketMaxSize,'symbol':symbol,"tradeType":tradeType})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/stop_loss_batch', methods='POST')
def stop_loss_batch():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX,MARKET_MAX_SIZE_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    coinAmount = float(request.forms.get('coinAmount'))
    positionDirection =  str(request.forms.get('positionDirection'))
    stopLossPriceArr =  json.loads(request.forms.get('stopLossPriceArr'))

    now = int(time.time())
    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]

    # request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    # result = request_client.get_open_orders(symbol=symbol)
    # result = json.loads(result)
    # stopLossOrderIDArr = []

    # for i in range(len(result)):
    #     clientOrderId = result[i]['clientOrderId']
    #     orderTypeSymbol = clientOrderId.split("_")[0]
    #     if orderTypeSymbol=="shortsStopLoss" or orderTypeSymbol=="longsStopLoss":
    #         stopLossOrderIDArr.append(clientOrderId)

    # for i in range(len(stopLossOrderIDArr)):
    #     try:
    #         request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    #         result = request_client.cancel_order(symbol=symbol,orderId=stopLossOrderIDArr[i])
    #     except Exception as e:
    #         try:
    #             request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    #             result = request_client.cancel_order(symbol=symbol,orderId=stopLossOrderIDArr[i])
    #         except Exception as e:
    #             print(e)

    stopLossCoinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount/len(stopLossPriceArr) ))



    orderResultArr = []
    positionSide = OrderSide.BUY
    if positionDirection =="longs":
        positionSide = OrderSide.SELL

    someOrderTimeOut = False
    for i in range(len(stopLossPriceArr)):
        stopLossPrice =  decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (stopLossPriceArr[i]))
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = positionDirection+"StopLoss_s_"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        if i==len(stopLossPriceArr)-1:
            stopLossCoinQuantity  =  coinAmount - float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount/len(stopLossPriceArr) )))*(len(stopLossPriceArr)-1)
            stopLossCoinQuantity = decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (stopLossCoinQuantity ))
        try:
            result = request_client.post_auto_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=stopLossCoinQuantity,side=positionSide, ordertype=OrderType.STOP_MARKET, stopPrice=stopLossPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            someOrderTimeOut = True
        result = json.loads(result)
        orderResultArr.append(result)

    resp = json.dumps({'s':'ok','resultArr':orderResultArr,'symbol':symbol,'someOrderTimeOut':someOrderTimeOut})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/stop_loss_once', methods='POST')
def stop_loss_once():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX,MARKET_MAX_SIZE_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    coinAmount = float(request.forms.get('coinAmount'))
    stopLossType = str(request.forms.get('stopLossType'))
    stopLossParaArr = json.loads(request.forms.get('stopLossParaArr'))
    positionDirection =  str(request.forms.get('positionDirection'))

    now = int(time.time())
    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]

    # request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    # result = request_client.get_open_orders(symbol=symbol)
    # result = json.loads(result)
    # stopLossOrderIDArr = []

    # for i in range(len(result)):
    #     clientOrderId = result[i]['clientOrderId']
    #     orderTypeSymbol = clientOrderId.split("_")[0]
    #     if orderTypeSymbol=="shortsStopLoss" or orderTypeSymbol=="longsStopLoss":
    #         stopLossOrderIDArr.append(clientOrderId)

    # for i in range(len(stopLossOrderIDArr)):
    #     try:
    #         request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    #         result = request_client.cancel_order(symbol=symbol,orderId=stopLossOrderIDArr[i])
    #     except Exception as e:
    #         try:
    #             request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    #             result = request_client.cancel_order(symbol=symbol,orderId=stopLossOrderIDArr[i])
    #         except Exception as e:
    #             print(e)

    stopLossPrice = 0
    if stopLossType=="time":
        timeIndex = stopLossParaArr[1]
        stopLossPrice = getStopLossPriceByTime(symbol,stopLossParaArr[0],positionDirection)*timeIndex
    elif stopLossType=="price":
        stopLossPrice = float(stopLossParaArr[0])

    stopLossPrice =  decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (stopLossPrice))
    orderResultArr = []
    positionSide = OrderSide.BUY
    if positionDirection =="longs":
        positionSide = OrderSide.SELL
    orderCount = math.ceil(coinAmount/marketMaxSize)
    if orderCount>10:
        resp = json.dumps({'s':'tooMuchPosition','marketMaxSize':marketMaxSize,'symbol':symbol})
        response.set_header('Access-Control-Allow-Origin', '*')
        return resp
    if orderCount==1:
        coinAmount =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount ))
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = positionDirection+"StopLoss_s_"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_auto_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=coinAmount,side=positionSide, ordertype=OrderType.STOP_MARKET, stopPrice=stopLossPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        orderResultArr.append(result)
    else:
        for i in range(orderCount):
            ORDER_ID_INDEX = ORDER_ID_INDEX+1
            newClientOrderId = positionDirection+"StopLoss_s_"+str(ORDER_ID_INDEX)
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            try:
                result = request_client.post_auto_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=marketMaxSize,side=positionSide, ordertype=OrderType.STOP_MARKET, stopPrice=stopLossPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
            except Exception as e:
                resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
                response.set_header('Access-Control-Allow-Origin', '*')
                return resp
            result = json.loads(result)
            orderResultArr.append(result)
    resp = json.dumps({'s':'ok','resultArr':orderResultArr,'symbol':symbol,"stopLossType":stopLossType})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/stop_profit_batch', methods='POST')
def stop_profit_batch():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX,MARKET_MAX_SIZE_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    coinAmount = float(request.forms.get('coinAmount'))
    positionDirection =  str(request.forms.get('positionDirection'))
    stopProfitPriceArr =  json.loads(request.forms.get('stopProfitPriceArr'))

    now = int(time.time())
    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]

    request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stopProfitOrderIDArr = []

    for i in range(len(result)):
        clientOrderId = result[i]['clientOrderId']
        orderTypeSymbol = clientOrderId.split("_")[0]
        if orderTypeSymbol=="shortsStopProfit" or orderTypeSymbol=="longsStopProfit":
            stopProfitOrderIDArr.append(clientOrderId)

    for i in range(len(stopProfitOrderIDArr)):
        try:
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            result = request_client.cancel_order(symbol=symbol,orderId=stopProfitOrderIDArr[i])
        except Exception as e:
            try:
                request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
                result = request_client.cancel_order(symbol=symbol,orderId=stopProfitOrderIDArr[i])
            except Exception as e:
                print(e)

    stopProfitCoinQuantity =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount/len(stopProfitPriceArr) ))

    if stopProfitCoinQuantity>marketMaxSize:
        resp = json.dumps({'s':'tooMuchPosition','marketMaxSize':marketMaxSize,'symbol':symbol})
        response.set_header('Access-Control-Allow-Origin', '*')
        return resp

    orderResultArr = []
    positionSide = OrderSide.BUY
    if positionDirection =="longs":
        positionSide = OrderSide.SELL

    someOrderTimeOut = False
    for i in range(len(stopProfitPriceArr)):
        stopProfitPrice =  decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (stopProfitPriceArr[i]))
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = positionDirection+"StopProfit_s_"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        if i==len(stopProfitPriceArr)-1:
            stopProfitCoinQuantity  =  coinAmount - float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount/len(stopProfitPriceArr) )))*(len(stopProfitPriceArr)-1)
            stopProfitCoinQuantity = decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (stopProfitCoinQuantity ))
        try:
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=stopProfitCoinQuantity,side=positionSide, ordertype=OrderType.LIMIT, price=stopProfitPrice, positionSide="BOTH", timeInForce=TimeInForce.GTX)
        except Exception as e:
            someOrderTimeOut = True
        result = json.loads(result)
        orderResultArr.append(result)

    resp = json.dumps({'s':'ok','resultArr':orderResultArr,'symbol':symbol,'someOrderTimeOut':someOrderTimeOut})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/stop_profit_once', methods='POST')
def stop_profit_once():
    global API_OBJ,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,RECENT_ORDERS_OBJ,ORDER_ID_INDEX,MARKET_MAX_SIZE_OBJ
    apiKey = str(request.forms.get('apiKey'))
    updateAPIObj(apiKey)
    symbol = str(request.forms.get('symbol'))
    coinAmount = float(request.forms.get('coinAmount'))
    stopProfitType = str(request.forms.get('stopProfitType'))
    stopProfitParaArr =  json.loads(request.forms.get('stopProfitParaArr'))
    positionDirection =  str(request.forms.get('positionDirection'))

    now = int(time.time())
    marketMaxSize = MARKET_MAX_SIZE_OBJ[symbol]

    request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stopProfitOrderIDArr = []

    for i in range(len(result)):
        clientOrderId = result[i]['clientOrderId']
        orderTypeSymbol = clientOrderId.split("_")[0]
        if orderTypeSymbol=="shortsStopProfit" or orderTypeSymbol=="longsStopProfit":
            stopProfitOrderIDArr.append(clientOrderId)

    for i in range(len(stopProfitOrderIDArr)):
        try:
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            result = request_client.cancel_order(symbol=symbol,orderId=stopProfitOrderIDArr[i])
        except Exception as e:
            try:
                request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
                result = request_client.cancel_order(symbol=symbol,orderId=stopProfitOrderIDArr[i])
            except Exception as e:
                print(e)

    stopProfitPrice = 0
    if stopProfitType=="time":
        timeIndex = stopProfitParaArr[1]
        stopProfitPrice = getStopProfitPriceByTime(symbol,stopProfitParaArr[0],positionDirection)*timeIndex
    elif stopProfitType=="price":
        stopProfitPrice = float(stopProfitParaArr[0])

    stopProfitPrice =  decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (stopProfitPrice))
    orderResultArr = []
    positionSide = OrderSide.BUY
    if positionDirection =="longs":
        positionSide = OrderSide.SELL
    orderCount = math.ceil(coinAmount/marketMaxSize)
    if orderCount>10:
        resp = json.dumps({'s':'tooMuchPosition','marketMaxSize':marketMaxSize,'symbol':symbol})
        response.set_header('Access-Control-Allow-Origin', '*')
        return resp
    if orderCount==1:
        coinAmount =  decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (coinAmount ))
        ORDER_ID_INDEX = ORDER_ID_INDEX+1
        newClientOrderId = positionDirection+"StopProfit_s_"+str(ORDER_ID_INDEX)
        request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
        try:
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=coinAmount,side=positionSide, ordertype=OrderType.LIMIT, price=stopProfitPrice, positionSide="BOTH", timeInForce=TimeInForce.GTX)
        except Exception as e:
            resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
            response.set_header('Access-Control-Allow-Origin', '*')
            return resp
        result = json.loads(result)
        orderResultArr.append(result)
    else:
        for i in range(orderCount):
            ORDER_ID_INDEX = ORDER_ID_INDEX+1
            newClientOrderId = positionDirection+"StopProfit_s_"+str(ORDER_ID_INDEX)
            request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
            try:
                result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=True,symbol=symbol, quantity=marketMaxSize,side=positionSide, ordertype=OrderType.LIMIT, price=stopProfitPrice, positionSide="BOTH", timeInForce=TimeInForce.GTX)
            except Exception as e:
                resp = json.dumps({'s':'timeout','t':tradeType,"i":symbol})
                response.set_header('Access-Control-Allow-Origin', '*')
                return resp
            result = json.loads(result)
            orderResultArr.append(result)
    resp = json.dumps({'s':'ok','resultArr':orderResultArr,'symbol':symbol,"stopProfitType":stopProfitType})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

def takeElemTime(elem):
    return float(elem["time"])

LAST_RECORD_TS = 0
RECORD_LOCK = False
@post('/r', methods='POST')
def r():
    global API_OBJ,LAST_RECORD_TS,RECORD_LOCK
    now = int(time.time())
    if now - LAST_RECORD_TS>=9:
        if now - LAST_RECORD_TS>=300 or (not RECORD_LOCK):
            RECORD_LOCK = True
            LAST_RECORD_TS= now
            apiKey = str(request.forms.get('apiKey'))
            updateAPIObj(apiKey)
            with FUNCTION_CLIENT.get_session() as session:
                lastBinanceTsData = session.exec(
                    select(Income)
                    .where(Income.api_key == apiKey)
                    .order_by(Income.id.desc())
                    .limit(100)
                ).all()

            lastBinanceTs = 0
            if len(lastBinanceTsData)>0:
                lastBinanceTs = lastBinanceTsData[0].binance_ts

            result= []
            try:
                request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)
            except Exception as e:
                request_client = RequestClient(api_key=apiKey,secret_key=API_OBJ[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)

            result.sort(key=takeElemTime,reverse=False)
            bnbPrice = getFutureNowPriceByDepth("BNBUSDT")

            for i in range(len(result)):
                trade_id = str(result[i]['tradeId'])
                binance_ts = str(result[i]['time'])
                incomeType = str(result[i]['incomeType'])
                income = str(result[i]['income'])
                asset = str(result[i]['asset'])
                info = str(result[i]['info'])

                symbol = str(result[i]['symbol'])
                if incomeType=="COMMISSION" or incomeType=="REALIZED_PNL":
                    isExit = False
                    for b in range(len(lastBinanceTsData)):
                        if int(result[i]['time'])<lastBinanceTs or ((str(int(lastBinanceTsData[b].binance_ts))==str(int(binance_ts))) and (str(lastBinanceTsData[b].income_type) == str(incomeType)) and (format(float(lastBinanceTsData[b].income),'.8f') == format(float(income),'.8f')) and (str(lastBinanceTsData[b].asset) == str(asset)) and (str(lastBinanceTsData[b].trade_id) == str(trade_id))):
                            isExit = True
                    if not isExit:
                        commission = 0
                        if incomeType=="COMMISSION":
                            if asset=="BNB":
                                if float(income)<0:
                                    commission = abs(float(income)*bnbPrice*0.1)
                                else:
                                    commission = abs(float(income)*bnbPrice*0.05)
                            else:
                                if float(income)<0:
                                    commission = abs(float(income)*0.1)
                                else:
                                    commission = abs(float(income)*0.05)

                        with FUNCTION_CLIENT.get_session() as session:
                            new_income = Income(
                                access_token=str(apiKey),
                                api_key=str(apiKey),
                                income_type=str(incomeType),
                                income=decimal.Decimal(str(income)),
                                asset=str(asset),
                                trade_id=trade_id,
                                binance_ts=int(binance_ts),
                                symbol=symbol,
                                bnb_price=decimal.Decimal(str(bnbPrice)),
                                commission=decimal.Decimal(str(commission)),
                            )
                            session.add(new_income)
                            session.commit()
            RECORD_LOCK = False
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

UPDATE_DAY_INCOME_TS = 0

def updateDayIncome():
    global UPDATE_DAY_INCOME_TS
    print("update_day_income")
    now = int(time.time())
    if now - UPDATE_DAY_INCOME_TS>30:
        UPDATE_DAY_INCOME_TS = now

        with FUNCTION_CLIENT.get_session() as session:
            latestDay = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.desc()).limit(1)
            ).first()

        initIncomeDayTime = "2022-11-20 00:00:00"
        initIncomeDayTs = FUNCTION_CLIENT.turn_ts_to_time(initIncomeDayTime)
        lastIncomeDayTs = 0
        if latestDay is not None:
            lastIncomeDayTs = FUNCTION_CLIENT.turn_ts_to_time(latestDay.day_begin_time)
        if lastIncomeDayTs==0:
            lastIncomeDayTs= initIncomeDayTs
        nowTs = int(time.time())
        todayTs = nowTs-nowTs%86400

        needInsertDay = int((todayTs - lastIncomeDayTs) /86400)
        print("todayTs:"+str(todayTs))
        print("lastIncomeDayTs:"+str(lastIncomeDayTs))
        for i in range(needInsertDay):
            endDayTs = lastIncomeDayTs+86400*(i+1)
            beginDayTs = lastIncomeDayTs+86400*i
            with FUNCTION_CLIENT.get_session() as session:
                incomeData = session.exec(
                    select(Income)
                    .where(Income.binance_ts > beginDayTs*1000)
                    .where(Income.binance_ts <= endDayTs*1000)
                ).all()
            dayBinanceCommission = 0
            dayZjyCommission = 0
            dayPnl = 0
            for item in incomeData:
                if item.income_type=="COMMISSION":
                    if item.asset=="BNB":
                        dayBinanceCommission = dayBinanceCommission+item.income*item.bnb_price
                    elif item.asset=="USDT" or item.asset=="BUSD":
                        dayBinanceCommission = dayBinanceCommission+item.income
                elif item.income_type=="REALIZED_PNL":
                    if item.asset=="BNB":
                        dayPnl = dayPnl+item.income*item.bnb_price
                    elif item.asset=="USDT" or item.asset=="BUSD":
                        dayPnl = dayPnl+item.income
                dayZjyCommission = dayZjyCommission+item.commission

            print(FUNCTION_CLIENT.turn_ts_to_time(beginDayTs))
            with FUNCTION_CLIENT.get_session() as session:
                existingDay = session.exec(
                    select(IncomeDay).where(IncomeDay.day_begin_time == FUNCTION_CLIENT.turn_ts_to_time(beginDayTs))
                ).first()
                if existingDay is None:
                    newDay = IncomeDay(
                        api_key="",
                        day_begin_time=FUNCTION_CLIENT.turn_ts_to_time(beginDayTs),
                        day_end_time=FUNCTION_CLIENT.turn_ts_to_time(endDayTs),
                        binance_commission=dayBinanceCommission,
                        pnl=dayPnl,
                        zjy_commission=dayZjyCommission,
                    )
                    session.add(newDay)
                    session.commit()
                else:
                    existingDay.binance_commission = dayBinanceCommission
                    existingDay.pnl = dayPnl
                    existingDay.zjy_commission = dayZjyCommission
                    session.add(existingDay)
                    session.commit()


GET_DAY_INCOME_TS = 0
GET_DAY_INCOME_TODAY_TS = 0
DAY_INCOME_DATA = []
@post('/get_day_income', methods='POST')
def get_day_income():
    global GET_DAY_INCOME_TS,DAY_INCOME_DATA,GET_DAY_INCOME_TODAY_TS,INCOME_OBJ
    now = int(time.time())
    todayTime = datetime.datetime.utcnow().strftime("%Y-%m-%d")+" 00:00:00"
    todayTs = FUNCTION_CLIENT.turn_ts_to_time(todayTime)
    isUpdate = 0
    print("------------a--------------")
    if now - GET_DAY_INCOME_TS>300 or GET_DAY_INCOME_TODAY_TS!=todayTs:
        updateDayIncome()
        print("------------b--------------")

        isUpdate = 1
        GET_DAY_INCOME_TODAY_TS = todayTs
        GET_DAY_INCOME_TS= now
        with FUNCTION_CLIENT.get_session() as session:
            dayIncomeData = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.asc())
            ).all()
        DAY_INCOME_DATA = []
        allNetProfit = 0
        for item in dayIncomeData:
            if FUNCTION_CLIENT.turn_ts_to_time(item.day_begin_time) !=todayTs:
                DAY_INCOME_DATA.append({'allNetProfit':0,'dayBeginTime':item.day_begin_time,'dayEndTime':item.day_end_time,'binanceCommission':item.binance_commission,'netProfit':item.pnl+item.binance_commission,'profit':item.pnl,'zjyCommission':item.zjy_commission})

    if FUNCTION_CLIENT.turn_ts_to_time(DAY_INCOME_DATA[len(DAY_INCOME_DATA)-1]["dayBeginTime"]) !=todayTs:
        DAY_INCOME_DATA.append({'allNetProfit':0,'dayBeginTime':FUNCTION_CLIENT.turn_ts_to_time(todayTs),'dayEndTime':FUNCTION_CLIENT.turn_ts_to_time(todayTs+86400),'binanceCommission':INCOME_OBJ["today"]["c"],'netProfit':INCOME_OBJ["today"]["c"]+INCOME_OBJ["today"]["p"],'profit':INCOME_OBJ["today"]["p"],'zjyCommission':INCOME_OBJ["today"]["s"]})
    else:
        print(INCOME_OBJ)
        DAY_INCOME_DATA[len(DAY_INCOME_DATA)-1] = {'allNetProfit':0,'dayBeginTime':FUNCTION_CLIENT.turn_ts_to_time(todayTs),'dayEndTime':FUNCTION_CLIENT.turn_ts_to_time(todayTs+86400),'binanceCommission':INCOME_OBJ["today"]["c"],'netProfit':INCOME_OBJ["today"]["c"]+INCOME_OBJ["today"]["p"],'profit':INCOME_OBJ["today"]["p"],'zjyCommission':INCOME_OBJ["today"]["s"]}

    resp = json_dumps({'s':'ok','d':DAY_INCOME_DATA,'u':isUpdate})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

ONE_MIN_UPDATE_TS = 0
ONE_MIN_KLINE = []
@post('/get_one_min_select_kline', methods='POST')
def get_one_min_select_kline():
    global ONE_MIN_UPDATE_TS,ONE_MIN_KLINE
    now = int(time.time()*1000)
    if now - ONE_MIN_UPDATE_TS>=100:
        ONE_MIN_UPDATE_TS = now
        symbol = str(request.forms.get('symbol'))
        klineArr =getKline(symbol,"1m",3)
        ONE_MIN_KLINE = klineArr
    resp = json.dumps({'s':'ok','k':ONE_MIN_KLINE})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_position_record', methods='POST')
def get_position_record():
    symbol = str(request.forms.get('symbol'))
    beginTs = int(request.forms.get('beginTs'))
    endTs = int(request.forms.get('endTs'))

    with FUNCTION_CLIENT.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol != "ALL":
            stmt = stmt.where(PositionRecord.symbol == symbol)
        positionRecordData = session.exec(stmt).all()
    positionRecordObjArr = []
    for row in positionRecordData:
        positionRecordObjArr.append({
                "positionAmt":row.position_amt,
                "price":None,
                "positionValue":row.position_value,
                "balance":row.balance,
                "time":row.time,
                "profit":row.profit,
                "commission":row.commission,
                "makerCommission":row.maker_commission,
                "entryPrice":None,
                "unrealizedProfit":row.unrealized_profit,
                "maintMargin":None
            })


    resp = json.dumps({'s':'ok','d':positionRecordObjArr,'symbol':symbol})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_history_position_record', methods='POST')
def get_history_position_record():
    symbol = str(request.forms.get('tableName'))
    beginTs = int(request.forms.get('beginTs'))
    endTs = int(request.forms.get('endTs'))

    # Consolidated: history records now live in position_record (no production data)
    with FUNCTION_CLIENT.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol != "ALL" and symbol != "":
            stmt = stmt.where(PositionRecord.symbol == symbol)
        positionRecordData = session.exec(stmt).all()
    positionRecordObjArr = []
    for row in positionRecordData:
        positionRecordObjArr.append({
                "positionAmt":row.position_amt,
                "price":None,
                "positionValue":row.position_value,
                "balance":row.balance,
                "time":row.time,
                "profit":row.profit,
                "commission":row.commission,
                "makerCommission":row.maker_commission
            })


    resp = json.dumps({'s':'ok','d':positionRecordObjArr})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

CUSTOMIZE_DANGEROUS_DATA_ARR = []
CUSTOMIZE_DANGEROUS_DATA_ARR_UPDATE_TS = 0
TRADE_SERVER_STATUS_DATA = []
UPDATE_TRADE_SERVER_STATUS_DATA_TS = 0
def updateTradeServerStatusData():
    global TRADE_SERVER_STATUS_DATA,UPDATE_TRADE_SERVER_STATUS_DATA_TS
    now = int(time.time())
    if now - UPDATE_TRADE_SERVER_STATUS_DATA_TS>5:
        UPDATE_TRADE_SERVER_STATUS_DATA_TS = now
        with FUNCTION_CLIENT.get_session() as session:
            rows = session.exec(select(TradeServerStatus)).all()
        TRADE_SERVER_STATUS_DATA = []
        for item in rows:
            extraPara = json.loads(item.extra_para) if item.extra_para else {}
            TRADE_SERVER_STATUS_DATA.append({
                    "extraPara":extraPara,
                    "runInfo":json.loads(item.run_info) if item.run_info else {},
                    "symbol":item.symbol,
                    "privateIP":item.private_ip,
                    "name":item.name,
                    "mySymbol":item.my_symbol,
                    "updateTs":item.update_ts,
                    "updateTime":item.update_time,
                    "customizeDangerousData":extraPara
                })

@post('/check_maker_server_in_data', methods='POST')
def check_maker_server_in_data():
    name = str(request.forms.get('name'))
    privateIP = str(request.forms.get('privateIP'))
    symbol = str(request.forms.get('symbol'))
    mySymbol = str(request.forms.get('mySymbol'))
    with FUNCTION_CLIENT.get_session() as session:
        existing = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            extraPara = {"customizeDangerous": 0}
            new_row = TradeServerStatus(
                private_ip=privateIP,
                name=name,
                extra_para=json.dumps(extraPara),
                symbol=symbol,
                my_symbol=mySymbol,
            )
            session.add(new_row)
            session.commit()
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/update_maker_server_run_info', methods='POST')
def update_maker_server_run_info():
    global TRADE_SERVER_STATUS_DATA
    privateIP = str(request.forms.get('privateIP'))
    dangerousClass = str(request.forms.get('dangerousClass'))
    dangerousName = str(request.forms.get('dangerousName'))
    direction = str(request.forms.get('direction'))
    longsOnceTradeValue = float(request.forms.get('longsOnceTradeValue'))
    shortsOnceTradeValue = float(request.forms.get('shortsOnceTradeValue'))
    longsBollTimeAmount = float(request.forms.get('longsBollTimeAmount'))
    shortsBollTimeAmount = float(request.forms.get('shortsBollTimeAmount'))
    positionValue = float(request.forms.get('positionValue'))
    runInfo = {
        "dangerousClass":dangerousClass,
        "dangerousName":dangerousName,
        "longsOnceTradeValue":longsOnceTradeValue,
        "shortsOnceTradeValue":shortsOnceTradeValue,
        "longsBollTimeAmount":longsBollTimeAmount,
        "shortsBollTimeAmount":shortsBollTimeAmount,
        "positionValue":positionValue,
        "direction":direction
    }
    now = int(time.time())
    symbol = str(request.forms.get('symbol'))
    with FUNCTION_CLIENT.get_session() as session:
        db_row = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).first()
        if db_row is not None:
            db_row.run_info = json.dumps(runInfo)
            db_row.update_ts = now
            db_row.update_time = FUNCTION_CLIENT.turn_ts_to_time(now)
            session.add(db_row)
            session.commit()
    updateTradeServerStatusData()
    customizeDangerousData = {"customizeDangerous":0}
    print(privateIP)
    for a in range(len(TRADE_SERVER_STATUS_DATA)):
        if TRADE_SERVER_STATUS_DATA[a]["privateIP"]==privateIP:
            customizeDangerousData = TRADE_SERVER_STATUS_DATA[a]["customizeDangerousData"]
            break

    resp = json.dumps({'s':'ok','customizeDangerous':customizeDangerousData["customizeDangerous"]})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_customize_dangerous', methods='POST')
def get_customize_dangerous():
    global CUSTOMIZE_DANGEROUS_DATA_ARR,CUSTOMIZE_DANGEROUS_DATA_ARR_UPDATE_TS,TRADE_SERVER_STATUS_DATA
    SYMBOL_ARR = ["ETHUSDT","BTCUSDT"]
    now = int(time.time())
    updateTradeServerStatusData()
    if now - CUSTOMIZE_DANGEROUS_DATA_ARR_UPDATE_TS>5:
        CUSTOMIZE_DANGEROUS_DATA_ARR_UPDATE_TS= now
        customizeDangerousDataArr = []
        for a in range(len(SYMBOL_ARR)):
            for b in range(len(TRADE_SERVER_STATUS_DATA)):
                if TRADE_SERVER_STATUS_DATA[b]["symbol"]==SYMBOL_ARR[a]:
                    customizeDangerousData = TRADE_SERVER_STATUS_DATA[b]["customizeDangerousData"]
                    runInfo = TRADE_SERVER_STATUS_DATA[b]["runInfo"]
                    customizeDangerousDataArr.append({
                        'customizeDangerous':customizeDangerousData["customizeDangerous"],'dangerousName':runInfo["dangerousName"],'dangerousClass':runInfo["dangerousClass"],'symbol':TRADE_SERVER_STATUS_DATA[b]["symbol"]
                    })
        CUSTOMIZE_DANGEROUS_DATA_ARR = customizeDangerousDataArr
    resp = json.dumps({'s':'ok','customizeDangerousDataArr':CUSTOMIZE_DANGEROUS_DATA_ARR})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/update_customize_dangerous', methods='POST')
def update_customize_dangerous():
    customizeDangerous = int(request.forms.get('customizeDangerous'))
    symbol = str(request.forms.get('symbol'))

    extraInfo = json.dumps({"customizeDangerous": customizeDangerous})
    with FUNCTION_CLIENT.get_session() as session:
        if symbol == "all":
            rows = session.exec(select(TradeServerStatus)).all()
        else:
            rows = session.exec(
                select(TradeServerStatus).where(TradeServerStatus.symbol == symbol)
            ).all()
        for row in rows:
            row.extra_para = extraInfo
            session.add(row)
        session.commit()
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

ALL_OPEN_ORDERS_ARR = []

@post('/get_all_open_orders_b', methods='POST')
def get_all_open_orders_b():
    global NEW_API_OBJ
    symbol = str(request.forms.get('symbol'))
    now  = int(time.time()*1000)
    result = {}
    request_client = RequestClient(api_key=NEW_API_OBJ[symbol]["apiKey"],secret_key=NEW_API_OBJ[symbol]["apiSecret"])
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    resp = json.dumps({'s':'ok','r':result,'t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_position', methods='POST')
def get_position():
    global NEW_API_OBJ
    symbol = str(request.forms.get('symbol'))
    positionsArr = []
    now  = int(time.time()*1000)
    result = {}
    request_client = RequestClient(api_key=NEW_API_OBJ[symbol]["apiKey"],secret_key=NEW_API_OBJ[symbol]["apiSecret"])
    result = request_client.get_account_information()
    result = json.loads(result)
    for i in range(len(result["positions"])):
        if float(result["positions"][i]["positionAmt"])!=0:
            positionsArr.append(result["positions"][i])

    resp = json.dumps({'s':'ok','r':positionsArr,'t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_trade_record', methods='POST')
def get_trade_record():
    global NEW_API_OBJ
    symbol = str(request.forms.get('symbol'))
    now  = int(time.time()*1000)
    result = {}
    request_client = RequestClient(api_key=NEW_API_OBJ[symbol]["apiKey"],secret_key=NEW_API_OBJ[symbol]["apiSecret"])
    result = request_client.get_account_trades(symbol)
    result = json.loads(result)
    resp = json.dumps({'s':'ok','r':result,'t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_all_acount_info', methods='POST')
def get_all_acount_info():
    allBalance = 0
    allPosition = 0
    # Sum latest positionValue and balance per symbol from the consolidated table
    from sqlalchemy import func
    with FUNCTION_CLIENT.get_session() as session:
        subq = select(func.max(PositionRecord.id)).group_by(PositionRecord.symbol).scalar_subquery()
        positionRecordData = session.exec(
            select(PositionRecord).where(PositionRecord.id.in_(subq))
        ).all()
    for row in positionRecordData:
        allPosition = allPosition + (row.position_value or 0)
        allBalance = allBalance + (row.balance or 0)
    resp = json.dumps({'s':'ok','b':allBalance,'p':allPosition,'t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

GET_LOSS_LIMIT_TIME_DATA_TS = 0
LOSS_LIMIT_TIME_DATA_ARR = []
def getLossLimitTimeData(forceUpdate):
    global GET_LOSS_LIMIT_TIME_DATA_TS,LOSS_LIMIT_TIME_DATA_ARR
    now = int(time.time())
    if (now - GET_LOSS_LIMIT_TIME_DATA_TS>60) or forceUpdate:
        GET_LOSS_LIMIT_TIME_DATA_TS = now
        with FUNCTION_CLIENT.get_session() as session:
            lossLimitTimeData = session.exec(select(LossLimitTime)).all()
        LOSS_LIMIT_TIME_DATA_ARR = []
        for row in lossLimitTimeData:
            LOSS_LIMIT_TIME_DATA_ARR.append({
                    "symbol":row.symbol,
                    "limitTime":row.limit_time
                })

ETH_1M_KLINE_ARR = []

BTC_1M_KLINE_ARR = []

ETH_TODAY_BEGIN_PRICE = {"price":0,"updateTs":0}

BTC_TODAY_BEGIN_PRICE = {"price":0,"updateTs":0}

TICK_ARR = []

UPDATE_BINANCE_DATA_TS = 0

def updateBinanceData():
    global TICK_ARR,ETH_1M_KLINE_ARR,BTC_1M_KLINE_ARR,UPDATE_BINANCE_DATA_TS,ETH_TODAY_BEGIN_PRICE,BTC_TODAY_BEGIN_PRICE
    now = int(time.time())
    if now - UPDATE_BINANCE_DATA_TS >= 1:
        UPDATE_BINANCE_DATA_TS = now
        try:
            klineAmount = 99
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=ETHUSDT&interval=1m&limit="+str(klineAmount)
            ethKlineData = requests.request("GET", url,timeout=(1,1),headers={}).json()
            if len(ethKlineData)==klineAmount:
                ETH_1M_KLINE_ARR =  ethKlineData
        except Exception as e:
            print(e)

        try:
            klineAmount = 99
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit="+str(klineAmount)
            btcKlineData = requests.request("GET", url,timeout=(1,1),headers={}).json()
            if len(btcKlineData)==klineAmount:
                BTC_1M_KLINE_ARR =  btcKlineData
        except Exception as e:
            print(e)

        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            tickArr = requests.request("GET", url,timeout=(1,1)).json()
            if len(tickArr)>100:
                TICK_ARR =  tickArr
        except Exception as e:
            print(e)
    # todayBeginTs=int(time.mktime(datetime.date.today().timetuple()))
    # if ETH_TODAY_BEGIN_PRICE["updateTs"]!=todayBeginTs:
    #     try:
    #         klineAmount = 99
    #         url = "https://fapi.binance.com/fapi/v1/klines?symbol=ETHUSDT&interval=1h&limit="+str(klineAmount)
    #         ethKlineData = requests.request("GET", url,timeout=(1,1),headers={}).json()
    #         if len(ethKlineData)==klineAmount:
    #             for i in range(len(ethKlineData)):
    #                 if int(ethKlineData[i][0])==int(todayBeginTs*1000):
    #                     ETH_TODAY_BEGIN_PRICE["price"]= float(ethKlineData[i][1])
    #                     ETH_TODAY_BEGIN_PRICE["updateTs"]=todayBeginTs
    #     except Exception as e:
    #         print(e)
    # if BTC_TODAY_BEGIN_PRICE["updateTs"]!=todayBeginTs:
    #     try:
    #         klineAmount = 99
    #         url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit="+str(klineAmount)
    #         btcKlineData = requests.request("GET", url,timeout=(1,1),headers={}).json()
    #         if len(btcKlineData)==klineAmount:
    #             for i in range(len(btcKlineData)):
    #                 if int(btcKlineData[i][0])==int(todayBeginTs*1000):
    #                     BTC_TODAY_BEGIN_PRICE["price"]= float(btcKlineData[i][1])
    #                     BTC_TODAY_BEGIN_PRICE["updateTs"]=todayBeginTs
    #     except Exception as e:
    #         print(e)

ETH_TURN_PRICE = 0

BTC_TURN_PRICE = 0


TURN_PRICE_UPDATE_TS = 0

ETH_TURN_TS = 0

BTC_TURN_TS = 0


def updateTurnPrice():
    global ETH_TURN_PRICE,BTC_TURN_PRICE,TURN_PRICE_UPDATE_TS,ETH_TURN_TS,BTC_TURN_TS
    now = int(time.time())
    for key in NEW_API_OBJ:
        if now - TURN_PRICE_UPDATE_TS>60:
            TURN_PRICE_UPDATE_TS = now
            with FUNCTION_CLIENT.get_session() as session:
                ethLatest = session.exec(
                    select(PositionRecord).where(PositionRecord.symbol == "ETHUSDT").order_by(PositionRecord.id.desc()).limit(1)
                ).first()
                if ethLatest:
                    positionAmt = ethLatest.position_amt or 0
                    if positionAmt > 0:
                        lastTurn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == "ETHUSDT", PositionRecord.position_amt < 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                        if lastTurn:
                            ETH_TURN_PRICE = 0
                            ETH_TURN_TS = lastTurn.ts
                    if positionAmt <= 0:
                        lastTurn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == "ETHUSDT", PositionRecord.position_amt > 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                        if lastTurn:
                            ETH_TURN_PRICE = 0
                            ETH_TURN_TS = lastTurn.ts

                btcLatest = session.exec(
                    select(PositionRecord).where(PositionRecord.symbol == "BTCUSDT").order_by(PositionRecord.id.desc()).limit(1)
                ).first()
                if btcLatest:
                    positionAmt = btcLatest.position_amt or 0
                    if positionAmt > 0:
                        lastTurn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == "BTCUSDT", PositionRecord.position_amt < 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                        if lastTurn:
                            BTC_TURN_PRICE = 0
                            BTC_TURN_TS = lastTurn.ts
                    if positionAmt <= 0:
                        lastTurn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == "BTCUSDT", PositionRecord.position_amt > 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                        if lastTurn:
                            BTC_TURN_PRICE = 0
                            BTC_TURN_TS = lastTurn.ts


WATCH_INFO_UPDATE_TS = 0
WATCH_INFO_OBJ = {}
@post('/get_watch_info', methods='POST')
def get_watch_info():
    global WATCH_INFO_OBJ,WATCH_INFO_UPDATE_TS,BTC_TURN_TS,ETH_TURN_TS,ETH_TURN_PRICE_UPDATE_TS,BTC_TURN_PRICE_UPDATE_TS,NEW_API_OBJ,TRADE_SERVER_STATUS_DATA,LOSS_LIMIT_TIME_DATA_ARR,TICK_ARR,ETH_1M_KLINE_ARR,BTC_1M_KLINE_ARR,ETH_TODAY_BEGIN_PRICE,BTC_TODAY_BEGIN_PRICE,BTC_TURN_PRICE,ETH_TURN_PRICE
    now = int(time.time())
    if now - WATCH_INFO_UPDATE_TS>=60:
        WATCH_INFO_UPDATE_TS = now
        updateBinanceData()
        allPositionArr = []
        updateTradeServerStatusData()
        updateTurnPrice()
        for key in NEW_API_OBJ:
            dayBeginBalaneUpdateTime = FUNCTION_CLIENT.turn_ts_to_day_time(now)
            if dayBeginBalaneUpdateTime!=NEW_API_OBJ[key]["dayBeginBalaneUpdateTime"]:
                zeroPoint = FUNCTION_CLIENT.turn_ts_to_time(dayBeginBalaneUpdateTime)
                with FUNCTION_CLIENT.get_session() as session:
                    firstRow = session.exec(
                        select(PositionRecord).where(PositionRecord.ts >= zeroPoint).order_by(PositionRecord.id.asc()).limit(1)
                    ).first()
                if firstRow:
                    NEW_API_OBJ[key]["dayBeginBalane"] = firstRow.balance
                    NEW_API_OBJ[key]["dayBeginBalaneUpdateTime"] = dayBeginBalaneUpdateTime

            thisIP = NEW_API_OBJ[key]["positionIP"]
            thisKey = NEW_API_OBJ[key]["apiKey"]
            mySymbol = NEW_API_OBJ[key]["mySymbol"]
            dayBeginBalane = NEW_API_OBJ[key]["dayBeginBalane"]
            symbol = NEW_API_OBJ[key]["symbol"]

            getLossLimitTimeData(False)
            thisLossLimitTime = ""
            for i in range(len(LOSS_LIMIT_TIME_DATA_ARR)):
                if LOSS_LIMIT_TIME_DATA_ARR[i]["symbol"]==symbol:
                    thisLossLimitTime = LOSS_LIMIT_TIME_DATA_ARR[i]["limitTime"]
                    break
            if thisLossLimitTime=="":
                with FUNCTION_CLIENT.get_session() as session:
                    session.add(LossLimitTime(symbol=symbol, limit_time="2023-03-28 01:00:00"))
                    session.commit()
                getLossLimitTimeData(True)

            url = "http://"+thisIP+"/"+thisKey[0:10]+".json"
            print(thisIP)
            result = requests.request("GET", url,timeout=(0.25,0.25)).json()
            accountBalanceValue = result["balance"]

            for a in range(len(result["positionArr"])):
                thisPrice = 0
                for b in range(len(TICK_ARR)):
                    if TICK_ARR[b]["symbol"]==result["positionArr"][a]["symbol"]:
                        thisPrice = float(TICK_ARR[b]["price"])
                result["positionArr"][a]["balance"] = accountBalanceValue
                result["positionArr"][a]["mySymbol"] = mySymbol
                if mySymbol=="OTHER":
                    result["positionArr"][a]["mySymbol"] = result["positionArr"][a]["symbol"]+"_BINANCE"
                result["positionArr"][a]["price"] = thisPrice
                result["positionArr"][a]["dayBeginBalane"] = dayBeginBalane
                result["positionArr"][a]["updateTime"] = int(time.time()*1000)
                result["positionArr"][a]["tradeType"] = str(result["positionArr"][a]["entryPrice"])[-1]
                result["positionArr"][a]["entryPrice"] = 0
                result["positionArr"][a]["unrealizedProfit"] = 0
                result["positionArr"][a]["profitPercent"] = 0
                allPositionArr.append(result["positionArr"][a])

        WATCH_INFO_OBJ ={'s':'ok','balance':accountBalanceValue,'ethP':ETH_TURN_PRICE,'btcP':BTC_TURN_PRICE,'ethT':ETH_TURN_TS,'btcT':BTC_TURN_TS,'eth':ETH_1M_KLINE_ARR,'btc':BTC_1M_KLINE_ARR,'e':LOSS_LIMIT_TIME_DATA_ARR,'d':TRADE_SERVER_STATUS_DATA,'a':allPositionArr,'t':int(time.time())}

    resp = json_dumps(WATCH_INFO_OBJ)
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

# @post('/get_loss_limit_time', methods='POST')
# def get_loss_limit_time():


@post('/update_loss_limit_time', methods='POST')
def update_loss_limit_time():
    symbol = str(request.forms.get('symbol'))
    nowTime = FUNCTION_CLIENT.turn_ts_to_time(int(time.time()))
    nowTimeStr = str(nowTime) if not isinstance(nowTime, str) else nowTime
    with FUNCTION_CLIENT.get_session() as session:
        row = session.exec(select(LossLimitTime).where(LossLimitTime.symbol == symbol)).first()
        if row:
            row.limit_time = nowTimeStr
            session.add(row)
            session.commit()
    getLossLimitTimeData(True)
    resp = json.dumps({'s':'ok','t':int(time.time())})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_second_open_position', methods='POST')
def get_second_open_position():
    BINANCE_API_KEY ="bJpPkJe9kW8USXKDQuP2WKeSVaEIOM5wKT7Uta1ir2wmlAxNHN9hwrZDhjJCYcEd"
    thisIP = "172.24.207.4"
    url = "http://"+thisIP+"/"+BINANCE_API_KEY[0:10]+".json"
    result = requests.request("GET", url,timeout=(0.5,0.5)).json()
    resp = json.dumps({'s':'ok','t':int(time.time()),'r':result})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/get_invest_percent', methods='POST')
def get_invest_percent():
    investPercentObjArr = [

    {'name': '吴钊庆', 'time': '2023-05-19 14:59:00', 'percent': 12.206461839330702, 'initValue': 2800, 'assetsWhileJoin': 20138.67, 'investType': 'longs'},
    {'name': '一零二四', 'time': '2023-05-19 13:36:00', 'percent': 21.81179905448812, 'initValue': 5000, 'assetsWhileJoin': 15125.24, 'investType': 'longs'}, 
    {'name': '李', 'time': '2023-05-16 21:52:00', 'percent': 8.808005636839024, 'initValue': 2000, 'assetsWhileJoin': 12982.22, 'investType': 'longs'}, 
    {'name': 'michael', 'time': '2023-05-12 20:28:00', 'percent': 52.16531441742779, 'initValue': 10000, 'assetsWhileJoin': 959, 'investType': 'longs'}, 
    {'name': 'ming', 'time': '2023-05-09 00:00:00', 'percent': 5.008419051914373, 'initValue': 750, 'assetsWhileJoin': 0, 'investType': 'longs'}]




    for i in range(len(investPercentObjArr)):
        investPercentObjArr[i]["percent"] = int(investPercentObjArr[i]["percent"]*10000)/10000

    resp = json.dumps({'s':'ok','t':int(time.time()),'r':investPercentObjArr})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp



@post('/update_machine_status', methods='POST')
def update_machine_status():
    privateIP = str(request.forms.get('privateIP'))
    symbol = str(request.forms.get('symbol'))
    updateTs = int(time.time())

    with FUNCTION_CLIENT.get_session() as session:
        existing = session.exec(
            select(MachineStatus).where(MachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = MachineStatus(
                private_ip=privateIP,
                insert_ts=updateTs,
                update_ts=updateTs,
                symbol=symbol,
            )
            session.add(row)
        else:
            print(privateIP)
            existing[0].update_ts = updateTs
            session.add(existing[0])
        session.commit()

    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/update_trade_status', methods='POST')
def update_trade_status():
    privateIP = str(request.forms.get('privateIP'))
    status = str(request.forms.get('status'))
    runTime = str(request.forms.get('runTime'))
    updateTs = int(time.time())

    with FUNCTION_CLIENT.get_session() as session:
        existing = session.exec(
            select(TradeMachineStatus).where(TradeMachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = TradeMachineStatus(
                private_ip=privateIP,
                insert_ts=updateTs,
                update_ts=updateTs,
                status=status,
            )
            session.add(row)
        else:
            print(privateIP)
            existing[0].status = status
            existing[0].update_ts = updateTs
            existing[0].run_time = int(runTime)
            session.add(existing[0])
        session.commit()

    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

TRADE_MACHINE_STATUS_DATA = []
UPDATE_TRADE_MACHINE_STATUS_DATA_TS = 0
AVERAGE_RUN_TIME = 0
@post('/get_trade_status', methods='POST')
def get_trade_status():
    global TRADE_MACHINE_STATUS_DATA,UPDATE_TRADE_MACHINE_STATUS_DATA_TS,AVERAGE_RUN_TIME
    from sqlalchemy import asc as _asc
    now = int(time.time())
    if now - UPDATE_TRADE_MACHINE_STATUS_DATA_TS>60:
        UPDATE_TRADE_MACHINE_STATUS_DATA_TS = now
        with FUNCTION_CLIENT.get_session() as session:
            TRADE_MACHINE_STATUS_DATA = session.exec(
                select(TradeMachineStatus).order_by(_asc(TradeMachineStatus.update_ts))
            ).all()
        allRunTime = 0
        for item in TRADE_MACHINE_STATUS_DATA:
            allRunTime = allRunTime + (item.run_time or 0)
        AVERAGE_RUN_TIME = int(allRunTime/len(TRADE_MACHINE_STATUS_DATA))
    resp = json.dumps({'s':'ok','updateTs':TRADE_MACHINE_STATUS_DATA[0].update_ts,'status':TRADE_MACHINE_STATUS_DATA[0].status,'runTime':AVERAGE_RUN_TIME})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

SYMBOL_DATA_OBJ = {}

UPDATE_ONE_DAY_RATE_TS = 0

def takeQuotVolume(elem):
    return float(elem['quoteVolume'])

@post('/get_one_day_rate', methods='POST')
def get_one_day_rate():
    global UPDATE_ONE_DAY_RATE_TS,SYMBOL_DATA_OBJ
    now = int(time.time()*1000)
    if now - UPDATE_ONE_DAY_RATE_TS>=30*1000:
        binanceResponse = []
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            binanceResponse = requests.request("GET", url,timeout=(3,3)).json()
            binanceResponse.sort(key=takeQuotVolume,reverse=True)
        except Exception as e:
            print(e)
        if len(binanceResponse)>=100:
            SYMBOL_DATA_OBJ = {}
            for i in range(len(binanceResponse)):
                volIndex = 1
                if i<=15:
                    volIndex = 1.5
                elif i<=30:
                    volIndex = 1.4
                elif i<=45:
                    volIndex = 1.3
                elif i<=60:
                    volIndex = 1.2
                elif i<=75:
                    volIndex = 1.1
                SYMBOL_DATA_OBJ[binanceResponse[i]["symbol"]] = {
                    "oneDayWave":int(FUNCTION_CLIENT.get_percent_num(float(binanceResponse[i]["highPrice"])-float(binanceResponse[i]["lowPrice"]),float(binanceResponse[i]["lowPrice"]))),
                    "volRank":i,
                    "volIndex":volIndex,
                    "vol":float(binanceResponse[i]["quoteVolume"]),
                    "highPrice":float(binanceResponse[i]["highPrice"]),
                    "lowPrice":float(binanceResponse[i]["lowPrice"])
                }
        UPDATE_ONE_DAY_RATE_TS = now
    resp = json.dumps({'s':'ok','d':SYMBOL_DATA_OBJ})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

SYMBOL_CANCEL_ORDERS_TS_OBJ = {}
@post('/cancel_binance_orders', methods='POST')
def cancel_binance_orders():
    global SYMBOL_CANCEL_ORDERS_TS_OBJ
    key = str(request.forms.get('key'))
    secret = str(request.forms.get('secret'))
    symbol = str(request.forms.get('symbol'))

    now = int(time.time()*1000)
    needCancel = True
    if symbol in SYMBOL_CANCEL_ORDERS_TS_OBJ:
        if now - SYMBOL_CANCEL_ORDERS_TS_OBJ[symbol]<=3000:
            needCancel = False

    if needCancel:
        try:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.cancel_all_orders(symbol=symbol)
        except Exception as e:
            print(e)

        try:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.cancel_all_orders(symbol=symbol)
        except Exception as e:
            print(e)

        try:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.cancel_all_orders(symbol=symbol)
        except Exception as e:
            print(e)

        SYMBOL_CANCEL_ORDERS_TS_OBJ[symbol] = now


    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp


@post('/cancel_binance_order', methods='POST')
def cancel_binance_order():
    key = str(request.forms.get('key'))
    secret = str(request.forms.get('secret'))
    symbol = str(request.forms.get('symbol'))
    clientOrderId = str(request.forms.get('clientOrderId'))
    now = int(time.time()*1000)
    try:
        request_client = RequestClient(api_key=key,secret_key=secret)
        result = request_client.cancel_order(symbol=symbol,orderId=clientOrderId)
    except Exception as e:
        print(e)
        try:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.cancel_order(symbol=symbol,orderId=clientOrderId)
        except Exception as e:
            print(e)
            try:
                request_client = RequestClient(api_key=key,secret_key=secret)
                result = request_client.cancel_order(symbol=symbol,orderId=clientOrderId)
            except Exception as e:
                FUNCTION_CLIENT.send_notify_limit_one_min("【cancel order error】，"+key+","+symbol+","+clientOrderId+","+str(e))


    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

BIG_LOSS_TRADES_ARR = []
UPDATE_BIG_LOSS_TRADES_DARA_TS = 0
@post('/get_big_loss_trades', methods='POST')
def get_big_loss_trades():
    global BIG_LOSS_TRADES_ARR,UPDATE_BIG_LOSS_TRADES_DARA_TS,AVERAGE_RUN_TIME
    now = int(time.time())
    if now - UPDATE_BIG_LOSS_TRADES_DARA_TS>60:
        UPDATE_BIG_LOSS_TRADES_DARA_TS = now
        with FUNCTION_CLIENT.get_session() as session:
            bigLossData = session.exec(
                select(TradeRecord).where(TradeRecord.profit_percent_by_balance <= -0.15).order_by(TradeRecord.id.desc())
            ).all()
        BIG_LOSS_TRADES_ARR = []
        for row in bigLossData:
            BIG_LOSS_TRADES_ARR.append({
                    "symbol":row.symbol,
                    "time":FUNCTION_CLIENT.turn_ts_to_time(row.end_ts),
                    "profit":row.profit,
                    "profitPercentByBalance":str(abs(int(row.profit_percent_by_balance*100)/100))+"%"
                })
    resp = json_dumps({'s':'ok','d':BIG_LOSS_TRADES_ARR})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

SYMBOL_LAST_INSEART_TS_OBJ = {}
@post('/begin_trade_record', methods='POST')
def begin_trade_record():
    global FUNCTION_CLIENT,SYMBOL_LAST_INSEART_TS_OBJ
    try:
        ts = int(time.time()*1000)
        tradeTime = FUNCTION_CLIENT.turn_ts_to_time(ts)
        volMultiple=  float(request.forms.get('volMultiple'))
        standardRate =  float(request.forms.get('standardRate'))
        symbol = str(request.forms.get('symbol'))
        klineArr =  json.dumps(json.loads(request.forms.get('klineArr')))
        nowOpenRate =  float(request.forms.get('nowOpenRate'))
        machineNumber =  str(request.forms.get('machineNumber'))
        direction =  str(request.forms.get('direction'))
        myTradeType = str(request.forms.get('myTradeType'))
        longsConditionA = int(request.forms.get('longsConditionA'))
        shortsConditionA = int(request.forms.get('shortsConditionA'))
        shortsConditionB = int(request.forms.get('shortsConditionB'))
        btcNowOpenRate = float(request.forms.get('btcNowOpenRate'))
        ethNowOpenRate = float(request.forms.get('ethNowOpenRate'))
        clientBeginPrice = float(request.forms.get('clientBeginPrice'))
        clientEndPrice = float(request.forms.get('clientEndPrice'))
        privateIP =  str(request.forms.get('privateIP'))

        with FUNCTION_CLIENT.get_session() as session:
            tradesData = session.exec(
                select(TradesTake).where(TradesTake.symbol == symbol, TradesTake.status == "tradeBegin")
            ).all()
        if myTradeType.find("open")>=0 and len(tradesData)==0:
            if not symbol in SYMBOL_LAST_INSEART_TS_OBJ or ts-SYMBOL_LAST_INSEART_TS_OBJ[symbol]>30000:
                SYMBOL_LAST_INSEART_TS_OBJ[symbol] = ts
                from decimal import Decimal
                with FUNCTION_CLIENT.get_session() as session:
                    new_row = TradesTake(
                        status="tradeBegin", version=3,
                        vol_multiple=Decimal(str(volMultiple)), standard_rate=Decimal(str(standardRate)),
                        symbol=symbol, kline_arr=klineArr,
                        now_open_rate=Decimal(str(nowOpenRate)), begin_machine_number=machineNumber,
                        direction=direction, longs_condition_a=longsConditionA,
                        shorts_condition_a=shortsConditionA, shorts_condition_b=shortsConditionB,
                        btc_now_open_rate=Decimal(str(btcNowOpenRate)), eth_now_open_rate=Decimal(str(ethNowOpenRate)),
                        begin_ts=ts, end_ts=ts, trade_type=myTradeType, update_ts=ts,
                        client_begin_price=Decimal(str(clientBeginPrice)), client_end_price=Decimal(str(clientEndPrice))
                    )
                    session.add(new_row)
                    session.commit()
        else:
            FUNCTION_CLIENT.send_notify_limit_one_min(myTradeType)
        #     if len(tradesData)==0:
        #         time.sleep(3)
        #         sql = "select `id` from trades where symbol=%s and status='tradeBegin'"
        #         tradesData = FUNCTION_CLIENT.mysql_pool_select(sql,[symbol])
        #     if myTradeType.find("close")<0 and len(tradesData)==0:
        #         FUNCTION_CLIENT.send_notify_limit_one_min(symbol+","+myTradeType)
        #     elif len(tradesData)>0:
        #         tradesID = tradesData[0][0]
        #         updateSql = ""
        #         if myTradeType.find("add")>=0:
        #             if myTradeType.find("gtx")>=0:
        #                 updateSql = "update trades set `addGtxTime` = `addGtxTime`+1 where id=%s"
        #             else:
        #                 updateSql = "update trades set `addTime` = `addTime`+1 where id=%s"
        #         if myTradeType.find("open")>=0:
        #             if myTradeType.find("gtx")>=0:
        #                 updateSql = "update trades set `openGtxTime` = `openGtxTime`+1 where id=%s"
        #             else:
        #                 updateSql = "update trades set `openTime` = `openTime`+1 where id=%s"
        #         if myTradeType.find("close")>=0:
        #             if myTradeType.find("gtx")>=0:
        #                 updateSql = "update trades set `closeGtxTime` = `closeGtxTime`+1 where id=%s"
        #             else:
        #                 updateSql = "update trades set `closeTime` = `closeTime`+1 where id=%s"
        #         FUNCTION_CLIENT.mysql_pool_commit(updateSql,[tradesID])

        resp = json.dumps({'s':'ok'})
        response.set_header('Access-Control-Allow-Origin', '*')
        return resp
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))

@post('/get_order_result_arr', methods='POST')
def get_order_result_arr():
    now = int(time.time())
    symbol = str(request.forms.get('symbol'))
    beginTs = int(request.forms.get('beginTs'))
    endTs = int(request.forms.get('endTs'))
    with FUNCTION_CLIENT.get_session() as session:
        beginTradeRecordData = session.exec(
            select(BeginTradeRecord)
            .where(BeginTradeRecord.symbol == symbol, BeginTradeRecord.ts > beginTs - 60000, BeginTradeRecord.ts < endTs + 60000)
            .order_by(BeginTradeRecord.id.desc())
            .limit(5000)
        ).all()
    beginTradeArr = []
    for row in beginTradeRecordData:
        beginTradeArr.append({
                "symbol":row.symbol,
                "time":row.time,
                "asksDepthArr":json.loads(row.asks_depth_arr or "[]"),
                "bidsDepthArr":json.loads(row.bids_depth_arr or "[]"),
                "ordersResult":json.loads(row.orders_result or "{}"),
                "direction":row.direction,
                "nowOpenRate":row.now_open_rate,
                "machineNumber":row.machine_number,
                "ts":row.ts,
                "myTradeType":row.my_trade_type,
                "nowPrice":row.now_price
            })
    resp = json.dumps({'s':'ok','d':beginTradeArr})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/get_trades_result_arr', methods='POST')
def get_trades_result_arr():
    try:
        now = int(time.time())
        tradeTimeIntervalIndex = int(request.forms.get('tradeTimeIntervalIndex'))
        nowTs = int(time.time()*1000)
        limitTs = 0
        if tradeTimeIntervalIndex==0:
           limitTs = nowTs - 4*60*60*1000
        if tradeTimeIntervalIndex==1:
           limitTs = nowTs - 8*60*60*1000 
        if tradeTimeIntervalIndex==2:
           limitTs = nowTs - 12*60*60*1000 
        if tradeTimeIntervalIndex==3:
           limitTs = nowTs - 24*60*60*1000
        if tradeTimeIntervalIndex==4:
           limitTs = nowTs - 72*60*60*1000
        if limitTs<1686960000000:
            limitTs= 1686960000000
        print(limitTs)
        with FUNCTION_CLIENT.get_session() as session:
            tradesRecordData = session.exec(
                select(Trades)
                .where(Trades.status == "updateProfit", Trades.begin_ts > limitTs, Trades.version == 2)
                .order_by(Trades.id.desc())
            ).all()
        tradesRecordArr = []
        for row in tradesRecordData:
            vol_info_parsed = json.loads(row.vol_info) if isinstance(row.vol_info, str) else (row.vol_info or {})
            boll_up = row.begin_boll_up or 0
            boll_down = row.begin_boll_down or 0
            tradesRecordArr.append([
                    row.symbol,
                    row.begin_ts,
                    row.end_ts,
                    row.direction,
                    row.profit,
                    row.value,
                    row.cost,
                    vol_info_parsed,
                    row.open_type,
                    row.open_time,
                    row.add_time,
                    row.close_time,
                    row.open_gtx_time,
                    row.add_gtx_time,
                    row.close_gtx_time,
                    row.now_open_rate,
                    row.standard_rate,
                    row.take_time,
                    FUNCTION_CLIENT.get_percent_num(boll_up - boll_down, boll_down),
                    row.take_value]
                )


        with FUNCTION_CLIENT.get_session() as session:
            tradesRecordData = session.exec(
                select(Trades).where(Trades.status == "updateProfitFail", Trades.begin_ts > limitTs, Trades.version == 2)
            ).all()
        failValue = 0
        resp = json.dumps({'s':'ok','d':tradesRecordArr,'fT':len(tradesRecordData),'fV':failValue})
        response.set_header('Access-Control-Allow-Origin', '*')
        return resp
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))

@post('/get_commission_rate', methods='POST')
def get_commission_rate():
    key = str(request.forms.get('key'))
    secret = str(request.forms.get('secret'))
    symbol = str(request.forms.get('symbol'))
    now = int(time.time()*1000)

    request_client = RequestClient(api_key=key,secret_key=secret)
    result = request_client.get_commission_rate(symbol=symbol)
    result = json.loads(result)
    resp = json.dumps({'s':'ok','d':result})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp



def takeShortsOrder(shortsPrice,shortsOnceTradeCoinQuantity,tradeType,symbol,key,secret):
    global FUNCTION_CLIENT,ORDER_ID_SYMBOL,PRICE_MOVE_SYMBOL,PRIVATE_IP,PUBLIC_SERVER_IP,SEND_PUBLIC_SERVER_TS,PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,ORDER_ID_INDEX,REQUEST_CLIENT,NEED_CANCEL_SHORTS_ORDER_ID_ARR,TRADE_INFO,EIGHT_HOURS_PROFIT,TRADE_INFO,FOUR_HOURS_PROFIT,EIGHT_HOURS_PROFIT,TWELVE_HOURS_PROFIT,TWENTY_FOUR_HOURS_PROFIT
    shortsPrice = float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (shortsPrice)))

    coinQuantity = shortsOnceTradeCoinQuantity

    ORDER_ID_INDEX = ORDER_ID_INDEX+1
    newClientOrderId = ORDER_ID_SYMBOL+"_"+tradeType+"_"+str(ORDER_ID_INDEX)
    result = {}
    try:
        request_client = RequestClient(api_key=key,secret_key=secret)
        result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.SELL, ordertype=OrderType.LIMIT, price=shortsPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        result = json.loads(result)
        if "code" in result and result['code']==-1001:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.SELL, ordertype=OrderType.LIMIT, price=shortsPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
            result = json.loads(result)
        if "code" in result and result['code']!=-5022  and result['code']!=-1001  and result['code']!=-2022:
            _thread.start_new_thread(FUNCTION_CLIENT.send_notify_limit_one_min,("shorts order error:"+str(result)+","+str(coinQuantity),))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(FUNCTION_CLIENT.send_notify_limit_one_min,("shortsM:"+str(e),))


    return result




def takeLongsOrder(longsPrice,longsOnceTradeCoinQuantity,tradeType,symbol,key,secret):
    global FUNCTION_CLIENT,ORDER_ID_SYMBOL,PRICE_MOVE_SYMBOL,PRIVATE_IP,PUBLIC_SERVER_IP,SEND_PUBLIC_SERVER_TS,PRIVATE_IP,THIRTY_MINS_POLE_SCORE,RICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,ORDER_ID_INDEX,REQUEST_CLIENT,NEED_CANCEL_LONGS_ORDER_ID_ARR,TRADE_INFO,EIGHT_HOURS_PROFIT,TRADE_INFO,FOUR_HOURS_PROFIT,EIGHT_HOURS_PROFIT,TWELVE_HOURS_PROFIT,TWENTY_FOUR_HOURS_PROFIT

    longsPrice = float(decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (longsPrice)))

    coinQuantity = longsOnceTradeCoinQuantity

    ORDER_ID_INDEX = ORDER_ID_INDEX+1
    newClientOrderId = ORDER_ID_SYMBOL+"_"+tradeType+"_"+str(ORDER_ID_INDEX)
    result = {}
    try:
        request_client = RequestClient(api_key=key,secret_key=secret)
        result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.BUY, ordertype=OrderType.LIMIT, price=longsPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
        result = json.loads(result)
        if "code" in result and result['code']==-1001:
            request_client = RequestClient(api_key=key,secret_key=secret)
            result = request_client.post_order(newClientOrderId=newClientOrderId,reduceOnly=False,symbol=symbol, quantity=coinQuantity,side=OrderSide.BUY, ordertype=OrderType.LIMIT, price=longsPrice, positionSide="BOTH", timeInForce=TimeInForce.GTC)
            result = json.loads(result)
        if "code" in result and result['code']!=-5022 and result['code']!=-1001:
            _thread.start_new_thread(FUNCTION_CLIENT.send_notify_limit_one_min,("longs order error:"+str(result)+","+str(coinQuantity),))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(FUNCTION_CLIENT.send_notify_limit_one_min,("longsM:"+str(e),))

    return result

TAKE_OPEN_OBJ = {
    
}


@post('/take_open', methods='POST')
def take_open():
    global AMOUNT_DECIMAL_OBJ,PRIVATE_IP,TAKE_OPEN_OBJ
    try:
        key = str(request.forms.get('key'))
        secret = str(request.forms.get('secret'))
        symbol = str(request.forms.get('symbol'))
        direction = str(request.forms.get('direction'))
        price = float(request.forms.get('price'))
        openTime = int(request.forms.get('openTime'))
        positionValue = float(request.forms.get('positionValue'))
        volMultiple = float(request.forms.get('volMultiple'))
        now = int(time.time()*1000)

        if (positionValue==0 and symbol in TAKE_OPEN_OBJ and now-TAKE_OPEN_OBJ[symbol]["ts"]>60000*15)  or (symbol in TAKE_OPEN_OBJ and TAKE_OPEN_OBJ[symbol]["status"]=="end") or (symbol in TAKE_OPEN_OBJ and openTime>TAKE_OPEN_OBJ[symbol]["openTime"]) or (not symbol in TAKE_OPEN_OBJ):
            TAKE_OPEN_OBJ[symbol] = {"ts":now,"openTime":openTime,"status":"trading"}
            ordersResult  = {}


            if direction=="longs":
                value = 100
                quantity = float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (value/price )))
                ordersResult = takeLongsOrder(price,quantity,"T",symbol,key,secret)
                FUNCTION_CLIENT.send_notify_limit_one_min(symbol+" take longs")
            if direction=="shorts":
                value = 100
                quantity = float(decimal.Decimal(AMOUNT_DECIMAL_OBJ[symbol] % (value/price )))
                ordersResult = takeShortsOrder(price,quantity,"T",symbol,key,secret)
                FUNCTION_CLIENT.send_notify_limit_one_min(symbol+" take shorts")

    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

@post('/end_open', methods='POST')
def end_open():
    global AMOUNT_DECIMAL_OBJ,PRIVATE_IP,TAKE_OPEN_OBJ
    try:
        symbol = str(request.forms.get('symbol'))
        now = int(time.time()*1000)
        if symbol in TAKE_OPEN_OBJ and TAKE_OPEN_OBJ[symbol]["status"] != "end":
            TAKE_OPEN_OBJ[symbol]["status"] = "end"
            FUNCTION_CLIENT.send_notify_limit_one_min(symbol+" end trade")
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
    resp = json.dumps({'s':'ok'})
    response.set_header('Access-Control-Allow-Origin', '*')
    return resp

# @post('/get_trades_result_arr', methods='POST')
# def get_trades_result_arr():


# print("-------0------------------")
def main():
    run(server='paste', host='0.0.0.0', port=8888)

if __name__ == "__main__":
    sys.exit(main())
