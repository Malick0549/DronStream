from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.app.auth.dependencies import (
    get_current_admin,
    get_current_broadcaster,
)
from backend.app.database import AsyncSessionLocal
from backend.app.models.account import (
    BroadcasterAccount,
    BroadcasterInvite,
    BroadcasterSession,
)
from backend.app.models.stream import Stream
from backend.app.models.viewer import StreamLink, ViewerEvent, ViewerSession
from backend.app.models.account import StreamOwnership
from backend.app.models.recording import RecordingPermission
from backend.app.models.screenshot_permission import ScreenshotPermission
from backend.app.models.recording import Recording
from backend.app.models.screenshot import Screenshot
from backend.app.models.security_log import SecurityLog
from backend.app.streaming.manager import stream_manager
from backend.app.recordings.service import get_stream_recording_service
from backend.app.screenshots.service import screenshot_service
from backend.app.config import settings


router = APIRouter(prefix="/api/accounts", tags=["Accounts"])
admin_router = APIRouter(prefix="/api/admin/broadcasters", tags=["Broadcasters"])
password_context = CryptContext(schemes=["argon2"], deprecated="auto")
SESSION_COOKIE = "drone_broadcaster_session"
SESSION_HOURS = 8


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=str(settings.environment).lower() not in {"development", "dev"},
        samesite="lax",
        max_age=SESSION_HOURS * 60 * 60,
        path="/",
    )


def _account_payload(account: BroadcasterAccount) -> dict:
    return {
        "id": account.id,
        "username": account.username,
        "permissions": {
            "can_start_streams": account.can_start_streams,
            "can_manage_links": account.can_manage_links,
            "can_record": account.can_record,
            "can_screenshot": account.can_screenshot,
            "can_manage_viewers": account.can_manage_viewers,
        },
    }


class RegistrationRequest(BaseModel):
    invite_token: str = Field(min_length=32, max_length=200)
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class InviteRequest(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=168)


class AccountPermissionsUpdate(BaseModel):
    is_active: bool | None = None
    can_start_streams: bool | None = None
    can_manage_links: bool | None = None
    can_record: bool | None = None
    can_screenshot: bool | None = None
    can_manage_viewers: bool | None = None


class StreamCreateRequest(BaseModel):
    title: str = Field(default="Live stream", min_length=1, max_length=100)


class ViewerLinkCreateRequest(BaseModel):
    expires_in_hours: int | None = Field(default=None, ge=1, le=720)


class ViewerPermissionsUpdate(BaseModel):
    can_record: bool | None = None
    can_screenshot: bool | None = None


@admin_router.post("/invites")
async def create_broadcaster_invite(
    request: InviteRequest,
    admin: str = Depends(get_current_admin),
):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        session.add(
            BroadcasterInvite(
                token_hash=_hash_token(token),
                created_by=admin,
                expires_at=now + timedelta(hours=request.expires_in_hours),
                created_at=now,
            )
        )
        await session.commit()
    return {"success": True, "invite_token": token}


@admin_router.get("")
async def list_broadcasters(admin: str = Depends(get_current_admin)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BroadcasterAccount).order_by(BroadcasterAccount.created_at.desc())
        )
        accounts = result.scalars().all()
        return {"success": True, "accounts": [
            {**_account_payload(account), "is_active": account.is_active}
            for account in accounts
        ]}


@admin_router.patch("/{account_id}")
async def update_broadcaster(
    account_id: int,
    update: AccountPermissionsUpdate,
    admin: str = Depends(get_current_admin),
):
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No account changes supplied.")

    async with AsyncSessionLocal() as session:
        account = await session.get(BroadcasterAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Broadcaster account not found.")
        for key, value in changes.items():
            setattr(account, key, value)

        now = datetime.now(timezone.utc)
        stop_streams = (
            changes.get("is_active") is False
            or changes.get("can_start_streams") is False
        )
        end_recordings = (
            stop_streams or changes.get("can_record") is False
        )
        stream_result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(StreamOwnership.account_id == account.id)
        )
        owned_streams = stream_result.scalars().all()
        stream_ids = [stream.id for stream in owned_streams]

        if end_recordings:
            for stream in owned_streams:
                recorder = get_stream_recording_service(stream.id)
                if recorder.is_recording:
                    recording = await recorder.stop()
                    session.add(Recording(
                        stream_id=stream.id,
                        started_at=recording["started_at"],
                        ended_at=recording["ended_at"],
                        duration_seconds=recording["duration_seconds"],
                        file_path=recording["file_path"],
                        file_name=recording["file_name"],
                        file_size_bytes=recording["file_size_bytes"],
                        status="completed",
                    ))

        if stop_streams:
            for stream in owned_streams:
                if stream.status in {"live", "starting"}:
                    stream.status = "offline"
                    stream.stopped_at = now
            if stream_ids:
                viewers_result = await session.execute(
                    select(ViewerSession).where(
                        ViewerSession.stream_id.in_(stream_ids),
                        ViewerSession.status == "watching",
                    )
                )
                for viewer in viewers_result.scalars().all():
                    viewer.status = "stream_ended"
                    viewer.disconnected_at = now
                    session.add(ViewerEvent(
                        session_id=viewer.id,
                        event_type="stream_ended",
                        created_at=now,
                    ))

        revoke_recording = (
            changes.get("is_active") is False
            or changes.get("can_record") is False
        )
        if revoke_recording and stream_ids:
            permissions_result = await session.execute(
                select(RecordingPermission)
                .join(ViewerSession, ViewerSession.id == RecordingPermission.viewer_session_id)
                .where(ViewerSession.stream_id.in_(stream_ids))
            )
            for permission in permissions_result.scalars().all():
                permission.allowed = False
                permission.revoked_at = now

        revoke_screenshots = (
            changes.get("is_active") is False
            or changes.get("can_screenshot") is False
        )
        if revoke_screenshots and stream_ids:
            permissions_result = await session.execute(
                select(ScreenshotPermission)
                .join(ViewerSession, ViewerSession.id == ScreenshotPermission.viewer_session_id)
                .where(ViewerSession.stream_id.in_(stream_ids))
            )
            for permission in permissions_result.scalars().all():
                permission.allowed = False
                permission.revoked_at = now

        if changes.get("is_active") is False:
            sessions_result = await session.execute(
                select(BroadcasterSession).where(
                    BroadcasterSession.account_id == account.id
                )
            )
            for account_session in sessions_result.scalars().all():
                await session.delete(account_session)

        await session.commit()
        await session.refresh(account)
        response_account = {"success": True, "account": {
            **_account_payload(account), "is_active": account.is_active
        }}

    if stop_streams:
        for stream_id in stream_ids:
            await stream_manager.stop_stream(str(stream_id))

    return response_account


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_broadcaster(
    data: RegistrationRequest,
    response: Response,
):
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        invite_result = await session.execute(
            select(BroadcasterInvite).where(
                BroadcasterInvite.token_hash == _hash_token(data.invite_token),
                BroadcasterInvite.used_at.is_(None),
                BroadcasterInvite.expires_at > now,
            )
        )
        invite = invite_result.scalar_one_or_none()
        if invite is None:
            raise HTTPException(status_code=400, detail="Invite is invalid or expired.")

        account_result = await session.execute(
            select(BroadcasterAccount.id).where(
                BroadcasterAccount.username == data.username
            )
        )
        if account_result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Username is already in use.")

        account = BroadcasterAccount(
            username=data.username,
            password_hash=password_context.hash(data.password),
            created_at=now,
        )
        invite.used_at = now
        session.add(account)
        await session.flush()

        token = secrets.token_urlsafe(48)
        session.add(
            BroadcasterSession(
                account_id=account.id,
                token_hash=_hash_token(token),
                expires_at=now + timedelta(hours=SESSION_HOURS),
                created_at=now,
            )
        )
        await session.commit()
        await session.refresh(account)

    _set_session_cookie(response, token)
    return {"success": True, "account": _account_payload(account)}


@router.post("/streams", status_code=status.HTTP_201_CREATED)
async def create_broadcaster_stream(
    data: StreamCreateRequest,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_start_streams:
        raise HTTPException(status_code=403, detail="You cannot create streams.")

    now = datetime.now(timezone.utc)
    viewer_token = (
        secrets.token_urlsafe(32)
        if account.can_manage_links
        else None
    )
    async with AsyncSessionLocal() as session:
        stream = Stream(
            stream_id=secrets.token_urlsafe(16),
            status="ready",
            created_at=now,
            viewer_count=0,
        )
        session.add(stream)
        await session.flush()
        session.add(StreamOwnership(stream_id=stream.id, account_id=account.id))
        if viewer_token is not None:
            session.add(StreamLink(
                stream_id=stream.id,
                token=viewer_token,
                created_at=now,
            ))
        await session.commit()

    return {
        "success": True,
        "stream": {"id": stream.stream_id, "status": stream.status},
        "viewer_token": viewer_token,
    }


@router.get("/streams")
async def list_broadcaster_streams(
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(StreamOwnership.account_id == account.id)
            .order_by(Stream.created_at.desc())
        )
        streams = result.scalars().all()
        return {
            "success": True,
            "streams": [
                {"id": stream.stream_id, "status": stream.status}
                for stream in streams
            ],
        }


@router.get("/streams/{stream_key}/links")
async def list_broadcaster_links(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_manage_links:
        raise HTTPException(status_code=403, detail="You cannot manage viewer links.")
    async with AsyncSessionLocal() as session:
        owner_result = await session.execute(
            select(StreamOwnership.id).join(
                Stream, Stream.id == StreamOwnership.stream_id
            ).where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        if owner_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        links_result = await session.execute(
            select(StreamLink)
            .join(Stream, Stream.id == StreamLink.stream_id)
            .where(Stream.stream_id == stream_key)
            .order_by(StreamLink.created_at.desc())
        )
        links = links_result.scalars().all()
        return {
            "success": True,
            "links": [
                {
                    "id": link.id,
                    "token": link.token,
                    "created_at": link.created_at.isoformat(),
                    "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                    "revoked": link.revoked_at is not None,
                }
                for link in links
            ],
        }


@router.post("/streams/{stream_key}/links", status_code=status.HTTP_201_CREATED)
async def create_broadcaster_link(
    stream_key: str,
    data: ViewerLinkCreateRequest,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_manage_links:
        raise HTTPException(status_code=403, detail="You cannot manage viewer links.")
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        link = StreamLink(
            stream_id=stream.id,
            token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=(
                now + timedelta(hours=data.expires_in_hours)
                if data.expires_in_hours
                else None
            ),
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
    return {"success": True, "link": {"id": link.id, "token": link.token}}


@router.delete("/streams/{stream_key}/links/{link_id}")
async def revoke_broadcaster_link(
    stream_key: str,
    link_id: int,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_manage_links:
        raise HTTPException(status_code=403, detail="You cannot manage viewer links.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(StreamLink)
            .join(Stream, Stream.id == StreamLink.stream_id)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
                StreamLink.id == link_id,
            )
        )
        link = result.scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=404, detail="Owned viewer link not found.")
        if link.revoked_at is None:
            link.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    return {"success": True}


@router.post("/streams/{stream_key}/start")
async def prepare_broadcaster_stream(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_start_streams:
        raise HTTPException(status_code=403, detail="You cannot start streams.")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found.")
        if stream.status == "live":
            raise HTTPException(status_code=409, detail="Stream is already live.")
        stream.status = "starting"
        stream.started_at = None
        stream.stopped_at = None
        await session.commit()

    return {"success": True, "stream": {"id": stream_key, "status": "starting"}}


@router.post("/streams/{stream_key}/stop")
async def stop_broadcaster_stream(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found.")
        stream.status = "offline"
        stream.stopped_at = datetime.now(timezone.utc)
        recorder = get_stream_recording_service(stream.id)
        if recorder.is_recording:
            recording = await recorder.stop()
            session.add(Recording(
                stream_id=stream.id,
                started_at=recording["started_at"],
                ended_at=recording["ended_at"],
                duration_seconds=recording["duration_seconds"],
                file_path=recording["file_path"],
                file_name=recording["file_name"],
                file_size_bytes=recording["file_size_bytes"],
                status="completed",
            ))

        active_viewers = await session.execute(
            select(ViewerSession).where(
                ViewerSession.stream_id == stream.id,
                ViewerSession.status == "watching",
            )
        )
        for viewer in active_viewers.scalars().all():
            viewer.status = "stream_ended"
            viewer.disconnected_at = stream.stopped_at
            session.add(ViewerEvent(
                session_id=viewer.id,
                event_type="stream_ended",
                created_at=stream.stopped_at,
            ))
        await session.commit()
        stream_id = str(stream.id)

    await stream_manager.stop_stream(stream_id)
    return {"success": True, "stream": {"id": stream_key, "status": "offline"}}


@router.post("/login")
async def login_broadcaster(data: LoginRequest, response: Response):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BroadcasterAccount).where(
                BroadcasterAccount.username == data.username
            )
        )
        account = result.scalar_one_or_none()
        if (
            account is None
            or not account.is_active
            or not password_context.verify(data.password, account.password_hash)
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(48)
        session.add(
            BroadcasterSession(
                account_id=account.id,
                token_hash=_hash_token(token),
                expires_at=now + timedelta(hours=SESSION_HOURS),
                created_at=now,
            )
        )
        await session.commit()
        await session.refresh(account)

    _set_session_cookie(response, token)
    return {"success": True, "account": _account_payload(account)}


@router.get("/me")
async def broadcaster_me(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return {"authenticated": False}

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BroadcasterAccount)
            .join(BroadcasterSession, BroadcasterSession.account_id == BroadcasterAccount.id)
            .where(
                BroadcasterSession.token_hash == _hash_token(token),
                BroadcasterSession.expires_at > now,
                BroadcasterAccount.is_active.is_(True),
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            return {"authenticated": False}
        return {"authenticated": True, "account": _account_payload(account)}


@router.post("/logout")
async def logout_broadcaster(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BroadcasterSession).where(
                    BroadcasterSession.token_hash == _hash_token(token)
                )
            )
            account_session = result.scalar_one_or_none()
            if account_session is not None:
                await session.delete(account_session)
                await session.commit()
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=str(settings.environment).lower() not in {"development", "dev"},
        samesite="lax",
        path="/",
    )
    return {"success": True}


@router.get("/streams/{stream_key}/viewers")
async def list_stream_viewers(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_manage_viewers:
        raise HTTPException(status_code=403, detail="You cannot manage viewers.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                ViewerSession,
                RecordingPermission.allowed,
                ScreenshotPermission.allowed,
            )
            .join(Stream, Stream.id == ViewerSession.stream_id)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .outerjoin(
                RecordingPermission,
                RecordingPermission.viewer_session_id == ViewerSession.id,
            )
            .outerjoin(
                ScreenshotPermission,
                ScreenshotPermission.viewer_session_id == ViewerSession.id,
            )
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
            .order_by(ViewerSession.connected_at.desc())
        )
        viewers = result.all()
        return {
            "success": True,
            "viewers": [
                {
                    "session_id": viewer.session_id,
                    "status": viewer.status,
                    "connected_at": viewer.connected_at.isoformat(),
                    "ip_address": viewer.ip_address,
                    "user_agent": viewer.user_agent,
                    "can_record": bool(recording_allowed),
                    "can_screenshot": bool(screenshot_allowed),
                }
                for viewer, recording_allowed, screenshot_allowed in viewers
            ],
        }


@router.patch("/streams/{stream_key}/viewers/{viewer_session_id}/permissions")
async def update_stream_viewer_permissions(
    stream_key: str,
    viewer_session_id: str,
    update: ViewerPermissionsUpdate,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No permission changes supplied.")
    if "can_record" in changes and not account.can_record:
        raise HTTPException(status_code=403, detail="You cannot grant recording access.")
    if "can_screenshot" in changes and not account.can_screenshot:
        raise HTTPException(status_code=403, detail="You cannot grant screenshot access.")

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession)
            .join(Stream, Stream.id == ViewerSession.stream_id)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
                ViewerSession.session_id == viewer_session_id,
            )
        )
        viewer = result.scalar_one_or_none()
        if viewer is None:
            raise HTTPException(status_code=404, detail="Viewer session not found.")

        permission_models = {
            "can_record": RecordingPermission,
            "can_screenshot": ScreenshotPermission,
        }
        for permission_name, allowed in changes.items():
            model = permission_models[permission_name]
            result = await session.execute(
                select(model).where(model.viewer_session_id == viewer.id)
            )
            permission = result.scalar_one_or_none()
            if permission is None:
                permission = model(viewer_session_id=viewer.id)
                session.add(permission)
            permission.allowed = allowed
            permission.granted_at = now if allowed else permission.granted_at
            permission.revoked_at = None if allowed else now
        await session.commit()
    return {"success": True}


@router.post("/streams/{stream_key}/viewers/{viewer_session_id}/kick")
async def kick_stream_viewer(
    stream_key: str,
    viewer_session_id: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_manage_viewers:
        raise HTTPException(status_code=403, detail="You cannot manage viewers.")
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession)
            .join(Stream, Stream.id == ViewerSession.stream_id)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
                ViewerSession.session_id == viewer_session_id,
            )
        )
        viewer = result.scalar_one_or_none()
        if viewer is None:
            raise HTTPException(status_code=404, detail="Viewer session not found.")
        viewer.status = "kicked"
        viewer.disconnected_at = now
        session.add(ViewerEvent(session_id=viewer.id, event_type="kicked", created_at=now))
        await session.commit()
    return {"success": True}


@router.post("/streams/{stream_key}/recording/start")
async def start_broadcaster_recording(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_record:
        raise HTTPException(status_code=403, detail="You cannot record streams.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        if stream.status != "live":
            raise HTTPException(status_code=409, detail="Stream is not live.")
        stream_id = stream.id

    recorder = get_stream_recording_service(stream_id)
    if recorder.is_recording:
        raise HTTPException(status_code=409, detail="This stream is already recording.")
    try:
        source_track = stream_manager.subscribe_recording(str(stream_id))
        active = recorder.start(stream_id=stream_id, source_track=source_track)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Unable to start recording: {error}") from error
    return {
        "success": True,
        "recording": {"file_name": active["file_name"], "started_at": active["started_at"].isoformat()},
    }


@router.post("/streams/{stream_key}/recording/stop")
async def stop_broadcaster_recording(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_record:
        raise HTTPException(status_code=403, detail="You cannot manage recordings.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        recorder = get_stream_recording_service(stream.id)
        if not recorder.is_recording:
            raise HTTPException(status_code=409, detail="This stream is not recording.")
        recording = await recorder.stop()
        session.add(Recording(
            stream_id=stream.id,
            started_at=recording["started_at"],
            ended_at=recording["ended_at"],
            duration_seconds=recording["duration_seconds"],
            file_path=recording["file_path"],
            file_name=recording["file_name"],
            file_size_bytes=recording["file_size_bytes"],
            status="completed",
        ))
        session.add(SecurityLog(
            event="recording",
            actor=account.username,
            detail=f"Stopped stream recording {recording['file_name']}",
        ))
        await session.commit()
    return {"success": True, "recording": {"file_name": recording["file_name"]}}


@router.post("/streams/{stream_key}/screenshot")
async def capture_broadcaster_screenshot(
    stream_key: str,
    account: BroadcasterAccount = Depends(get_current_broadcaster),
):
    if not account.can_screenshot:
        raise HTTPException(status_code=403, detail="You cannot capture screenshots.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_key,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
        if stream is None:
            raise HTTPException(status_code=404, detail="Owned stream not found.")
        if stream.status != "live":
            raise HTTPException(status_code=409, detail="Stream is not live.")
        track = stream_manager.subscribe_stream(str(stream.id))
        try:
            screenshot = await screenshot_service.capture(
                source_track=track,
                stream_id=stream.id,
            )
        finally:
            track.stop()
        session.add(Screenshot(
            stream_id=stream.id,
            file_path=screenshot["file_path"],
            file_name=screenshot["file_name"],
            file_size_bytes=screenshot["file_size_bytes"],
            captured_at=screenshot["captured_at"],
        ))
        session.add(SecurityLog(
            event="screenshot",
            actor=account.username,
            detail=f"Captured stream screenshot {screenshot['file_name']}",
        ))
        await session.commit()
    return {"success": True, "screenshot": {"file_name": screenshot["file_name"]}}