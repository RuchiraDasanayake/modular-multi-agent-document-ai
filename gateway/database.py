"""
Database pool for the gateway (auth tables only).
"""

import logging
from typing import AsyncGenerator

from fastapi import HTTPException, status
from psycopg_pool import AsyncConnectionPool, PoolTimeout

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
                timeout=30.0,         # max wait for a connection from pool
                max_idle=300.0,       # close idle connections after 5 min
                max_lifetime=3600.0,  # recycle connections after 1 hour
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

    @classmethod
    async def reset_pool(cls) -> AsyncConnectionPool:
        await cls.close_pool()
        return await cls.get_pool()

async def get_db_connection() -> AsyncGenerator:
    attempts = (
        ("existing", DatabasePool.get_pool),
        ("reset", DatabasePool.reset_pool),
    )

    for label, pool_factory in attempts:
        try:
            pool = await pool_factory()
            async with pool.connection() as conn:
                yield conn
                return
        except PoolTimeout:
            logger.warning(
                "Gateway database pool timed out while acquiring a connection (%s pool).",
                label,
            )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Gateway database temporarily unavailable",
    )
