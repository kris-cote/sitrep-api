from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    The original SixthSense Hub required HUB_* variables at import time. SitRep now
    uses Railway's DATABASE_URL as the canonical database configuration, so the
    legacy Hub values must not prevent the API from starting when they are absent.
    Authentication code can still require/validate these values at the point where
    a legacy Hub feature is actually used.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    hub_jwt_algo: str = "HS256"

    # Legacy Hub compatibility. Optional at process startup so Railway deployments
    # configured with DATABASE_URL do not crash during module import.
    hub_db_url: str | None = None
    hub_jwt_secret: str | None = None
    hub_api_key_master: str | None = None


settings = Settings()
