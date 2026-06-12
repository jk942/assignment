import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Transaction Processing Pipeline"
    
    # Database Configuration
    # Fallback to sqlite for testing or local run if database URL is not set
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/transactions"
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Uploads Configuration
    UPLOAD_DIR: str = "./uploads"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
