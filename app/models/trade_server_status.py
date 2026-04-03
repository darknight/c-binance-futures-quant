from datetime import datetime
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, DateTime, String, Text


class TradeServerStatus(SQLModel, table=True):
    __tablename__ = "trade_server_status"

    id: int | None = Field(default=None, primary_key=True)
    private_ip: str | None = Field(default=None, max_length=255, index=True)
    name: str | None = Field(default=None, max_length=255)
    extra_para: str | None = Field(default=None, sa_column=Column(Text))
    symbol: str | None = Field(default=None, max_length=255)
    my_symbol: str | None = Field(default=None, max_length=255)
    run_info: str | None = Field(default=None, sa_column=Column(Text))
    update_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    update_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
