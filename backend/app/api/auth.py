from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from backend.app.auth.security import (
    verify_admin_credentials,
    create_admin_session,
    validate_admin_session,
    delete_admin_session,
)
from backend.app.config import settings


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(credentials: LoginRequest, response: Response):
    """Authenticate an administrator and create a login session."""

    if not verify_admin_credentials(
        credentials.username,
        credentials.password,
    ):
        return {
            "success": False,
            "message": "Invalid username or password.",
        }

    session_token = create_admin_session()

    response.set_cookie(
        key="drone_admin_session",
        value=session_token,
        httponly=True,
        secure=str(settings.environment).lower() not in {"development", "dev"},
        samesite="lax",
        max_age=8 * 60 * 60,
    )

    try:
        from datetime import datetime, timezone
        from backend.app.database import AsyncSessionLocal
        from backend.app.models.security_log import SecurityLog

        async with AsyncSessionLocal() as session:
            session.add(
                SecurityLog(
                    event="login",
                    actor=credentials.username,
                    detail="Admin signed in",
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception:
        pass

    return {
        "success": True,
        "message": "Login successful.",
    }


@router.post("/logout")
async def admin_logout(request: Request, response: Response):
    """Log out the current administrator."""

    session_token = request.cookies.get("drone_admin_session")

    if session_token:
        delete_admin_session(session_token)

    response.delete_cookie(
        key="drone_admin_session",
        httponly=True,
        samesite="lax",
    )

    try:
        from backend.app.database import AsyncSessionLocal
        from backend.app.models.security_log import SecurityLog

        async with AsyncSessionLocal() as session:
            session.add(
                SecurityLog(
                    event="logout",
                    actor="admin",
                    detail="Admin signed out",
                )
            )
            await session.commit()
    except Exception:
        pass

    return {
        "success": True,
        "message": "Logout successful.",
    }


@router.get("/me")
async def current_admin(request: Request):
    """Check whether the current browser has a valid admin session."""

    session_token = request.cookies.get("drone_admin_session")

    if not session_token or not validate_admin_session(session_token):
        return {
            "authenticated": False,
        }

    return {
        "authenticated": True,
        "username": "admin",
    }