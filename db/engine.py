"""
Async SQLAlchemy engine and session factory.

Reads DATABASE_URL from the environment (set via .env).
Uses asyncpg as the async Postgres driver.
"""

import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# asyncpg requires the postgresql+asyncpg:// scheme
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True for SQL debug logging
    pool_pre_ping=True,  # drop stale connections automatically
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
