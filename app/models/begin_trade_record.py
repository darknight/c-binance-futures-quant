from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String, Text


class BeginTradeRecord(SQLModel, table=True):
    __tablename__ = "begin_trade_record"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str | None = Field(default=None, sa_column=Column(String(255), index=True))
    time: str | None = Field(default=None, max_length=255)
    asks_depth_arr: str | None = Field(default=None, sa_column=Column(Text))
    bids_depth_arr: str | None = Field(default=None, sa_column=Column(Text))
    orders_result: str | None = Field(default=None, sa_column=Column(Text))
    direction: str | None = Field(default=None, max_length=255)
    now_open_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    machine_number: str | None = Field(default=None, max_length=255)
    ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    my_trade_type: str | None = Field(default=None, max_length=255)
    now_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
