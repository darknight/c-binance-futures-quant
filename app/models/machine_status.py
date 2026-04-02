from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, String


class MachineStatus(SQLModel, table=True):
    __tablename__ = "machine_status"

    id: int | None = Field(default=None, primary_key=True)
    private_ip: str | None = Field(default=None, max_length=255, index=True)
    insert_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    update_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    status: str | None = Field(default=None, max_length=255)
    symbol: str | None = Field(default=None, max_length=255)
    run_time: int | None = Field(default=None, sa_column=Column(BigInteger))


class TradeMachineStatus(SQLModel, table=True):
    __tablename__ = "trade_machine_status"

    id: int | None = Field(default=None, primary_key=True)
    private_ip: str | None = Field(default=None, max_length=255, index=True)
    insert_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    update_ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    status: str | None = Field(default=None, max_length=255)
    run_time: int | None = Field(default=None, sa_column=Column(BigInteger))
