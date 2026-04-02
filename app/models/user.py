from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON, Text


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    account: str = Field(max_length=255, index=True)
    password: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=255)
    register_ip: str | None = Field(default=None, max_length=255)
    register_time: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, max_length=255, index=True)
    usdt_assets: str | None = Field(default=None, max_length=255)
    binance_api_arr: str | None = Field(default=None, sa_column=Column(Text))
    hot_key_config_obj: str | None = Field(default=None, sa_column=Column(Text))
    state_config_obj: str | None = Field(default=None, sa_column=Column(Text))
    server_info_obj: str | None = Field(default=None, sa_column=Column(Text))
    show_symbol_obj: str | None = Field(default=None, sa_column=Column(Text))
