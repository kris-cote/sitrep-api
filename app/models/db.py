from typing import Generator

from sqlmodel import SQLModel, Session, create_engine

from app.core.database_url import sync_database_url


engine = create_engine(sync_database_url(), echo=False)


def init_db() -> None:
    """Create SQLModel-managed tables if they do not already exist."""
    # Import models before create_all so their metadata is registered.
    from app.models import decision, dependency, exposure, infrastructure, resource_capability, situation  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
