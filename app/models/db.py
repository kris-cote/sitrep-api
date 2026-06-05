# app/models/db.py
from typing import Generator

from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

engine = create_engine(str(settings.hub_db_url), echo=False)


def init_db() -> None:
    """Create tables if they don't exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
