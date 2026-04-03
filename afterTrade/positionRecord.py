#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# encoding: utf-8
#客户端调用，用于查看API返回结果
import decimal
import time
import requests
import json
import traceback
from datetime import datetime
from sqlmodel import select
from sqlalchemy import func
from settings import settings
from infra_client import InfraClient
from app.models.position_record import PositionRecord
from app.models.income_history_take import IncomeHistoryTake

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="positionReord")

POSITION_TABLE_NAME = "position_record"


PUBLIC_SERVER_IP = "http://"+settings.web_address+":8888/"

TRADE_SYMBOL_ARR =  []

response = requests.request("POST", PUBLIC_SERVER_IP+"get_symbol_index", timeout=3).json()

TRADE_SYMBOL_ARR = response["d"]


print(TRADE_SYMBOL_ARR)


PRICE_DECIMAL_OBJ = {}

AMOUNT_DECIMAL_OBJ = {}

PRICE_TICK_OBJ = {}

PRICE_DECIMAL_AMOUNT_OBJ = {}

AMOUNT_DECIMAL_AMOUNT_OBJ = {}

MARKET_MAX_SIZE_OBJ = {}


def updateSymbolInfo():
    global PRICE_DECIMAL_OBJ,AMOUNT_DECIMAL_OBJ,PRICE_DECIMAL_AMOUNT_OBJ,AMOUNT_DECIMAL_AMOUNT_OBJ,PRICE_TICK_OBJ,MARKET_MAX_SIZE_OBJ
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
        PRICE_DECIMAL_OBJ[thisInstrumentID] = priceDecimal
        AMOUNT_DECIMAL_OBJ[thisInstrumentID] = amountDecimal
        PRICE_TICK_OBJ[thisInstrumentID] = priceTick
        PRICE_DECIMAL_AMOUNT_OBJ[thisInstrumentID] = priceDecimalAmount
        AMOUNT_DECIMAL_AMOUNT_OBJ[thisInstrumentID] = amountDecimalAmount

updateSymbolInfo()

while not "BTCUSDT" in PRICE_DECIMAL_OBJ:
    updateSymbolInfo()
    time.sleep(1)

POSITION_ARR = []

ACCOUNT_BALANCE_VALUE = 0

def getBinancePositionFromMyServer():
    global FUNCTION_CLIENT,POSITION_ARR,ACCOUNT_BALANCE_VALUE
    try:
        dataStr = FUNCTION_CLIENT.get_from_ws_a("B")
        dataArr = dataStr.split("*")
        ACCOUNT_BALANCE_VALUE = float(dataArr[4])
        if dataArr[2]!="":
            positionStrArr= dataArr[2].split("&")
            positionArr= []
            for a in range(len(positionStrArr)):
                positionArr.append(positionStrArr[a].split("@"))
                positionArr[a][1] = float(positionArr[a][1])
                positionArr[a][2] = float(positionArr[a][2])
            POSITION_ARR = positionArr
        else:
            POSITION_ARR = []
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))


def getPositionInfoArrBySymbol(symbol):
    global POSITION_ARR
    for positionIndex in range(len(POSITION_ARR)):
        if POSITION_ARR[positionIndex][0] == symbol:
            return [POSITION_ARR[positionIndex][2],POSITION_ARR[positionIndex][1]]
    return [0,0]


def getFutureDepthBySymbol(symbol,limit):
    response = {}
    errorTime = 0
    while errorTime<100:
        try:
            url = "https://fapi.binance.com/fapi/v1/depth?symbol="+symbol+"&limit="+str(limit)
            response = requests.request("GET", url,timeout=(0.5,0.5)).json()
            errorTime = 100
        except Exception as e:
            print(e)
            errorTime = errorTime+1
            time.sleep(errorTime*0.5)
    return response


UPDATE_TS = 0
def record_position():
    global POSITION_TABLE_NAME,BINANCE_API_KEY_ARR,BINANCE_API_SECRET_ARR,TABLE_NAME_ARR,UPDATE_TS,ACCOUNT_BALANCE_VALUE,EIGHT_HOURS_PROFIT,SYMBOL_ARR,PRICE_DECIMAL_OBJ

    now = int(time.time())
    allPositionAmt = 0
    allUnrealizedProfit = 0
    allPositionValue = 0

    if now - UPDATE_TS>60:
        UPDATE_TS = now

        getBinancePositionFromMyServer()
        for tradeSymbolIndex in range(len(TRADE_SYMBOL_ARR)):
            symbol = TRADE_SYMBOL_ARR[tradeSymbolIndex]["symbol"]
            symbolPositionInfoArr = getPositionInfoArrBySymbol(symbol)
            symbolPositionAmt = symbolPositionInfoArr[0]
            symbolCost = symbolPositionInfoArr[1]
            if symbolCost!=0:
                depthObj = getFutureDepthBySymbol(symbol,5)
                midPrice = (float(depthObj["bids"][0][0])+float(depthObj["asks"][0][0])) /2
                unrealizedProfit = symbolPositionAmt*(midPrice-symbolCost)
                symbolCost =  decimal.Decimal(PRICE_DECIMAL_OBJ[symbol] % (symbolCost))

                allUnrealizedProfit = allUnrealizedProfit+unrealizedProfit
                allPositionAmt = allPositionAmt+symbolPositionInfoArr[0]

                allPositionValue = allPositionValue+abs(symbolPositionAmt*midPrice)

        with FUNCTION_CLIENT.get_session() as session:
            record = PositionRecord(
                symbol="all",
                unrealized_profit=decimal.Decimal(str(allUnrealizedProfit)),
                position_amt=decimal.Decimal(str(allPositionAmt)),
                ts=now,
                time=FUNCTION_CLIENT.turn_ts_to_time(now),
                position_value=decimal.Decimal(str(allPositionValue)),
                balance=decimal.Decimal(str(ACCOUNT_BALANCE_VALUE)),
            )
            session.add(record)
            session.commit()

UPDATE_PROFIT_AND_COMMISSION_TS  = 0
def updateProfitAndCommission():
    global UPDATE_PROFIT_AND_COMMISSION_TS,ACCOUNT_SYMBOL,POSITION_TABLE_NAME
    now = int(time.time())
    if now - UPDATE_PROFIT_AND_COMMISSION_TS>60:
        UPDATE_PROFIT_AND_COMMISSION_TS = now

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT ts, id from position_record where ts < now-30min and updateProfitAndCommission=0 ORDER BY id DESC
            positionRecords = session.exec(
                select(PositionRecord)
                .where(PositionRecord.ts < now - 60 * 30)
                .where(PositionRecord.update_profit_and_commission == False)
                .order_by(PositionRecord.id.desc())
            ).all()

            if len(positionRecords) > 1:
                for i in range(len(positionRecords) - 1):
                    thisRecord = positionRecords[i]
                    thisID = thisRecord.id

                    # SELECT the record with max id < thisID
                    lastRecord = session.exec(
                        select(PositionRecord)
                        .where(PositionRecord.id < thisID)
                        .order_by(PositionRecord.id.desc())
                        .limit(1)
                    ).first()

                    if lastRecord is not None:
                        endTs = thisRecord.ts
                        beginTs = lastRecord.ts
                        allProfit = 0
                        allCommission = 0
                        allMakerCommission = 0

                        # SELECT income records in time range
                        incomeRecords = session.exec(
                            select(IncomeHistoryTake)
                            .where(IncomeHistoryTake.binance_ts > beginTs * 1000)
                            .where(IncomeHistoryTake.binance_ts <= endTs * 1000)
                            .order_by(IncomeHistoryTake.id.asc())
                        ).all()

                        for incomeRecord in incomeRecords:
                            if incomeRecord.income_type == "COMMISSION":
                                if incomeRecord.asset == "BNB":
                                    allCommission = allCommission + float(incomeRecord.income) * float(incomeRecord.bnb_price)
                                else:
                                    allCommission = allCommission + float(incomeRecord.income)
                                if float(incomeRecord.income) > 0:
                                    if incomeRecord.asset == "BNB":
                                        allMakerCommission = allMakerCommission + float(incomeRecord.income) * float(incomeRecord.bnb_price)
                                    else:
                                        allMakerCommission = allMakerCommission + float(incomeRecord.income)
                            if incomeRecord.income_type == "REALIZED_PNL":
                                allProfit = allProfit + float(incomeRecord.income)

                        # UPDATE position record with profit, commission, makerCommission
                        dbRecord = session.exec(
                            select(PositionRecord).where(PositionRecord.id == thisID)
                        ).one()
                        dbRecord.profit = decimal.Decimal(str(allProfit))
                        dbRecord.commission = decimal.Decimal(str(allCommission))
                        dbRecord.maker_commission = decimal.Decimal(str(allMakerCommission))
                        dbRecord.update_profit_and_commission = True
                        session.add(dbRecord)
                        session.commit()

ERROR_TIME = 0
while 1:
    try:
        record_position()
        updateProfitAndCommission()
        ERROR_TIME = 0
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
        time.sleep(1)
        print(ex)
    time.sleep(3)
