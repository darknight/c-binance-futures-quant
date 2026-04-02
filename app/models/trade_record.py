from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String, JSON


class TradeRecord(SQLModel, table=True):
    __tablename__ = "trade_record"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(255), index=True))
    begin_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    end_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    profit_percent_by_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    profit: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    income: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    value: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    amount: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    cost: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    status: str | None = Field(default=None, max_length=255)
    direction: str | None = Field(default=None, max_length=255)
    vol_info: dict | list | None = Field(default=None, sa_column=Column(JSON))
    extra_info: dict | list | None = Field(default=None, sa_column=Column(JSON))
