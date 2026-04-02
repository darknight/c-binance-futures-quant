from sqlmodel import SQLModel, Field


class Visitor(SQLModel, table=True):
    __tablename__ = "visitor"

    id: int | None = Field(default=None, primary_key=True)
    ip: str | None = Field(default=None, max_length=255)
    time: str | None = Field(default=None, max_length=255)
    page: str | None = Field(default=None, max_length=255)
