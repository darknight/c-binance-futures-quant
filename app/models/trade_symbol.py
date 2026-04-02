from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, JSON, String


class TradeSymbol(SQLModel, table=True):
    __tablename__ = "trade_symbol"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(255), unique=True, index=True))
    coin: str | None = Field(default=None, max_length=255)
    quote: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=255)
    onboard_date: str | None = Field(default=None, max_length=255)
    index: int | None = Field(default=None)
    default_show: bool | None = Field(default=None)
    onboard_ts: int | None = Field(default=None)
    link_symbol_arr: dict | list | None = Field(default=None, sa_column=Column(JSON))
    quote_volume: Decimal | None = Field(default=Decimal("0"), sa_column=Column(Numeric(30, 10)))
    quote_volume_rank: int | None = Field(default=None)
    link_private_ip: str | None = Field(default="", max_length=255)
    machine_run_ts: int | None = Field(default=0, sa_column=Column(BigInteger))
    machine_run_time: str | None = Field(default=None, max_length=255)
