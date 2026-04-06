#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# encoding: utf-8
#客户端调用，用于查看API返回结果
import _thread
import decimal
import time
import requests
import json
import traceback
from binance_f.impl.utils.apisignature import create_signature
from binance_f.requestclient import RequestClient
from binance_f.constant.test import *
from binance_f.base.printobject import *
from binance_f.model.constant import *
from settings import settings
from infra_client import InfraClient
from sqlmodel import select
from sqlalchemy import delete
from app.models.income import Income
from app.models.income_history_take import IncomeHistoryTake


FUNCTION_CLIENT = InfraClient(larkMsgSymbol="commission",connectMysql =True)


privateIP = FUNCTION_CLIENT.get_private_ip()


BINANCE_API_KEY =""

BINANCE_API_SECRET =""

LAST_SHORT_LOSS_LOCK_TS = 0

MACHINE_INDEX = settings.machine_index

INCOME_TABLE_NAME_ARR = ["income_history_take"]

TEMP_INCOME_TABLE_NAME_ARR = ["income"]

TRADES_TABLE_NAME = "binance_trades"

SCAN_EXIT_TABLE = INCOME_TABLE_NAME_ARR+TEMP_INCOME_TABLE_NAME_ARR


BINANCE_API_KEY_ARR =[""]
BINANCE_API_SECRET_ARR =[""]

REQUEST_CLIENT = RequestClient(api_key=BINANCE_API_KEY_ARR[MACHINE_INDEX],secret_key=BINANCE_API_SECRET_ARR[MACHINE_INDEX])

INCOME_TABLE_NAME = INCOME_TABLE_NAME_ARR[MACHINE_INDEX]

TEMP_INCOME_TABLE_NAME = TEMP_INCOME_TABLE_NAME_ARR[MACHINE_INDEX]


def getBNBPrice():
    nowPrice = 0
    tryTime = 0
    while nowPrice==0:
        try:
            url = "https://api.binance.com/api/v1/depth?symbol=BNBUSDT&limit=5"
            response = requests.request("GET", url,timeout=(3,7)).json()
            nowPrice = (float(response['asks'][0][0])+float(response['bids'][0][0])) /2
        except Exception as e:
            tryTime = tryTime+1
            time.sleep(1)
            if tryTime>3:
                FUNCTION_CLIENT.send_notify_limit_one_min("读取bnb价格出错")
            print(e)
    return nowPrice

INCOME_TABLE_DELETE_TS = 0
UPDATE_TS = 0
def record_commission():
    global MACHINE_INDEX,TEMP_INCOME_TABLE_NAME,INCOME_TABLE_NAME,REQUEST_CLIENT,BINANCE_API_KEY_ARR,BINANCE_API_SECRET_ARR,INCOME_TABLE_NAME_ARR,FUNCTION_CLIENT,INCOME_TABLE_DELETE_TS,UPDATE_TS

    now = int(time.time()*1000)
    if now - UPDATE_TS>1000:
        UPDATE_TS = now
        with FUNCTION_CLIENT.get_session() as session:
            if now - INCOME_TABLE_DELETE_TS>3600000:
                INCOME_TABLE_DELETE_TS = now
                session.exec(delete(Income).where(Income.binance_ts < now - 86400000))
                session.commit()

            incomeRows = session.exec(
                select(Income).order_by(Income.id.desc())
            ).all()
        lasIncomeTs = 0
        if len(incomeRows)>0:
            lasIncomeTs = incomeRows[0].binance_ts

        fourHoursProfitObj = {}
        oneDayProfitObj = {}
        allOneDayProfit = 0
        allFourHoursProfit= 0
        for row in incomeRows:
            symbol = row.symbol
            profit = float(row.income) if row.income is not None else 0

            binanceTs = row.binance_ts
            allOneDayProfit = allOneDayProfit+profit
            if now - binanceTs<4*60*60*1000:
                allFourHoursProfit = allFourHoursProfit+profit
                if symbol in fourHoursProfitObj:
                    fourHoursProfitObj[symbol] =  fourHoursProfitObj[symbol]+profit
                else:
                    fourHoursProfitObj[symbol] = profit
            if symbol in oneDayProfitObj:
                oneDayProfitObj[symbol] =  oneDayProfitObj[symbol]+profit
            else:
                oneDayProfitObj[symbol] = profit

            if not(symbol in fourHoursProfitObj):
                fourHoursProfitObj[symbol] = 0
        banSymbolArr = []

        for key in fourHoursProfitObj:
            if fourHoursProfitObj[key]<=-150 or oneDayProfitObj[key]<=-1800:
                banSymbolArr.append(key)

        if allOneDayProfit<=-3000:
            banSymbolArr = ["ALL"]


        sendStr = ""
        for a in range(len(banSymbolArr)):

            if sendStr=="":
                sendStr = banSymbolArr[a]
            else:
                sendStr = sendStr+"@"+ banSymbolArr[a]
        if sendStr=="":
            sendStr = "AAAUSDT"
        sendStr = "abcoihsoaitowljd"+sendStr

        FUNCTION_CLIENT.send_to_ws_a(sendStr)

        with FUNCTION_CLIENT.get_session() as session:
            lastBinanceTsRows = session.exec(
                select(IncomeHistoryTake).order_by(IncomeHistoryTake.id.desc()).limit(2000)
            ).all()
        lastBinanceTs = 0
        if len(lastBinanceTsRows)>0:
            lastBinanceTs = lastBinanceTsRows[0].binance_ts

        result = REQUEST_CLIENT.get_income_history_with_no_symbol()
        result = json.loads(result)

        if "code" in result:
            FUNCTION_CLIENT.send_notify_limit_one_min(str(result))
        else:
            new_income_rows = []
            for i in range(len(result)):
                trade_id = str(result[i]['tradeId'])
                binance_ts = int(result[i]['time'])
                incomeType = str(result[i]['incomeType'])
                income = str(result[i]['income'])
                asset = str(result[i]['asset'])
                info = str(result[i]['info'])
                my_ts = int(time.time())
                symbol = str(result[i]['symbol'])
                if incomeType=="REALIZED_PNL":
                    isExit = False
                    scanCount = len(incomeRows)
                    if scanCount>2000:
                        scanCount = 2000
                    for b in range(scanCount):
                        if (str(int(incomeRows[b].binance_ts))==str(int(binance_ts))) and (format(float(incomeRows[b].income),'.8f') == format(float(income),'.8f')) and  (str(incomeRows[b].trade_id) == str(trade_id)):
                            isExit = True
                    if not isExit:
                        new_income_rows.append(Income(
                            income=income,
                            trade_id=trade_id,
                            binance_ts=binance_ts,
                            symbol=symbol,
                        ))
            if new_income_rows:
                with FUNCTION_CLIENT.get_session() as session:
                    session.add_all(new_income_rows)
                    session.commit()

            bnbPrice = getBNBPrice()

            new_history_rows = []
            for i in range(len(result)):
                trade_id = str(result[i]['tradeId'])
                binance_ts = int(result[i]['time'])
                incomeType = str(result[i]['incomeType'])
                income = str(result[i]['income'])
                asset = str(result[i]['asset'])
                info = str(result[i]['info'])
                my_ts = int(time.time())
                symbol = str(result[i]['symbol'])

                isExit = False

                for b in range(len(lastBinanceTsRows)):
                    if (str(int(lastBinanceTsRows[b].binance_ts))==str(int(binance_ts))) and (str(lastBinanceTsRows[b].income_type) == str(incomeType)) and (format(float(lastBinanceTsRows[b].income),'.8f') == format(float(income),'.8f')) and (str(lastBinanceTsRows[b].asset) == str(asset)) and (str(lastBinanceTsRows[b].trade_id) == str(trade_id)):
                        isExit = True
                if not isExit and result[i]['time']>1688256000000:
                    new_history_rows.append(IncomeHistoryTake(
                        income_type=incomeType,
                        income=income,
                        asset=asset,
                        info=info,
                        trade_id=trade_id,
                        binance_ts=binance_ts,
                        my_ts=my_ts,
                        symbol=symbol,
                        instrument_id=symbol,
                        coin=symbol,
                        bnb_price=bnbPrice,
                    ))
            if new_history_rows:
                with FUNCTION_CLIENT.get_session() as session:
                    session.add_all(new_history_rows)
                    session.commit()


while 1:
    try:
        _thread.start_new_thread(FUNCTION_CLIENT.update_machine_status,())
        record_commission()
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
        time.sleep(1)
        print(e)
    time.sleep(1)
