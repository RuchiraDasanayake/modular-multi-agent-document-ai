"""
Database connection pool (PostgreSQL via psycopg3, Redis).
"""

import logging

import redis.asyncio as aioredis
from psycopg_pool import AsyncConnectionPool
from typing import AsyncGenerator
from .config import settings

logger = logging.getLogger(__name__)

# ── Redis ──
redis_client = aioredis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True,
)


def _register_vector(conn):
    """Register pgvector type on each new connection."""
    try:
        from pgvector.psycopg import register_vector
        register_vector(conn)
    except ImportError:
        logger.warning("pgvector Python package not installed — vector ops may fail")
    except Exception as e:
        logger.debug("pgvector registration skipped: %s", e)


# ── PostgreSQL ──
class DatabasePool:
    _pool: AsyncConnectionPool | None = None

    @classmethod
    async def get_pool(cls) -> AsyncConnectionPool:
        if cls._pool is None:
            cls._pool = AsyncConnectionPool(
                conninfo=settings.POSTGRES_URI,
                open=False,
                min_size=2,
                max_size=20,
                configure=_register_vector,
            )
            await cls._pool.open()
        return cls._pool

    @classmethod
    async def close_pool(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None


async def get_db_connection() -> AsyncGenerator:
    pool = await DatabasePool.get_pool()
    async with pool.connection() as conn:
        yield conn


async def get_redis() -> aioredis.Redis:
    return redis_client
