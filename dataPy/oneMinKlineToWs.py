#!/usr/bin/env python3
# coding=utf-8
import time
import requests
import traceback
import json
from settings import settings
from infra_client import InfraClient
from sqlmodel import select
from app.models.trade_symbol import TradeSymbol


FUNCTION_CLIENT = InfraClient(larkMsgSymbol="oneMinKlineToWs",connectMysql =True)

privateIP = FUNCTION_CLIENT.get_private_ip()

with FUNCTION_CLIENT.get_session() as session:
    TRADE_SYMBOL_DATA = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()

TRADE_SYMBOL_ARR = []
for row in TRADE_SYMBOL_DATA:
    symbolIndex = str(row.index)
    if len(symbolIndex) ==2:
        symbolIndex = "0"+symbolIndex
    if len(symbolIndex) ==1:
        symbolIndex = "00"+symbolIndex
    TRADE_SYMBOL_ARR.append({
            "symbol": row.symbol,
            "id": row.id,
            "price": "0",
            "symbolIndex": symbolIndex
        })

sendStr = "bbboiyfpdufiyuyu"+str(len(TRADE_SYMBOL_ARR))
FUNCTION_CLIENT.send_to_ws_a(sendStr)


REQUESTS_SESSION = requests.Session()

def klineToWs(tradeSymbolObj):
    global TRADE_SYMBOL_DATA,FUNCTION_CLIENT,REQUESTS_SESSION

    url = "https://fapi.binance.com/fapi/v1/klines?symbol="+tradeSymbolObj["symbol"]+"&interval=1m&limit=45"
    klineData = json.loads(REQUESTS_SESSION.get(url,timeout=(1,1)).content.decode())
    if 'code' in klineData:
        FUNCTION_CLIENT.send_notify_limit_one_min(str(klineData))
    else:
        try:
            url = "https://fapi.binance.com/fapi/v1/depth?symbol="+tradeSymbolObj["symbol"]+"&limit=5"
            depthData = json.loads(REQUESTS_SESSION.get(url,timeout=(1,1)).content.decode())
        except Exception as e:
            ex = traceback.format_exc()
            FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
        bidsPrice = 0
        asksPrice = 0
        if 'code' in depthData:
            FUNCTION_CLIENT.send_notify_limit_one_min(str(depthData))
        else:
            bidsPrice = float(depthData["bids"][0][0])
            asksPrice = float(depthData["asks"][0][0])

        allPriceStr = ""

        twoPriceStr = ""

        for i in range(len(klineData)):
            openPrice = float(klineData[i][1])
            highPrice = float(klineData[i][2])
            lowPrice = float(klineData[i][3])
            closePrice = float(klineData[i][4])

            if i ==len(klineData)-1:

                if bidsPrice!=0 and asksPrice!=0:
                    if asksPrice>highPrice:
                        highPrice = asksPrice

                    if bidsPrice<lowPrice:
                        lowPrice = bidsPrice


                    if closePrice>openPrice:
                        closePrice = asksPrice

                    if closePrice<openPrice:
                        closePrice = bidsPrice

                if allPriceStr=="":
                    allPriceStr = str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&"+str(highPrice)+"&"+str(lowPrice)+"&"+str(closePrice)
                else:
                    allPriceStr = allPriceStr+"~"+str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&"+str(highPrice)+"&"+str(lowPrice)+"&"+str(closePrice)
            else:
                if allPriceStr=="":
                    allPriceStr = str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&0&0&"+str(closePrice)
                else:
                    allPriceStr = allPriceStr+"~"+str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&0&0&"+str(closePrice)
            if i>len(klineData)-3:
                if i ==len(klineData)-1:

                    if bidsPrice!=0 and asksPrice!=0:
                        if asksPrice>highPrice:
                            highPrice = asksPrice

                        if bidsPrice<lowPrice:
                            lowPrice = bidsPrice


                        if closePrice>openPrice:
                            closePrice = asksPrice

                        if closePrice<openPrice:
                            closePrice = bidsPrice

                    if twoPriceStr=="":
                        twoPriceStr = str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&"+str(highPrice)+"&"+str(lowPrice)+"&"+str(closePrice)
                    else:
                        twoPriceStr = twoPriceStr+"~"+str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&"+str(highPrice)+"&"+str(lowPrice)+"&"+str(closePrice)
                else:
                    if twoPriceStr=="":
                        twoPriceStr = str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&0&0&"+str(closePrice)
                    else:
                        twoPriceStr = twoPriceStr+"~"+str(FUNCTION_CLIENT.turn_ts_to_min(klineData[i][0]))+"&"+str(openPrice)+"&0&0&"+str(closePrice)

        sendStr = "sajoiyfpdufiyiry"+str(tradeSymbolObj["symbolIndex"])+twoPriceStr
        FUNCTION_CLIENT.send_to_ws_a(sendStr)

        sendStr = "sjaiyhsaoyosauio"+str(tradeSymbolObj["symbolIndex"])+allPriceStr
        FUNCTION_CLIENT.send_to_ws_a(sendStr)

    time.sleep(0.25)



FUNCTION_CLIENT.send_notify_limit_one_min("start")

while 1:
    try:
        FUNCTION_CLIENT.update_machine_status()
        dataStr = FUNCTION_CLIENT.get_from_ws_a("F")
        symbolIndex = int(dataStr)
        klineToWs(TRADE_SYMBOL_ARR[symbolIndex])
    except Exception as e:
        FUNCTION_CLIENT.send_notify_limit_one_min(str(e))
        print(e)
        time.sleep(0.5)
        try:
            klineToWs(TRADE_SYMBOL_ARR[i])
        except Exception as e:
            FUNCTION_CLIENT.send_notify_limit_one_min(str(e))
            print(e)
            time.sleep(1)

