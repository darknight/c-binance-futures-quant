#!/usr/bin/env python3
"""Seed local demo data for the dashboard frontend.

This script is intentionally small and deterministic. It is for local UI
development only; do not run it against a production database.
"""

import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine.url import make_url
from sqlmodel import Session, delete

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import engine
from app.models.income import Income
from app.models.income_day import IncomeDay
from app.models.income_history_take import IncomeHistoryTake
from app.models.position_record import PositionRecord
from app.models.trade_record import TradeRecord
from settings import settings


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
ALLOWED_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "postgres"}


def dec(value: float | int | str) -> Decimal:
    return Decimal(str(round(float(value), 8)))


def utc_midnight(ts: int) -> datetime:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def assert_safe_database() -> None:
    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite"):
        return
    if url.host in ALLOWED_LOCAL_DB_HOSTS:
        return
    if os.environ.get("FORCE_DEMO_SEED") == "1":
        return
    raise SystemExit(
        "Refusing to seed demo data into a non-local database. "
        "Set FORCE_DEMO_SEED=1 only if you intentionally want to override this guard."
    )


def seed_position_records(session: Session, now: int) -> None:
    start = now - 7 * 86400
    for i in range(7 * 24):
        ts = start + i * 3600
        when = datetime.fromtimestamp(ts, tz=timezone.utc)
        balance_base = 100_000 + i * 55 + math.sin(i / 5) * 900
        for idx, symbol in enumerate(SYMBOLS):
            position_value = 12_000 + idx * 5_500 + math.sin(i / 4 + idx) * 1_800
            session.add(
                PositionRecord(
                    symbol=symbol,
                    unrealized_profit=dec(math.sin(i / 3 + idx) * 180),
                    position_amt=dec((idx + 1) * 0.15),
                    ts=ts,
                    time=when,
                    position_value=dec(position_value),
                    balance=dec(balance_base / len(SYMBOLS)),
                    update_profit_and_commission=True,
                    profit=dec(math.sin(i / 6 + idx) * 75),
                    commission=dec(-2.5 - idx * 0.7),
                    maker_commission=dec(-1.1 - idx * 0.3),
                )
            )


def seed_income(session: Session, now: int) -> None:
    today = utc_midnight(now)

    for day_offset in range(30, 0, -1):
        day_begin = today - timedelta(days=day_offset)
        day_end = day_begin + timedelta(days=1)
        day_index = 30 - day_offset
        pnl = 420 * math.sin(day_index / 3) + day_index * 18 - 130
        commission = -38 - abs(math.sin(day_index)) * 26
        zjy_commission = commission * 0.6
        session.add(
            IncomeDay(
                api_key="demo",
                day_begin_time=day_begin,
                day_end_time=day_end,
                binance_commission=dec(commission),
                zjy_commission=dec(zjy_commission),
                pnl=dec(pnl),
            )
        )

    trade_id = 1
    for day_offset in range(30, -1, -1):
        day_ts_ms = int((today - timedelta(days=day_offset)).timestamp() * 1000)
        for idx, symbol in enumerate(SYMBOLS):
            pnl = 180 * math.sin((30 - day_offset + idx) / 3) + 35 * (idx + 1)
            commission = -4.5 - idx * 1.2
            funding = -2.0 + idx * 1.6
            rows = [
                ("REALIZED_PNL", pnl, "USDT", Decimal("0"), Decimal("0")),
                ("COMMISSION", commission, "USDT", Decimal(str(commission)), Decimal(str(commission))),
                ("FUNDING_FEE", funding, "USDT", Decimal("0"), Decimal("0")),
            ]
            for income_type, income, asset, commission_value, zjy_commission in rows:
                binance_ts = day_ts_ms + (idx + 1) * 60 * 60 * 1000
                kwargs = {
                    "income_type": income_type,
                    "income": dec(income),
                    "bnb_price": dec(600),
                    "asset": asset,
                    "trade_id": f"demo-{trade_id}",
                    "binance_ts": binance_ts,
                    "symbol": symbol,
                    "api_key": "demo",
                    "commission": dec(zjy_commission),
                }
                session.add(Income(**kwargs))
                session.add(IncomeHistoryTake(**kwargs))
                trade_id += 1


def seed_trade_records(session: Session, now: int) -> None:
    losses = [
        ("BTCUSDT", -1850, -0.21, 92_000),
        ("ETHUSDT", -960, -0.18, 88_500),
        ("SOLUSDT", -520, -0.16, 84_200),
    ]
    for idx, (symbol, profit, pct, balance) in enumerate(losses):
        end_ts = (now - (idx + 1) * 7200) * 1000
        session.add(
            TradeRecord(
                symbol=symbol,
                begin_ts=end_ts - 45 * 60 * 1000,
                end_ts=end_ts,
                profit_percent_by_balance=dec(pct),
                profit=dec(profit),
                balance=dec(balance),
                income=dec(profit),
                value=dec(abs(profit) * 8),
                amount=dec(idx + 1),
                cost=dec(abs(profit) * 7),
                commission=dec(-12 - idx * 3),
                status="closed",
                direction="longs" if idx % 2 == 0 else "shorts",
                vol_info={"source": "demo"},
                extra_info={"seed": "dashboard", "priceRate": 1.8 + idx * 0.7},
            )
        )


def main() -> None:
    assert_safe_database()
    now = int(time.time())
    with Session(engine) as session:
        for model in (PositionRecord, Income, IncomeDay, IncomeHistoryTake, TradeRecord):
            session.exec(delete(model))
        session.commit()

        seed_position_records(session, now)
        seed_income(session, now)
        seed_trade_records(session, now)
        session.commit()

    print("Seeded demo dashboard data.")


if __name__ == "__main__":
    main()
