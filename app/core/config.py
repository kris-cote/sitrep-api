from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # optional
    env: str = "local"
    hub_jwt_algo: str = "HS256"
    # MUST match code references like settings.hub_db_url
    hub_db_url: str
    hub_jwt_secret: str
    hub_api_key_master: str


settings = Settings()
