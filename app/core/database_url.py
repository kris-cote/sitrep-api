import os

from app.core.config import settings


def raw_database_url() -> str:
    """Return the canonical database URL for all SitRep persistence layers.

    Railway normally exposes DATABASE_URL. HUB_DB_URL remains supported for
    backwards compatibility with the original Hub API configuration.
    """
    url = os.getenv("DATABASE_URL") or settings.hub_db_url
    if not url:
        raise RuntimeError(
            "No database URL configured. Set DATABASE_URL (preferred) or legacy HUB_DB_URL."
        )
    return str(url)


def async_database_url() -> str:
    url = raw_database_url()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def sync_database_url() -> str:
    url = raw_database_url()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url
