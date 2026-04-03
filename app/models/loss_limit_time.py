from sqlmodel import SQLModel, Field, Column
from sqlalchemy import String


class LossLimitTime(SQLModel, table=True):
    __tablename__ = "loss_limit_time"

    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(sa_column=Column(String(255), unique=True, index=True))
    limit_time: str | None = Field(default=None, max_length=255)
