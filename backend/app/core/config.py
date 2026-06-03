# File: backend/app/core/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AI IT Support Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str

    REDIS_URL: str = "redis://localhost:6379"

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""

    ANTHROPIC_API_KEY: str = ""

    FRONTEND_URL: str = "http://localhost:3000"
    AI_SERVICES_URL: str = "http://localhost:8001"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()