from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String, JSON, Text


class Trades(SQLModel, table=True):
    __tablename__ = "trades"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str | None = Field(default=None, sa_column=Column(String(255), index=True))
    status: str | None = Field(default=None, max_length=255)
    version: int | None = Field(default=None)
    vol_multiple: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    standard_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    kline_arr: str | None = Field(default=None, sa_column=Column(Text))
    now_open_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    begin_machine_number: str | None = Field(default=None, max_length=255)
    direction: str | None = Field(default=None, max_length=255)
    longs_condition_a: int | None = Field(default=None)
    shorts_condition_a: int | None = Field(default=None)
    shorts_condition_b: int | None = Field(default=None)
    btc_now_open_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    eth_now_open_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    begin_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    end_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    trade_type: str | None = Field(default=None, max_length=255)
    update_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    client_begin_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    client_end_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    profit: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    value: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    cost: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    vol_info: str | None = Field(default=None, sa_column=Column(Text))
    open_type: str | None = Field(default=None, max_length=255)
    open_time: int | None = Field(default=None)
    add_time: int | None = Field(default=None)
    close_time: int | None = Field(default=None)
    open_gtx_time: int | None = Field(default=None)
    add_gtx_time: int | None = Field(default=None)
    close_gtx_time: int | None = Field(default=None)
    take_time: int | None = Field(default=None)
    begin_boll_up: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    begin_boll_down: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    take_value: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
