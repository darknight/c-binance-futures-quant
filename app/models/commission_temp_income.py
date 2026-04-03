from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String


class CommissionTempIncome(SQLModel, table=True):
    __tablename__ = "commission_temp_income"

    id: int | None = Field(default=None, primary_key=True)
    income_type: str | None = Field(default=None, max_length=255)
    income: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    bnb_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    asset: str | None = Field(default=None, max_length=255)
    trade_id: str | None = Field(default=None, max_length=255)
    binance_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    symbol: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=255)
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    info: str | None = Field(default=None, max_length=255)
    my_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    instrument_id: str | None = Field(default=None, max_length=255)
    coin: str | None = Field(default=None, max_length=255)
