"""
Database engine/session setup using SQLAlchemy against PostgreSQL.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

# PostgreSQL-specific engine configuration
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verifies connection health before executing queries
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()