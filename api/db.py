"""Database engine. Built lazily so the API (and its tests) import without a database."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


@lru_cache
def get_engine():
    # Scheme must be postgresql+psycopg:// (SQLAlchemy 2 rejects postgres://).
    return create_engine(os.environ["DATABASE_URL"], pool_size=5, max_overflow=2, pool_pre_ping=True)
