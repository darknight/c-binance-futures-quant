from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Numeric, String


class IncomeDay(SQLModel, table=True):
    __tablename__ = "income_day"

    id: int | None = Field(default=None, primary_key=True)
    api_key: str = Field(sa_column=Column(String(255), index=True))
    day_begin_time: str | None = Field(default=None, max_length=255)
    day_end_time: str | None = Field(default=None, max_length=255)
    binance_commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    zjy_commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    pnl: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
