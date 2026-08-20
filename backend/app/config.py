import os
from dotenv import load_dotenv

load_dotenv()

def _require(name: str, default: str) -> str:
    value = os.getenv(name, default)
    if not value or value.startswith("REPLACE"):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

class Settings:
    OPENROUTER_API_KEY: str = _require(
        "OPENROUTER_API_KEY", 
        "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"
    )
    JWT_SECRET: str = _require(
        "JWT_SECRET", 
        "c23f7902d184eb43b3512a84b2e88a0b06db2328114ef97ad76e82a392815f9d"
    )
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/xyz_ai"
    )
    OPENROUTER_MODEL: str = os.getenv(
        "OPENROUTER_MODEL", 
        "openai/gpt-4o-mini"
    )
    OPENROUTER_BASE_URL: str = os.getenv(
        "OPENROUTER_BASE_URL", 
        "https://openrouter.ai/api/v1"
    )
    OPENROUTER_SITE_URL: str = os.getenv(
        "OPENROUTER_SITE_URL", 
        "http://localhost:8000"
    )
    OPENROUTER_APP_NAME: str = os.getenv(
        "OPENROUTER_APP_NAME", 
        "XYZ AI"
    )

settings = Settings()