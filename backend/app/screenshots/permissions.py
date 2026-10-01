from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.screenshot_permission import (
    ScreenshotPermission,
)


async def grant_screenshot_permission(
    db: AsyncSession,
    viewer_session_id: int,
    admin_id: int,
) -> ScreenshotPermission:
    """
    Grant screenshot permission to a specific viewer session.
    """

    result = await db.execute(
        select(ScreenshotPermission).where(
            ScreenshotPermission.viewer_session_id
            == viewer_session_id
        )
    )

    permission = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if permission is None:

        permission = ScreenshotPermission(
            viewer_session_id=viewer_session_id,
            allowed=True,
            granted_at=now,
            revoked_at=None,
            granted_by_admin_id=admin_id,
        )

        db.add(permission)

    else:

        permission.allowed = True
        permission.granted_at = now
        permission.revoked_at = None
        permission.granted_by_admin_id = admin_id

    await db.commit()
    await db.refresh(permission)

    return permission


async def revoke_screenshot_permission(
    db: AsyncSession,
    viewer_session_id: int,
) -> ScreenshotPermission | None:
    """
    Revoke screenshot permission from a specific viewer session.
    """

    result = await db.execute(
        select(ScreenshotPermission).where(
            ScreenshotPermission.viewer_session_id
            == viewer_session_id
        )
    )

    permission = result.scalar_one_or_none()

    if permission is None:
        return None

    permission.allowed = False
    permission.revoked_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(permission)

    return permission


async def check_screenshot_permission(
    db: AsyncSession,
    viewer_session_id: int,
) -> bool:
    """
    Check whether a viewer session currently has
    screenshot permission.
    """

    result = await db.execute(
        select(ScreenshotPermission.allowed).where(
            ScreenshotPermission.viewer_session_id
            == viewer_session_id
        )
    )

    allowed = result.scalar_one_or_none()

    return bool(allowed)