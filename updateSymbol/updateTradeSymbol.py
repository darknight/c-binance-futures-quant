#!/usr/bin/env python3
# coding=utf-8

import sys
import json
import random
import time
import requests
import socket
import decimal
import datetime
import string
from settings import settings
from infra_client import InfraClient
from sqlmodel import select
from sqlalchemy import delete
from app.models.trade_symbol import TradeSymbol

FUNCTION_CLIENT = InfraClient(larkMsgSymbol="updateTradeSymbol",connectMysql =True)

# Truncate trade_symbol
with FUNCTION_CLIENT.get_session() as session:
    session.exec(delete(TradeSymbol))
    session.commit()

url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
response = requests.request("GET", url,timeout=(3,7)).json()
symbolsArr = response["symbols"]

#update symbol
new_symbols = []
for a in range(len(symbolsArr)):
    if  symbolsArr[a]["status"]=="TRADING" and symbolsArr[a]["deliveryDate"]==4133404800000 and symbolsArr[a]["underlyingType"]!="INDEX"  and symbolsArr[a]["quoteAsset"]=="USDT":
        thisSymbol = symbolsArr[a]["symbol"]
        thisBaseAsset = symbolsArr[a]["baseAsset"]
        thisQuote = thisSymbol.replace(thisBaseAsset,"")
        new_symbols.append(TradeSymbol(
            symbol=thisSymbol,
            coin=thisBaseAsset,
            quote=thisQuote,
            status="yes",
            onboard_date=str(FUNCTION_CLIENT.turn_ts_to_time(int(symbolsArr[a]["onboardDate"]/1000))),
            index=0,
            default_show=False,
            onboard_ts=int(symbolsArr[a]["onboardDate"]/1000),
            link_symbol_arr=[],
        ))
with FUNCTION_CLIENT.get_session() as session:
    session.add_all(new_symbols)
    session.commit()


url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
response = requests.request("GET", url,timeout=(3,7)).json()
oneDayVolArr = response
with FUNCTION_CLIENT.get_session() as session:
    for i in range(len(oneDayVolArr)):
        symbol = oneDayVolArr[i]["symbol"]
        db_row = session.exec(select(TradeSymbol).where(TradeSymbol.symbol == symbol)).first()
        if db_row:
            db_row.quote_volume = oneDayVolArr[i]["quoteVolume"]
            session.add(db_row)
    session.commit()

print("update index")
#update index
with FUNCTION_CLIENT.get_session() as session:
    tradeSymbolData = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    for i, row in enumerate(tradeSymbolData):
        row.index = i
        session.add(row)
    session.commit()


#update default show
with FUNCTION_CLIENT.get_session() as session:
    active_rows = session.exec(
        select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
    ).all()
    coinArr = []
    for row in active_rows:
        if row.coin not in coinArr:
            coinArr.append(row.coin)

    for thisCoin in coinArr:
        coin_rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.coin == thisCoin).order_by(TradeSymbol.quote_volume.desc())
        ).all()
        for b, row in enumerate(coin_rows):
            row.default_show = (b == 0)
            session.add(row)
    session.commit()


#update link symbol arr
with FUNCTION_CLIENT.get_session() as session:
    all_rows = session.exec(
        select(TradeSymbol).order_by(TradeSymbol.id.asc())
    ).all()
    for row in all_rows:
        thisCoin = row.coin
        link_rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.coin == thisCoin)
        ).all()
        linkSymbolArr = [r.symbol for r in link_rows]
        row.link_symbol_arr = linkSymbolArr
        session.add(row)
    session.commit()
