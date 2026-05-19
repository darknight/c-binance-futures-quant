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
from app.models.order import Order

PUBLIC_SERVER_IP = "http://"+settings.web_address+":8888/"

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="ordersRecord",connectMysql =True)

BINANCE_API_KEY =""

BINANCE_API_SECRET =""

response = requests.request("POST", PUBLIC_SERVER_IP+"get_symbol_index", timeout=3).json()

TRADE_SYMBOL_ARR = response["d"]

ORDERS_TABLE_NAME = "order"




def recordTrades(symbol):
    global BINANCE_API_KEY,BINANCE_API_SECRET,ORDERS_TABLE_NAME
    now = int(time.time())

    with FUNCTION_CLIENT.get_session() as session:
        lastBinanceTsData = session.exec(
            select(Order).where(Order.symbol == symbol).order_by(Order.id.desc()).limit(1000)
        ).all()
    lastBinanceTs = 0
    if len(lastBinanceTsData)>0:
        lastBinanceTs = lastBinanceTsData[0].binance_ts


    request_client = RequestClient(api_key=BINANCE_API_KEY,secret_key=BINANCE_API_SECRET)
    result = request_client.get_all_orders(symbol)
    result = json.loads(result)
    for i in range(len(result)):
        if result[i]["executedQty"]!="0" and result[i]["side"]=="SELL":
            print(result[i])
    if "code" in result:
        FUNCTION_CLIENT.send_notify_limit_one_min(str(result))
    else:
        new_orders = []
        update_orders = []
        for i in range(len(result)):

            avgPrice = result[i]['avgPrice']
            clientOrderId = result[i]['clientOrderId']
            cumQuote = result[i]['cumQuote']
            executedQty = result[i]['executedQty']
            orderId = result[i]['orderId']

            origQty = result[i]['origQty']
            origType = result[i]['origType']
            price = result[i]['price']
            reduceOnly = str(result[i]['reduceOnly'])
            side = result[i]['side']

            positionSide = result[i]['positionSide']
            status = result[i]['status']
            stopPrice = result[i]['stopPrice']
            closePosition = str(result[i]['closePosition'])
            symbol = result[i]['symbol']

            timeInForce = result[i]['timeInForce']
            orderType = result[i]['type']
            updateTime = result[i]['updateTime']
            workingType = result[i]['workingType']
            priceProtect = str(result[i]['priceProtect'])

            binanceTs = result[i]['time']
            myTs = int(time.time())


            noInsert = False
            update = False
            DBID = None
            for b in range(len(lastBinanceTsData)):
                DBBinanceTs = lastBinanceTsData[b].binance_ts
                DBOrderId = lastBinanceTsData[b].order_id
                DBUpdateTime = lastBinanceTsData[b].update_time
                DBStatus = lastBinanceTsData[b].status
                DBID = lastBinanceTsData[b].id
                if int(DBOrderId) == int(orderId):
                    noInsert = True
                if int(DBBinanceTs)==int(binanceTs) and int(DBOrderId) == int(orderId) and (int(DBUpdateTime) != int(updateTime) or str(DBStatus) != str(status)):
                    update = True
            if not noInsert:
                new_orders.append(Order(
                    avg_price=avgPrice,
                    client_order_id=clientOrderId,
                    cum_quote=cumQuote,
                    executed_qty=executedQty,
                    order_id=orderId,
                    orig_qty=origQty,
                    orig_type=origType,
                    price=price,
                    reduce_only=reduceOnly,
                    side=side,
                    position_side=positionSide,
                    status=status,
                    stop_price=stopPrice,
                    close_position=closePosition,
                    symbol=symbol,
                    time_in_force=timeInForce,
                    order_type=orderType,
                    update_time=updateTime,
                    working_type=workingType,
                    price_protect=priceProtect,
                    binance_ts=binanceTs,
                    my_ts=myTs,
                ))
            if update:
                update_orders.append((DBID, dict(
                    avg_price=avgPrice,
                    client_order_id=clientOrderId,
                    cum_quote=cumQuote,
                    executed_qty=executedQty,
                    order_id=orderId,
                    orig_qty=origQty,
                    orig_type=origType,
                    price=price,
                    reduce_only=reduceOnly,
                    side=side,
                    position_side=positionSide,
                    status=status,
                    stop_price=stopPrice,
                    close_position=closePosition,
                    symbol=symbol,
                    time_in_force=timeInForce,
                    order_type=orderType,
                    update_time=updateTime,
                    working_type=workingType,
                    price_protect=priceProtect,
                    binance_ts=binanceTs,
                    my_ts=myTs,
                )))

        if new_orders or update_orders:
            with FUNCTION_CLIENT.get_session() as session:
                if new_orders:
                    session.add_all(new_orders)
                for (row_id, fields) in update_orders:
                    db_row = session.get(Order, row_id)
                    if db_row:
                        for k, v in fields.items():
                            setattr(db_row, k, v)
                        session.add(db_row)
                session.commit()

        time.sleep(3)

TRADES_ERROR_WARN_TS = 0

def updateTrade(symbol):
    global BINANCE_API_KEY,BINANCE_API_SECRET,SEND_ORDERS_CODE_ERROR_TS,TRADES_ERROR_WARN_TS,ORDERS_TABLE_NAME
    now = int(time.time())
    myTs = int(time.time())

    with FUNCTION_CLIENT.get_session() as session:
        data = session.exec(
            select(Order).where(Order.status == "NEW", Order.my_ts < now - 3600)
        ).all()
    if len(data)>0:
        request_client = RequestClient(api_key=BINANCE_API_KEY,secret_key=BINANCE_API_SECRET)
        result = request_client.get_order_by_client_id(symbol, data[0].client_order_id)
        result = json.loads(result)
        if "code" in result:
            if result["code"]==-2013:
                with FUNCTION_CLIENT.get_session() as session:
                    db_row = session.get(Order, data[0].id)
                    if db_row:
                        db_row.status = "noExit"
                        db_row.my_ts = myTs
                        session.add(db_row)
                        session.commit()
            else:
                FUNCTION_CLIENT.send_notify_limit_one_min(str(result))
        else:
            print(result)
            avgPrice = result['avgPrice']
            clientOrderId = result['clientOrderId']
            cumQuote = result['cumQuote']
            executedQty = result['executedQty']
            orderId = result['orderId']

            origQty = result['origQty']
            origType = result['origType']
            price = result['price']
            reduceOnly = str(result['reduceOnly'])
            side = result['side']

            positionSide = result['positionSide']
            status = result['status']
            stopPrice = result['stopPrice']
            closePosition = str(result['closePosition'])
            symbol = result['symbol']

            timeInForce = result['timeInForce']
            orderType = result['type']
            updateTime = result['updateTime']
            workingType = result['workingType']
            priceProtect = str(result['priceProtect'])

            binanceTs = result['time']
            with FUNCTION_CLIENT.get_session() as session:
                db_row = session.get(Order, data[0].id)
                if db_row:
                    db_row.avg_price = avgPrice
                    db_row.client_order_id = clientOrderId
                    db_row.cum_quote = cumQuote
                    db_row.executed_qty = executedQty
                    db_row.order_id = orderId
                    db_row.orig_qty = origQty
                    db_row.orig_type = origType
                    db_row.price = price
                    db_row.reduce_only = reduceOnly
                    db_row.side = side
                    db_row.position_side = positionSide
                    db_row.status = status
                    db_row.stop_price = stopPrice
                    db_row.close_position = closePosition
                    db_row.symbol = symbol
                    db_row.time_in_force = timeInForce
                    db_row.order_type = orderType
                    db_row.update_time = updateTime
                    db_row.working_type = workingType
                    db_row.price_protect = priceProtect
                    db_row.binance_ts = binanceTs
                    db_row.my_ts = myTs
                    session.add(db_row)
                    session.commit()



recordTrades("MAVUSDT")
while 1:
    for i in range(len(TRADE_SYMBOL_ARR)):
        try:
            recordTrades(TRADE_SYMBOL_ARR[i]["symbol"])
            updateTrade(TRADE_SYMBOL_ARR[i]["symbol"])

        except Exception as e:
            FUNCTION_CLIENT.send_notify_limit_one_min(str(e))
        time.sleep(1)
