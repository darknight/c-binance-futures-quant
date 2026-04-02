from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Numeric, String


class PositionRecord(SQLModel, table=True):
    __tablename__ = "position_record"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(255), index=True))
    unrealized_profit: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    position_amt: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    time: str | None = Field(default=None, max_length=255)
    position_value: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    update_profit_and_commission: bool | None = Field(default=False)
    profit: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    maker_commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
