import redis.asyncio as redis
from psycopg_pool import AsyncConnectionPool
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from .config import settings

# Redis Client
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True
)

# Postgres Connection Pool
class DatabasePool:
    _pool: AsyncConnectionPool = None # type: ignore

    @classmethod
    async def get_pool(cls) -> AsyncConnectionPool:
        if cls._pool is None:
            cls._pool = AsyncConnectionPool(
                conninfo=settings.POSTGRES_URI,
                open=False,
                min_size=1,
                max_size=10
            )
            await cls._pool.open()
        return cls._pool

    @classmethod
    async def close_pool(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None # type: ignore

async def get_db_connection() -> AsyncGenerator:
    pool = await DatabasePool.get_pool()
    async with pool.connection() as conn:
        yield conn

async def get_redis_client() -> redis.Redis:
    return redis_client
