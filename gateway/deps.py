"""
FastAPI dependencies — current user extraction, admin guard.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from psycopg import AsyncConnection

from .database import get_db_connection
from .auth_service import verify_token

security = HTTPBearer()

async def get_db(conn=Depends(get_db_connection)) -> AsyncConnection:
    return conn

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncConnection = Depends(get_db),
) -> dict:
    """Decode JWT, look up user in Postgres, return user dict."""
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, email, username, role, is_active FROM users WHERE id = %s",
            (user_id,),
        )
        row = await cur.fetchone()

    if row is None or not row[4]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return {"id": str(row[0]), "email": row[1], "username": row[2], "role": row[3], "is_active": row[4]}

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin required"
        )
    return user
