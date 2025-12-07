import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:////data/app.db"
    log_level: str = "INFO"
    webhook_secret: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()

def validate_settings():
    """Validate that required settings are present"""
    if not settings.webhook_secret:
        raise ValueError("WEBHOOK_SECRET environment variable must be set")
    return True
