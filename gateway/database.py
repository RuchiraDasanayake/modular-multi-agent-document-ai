"""
Database pool for the gateway (auth tables only).
"""

import logging
from typing import AsyncGenerator

from psycopg_pool import AsyncConnectionPool

from .config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    _pool: AsyncConnectionPool | None = None

    @classmethod
    async def get_pool(cls) -> AsyncConnectionPool:
        if cls._pool is None:
            cls._pool = AsyncConnectionPool(
                conninfo=settings.POSTGRES_URI,
                open=False,
                min_size=2,
                max_size=10,
            )
            await cls._pool.open()
            logger.info("Gateway database pool opened")
        return cls._pool

    @classmethod
    async def close_pool(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("Gateway database pool closed")

async def get_db_connection() -> AsyncGenerator:
    pool = await DatabasePool.get_pool()
    async with pool.connection() as conn:
        yield conn
