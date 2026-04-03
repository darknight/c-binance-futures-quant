from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Numeric


class IncomeHistoryTakeDay(SQLModel, table=True):
    __tablename__ = "income_history_take_day"

    id: int | None = Field(default=None, primary_key=True)
    day_begin_time: str | None = Field(default=None, max_length=30)
    day_end_time: str | None = Field(default=None, max_length=30)
    commission: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
    profit: Decimal | None = Field(default=None, sa_column=Column(Numeric(30, 10)))
