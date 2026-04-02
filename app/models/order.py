from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String


class Order(SQLModel, table=True):
    __tablename__ = "order"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(50), index=True))
    avg_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    client_order_id: str | None = Field(default=None, max_length=255)
    cum_quote: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    executed_qty: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    order_id: int | None = Field(default=None, sa_column=Column(BigInteger))
    orig_qty: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    orig_type: str | None = Field(default=None, max_length=255)
    price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    reduce_only: str | None = Field(default=None, max_length=255)
    side: str | None = Field(default=None, max_length=255)
    position_side: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=255)
    stop_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    close_position: str | None = Field(default=None, max_length=30)
    time_in_force: str | None = Field(default=None, max_length=30)
    order_type: str | None = Field(default=None, max_length=30)
    update_time: int | None = Field(default=None, sa_column=Column(BigInteger))
    working_type: str | None = Field(default=None, max_length=30)
    price_protect: str | None = Field(default=None, max_length=30)
    binance_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    my_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
