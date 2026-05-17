import json
import time
import traceback
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from app.models.position_record import PositionRecord
from app.models.trade_record import TradeRecord
from app.models.trades import Trades
from app.models.trades_take import TradesTake
from app.models.begin_trade_record import BeginTradeRecord
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_position_record")
def get_position_record(
    request: Request,
    symbol: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol != "ALL":
            stmt = stmt.where(PositionRecord.symbol == symbol)
        position_record_data = session.exec(stmt).all()

    result = []
    for row in position_record_data:
        result.append({
            "positionAmt": row.position_amt,
            "price": None,
            "positionValue": row.position_value,
            "balance": row.balance,
            "time": row.time,
            "profit": row.profit,
            "commission": row.commission,
            "makerCommission": row.maker_commission,
            "entryPrice": None,
            "unrealizedProfit": row.unrealized_profit,
            "maintMargin": None,
        })
    return {"s": "ok", "d": result, "symbol": symbol}


@router.post("/get_history_position_record")
def get_history_position_record(
    request: Request,
    tableName: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    symbol = tableName
    with state.infra_client.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol not in ("ALL", ""):
            stmt = stmt.where(PositionRecord.symbol == symbol)
        position_record_data = session.exec(stmt).all()

    result = []
    for row in position_record_data:
        result.append({
            "positionAmt": row.position_amt,
            "price": None,
            "positionValue": row.position_value,
            "balance": row.balance,
            "time": row.time,
            "profit": row.profit,
            "commission": row.commission,
            "makerCommission": row.maker_commission,
        })
    return {"s": "ok", "d": result}


@router.post("/get_big_loss_trades")
def get_big_loss_trades(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.update_big_loss_trades_data_ts > 60:
        state.update_big_loss_trades_data_ts = now
        with state.infra_client.get_session() as session:
            big_loss_data = session.exec(
                select(TradeRecord).where(TradeRecord.profit_percent_by_balance <= -0.15).order_by(TradeRecord.id.desc())
            ).all()
        state.big_loss_trades_arr = []
        for row in big_loss_data:
            state.big_loss_trades_arr.append({
                "symbol": row.symbol,
                "time": state.infra_client.turn_ts_to_time(row.end_ts),
                "profit": row.profit,
                "profitPercentByBalance": str(abs(int(row.profit_percent_by_balance * 100) / 100)) + "%",
                "priceRate": str(abs(int(float((row.extra_info or {}).get("priceRate", 0)) * 100) / 100)) + "%",
                "direction": "做空" if row.direction == "shorts" else "做多",
            })
    return json.loads(json_dumps({"s": "ok", "d": state.big_loss_trades_arr}))


@router.post("/begin_trade_record")
def begin_trade_record(
    request: Request,
    volMultiple: float = Form(),
    standardRate: float = Form(),
    symbol: str = Form(),
    klineArr: str = Form(),
    nowOpenRate: float = Form(),
    machineNumber: str = Form(),
    direction: str = Form(),
    myTradeType: str = Form(),
    longsConditionA: int = Form(),
    shortsConditionA: int = Form(),
    shortsConditionB: int = Form(),
    btcNowOpenRate: float = Form(),
    ethNowOpenRate: float = Form(),
    clientBeginPrice: float = Form(),
    clientEndPrice: float = Form(),
    privateIP: str = Form(),
):
    state = request.app.state.app_state
    try:
        ts = int(time.time() * 1000)
        kline_arr_str = json.dumps(json.loads(klineArr))

        with state.infra_client.get_session() as session:
            trades_data = session.exec(
                select(TradesTake).where(TradesTake.symbol == symbol, TradesTake.status == "tradeBegin")
            ).all()

        if myTradeType.find("open") >= 0 and len(trades_data) == 0:
            if symbol not in state.symbol_last_insert_ts_obj or ts - state.symbol_last_insert_ts_obj[symbol] > 30000:
                state.symbol_last_insert_ts_obj[symbol] = ts
                with state.infra_client.get_session() as session:
                    new_row = TradesTake(
                        status="tradeBegin", version=3,
                        vol_multiple=Decimal(str(volMultiple)), standard_rate=Decimal(str(standardRate)),
                        symbol=symbol, kline_arr=kline_arr_str,
                        now_open_rate=Decimal(str(nowOpenRate)), begin_machine_number=machineNumber,
                        direction=direction, longs_condition_a=longsConditionA,
                        shorts_condition_a=shortsConditionA, shorts_condition_b=shortsConditionB,
                        btc_now_open_rate=Decimal(str(btcNowOpenRate)), eth_now_open_rate=Decimal(str(ethNowOpenRate)),
                        begin_ts=ts, end_ts=ts, trade_type=myTradeType, update_ts=ts,
                        client_begin_price=Decimal(str(clientBeginPrice)), client_end_price=Decimal(str(clientEndPrice)),
                    )
                    session.add(new_row)
                    session.commit()
        else:
            state.infra_client.send_notify_limit_one_min(myTradeType)

        return {"s": "ok"}
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
        return {"s": "error"}


@router.post("/get_order_result_arr")
def get_order_result_arr(
    request: Request,
    symbol: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        begin_trade_record_data = session.exec(
            select(BeginTradeRecord)
            .where(BeginTradeRecord.symbol == symbol, BeginTradeRecord.ts > beginTs - 60000, BeginTradeRecord.ts < endTs + 60000)
            .order_by(BeginTradeRecord.id.desc())
            .limit(5000)
        ).all()

    result = []
    for row in begin_trade_record_data:
        result.append({
            "symbol": row.symbol,
            "time": row.time,
            "asksDepthArr": json.loads(row.asks_depth_arr or "[]"),
            "bidsDepthArr": json.loads(row.bids_depth_arr or "[]"),
            "ordersResult": json.loads(row.orders_result or "{}"),
            "direction": row.direction,
            "nowOpenRate": row.now_open_rate,
            "machineNumber": row.machine_number,
            "ts": row.ts,
            "myTradeType": row.my_trade_type,
            "nowPrice": row.now_price,
        })
    return {"s": "ok", "d": result}


@router.post("/get_trades_result_arr")
def get_trades_result_arr(request: Request, tradeTimeIntervalIndex: int = Form()):
    state = request.app.state.app_state
    try:
        now_ts = int(time.time() * 1000)
        interval_map = {0: 4, 1: 8, 2: 12, 3: 24, 4: 72}
        hours = interval_map.get(tradeTimeIntervalIndex, 4)
        limit_ts = now_ts - hours * 60 * 60 * 1000
        if limit_ts < 1686960000000:
            limit_ts = 1686960000000

        with state.infra_client.get_session() as session:
            trades_record_data = session.exec(
                select(Trades)
                .where(Trades.status == "updateProfit", Trades.begin_ts > limit_ts, Trades.version == 2)
                .order_by(Trades.id.desc())
            ).all()

        trades_record_arr = []
        for row in trades_record_data:
            vol_info_parsed = json.loads(row.vol_info) if isinstance(row.vol_info, str) else (row.vol_info or {})
            boll_up = row.begin_boll_up or 0
            boll_down = row.begin_boll_down or 0
            trades_record_arr.append([
                row.symbol, row.begin_ts, row.end_ts, row.direction,
                row.profit, row.value, row.cost, vol_info_parsed,
                row.open_type, row.open_time, row.add_time, row.close_time,
                row.open_gtx_time, row.add_gtx_time, row.close_gtx_time,
                row.now_open_rate, row.standard_rate, row.take_time,
                state.infra_client.get_percent_num(boll_up - boll_down, boll_down),
                row.take_value,
            ])

        with state.infra_client.get_session() as session:
            fail_data = session.exec(
                select(Trades).where(Trades.status == "updateProfitFail", Trades.begin_ts > limit_ts, Trades.version == 2)
            ).all()

        return {"s": "ok", "d": trades_record_arr, "fT": len(fail_data), "fV": 0}
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
        return {"s": "error"}
