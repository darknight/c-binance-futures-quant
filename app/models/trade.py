from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String


class Trade(SQLModel, table=True):
    __tablename__ = "trade"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(50), index=True))
    buyer: bool | None = Field(default=None)
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    binance_id: int | None = Field(default=None, sa_column=Column(BigInteger))
    maker: bool | None = Field(default=None)
    order_id: int | None = Field(default=None, sa_column=Column(BigInteger))
    price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    qty: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    quote_qty: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    realized_pnl: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    side: str | None = Field(default=None, max_length=30)
    position_side: str | None = Field(default=None, max_length=30)
    ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    my_ts: int | None = Field(default=None)
