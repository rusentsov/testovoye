from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "dev-api-key-change-me"
    outbox_poll_interval_sec: float = 1.0
    payments_queue: str = "payments.new"
    payments_dlq: str = "payments.new.dlq"
    max_retries: int = 3


settings = Settings()
