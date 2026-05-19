#!/usr/bin/env python3
# encoding:utf-8
import time
import requests
import json
import random
import traceback
import _thread
from sqlmodel import select
from sqlalchemy import asc
from settings import settings
from infra_client import InfraClient
from app.models.income_history_take import IncomeHistoryTake
from app.models.income_history_take_day import IncomeHistoryTakeDay
from app.models.machine_status import TradeMachineStatus
from app.models.trades_take import TradesTake
from app.models.position_record import PositionRecord

PUBLIC_SERVER_IP = "http://"+settings.web_address+":8888/"

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="dataToOss",connectMysql =True)

DAY_INCOME_TABLE_NAME = "income_history_take_day"

INCOME_TABLE_NAME = "income_history_take"

INIT_DAY_INCOME_RECORD_TIME = "2023-07-20 00:00:00"



LAST_GENERATE_TIME = ""

HISTORY_INVESTOR_OBJ = [
    {
        "id":1,
        "beginTime":"2023-05-09",
        "endTime":"2023-05-28",
        "initValue":0,
        "endValue":0,
        "userData":[]

    }
]
INVESTOR_OBJ =[{'name': 'mele', 'time': '2023-07-20 00:00:00', 'percent': 100, 'initValue': 922, 'assetsWhileJoin': 922, 'protectValue': 0}]



PROFIT_UPDATE_TS = 0

INFO_OBJ = {}


def _dt_to_str(dt_obj):
    """Convert a datetime object to 'YYYY-MM-DD HH:MM:SS' string (UTC)."""
    return dt_obj.strftime("%Y-%m-%d %H:%M:%S")


def getProfit():
    global ALL_PROFIT,MAKER_COMMISSION_RATE,FUNCTION_CLIENT,INCOME_TABLE_NAME,INFO_OBJ,PROFIT_UPDATE_TS,SEND_PROFIT_EX_TS
    now = int(time.time()*1000)
    todayTs = FUNCTION_CLIENT.turn_ts_to_time(FUNCTION_CLIENT.turn_ts_to_day_time(int(time.time())))*1000

    nowMin = int(FUNCTION_CLIENT.turn_ts_to_min(now))
    print(nowMin)
    if (todayTs != PROFIT_UPDATE_TS and nowMin>=5) or INFO_OBJ=={}:

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT income, binance_ts, incomeType, bnbPrice, asset, symbol from income_history_take where binance_ts < todayTs
            incomeRows = session.exec(
                select(IncomeHistoryTake).where(IncomeHistoryTake.binance_ts < todayTs)
            ).all()

        INFO_OBJ["p"] = {}
        INFO_OBJ["c"] = {}
        INFO_OBJ["v"] = {}
        INFO_OBJ["t"] = 0
        for row in incomeRows:
            income = float(row.income) if row.income is not None else 0
            binanceTs = row.binance_ts
            incomeType = row.income_type
            bnbPrice = float(row.bnb_price) if row.bnb_price is not None else 0
            asset = row.asset
            symbol = row.symbol

            if symbol!='':
                realIncome = 0
                if not (symbol in INFO_OBJ["p"]):
                    INFO_OBJ["p"][symbol]=[0,0,0,0]
                if not (symbol in INFO_OBJ["c"]):
                    INFO_OBJ["c"][symbol]=[0,0,0,0]
                if not (symbol in INFO_OBJ["v"]):
                    INFO_OBJ["v"][symbol]=[0,0,0,0]

                if asset=="BNB":
                    realIncome = income*bnbPrice
                else:
                    realIncome = income
                if incomeType=="COMMISSION":
                    if binanceTs>=todayTs-86400*1000:
                        INFO_OBJ["c"][symbol][0] = INFO_OBJ["c"][symbol][0]+realIncome*0.6
                        if asset=="BNB":
                            INFO_OBJ["v"][symbol][0] = INFO_OBJ["v"][symbol][0]+income*0.6

                    if binanceTs>=todayTs-7*24*60*60*1000:
                        INFO_OBJ["c"][symbol][1] = INFO_OBJ["c"][symbol][1]+realIncome*0.6
                        if asset=="BNB":
                            INFO_OBJ["v"][symbol][1] = INFO_OBJ["v"][symbol][1]+income*0.6
                    if binanceTs>=todayTs-30*24*60*60*1000:
                        INFO_OBJ["c"][symbol][2] = INFO_OBJ["c"][symbol][2]+realIncome*0.6
                        if asset=="BNB":
                            INFO_OBJ["v"][symbol][2] = INFO_OBJ["v"][symbol][2]+income*0.6

                    INFO_OBJ["c"][symbol][3] = INFO_OBJ["c"][symbol][3]+realIncome*0.6
                    if asset=="BNB":
                        INFO_OBJ["v"][symbol][3] = INFO_OBJ["v"][symbol][3]+income*0.6

                if incomeType=="REALIZED_PNL"  or incomeType=="FUNDING_FEE" :
                    if binanceTs>=todayTs-86400*1000:
                        INFO_OBJ["p"][symbol][0] = INFO_OBJ["p"][symbol][0]+realIncome
                    if binanceTs>=todayTs-7*24*60*60*1000:
                        INFO_OBJ["p"][symbol][1] = INFO_OBJ["p"][symbol][1]+realIncome
                    if binanceTs>=todayTs-30*24*60*60*1000:
                        INFO_OBJ["p"][symbol][2] = INFO_OBJ["p"][symbol][2]+realIncome

                    INFO_OBJ["p"][symbol][3] = INFO_OBJ["p"][symbol][3]+realIncome
                if  incomeType=="COMMISSION":
                    if binanceTs>=todayTs-86400*1000:
                        INFO_OBJ["p"][symbol][0] = INFO_OBJ["p"][symbol][0]+realIncome*0.6
                    if binanceTs>=todayTs-7*24*60*60*1000:
                        INFO_OBJ["p"][symbol][1] = INFO_OBJ["p"][symbol][1]+realIncome*0.6
                    if binanceTs>=todayTs-30*24*60*60*1000:
                        INFO_OBJ["p"][symbol][2] = INFO_OBJ["p"][symbol][2]+realIncome*0.6

                    INFO_OBJ["p"][symbol][3] = INFO_OBJ["p"][symbol][3]+realIncome*0.6
        INFO_OBJ["p"]["all"] = [0,0,0,0]
        for key in (INFO_OBJ["p"]):
            for i in range(4):
                if key!="all":
                    INFO_OBJ["p"]["all"][i] = INFO_OBJ["p"]["all"][i]+INFO_OBJ["p"][key][i]
                INFO_OBJ["p"][key][i] = INFO_OBJ["p"][key][i]

        INFO_OBJ["v"]["all"] = [0,0,0,0]
        for key in (INFO_OBJ["v"]):
            for i in range(4):
                if key!="all":
                    INFO_OBJ["v"]["all"][i] = INFO_OBJ["v"]["all"][i]+INFO_OBJ["v"][key][i]
                INFO_OBJ["v"][key][i] = INFO_OBJ["v"][key][i]

        INFO_OBJ["c"]["all"] = [0,0,0,0]
        for key in (INFO_OBJ["c"]):
            for i in range(4):
                if key!="all":
                    INFO_OBJ["c"]["all"][i] = INFO_OBJ["c"]["all"][i]+INFO_OBJ["c"][key][i]
                INFO_OBJ["c"][key][i] = INFO_OBJ["c"][key][i]

        INFO_OBJ["t"] = todayTs
        PROFIT_UPDATE_TS = todayTs
        # except Exception as e:
        #     print(e)
        #     FUNCTION_CLIENT.send_notify_limit_one_min("getProfit ex:"+str(e))


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


SECOND_OPEN_OBJ_ARR = []

SECOND_OPEN_OBJ_ARR_UPDATE_TS = 0

SECOND_OPEN_OBJ_ARR_UPDATE_DELAY_TIME = random.randint(1,60)

TODAY_PROFIT = 0

LAST_GENERATE_TS = 0

def generateObj():
    global POSITION_ARR,ACCOUNT_BALANCE_VALUE,LAST_GENERATE_TS,TODAY_PROFIT,MAKER_COMMISSION_RATE,TAKER_COMMISSION_RATE,INFO_OBJ,FUNCTION_CLIENT,LAST_GENERATE_TIME,INVESTOR_OBJ,HISTORY_INVESTOR_OBJ,SECOND_OPEN_OBJ_ARR,SECOND_OPEN_OBJ_ARR_UPDATE_TS,SECOND_OPEN_OBJ_ARR_UPDATE_DELAY_TIME
    nowTime = FUNCTION_CLIENT.turn_ts_to_time(int(time.time()))
    now = int(time.time()*1000)
    if now - LAST_GENERATE_TS>3000:

        LAST_GENERATE_TS = now

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT status, update_ts, run_time from trade_machine_status ORDER BY update_ts ASC
            tradeMachineRows = session.exec(
                select(TradeMachineStatus).order_by(asc(TradeMachineStatus.update_ts))
            ).all()

        allRunTime = 0
        for row in tradeMachineRows:
            allRunTime = allRunTime + (row.run_time or 0)

        systemAverageRunTime = int(allRunTime/len(tradeMachineRows))
        systemUpdateTs = tradeMachineRows[0].update_ts
        systemStatus = tradeMachineRows[0].status

        bigLossTradeArr = []
        with FUNCTION_CLIENT.get_session() as session:
            # SELECT symbol, endTs, profit, profitPercentByBalance, extraInfo, direction from trades_take
            # where status='updateProfit' ORDER BY id ASC LIMIT 1000
            bigLossRows = session.exec(
                select(TradesTake)
                .where(TradesTake.status == "updateProfit")
                .order_by(TradesTake.id.asc())
                .limit(1000)
            ).all()

        for row in bigLossRows:
            extraInfo = row.extra_info if row.extra_info is not None else {}
            priceRate = 0
            if "priceRate" in extraInfo:
                priceRate = abs(int(float(extraInfo["priceRate"])*100)/100)
            bigLossTradeArr.insert(0,[
                    row.symbol,
                    FUNCTION_CLIENT.turn_ts_to_time(row.end_ts),
                    int(float(row.profit) if row.profit is not None else 0),
                    str(abs(int(float(row.profit_percent_by_balance)*100)/100))+"%",
                    priceRate,
                    row.direction
                ])


        getBinancePositionFromMyServer()

        allPositionValue = 0
        positionArr = []
        for a in range(len(POSITION_ARR)):
            positionValue = int(abs(float(POSITION_ARR[a][1])*float(POSITION_ARR[a][2])))
            allPositionValue = allPositionValue + positionValue
            direction = "s"
            if float(POSITION_ARR[a][1])>0:
                direction = "l"
            positionArr.append({
                    "value":positionValue,
                    "symbol":float(POSITION_ARR[a][0]),
                    "direction":direction,
                    "entryPrice":float(POSITION_ARR[a][2])
                })

        todayTs = FUNCTION_CLIENT.turn_ts_to_time(FUNCTION_CLIENT.turn_ts_to_day_time(int(time.time())))*1000

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT income, binance_ts, incomeType, bnbPrice, asset, symbol from income_history_take
            # where binance_ts >= now - 24h
            incomeRows = session.exec(
                select(IncomeHistoryTake).where(IncomeHistoryTake.binance_ts >= now - 86400000)
            ).all()

        oneDayVol = 0
        oneDayProfit = 0
        todayProfit = 0
        for row in incomeRows:
            income = float(row.income) if row.income is not None else 0
            binanceTs = row.binance_ts
            incomeType = row.income_type
            bnbPrice = float(row.bnb_price) if row.bnb_price is not None else 0
            asset = row.asset
            symbol = row.symbol

            if symbol!='':
                realIncome = 0
                if not (symbol in INFO_OBJ["p"]):
                    INFO_OBJ["p"][symbol]=[0,0,0,0]
                if not (symbol in INFO_OBJ["c"]):
                    INFO_OBJ["c"][symbol]=[0,0,0,0]
                if not (symbol in INFO_OBJ["v"]):
                    INFO_OBJ["v"][symbol]=[0,0,0,0]

                if asset=="BNB":
                    realIncome = income*bnbPrice
                else:
                    realIncome = income

                if incomeType=="COMMISSION":

                    if realIncome>0:
                        oneDayVol = oneDayVol+realIncome*0.6
                    else:
                        oneDayVol = oneDayVol+realIncome*0.6


                if incomeType=="REALIZED_PNL" or incomeType=="FUNDING_FEE":
                    oneDayProfit = oneDayProfit+realIncome
                    if binanceTs>=todayTs:
                        todayProfit = todayProfit+realIncome
                if incomeType=="COMMISSION":
                    oneDayProfit = oneDayProfit+realIncome*0.6
                    if binanceTs>=todayTs:
                        todayProfit = todayProfit+realIncome*0.6



        fromLastInvestor = []
        lastOneDays = []
        lastSevenDays = []
        lastOneMonth = []
        TODAY_PROFIT = todayProfit


        pushObj = {
            "positionArr":positionArr,
            "todayProfit":todayProfit,
            "oneDayVol":int(abs(oneDayVol)),
            "oneDayProfit":int(oneDayProfit),
            "allPositionValue":int(allPositionValue),
            "secondOpenObjArr":INFO_OBJ,
            "accountBalanceValue":ACCOUNT_BALANCE_VALUE,
            "bigLossTradeArr":bigLossTradeArr,
            "investPercentObjArr":INVESTOR_OBJ,
            "systemStatus":systemStatus,
            "systemUpdateTs":systemUpdateTs,
            "runTime":allRunTime,
        }

        LAST_GENERATE_TIME = nowTime
        FUNCTION_CLIENT.oss_put_obj(pushObj,"cQuant/"+nowTime+".json")

        FUNCTION_CLIENT.oss_put_obj(pushObj,"cQuant/a.json")

        pushObj = {
            "now":INVESTOR_OBJ,
            "history":HISTORY_INVESTOR_OBJ
        }
        FUNCTION_CLIENT.oss_put_obj(pushObj,"investor/"+nowTime+".json")
    time.sleep(1)


LAST_UPDATE_RECORD_TIME = ""
def updateRecord():
    global INVESTOR_OBJ,LAST_UPDATE_RECORD_TIME
    nowTime = FUNCTION_CLIENT.turn_ts_to_time(int(time.time()))
    if LAST_UPDATE_RECORD_TIME!=nowTime:
        LAST_UPDATE_RECORD_TIME = nowTime
        now  = int(time.time())

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT positionValue, balance, ts, time from position_record ORDER BY id ASC
            positionRows = session.exec(
                select(PositionRecord).order_by(PositionRecord.id.asc())
            ).all()

        fromLastInvestorLimitTs = FUNCTION_CLIENT.turn_ts_to_day_time(INVESTOR_OBJ[0]["time"])
        # fromLastInvestorLimitTs = FUNCTION_CLIENT.turn_ts_to_day_time('2023-06-13 20:17:00')
        print("fromLastInvestorLimitTs:"+str(fromLastInvestorLimitTs))
        lastOneDayLimitTs = now-86400
        lastSevenDaysLimitTs = now-7*86400
        lastOneMonthLimitTs = now-30*86400


        fromLastInvestorArr = []
        lastDataTsA = 0
        lastBalanceA = 0
        lastPositionValueA = 0

        lastOneDayArr = []
        lastDataTsB = 0
        lastBalanceB = 0
        lastPositionValueB = 0

        lastSevenDaysArr = []
        lastDataTsC = 0
        lastBalanceC = 0
        lastPositionValueC = 0

        lastOneMonthArr = []
        lastDataTsD = 0
        lastBalanceD = 0
        lastPositionValueD = 0

        allArr = []
        lastDataTsE = 0
        lastBalanceE = 0
        lastPositionValueE = 0

        for row in positionRows:
            dataTs = row.ts
            positionValue =  int(float(row.position_value) if row.position_value is not None else 0)
            balance =  int(float(row.balance) if row.balance is not None else 0)
            dataTime = row.time



            if dataTs>=fromLastInvestorLimitTs:
                tsChange = int(dataTs-lastDataTsA)
                positionValueChange = int(positionValue-lastPositionValueA)
                balanceChange = int(balance-lastBalanceA)
                fromLastInvestorArr.append([positionValueChange,balanceChange,tsChange])
                lastDataTsA = dataTs
                lastPositionValueA = int(positionValue)
                lastBalanceA = int(balance)
            if dataTs>=lastOneDayLimitTs:
                tsChange = int(dataTs-lastDataTsB)
                positionValueChange = int(positionValue-lastPositionValueB)
                balanceChange = int(balance-lastBalanceB)
                lastOneDayArr.append([positionValueChange,balanceChange,tsChange])
                lastDataTsB = dataTs
                lastPositionValueB = int(positionValue)
                lastBalanceB = int(balance)
            if dataTs>=lastSevenDaysLimitTs:
                tsChange = int(dataTs-lastDataTsC)
                positionValueChange = int(positionValue-lastPositionValueC)
                balanceChange = int(balance-lastBalanceC)
                lastSevenDaysArr.append([positionValueChange,balanceChange,tsChange])
                lastDataTsC = dataTs
                lastPositionValueC = int(positionValue)
                lastBalanceC = int(balance)
            if dataTs>=lastOneMonthLimitTs:
                tsDhange = int(dataTs-lastDataTsD)
                positionValueDhange = int(positionValue-lastPositionValueD)
                balanceDhange = int(balance-lastBalanceD)
                lastOneMonthArr.append([positionValueDhange,balanceDhange,tsDhange])
                lastDataTsD = dataTs
                lastPositionValueD = int(positionValue)
                lastBalanceD = int(balance)
            tsEhange = int(dataTs-lastDataTsE)
            positionValueEhange = int(positionValue-lastPositionValueE)
            balanceEhange = int(balance-lastBalanceE)
            allArr.append([positionValueEhange,balanceEhange,tsEhange])
            lastDataTsE = dataTs
            lastPositionValueE = int(positionValue)
            lastBalanceE = int(balance)
        FUNCTION_CLIENT.oss_put_obj(fromLastInvestorArr,"cQuant_change/fromLastInvestorArr.json")
        FUNCTION_CLIENT.oss_put_obj(lastOneDayArr,"cQuant_change/lastOneDayArr.json")
        FUNCTION_CLIENT.oss_put_obj(lastSevenDaysArr,"cQuant_change/lastSevenDaysArr.json")
        FUNCTION_CLIENT.oss_put_obj(lastOneMonthArr,"cQuant_change/lastOneMonthArr.json")
        FUNCTION_CLIENT.oss_put_obj(allArr,"cQuant_change/allArr.json")

UPDATE_DAY_INCOME_TS = 0

def updateDayIncome():
    global UPDATE_DAY_INCOME_TS,TODAY_PROFIT,INIT_DAY_INCOME_RECORD_TIME
    print("update_day_income")
    now = int(time.time())
    if now - UPDATE_DAY_INCOME_TS>60*15:
        UPDATE_DAY_INCOME_TS = now

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT dayBeginTime from income_history_take_day ORDER BY id DESC LIMIT 1
            lastRow = session.exec(
                select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.desc()).limit(1)
            ).first()

        initIncomeDayTs = FUNCTION_CLIENT.turn_ts_to_time(INIT_DAY_INCOME_RECORD_TIME)
        lastIncomeDayTs = 0
        if lastRow is not None:
            lastIncomeDayTs = FUNCTION_CLIENT.turn_ts_to_time(lastRow.day_begin_time)
        if lastIncomeDayTs==0:
            lastIncomeDayTs= initIncomeDayTs
        nowTs = int(time.time())
        todayTs = FUNCTION_CLIENT.turn_ts_to_time(FUNCTION_CLIENT.turn_ts_to_day_time(int(time.time())))

        needInsertDay = int((todayTs - lastIncomeDayTs) /86400)

        for i in range(needInsertDay):
            endDayTs = lastIncomeDayTs+86400*(i+1)
            beginDayTs = lastIncomeDayTs+86400*i

            with FUNCTION_CLIENT.get_session() as session:
                # SELECT incomeType, income, asset, bnbPrice from income_history_take
                # where binance_ts > beginDayTs*1000 AND binance_ts <= endDayTs*1000
                incomeRows = session.exec(
                    select(IncomeHistoryTake)
                    .where(IncomeHistoryTake.binance_ts > beginDayTs * 1000)
                    .where(IncomeHistoryTake.binance_ts <= endDayTs * 1000)
                ).all()

            dayCommission = 0
            dayProfit = 0
            for incomeRow in incomeRows:
                incomeType = incomeRow.income_type
                incomeVal = float(incomeRow.income) if incomeRow.income is not None else 0
                bnbPriceVal = float(incomeRow.bnb_price) if incomeRow.bnb_price is not None else 0
                assetVal = incomeRow.asset
                if incomeType=="COMMISSION":
                    if assetVal=="BNB":
                        dayCommission = dayCommission+incomeVal*bnbPriceVal
                    elif assetVal=="USDT" or assetVal=="BUSD":
                        dayCommission = dayCommission+incomeVal
                if incomeType=="REALIZED_PNL" or incomeType=="FUNDING_FEE":
                    if assetVal=="BNB":
                        dayProfit = dayProfit+incomeVal*bnbPriceVal
                    elif assetVal=="USDT" or assetVal=="BUSD":
                        dayProfit = dayProfit+incomeVal
                if incomeType=="COMMISSION" :
                    if assetVal=="BNB":
                        dayProfit = dayProfit+incomeVal*bnbPriceVal*0.6
                    elif assetVal=="USDT" or assetVal=="BUSD":
                        dayProfit = dayProfit+incomeVal*0.6

            # turn_ts_to_time(int) returns a datetime object; convert to string for the str column
            beginDayDt = FUNCTION_CLIENT.turn_ts_to_time(beginDayTs)
            endDayDt = FUNCTION_CLIENT.turn_ts_to_time(endDayTs)
            beginDayStr = _dt_to_str(beginDayDt)
            endDayStr = _dt_to_str(endDayDt)
            print(beginDayStr)

            with FUNCTION_CLIENT.get_session() as session:
                # SELECT id from income_history_take_day WHERE dayBeginTime = beginDayStr
                existingRow = session.exec(
                    select(IncomeHistoryTakeDay)
                    .where(IncomeHistoryTakeDay.day_begin_time == beginDayStr)
                ).first()

                if existingRow is None:
                    # INSERT new row
                    newRow = IncomeHistoryTakeDay(
                        day_begin_time=beginDayStr,
                        day_end_time=endDayStr,
                        commission=dayCommission,
                        profit=dayProfit,
                    )
                    session.add(newRow)
                    session.commit()
                else:
                    # UPDATE commission, profit WHERE dayEndTime = endDayStr
                    targetRow = session.exec(
                        select(IncomeHistoryTakeDay)
                        .where(IncomeHistoryTakeDay.day_end_time == endDayStr)
                    ).first()
                    if targetRow is not None:
                        targetRow.commission = dayCommission
                        targetRow.profit = dayProfit
                        session.add(targetRow)
                        session.commit()

        with FUNCTION_CLIENT.get_session() as session:
            # SELECT dayBeginTime, profit from income_history_take_day ORDER BY id ASC
            incomeDayRows = session.exec(
                select(IncomeHistoryTakeDay).order_by(IncomeHistoryTakeDay.id.asc())
            ).all()

        dayIncomeArr = []
        for row in incomeDayRows:
            dayIncomeArr.append([row.day_begin_time, float(row.profit) if row.profit is not None else 0])
        todayTs = FUNCTION_CLIENT.turn_ts_to_time(FUNCTION_CLIENT.turn_ts_to_day_time(int(time.time())))
        dayIncomeArr.append([_dt_to_str(FUNCTION_CLIENT.turn_ts_to_time(todayTs)), TODAY_PROFIT])

        ossObj = {
            "ts":int(time.time()),
            "data":dayIncomeArr,
        }
        FUNCTION_CLIENT.oss_put_obj(ossObj,"cQuant_day_income/data.json")


getBinancePositionFromMyServer()
while 1:
    try:
        _thread.start_new_thread(FUNCTION_CLIENT.update_machine_status,())
        getProfit()
        generateObj()
        updateRecord()
        updateDayIncome()
    except Exception as e:
        ex = traceback.format_exc()
        FUNCTION_CLIENT.send_notify_limit_one_min(str(ex))
        time.sleep(1)
