from fastapi import Cookie, HTTPException, status

from backend.app.auth.security import validate_admin_session


SESSION_COOKIE_NAME = "drone_admin_session"


async def get_current_admin(
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
) -> str:
    """
    FastAPI dependency.

    Reads the drone_admin_session cookie. If it is missing or invalid,
    raises 401. Otherwise returns the authenticated admin's username.
    """

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    if not validate_admin_session(session_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    return "admin"