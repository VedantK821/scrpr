from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://scrpr:scrpr@localhost:5432/scrpr"
    redis_url: str = "redis://localhost:6379/0"

    ollama_base_url: str = "http://localhost:11434"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    scraper_api_key: str = ""
    browserless_api_key: str = ""

    hunter_api_key: str = ""
    apollo_api_key: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
