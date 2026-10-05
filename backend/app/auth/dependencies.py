from datetime import datetime, timezone

from fastapi import Cookie, HTTPException, Request, status
from sqlalchemy import select

from backend.app.auth.security import validate_admin_session
from backend.app.database import AsyncSessionLocal
from backend.app.models.account import BroadcasterAccount, BroadcasterSession


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


async def get_current_broadcaster(request: Request) -> BroadcasterAccount:
    token = request.cookies.get("drone_broadcaster_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broadcaster authentication required.",
        )

    import hashlib

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BroadcasterAccount)
            .join(
                BroadcasterSession,
                BroadcasterSession.account_id == BroadcasterAccount.id,
            )
            .where(
                BroadcasterSession.token_hash == token_hash,
                BroadcasterSession.expires_at > datetime.now(timezone.utc),
                BroadcasterAccount.is_active.is_(True),
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Broadcaster session is invalid or expired.",
            )
        return account