#!/usr/bin/env python3
# coding=utf-8
import traceback
import json
import random
import time
import requests
import socket
import decimal
from sqlmodel import select
from binance_f.impl.utils.apisignature import create_signature
from binance_f.requestclient import RequestClient
from binance_f.constant.test import *
from binance_f.base.printobject import *
from binance_f.model.constant import *
from settings import settings
from infra_client import InfraClient
from app.models.trades_take import TradesTake
from app.models.income_history_take import IncomeHistoryTake

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="recordOrders",connectMysql =True)

TRADES_TABLE_NAME = "trades_take"


PUBLIC_SERVER_IP = "http://"+settings.web_address+":8888/"

response = requests.request("POST", PUBLIC_SERVER_IP+"get_symbol_index", timeout=3).json()

TRADE_SYMBOL_ARR = response["d"]

SYMBOL_OBJ_ARR = []

for i in range(len(TRADE_SYMBOL_ARR)):
    SYMBOL_OBJ_ARR.append({
            "coin":TRADE_SYMBOL_ARR[i]["coin"],
            "binanceSymbol":TRADE_SYMBOL_ARR[i]["symbol"],
            "bybitSymbol":"",
            "okexSymbol":""
        })


def updateOkexSymbolInfo():
    global SYMBOL_OBJ_ARR
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    response = requests.request("GET", url,timeout=(3,7)).json()
    resultArr = response["data"]
    for a in range(len(resultArr)):
        for b in range(len(SYMBOL_OBJ_ARR)):
            if resultArr[a]["instType"]=="SWAP" and resultArr[a]["ctValCcy"].upper()==SYMBOL_OBJ_ARR[b]["coin"].upper():
                SYMBOL_OBJ_ARR[b]["okexSymbol"] = resultArr[a]["instId"]

def updateBybitSymbolInfo():
    global SYMBOL_OBJ_ARR
    url = "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000"
    response = requests.request("GET", url,timeout=(3,7)).json()
    resultArr = response["result"]["list"]
    for a in range(len(resultArr)):
        for b in range(len(SYMBOL_OBJ_ARR)):
            if resultArr[a]["symbol"]==SYMBOL_OBJ_ARR[b]["binanceSymbol"]:
                SYMBOL_OBJ_ARR[b]["bybitSymbol"] = resultArr[a]["symbol"]

updateOkexSymbolInfo()
updateBybitSymbolInfo()



def takeElemZero(elem):
    return int(elem[0])

def getOkexKline(startTs,symbol):
    url = "https://www.okx.com/api/v5/market/history-candles?instId="+symbol+"&limit=100&bar=15m&after="+str(int(startTs))
    okexResponseA = requests.request("GET", url,timeout=(3,7)).json()
    okexDataA = okexResponseA["data"]
    okexDataA.sort(key=takeElemZero,reverse=False)

    url = "https://www.okx.com/api/v5/market/history-candles?instId="+symbol+"&limit=100&bar=15m&after="+str(int(startTs)-15*60*100*1000)
    okexResponseB = requests.request("GET", url,timeout=(3,7)).json()
    okexDataB = okexResponseB["data"]
    okexDataB.sort(key=takeElemZero,reverse=True)

    url = "https://www.okx.com/api/v5/market/history-candles?instId="+symbol+"&limit=100&bar=15m&after="+str(int(startTs)-15*60*200*1000)
    okexResponseC = requests.request("GET", url,timeout=(3,7)).json()
    okexDataC = okexResponseC["data"]
    okexDataC.sort(key=takeElemZero,reverse=True)

    url = "https://www.okx.com/api/v5/market/history-candles?instId="+symbol+"&limit=100&bar=15m&after="+str(int(startTs)-15*60*300*1000)
    okexResponseD = requests.request("GET", url,timeout=(3,7)).json()
    okexDataD = okexResponseD["data"]
    okexDataD.sort(key=takeElemZero,reverse=True)

    url = "https://www.okx.com/api/v5/market/history-candles?instId="+symbol+"&limit=100&bar=15m&after="+str(int(startTs)-15*60*400*1000)
    okexResponseE = requests.request("GET", url,timeout=(3,7)).json()
    okexDataE = okexResponseE["data"]
    okexDataE.sort(key=takeElemZero,reverse=True)

    okexKlineArr = okexDataA


    for i in range(len(okexDataB)):
        okexDataB[i].append("B")
        okexKlineArr.insert(0,okexDataB[i])

    for i in range(len(okexDataC)):
        okexDataC[i].append("C")
        okexKlineArr.insert(0,okexDataC[i])

    for i in range(len(okexDataD)):
        okexDataD[i].append("D")
        okexKlineArr.insert(0,okexDataD[i])

    for i in range(len(okexDataE)):
        okexDataE[i].append("E")
        okexKlineArr.insert(0,okexDataE[i])

    for i in range(len(okexKlineArr)):
        if i+1<len(okexKlineArr):
            if int(okexKlineArr[i][0]) !=int(okexKlineArr[i+1][0])-15*60*1000:
                print("---------------------------------")
                print(i)
                print(int(okexKlineArr[i+1][0])-int(okexKlineArr[i][0]))
                print(okexKlineArr[i])
                print(okexKlineArr[i+1])
    return okexKlineArr

def getBybitKline(startTs,symbol):

    url = "https://api.bybit.com/v5/market/kline?category=linear&symbol="+symbol+"&limit=200&interval=15&end="+str(int(startTs))
    bybitResponseA = requests.request("GET", url,timeout=(3,7)).json()
    bybitDataA = bybitResponseA["result"]["list"]
    bybitDataA.sort(key=takeElemZero,reverse=False)

    url = "https://api.bybit.com/v5/market/kline?category=linear&symbol="+symbol+"&limit=200&interval=15&end="+str(int(startTs)-15*60*200*1000)
    bybitResponseB = requests.request("GET", url,timeout=(3,7)).json()
    bybitDataB = bybitResponseB["result"]["list"]
    bybitDataB.sort(key=takeElemZero,reverse=True)

    url = "https://api.bybit.com/v5/market/kline?category=linear&symbol="+symbol+"&limit=100&interval=15&end="+str(int(startTs)-15*60*400*1000)
    bybitResponseC = requests.request("GET", url,timeout=(3,7)).json()
    bybitDataC = bybitResponseC["result"]["list"]
    bybitDataC.sort(key=takeElemZero,reverse=True)


    bybitKlineArr = bybitDataA


    for i in range(len(bybitDataB)):
        bybitDataB[i].append("B")
        bybitKlineArr.insert(0,bybitDataB[i])

    for i in range(len(bybitDataC)):
        bybitDataC[i].append("C")
        bybitKlineArr.insert(0,bybitDataC[i])

    for i in range(len(bybitKlineArr)):
        if i+1<len(bybitKlineArr):
            if int(bybitKlineArr[i][0]) !=int(bybitKlineArr[i+1][0])-15*60*1000:
                print("---------------------------------")
                print(i)
                print(int(bybitKlineArr[i+1][0])-int(bybitKlineArr[i][0]))
                print(bybitKlineArr[i])
                print(bybitKlineArr[i+1])
    return bybitKlineArr

def getBinanceKline(startTs,symbol):
    url = "https://fapi.binance.com/fapi/v1/klines?symbol="+symbol+"&endTime="+str(int(startTs))+"&interval=15m&limit=500"
    responseB = requests.request("GET", url,timeout=(3,7)).json()
    responseB.sort(key=takeElemZero,reverse=False)
    return responseB




PRIVATE_IP = FUNCTION_CLIENT.get_private_ip()

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


RECORD_OBJ = {}

def update():
    global RECORD_OBJ,PRIVATE_IP,ACCOUNT_BALANCE_VALUE,TRADES_TABLE_NAME
    now = int(time.time()*1000)

    with FUNCTION_CLIENT.get_session() as session:
        # SELECT id, symbol, beginTs from trades_take where status='tradeBegin'
        tradesRows = session.exec(
            select(TradesTake).where(TradesTake.status == "tradeBegin")
        ).all()

        for tradeRow in tradesRows:
            tradeBeginTs = tradeRow.begin_ts
            dataID = tradeRow.id
            symbol = tradeRow.symbol
            symbolPositionInfoArr = getPositionInfoArrBySymbol(symbol)
            positionCost = symbolPositionInfoArr[1]
            symbolPositionAmt = symbolPositionInfoArr[0]
            positionValue = abs(int(positionCost*symbolPositionAmt))

            if ((not (symbol in RECORD_OBJ)) or RECORD_OBJ[symbol]["status"]=="tradeEnd"):
                RECORD_OBJ[symbol] = {"balance":ACCOUNT_BALANCE_VALUE,"status":"tradeBegin","beginTs":now,"symbol":symbol,"value":positionValue,"amount":symbolPositionAmt,"cost":positionCost}
                print(RECORD_OBJ)
            if ( symbol in RECORD_OBJ) and RECORD_OBJ[symbol]["status"]=="tradeBegin" and positionValue>RECORD_OBJ[symbol]["value"]:
                RECORD_OBJ[symbol]["value"] = positionValue
                RECORD_OBJ[symbol]["amount"] = symbolPositionAmt
                RECORD_OBJ[symbol]["cost"] = positionCost
            if ( symbol in RECORD_OBJ) and RECORD_OBJ[symbol]["status"]=="tradeBegin" and positionValue==0 and now-tradeBeginTs>60000:
                RECORD_OBJ[symbol]["status"]="tradeEnd"
                insertBalance = RECORD_OBJ[symbol]["balance"]
                if insertBalance==0:
                    insertBalance = ACCOUNT_BALANCE_VALUE

                # UPDATE trades_take set value, amount, cost, balance, endTs, status='tradeEnd' where id=X
                dbRow = session.exec(
                    select(TradesTake).where(TradesTake.id == dataID)
                ).one()
                dbRow.value = decimal.Decimal(str(RECORD_OBJ[symbol]["value"]))
                dbRow.amount = decimal.Decimal(str(RECORD_OBJ[symbol]["amount"]))
                dbRow.cost = decimal.Decimal(str(RECORD_OBJ[symbol]["cost"]))
                dbRow.balance = decimal.Decimal(str(insertBalance))
                dbRow.end_ts = now
                dbRow.status = "tradeEnd"
                session.add(dbRow)
                session.commit()

def takeElemZero(elem):
    return float(elem[0])

UPDATE_PROFIT_TS = 0
def updateProfit():
    global UPDATE_PROFIT_TS,SYMBOL_OBJ_ARR
    now = int(time.time()*1000)
    if now - UPDATE_PROFIT_TS>1*60*1000:
        with FUNCTION_CLIENT.get_session() as session:
            # SELECT binance_ts from income_history_take ORDER BY id DESC LIMIT 1
            lastIncomeRow = session.exec(
                select(IncomeHistoryTake).order_by(IncomeHistoryTake.id.desc()).limit(1)
            ).first()
            if lastIncomeRow is None:
                return
            lastBinanceUpdateTs = lastIncomeRow.binance_ts

            UPDATE_PROFIT_TS = now

            # SELECT beginTs, endTs, symbol, id, balance, direction, symbol from trades_take
            # where status='tradeEnd' and endTs < lastBinanceUpdateTs - 5min
            tradesRecordRows = session.exec(
                select(TradesTake)
                .where(TradesTake.status == "tradeEnd")
                .where(TradesTake.end_ts < lastBinanceUpdateTs - 5 * 60 * 1000)
            ).all()

            for tradeRow in tradesRecordRows:
                tradeBeginTs = tradeRow.begin_ts
                tradeEndTs = tradeRow.end_ts
                tradeRecordDataID = tradeRow.id
                balance = float(tradeRow.balance) if tradeRow.balance is not None else 0
                direction = tradeRow.direction
                binanceSymbol = tradeRow.symbol

                # SELECT income records in trade time range for this symbol
                incomeRows = session.exec(
                    select(IncomeHistoryTake)
                    .where(IncomeHistoryTake.binance_ts >= tradeBeginTs)
                    .where(IncomeHistoryTake.binance_ts <= tradeEndTs)
                    .where(IncomeHistoryTake.symbol == tradeRow.symbol)
                ).all()

                profit = 0
                commission = 0

                bybitSymbol = ""
                okexSymbol = ""
                for i in range(len(SYMBOL_OBJ_ARR)):
                    if SYMBOL_OBJ_ARR[i]["binanceSymbol"]==binanceSymbol:
                        bybitSymbol = SYMBOL_OBJ_ARR[i]["bybitSymbol"]
                        okexSymbol = SYMBOL_OBJ_ARR[i]["okexSymbol"]
                        break

                for incomeRow in incomeRows:
                    income = float(incomeRow.income) if incomeRow.income is not None else 0
                    bnbPrice = float(incomeRow.bnb_price) if incomeRow.bnb_price is not None else 0
                    asset = incomeRow.asset
                    incomeType = incomeRow.income_type
                    realIncome = 0
                    if asset=="BNB":
                        realIncome = income*bnbPrice
                    else:
                        realIncome = income
                    if incomeType=="COMMISSION":
                        commission = commission+realIncome
                    if incomeType=="REALIZED_PNL" or incomeType=="COMMISSION":
                        profit = profit+realIncome

                if commission!=0 or profit!=0:
                    profitPercentByBalance = FUNCTION_CLIENT.get_percent_num(profit,balance)
                    priceRate = 0
                    try:
                        url = "https://fapi.binance.com/fapi/v1/klines?symbol="+binanceSymbol+"&startTime="+str(tradeBeginTs-60000)+"&endTime="+str(tradeEndTs+60000)+"&interval=1m"
                        response = requests.request("GET", url,timeout=(3,7)).json()

                        bybitHoursVolArr = []
                        if bybitSymbol!="":
                            bybitKlineArr = getBybitKline(tradeBeginTs-15*60000,bybitSymbol)
                            bybitHoursVolArr = []
                            for i in range(125):
                                bybitHoursVolArr.append(0)
                            for i in range(len(bybitKlineArr)):
                                index  = int(i/4)
                                bybitHoursVolArr[index] = bybitHoursVolArr[index]+float(bybitKlineArr[len(bybitKlineArr)-1-i][6])
                            for i in range(len(bybitHoursVolArr)):
                                bybitHoursVolArr[i] = int(bybitHoursVolArr[i])

                        okexHoursVolArr = []
                        if okexSymbol!="":
                            okexKlineArr = getOkexKline(tradeBeginTs-15*60000,okexSymbol)
                            okexHoursVolArr = []
                            for i in range(125):
                                okexHoursVolArr.append(0)
                            for i in range(len(okexKlineArr)):
                                index  = int(i/4)
                                okexHoursVolArr[index] = okexHoursVolArr[index]+float(okexKlineArr[len(okexKlineArr)-1-i][7])
                            for i in range(len(okexHoursVolArr)):
                                okexHoursVolArr[i] = int(okexHoursVolArr[i])

                        binanceKlineArr = getBinanceKline(tradeBeginTs-15*60000,binanceSymbol)
                        binanceHoursVolArr = []
                        for i in range(125):
                            binanceHoursVolArr.append(0)
                        for i in range(len(binanceKlineArr)):
                            index  = int(i/4)
                            binanceHoursVolArr[index] = binanceHoursVolArr[index]+float(binanceKlineArr[len(binanceKlineArr)-1-i][7])
                        for i in range(len(binanceHoursVolArr)):
                            binanceHoursVolArr[i] = int(binanceHoursVolArr[i])


                        highPrice = 0
                        lowPrice = 9999999
                        for i in range(len(response)):
                            if float(response[i][2])>highPrice:
                                highPrice = float(response[i][2])
                            if float(response[i][3])<lowPrice:
                                lowPrice = float(response[i][3])
                        if direction=="s":
                            priceRate = FUNCTION_CLIENT.get_percent_num(highPrice-lowPrice,lowPrice)
                        elif direction=="l":
                            priceRate = FUNCTION_CLIENT.get_percent_num(highPrice-lowPrice,lowPrice)

                        profitPercentByBalance = FUNCTION_CLIENT.get_percent_num(profit,balance)

                        # UPDATE trades_take set profit, commission, status, profitPercentByBalance, volInfo, extraInfo where id=X
                        dbRow = session.exec(
                            select(TradesTake).where(TradesTake.id == tradeRecordDataID)
                        ).one()
                        dbRow.profit = decimal.Decimal(str(profit))
                        dbRow.commission = decimal.Decimal(str(commission))
                        dbRow.status = "updateProfit"
                        dbRow.profit_percent_by_balance = decimal.Decimal(str(profitPercentByBalance))
                        dbRow.vol_info = {"binanceHoursVolArr":binanceHoursVolArr,"okexHoursVolArr":okexHoursVolArr,"bybitHoursVolArr":bybitHoursVolArr}
                        dbRow.extra_info = {"priceRate":priceRate}
                        session.add(dbRow)
                        session.commit()
                    except Exception as e:
                        time.sleep(3)
                        ex = traceback.format_exc()
                        print(ex)
                else:
                    # UPDATE trades_take set status='updateProfitFail' where id=X
                    dbRow = session.exec(
                        select(TradesTake).where(TradesTake.id == tradeRecordDataID)
                    ).one()
                    dbRow.status = "updateProfitFail"
                    session.add(dbRow)
                    session.commit()


while 1:
    getBinancePositionFromMyServer()
    update()
    updateProfit()
    time.sleep(1)
