from sqlmodel import SQLModel, Session, create_engine, select


def test_engine_creates_session():
    """Verify we can create an in-memory SQLite engine and session."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        assert session is not None
