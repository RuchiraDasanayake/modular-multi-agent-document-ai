"""
Database connection pool (PostgreSQL via psycopg3, Redis).
"""

import redis.asyncio as aioredis
from psycopg_pool import AsyncConnectionPool
from typing import AsyncGenerator
from .config import settings


# ── Redis ──
redis_client = aioredis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True,
)


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
