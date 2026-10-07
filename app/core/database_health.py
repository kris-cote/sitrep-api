"""A bounded, read-only database probe with no credential-bearing diagnostics."""
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.database_url import sync_database_url


def database_ready() -> bool:
    probe = None
    try:
        url = sync_database_url()
        options = {"poolclass": NullPool}
        if url.startswith(("postgresql", "postgres:")):
            options["connect_args"] = {"connect_timeout": 2}
        probe = create_engine(url, **options)
        with probe.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = 2000"))
            return connection.execute(text("SELECT 1")).scalar_one() == 1
    except Exception:
        # Provider exceptions can contain credentials and connection strings.
        return False
    finally:
        if probe is not None:
            probe.dispose()
