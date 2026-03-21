from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Database Configuration
    POSTGRES_USER: str = "fin_user"
    POSTGRES_PASSWORD: str = "fin_password"
    POSTGRES_DB: str = "fin_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Qdrant Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "financial_context"

    # Data Pipeline Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    BATCH_SIZE_YEARS: int = 5

    # Provider API Keys
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Langfuse Configuration (Legacy)
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Phoenix Configuration
    PHOENIX_HOST: str = "http://localhost:6006"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )


settings = Settings()
