#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# encoding: utf-8
#客户端调用，用于查看API返回结果
import json
import random
import time
import requests
import socket
import decimal
import traceback
import _thread
from binance_f.impl.utils.apisignature import create_signature
from binance_f.requestclient import RequestClient
from binance_f.constant.test import *
from binance_f.base.printobject import *
from binance_f.model.constant import *
from settings import settings
from infra_client import InfraClient
from sqlmodel import select
from app.models.trade import Trade

PUBLIC_SERVER_IP = "http://"+settings.web_address+":8888/"

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="ordersRecord",connectMysql =True)

BINANCE_API_KEY =""

BINANCE_API_SECRET =""

response = requests.request("POST", PUBLIC_SERVER_IP+"get_symbol_index", timeout=3).json()

TRADE_SYMBOL_ARR = response["d"]

TRADES_TABLE_NAME = "trade"




BNB_PRICE  = 0
LAST_UPDATE_BNB_PRICE_TS = 0
def updateBnbPrice():
    global BNB_PRICE,LAST_UPDATE_BNB_PRICE_TS
    now  = int(time.time()*1000)
    if now - LAST_UPDATE_BNB_PRICE_TS>60000:
        LAST_UPDATE_BNB_PRICE_TS = now
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=BNBUSDT&limit=1&interval=1m"
            response = requests.request("GET", url,timeout=(2,2)).json()
            if float(response[0][4])>0:
                BNB_PRICE = float(response[0][4])
        except Exception as e:
            print(e)
def recordTrades(symbol):
    global BINANCE_API_KEY,BINANCE_API_SECRET,TRADES_TABLE_NAME
    now = int(time.time())
    updateBnbPrice()
    with FUNCTION_CLIENT.get_session() as session:
        tradesData = session.exec(
            select(Trade).where(Trade.symbol == symbol).order_by(Trade.id.desc()).limit(1000)
        ).all()
    lastBinanceTs = 0
    if len(tradesData)>0:
        lastBinanceTs = tradesData[0].ts


    request_client = RequestClient(api_key=BINANCE_API_KEY,secret_key=BINANCE_API_SECRET)
    result = request_client.get_account_trades(symbol)
    result = json.loads(result)
    print(result)
    if "code" in result:
        FUNCTION_CLIENT.send_notify_limit_one_min(str(result))
    else:
        new_trades = []
        for i in range(len(result)):

            buyer = result[i]['buyer']
            commission = result[i]['commission']
            commissionAsset = result[i]['commissionAsset']
            binanceId = result[i]['id']
            maker = result[i]['maker']

            orderId = result[i]['orderId']
            price = result[i]['price']
            qty = result[i]['qty']
            quoteQty = result[i]['quoteQty']
            realizedPnl = result[i]['realizedPnl']

            side = result[i]['side']
            positionSide = result[i]['positionSide']
            symbol = result[i]['symbol']
            binanceTs = result[i]['time']

            myTs = int(time.time())


            insert = True
            for b in range(len(tradesData)):
                if int(tradesData[b].binance_id) == int(binanceId):
                    insert = False
                    break

            if insert:
                new_trades.append(Trade(
                    buyer=bool(buyer),
                    commission=commission,
                    binance_id=binanceId,
                    maker=bool(maker),
                    order_id=orderId,
                    price=price,
                    qty=qty,
                    quote_qty=quoteQty,
                    realized_pnl=realizedPnl,
                    side=side,
                    position_side=positionSide,
                    symbol=symbol,
                    ts=binanceTs,
                    my_ts=now,
                ))
        if new_trades:
            with FUNCTION_CLIENT.get_session() as session:
                session.add_all(new_trades)
                session.commit()


while 1:
    for i in range(len(TRADE_SYMBOL_ARR)):
        try:
            recordTrades(TRADE_SYMBOL_ARR[i]["symbol"])
        except Exception as e:
            FUNCTION_CLIENT.send_notify_limit_one_min(str(e))
        time.sleep(1)
