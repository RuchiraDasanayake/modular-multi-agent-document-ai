"""
Auth router — login, register, user management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection

from ..deps import get_db, get_current_user, require_admin
from ..schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from ..services.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncConnection = Depends(get_db)):
    async with db.cursor() as cur:
        await cur.execute(
            "SELECT id, hashed_password, is_active FROM users WHERE username = %s",
            (body.username,),
        )
        row = await cur.fetchone()

    if row is None or not verify_password(body.password, row[1]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not row[2]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token({"sub": str(row[0])})
    return TokenResponse(access_token=token)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Create a new user (admin only)."""
    hashed = hash_password(body.password)
    try:
        async with db.cursor() as cur:
            await cur.execute(
                """INSERT INTO users (email, username, hashed_password, role)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, email, username, role, is_active""",
                (body.email, body.username, hashed, body.role),
            )
            row = await cur.fetchone()
            await db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="Username or email already taken")

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")
    return UserResponse(id=str(row[0]), email=row[1], username=row[2], role=row[3], is_active=row[4])


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(**user, is_active=True)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    async with db.cursor() as cur:
        await cur.execute("SELECT id, email, username, role, is_active FROM users ORDER BY created_at")
        rows = await cur.fetchall()
    return [
        UserResponse(id=str(r[0]), email=r[1], username=r[2], role=r[3], is_active=r[4])
        for r in rows
    ]


@router.patch("/users/{user_id}/toggle")
async def toggle_user(
    user_id: str,
    db: AsyncConnection = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE users SET is_active = NOT is_active, updated_at = NOW() WHERE id = %s RETURNING is_active",
            (user_id,),
        )
        row = await cur.fetchone()
        await db.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"is_active": row[0]}
