from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, Text


class Chat(SQLModel, table=True):
    __tablename__ = "chat"

    id: int | None = Field(default=None, primary_key=True)
    access_token: str | None = Field(default=None, max_length=255, index=True)
    name: str | None = Field(default=None, max_length=255)
    time: str | None = Field(default=None, max_length=255)
    ts: int | None = Field(default=None, sa_column=Column(BigInteger))
    content: str | None = Field(default=None, sa_column=Column(Text))
    chat_type: str | None = Field(default=None, max_length=255)
