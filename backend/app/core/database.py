from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,       # base pool connections
    max_overflow=30,    # additional burst connections (total max: 50)
    pool_timeout=10,    # fail fast rather than queue indefinitely
    pool_recycle=1800,  # recycle connections every 30 min (avoids stale Supabase pooler conns)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
