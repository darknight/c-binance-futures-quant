from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String


class Income(SQLModel, table=True):
    __tablename__ = "income"

    id: int | None = Field(default=None, primary_key=True)
    access_token: str = Field(default="", sa_column=Column(String(255), index=True))
    income_type: str | None = Field(default=None, max_length=255)
    income: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    bnb_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    asset: str | None = Field(default=None, max_length=255)
    trade_id: str | None = Field(default=None, max_length=255)
    binance_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    symbol: str | None = Field(default=None, max_length=255, index=True)
    api_key: str | None = Field(default=None, max_length=255)
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
