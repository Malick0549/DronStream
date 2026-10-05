from ipaddress import ip_address

from fastapi import APIRouter, Request, Depends
from datetime import datetime, timezone
import secrets
from backend.app.models.settings import PlatformSettings
from backend.app.models.security_log import SecurityLog
from sqlalchemy import select, func
from pathlib import Path
from fastapi.responses import FileResponse
from backend.app.api.streams import stream_state
from backend.app.streaming.manager import stream_manager
from backend.app.auth.dependencies import get_current_admin
from backend.app.database import AsyncSessionLocal
from backend.app.models import (
    Stream,
    StreamLink,
    ViewerSession,
    ViewerEvent,
    Screenshot,
    Recording,
    RecordingPermission,
)
from backend.app.models.screenshot_permission import (
    ScreenshotPermission,
)

from backend.app.screenshots.service import (
    screenshot_service,
)
from backend.app.recordings.service import (
    recording_service,
    get_stream_recording_service,
)

router = APIRouter(
    prefix="/api/viewer",
    tags=["Viewer"],
)

# stream_id -> set of kicked IPs (blocked until stream ends)
_kicked_ips: dict[int, set[str]] = {}

# session_id -> last status-poll time (UTC)
_viewer_heartbeats: dict[str, datetime] = {}
STALE_VIEWER_SECONDS = 20

def get_client_ip(request: Request):
    """
    Get the viewer IP address.

    For now, use the direct client address.
    When deployed behind a trusted reverse proxy,
    this can later be extended safely.
    """

    if request.client:
        return request.client.host

    return "unknown"


async def get_stream_by_public_id(session, stream_id: str):
    """
    Find a stream using its public stream_id.
    """

    result = await session.execute(
        select(Stream).where(
            Stream.stream_id == stream_id
        )
    )

    return result.scalar_one_or_none()


async def update_viewer_count(session, stream):
    """
    Calculate and synchronize the active viewer count.
    """

    result = await session.execute(
        select(func.count(ViewerSession.id))
        .where(
            ViewerSession.stream_id == stream.id,
            ViewerSession.status == "watching",
        )
    )

    count = result.scalar_one()

    stream.viewer_count = count

    # Keep WebRTC compatibility state synchronized.
    if stream_state["id"] == stream.stream_id:
        stream_state["viewer_count"] = count

    return count


# ------------------------------------------------------------------
# PUBLIC VIEWER STREAM ACCESS
# ------------------------------------------------------------------

@router.get("/stream/{viewer_token}")
async def viewer_stream(
    viewer_token: str,
    request: Request,
):
    """
    Public viewer access.

    No admin authentication is required.
    """

    async with AsyncSessionLocal() as session:

        # ---------------------------------------------------------
        # 1. Find the viewer link.
        # ---------------------------------------------------------

        result = await session.execute(
            select(StreamLink)
            .where(
                StreamLink.token == viewer_token,
                StreamLink.revoked_at.is_(None),
            )
        )

        stream_link = result.scalar_one_or_none()

        if not stream_link:
            return {
                "success": False,
                "authorized": False,
                "message": "Invalid or revoked viewer link.",
            }

        # ---------------------------------------------------------
        # 2. Check link expiration.
        # ---------------------------------------------------------

        now = datetime.now(timezone.utc)

        if (
            stream_link.expires_at
            and now >= stream_link.expires_at
        ):
            return {
                "success": False,
                "authorized": False,
                "message": "This viewer link has expired.",
            }
            
                # Password-protected link
        if stream_link.password_hash:
            provided = request.query_params.get("password") or ""
            import hashlib
            provided_hash = hashlib.sha256(
                provided.strip().encode("utf-8")
            ).hexdigest()
            if provided_hash != stream_link.password_hash:
                session.add(
                    SecurityLog(
                        event="link_password_fail",
                        actor="viewer",
                        ip_address=get_client_ip(request),
                        detail="Wrong or missing viewer link password",
                    )
                )
                await session.commit()
                return {
                    "success": False,
                    "authorized": False,
                    "password_required": True,
                    "message": "Password required or incorrect.",
                }

        # ---------------------------------------------------------
        # 3. Get associated stream.
        # ---------------------------------------------------------

        result = await session.execute(
            select(Stream).where(
                Stream.id == stream_link.stream_id
            )
        )

        stream = result.scalar_one_or_none()

        if not stream:
            return {
                "success": False,
                "authorized": False,
                "message": "No stream exists.",
            }
            
        client_ip = get_client_ip(request)
        blocked = _kicked_ips.get(stream.id) or set()
        if client_ip and client_ip in blocked:
            return {
                "success": False,
                "authorized": False,
                "message": "Access denied. You were removed from this stream.",
            }
                    # Max concurrent viewers (from Settings)
        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()

        if platform_settings and platform_settings.max_viewer_sessions:
            active_count = await update_viewer_count(session, stream)
            if active_count >= platform_settings.max_viewer_sessions:
                return {
                    "success": False,
                    "authorized": False,
                    "message": "Maximum viewer limit reached.",
                }

        # ---------------------------------------------------------
        # 4. Create viewer session.
        # ---------------------------------------------------------

        session_id = secrets.token_urlsafe(16)

        client_ip = get_client_ip(request)
        try:
            from backend.app.services.geo import lookup_ip_location
            geo = lookup_ip_location(client_ip)
        except Exception:
            geo = {"country": None, "region": None, "city": None}

        viewer_session = ViewerSession(
            session_id=session_id,
            stream_id=stream.id,
            stream_link_id=stream_link.id,
            connected_at=now,
            disconnected_at=None,
            status="watching",
            ip_address=client_ip,
            user_agent=request.headers.get(
                "user-agent",
                "unknown",
            ),
            referrer=request.headers.get(
                "referer",
            ),
            country=geo.get("country"),
            region=geo.get("region"),
            city=geo.get("city"),
        )

        session.add(viewer_session)

        await session.flush()

        # Default permissions from Settings
        if platform_settings:
            if platform_settings.default_viewer_can_screenshot:
                session.add(
                    ScreenshotPermission(
                        viewer_session_id=viewer_session.id,
                        allowed=True,
                        granted_at=now,
                    )
                )
            if platform_settings.default_viewer_can_record:
                session.add(
                    RecordingPermission(
                        viewer_session_id=viewer_session.id,
                        allowed=True,
                        granted_at=now,
                    )
                )

        session.add(
            SecurityLog(
                event="viewer_connect",
                actor=f"VIEWER #{viewer_session.id}",
                ip_address=viewer_session.ip_address,
                detail=f"Viewer connected to stream {stream.stream_id}",
            )
        )

        # ---------------------------------------------------------
        # 5. Record viewer connection event.
        # ---------------------------------------------------------

        viewer_event = ViewerEvent(
            session_id=viewer_session.id,
            event_type="connected",
            created_at=now,
        )

        session.add(viewer_event)

        # ---------------------------------------------------------
        # 6. Update active viewer count.
        # ---------------------------------------------------------

        viewer_count = await update_viewer_count(
            session,
            stream,
        )

        await session.commit()

        # ---------------------------------------------------------
        # 7. Keep WebRTC compatibility state synchronized.
        # ---------------------------------------------------------

        stream_state["id"] = stream.stream_id
        stream_state["status"] = stream.status
        stream_state["created_at"] = (
            stream.created_at.isoformat()
            if stream.created_at
            else None
        )
        stream_state["started_at"] = (
            stream.started_at.isoformat()
            if stream.started_at
            else None
        )
        stream_state["viewer_count"] = viewer_count
        stream_state["viewer_token"] = viewer_token

        # ---------------------------------------------------------
        # 8. Return authorized stream information.
        # ---------------------------------------------------------

        return {
            "success": True,
            "authorized": True,
            "session_id": session_id,
            "stream": {
                "id": stream.stream_id,
                "status": stream.status,
                "viewer_count": viewer_count,
                "started_at": (
                    stream.started_at.isoformat()
                    if stream.started_at
                    else None
                ),
            },
        }


@router.get("/session/{session_id}/status")
async def viewer_session_status(session_id: str):
    """Viewer polls this to learn if still allowed (kick / revoke)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )
        viewer_session = result.scalar_one_or_none()

        if not viewer_session:
            return {
                "success": False,
                "authorized": False,
                "status": "missing",
                "message": "Session not found.",
            }

        if viewer_session.status != "watching":
            return {
                "success": True,
                "authorized": False,
                "status": viewer_session.status,
                "message": "Session is no longer active.",
            }

        link_result = await session.execute(
            select(StreamLink).where(
                StreamLink.id == viewer_session.stream_link_id
            )
        )
        link = link_result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if not link or link.revoked_at is not None:
            viewer_session.status = "revoked"
            viewer_session.disconnected_at = now
            await session.commit()
            return {
                "success": True,
                "authorized": False,
                "status": "revoked",
                "message": "Viewer link has been revoked.",
            }

        if link.expires_at and now >= link.expires_at:
            viewer_session.status = "revoked"
            viewer_session.disconnected_at = now
            await session.commit()
            return {
                "success": True,
                "authorized": False,
                "status": "expired",
                "message": "Viewer link has expired.",
            }

        _viewer_heartbeats[session_id] = now

        return {
            "success": True,
            "authorized": True,
            "status": "watching",
        }

# ------------------------------------------------------------------
# PUBLIC VIEWER DISCONNECT
# ------------------------------------------------------------------

@router.post("/session/{session_id}/disconnect")
async def disconnect_viewer(
    session_id: str,
):
    """
    Mark a viewer session as disconnected.

    This remains public because viewers call it when leaving.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = result.scalar_one_or_none()

        if not viewer_session:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        if viewer_session.status == "disconnected":
            return {
                "success": True,
                "message": "Viewer session was already disconnected.",
            }

        now = datetime.now(timezone.utc)

        viewer_session.disconnected_at = now
        viewer_session.status = "disconnected"
        _viewer_heartbeats.pop(session_id, None)

        # Record disconnect event.
        viewer_event = ViewerEvent(
            session_id=viewer_session.id,
            event_type="disconnected",
            created_at=now,
        )

        session.add(viewer_event)

        session.add(
            SecurityLog(
                event="viewer_disconnect",
                actor=f"VIEWER #{viewer_session.id}",
                ip_address=viewer_session.ip_address,
                detail=f"Viewer disconnected session {session_id}",
            )
        )

        # Get associated stream.
        result = await session.execute(
            select(Stream).where(
                Stream.id == viewer_session.stream_id
            )
        )

        stream = result.scalar_one_or_none()

        viewer_count = 0

        if stream:
            viewer_count = await update_viewer_count(
                session,
                stream,
            )

        await session.commit()

        return {
            "success": True,
            "message": "Viewer session disconnected.",
            "session_id": session_id,
            "viewer_count": viewer_count,
        }
        
        
@router.post("/sessions/{session_id}/kick")
async def kick_viewer(
    session_id: str,
    admin: str = Depends(get_current_admin),
):
    """Admin forces a viewer session offline."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )
        viewer_session = result.scalar_one_or_none()

        if not viewer_session:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        if viewer_session.status == "disconnected":
            return {
                "success": True,
                "message": "Viewer was already disconnected.",
            }

        now = datetime.now(timezone.utc)
        viewer_session.disconnected_at = now
        viewer_session.status = "kicked"
        ip = (viewer_session.ip_address or "").strip()
        if ip and viewer_session.stream_id is not None:
            _kicked_ips.setdefault(viewer_session.stream_id, set()).add(ip)
        _viewer_heartbeats.pop(session_id, None)

        session.add(
            ViewerEvent(
                session_id=viewer_session.id,
                event_type="kicked",
                created_at=now,
            )
        )
        session.add(
            SecurityLog(
                event="viewer_kick",
                actor=admin,
                ip_address=viewer_session.ip_address,
                detail=f"Kicked viewer session {session_id}",
            )
        )

        result = await session.execute(
            select(Stream).where(Stream.id == viewer_session.stream_id)
        )
        stream = result.scalar_one_or_none()
        viewer_count = 0
        if stream:
            viewer_count = await update_viewer_count(session, stream)

        await session.commit()

        return {
            "success": True,
            "message": "Viewer kicked.",
            "session_id": session_id,
            "viewer_count": viewer_count,
        }


# ------------------------------------------------------------------
# ADMIN VIEWER MONITORING
# ------------------------------------------------------------------

@router.get("/sessions")
async def get_viewer_sessions(
    admin: str = Depends(get_current_admin),
):
    """
    Return viewer sessions for the admin dashboard.
    """

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)

        # End sessions that stopped polling (tab closed without disconnect)
        watching_result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.status == "watching"
            )
        )
        settings_result = await session.execute(
            select(PlatformSettings)
            .order_by(PlatformSettings.id.asc())
            .limit(1)
        )
        platform_settings = settings_result.scalar_one_or_none()
        # Stored column name is historical; value is seconds.
        stale_seconds = STALE_VIEWER_SECONDS
        if platform_settings and platform_settings.session_timeout_minutes:
            stale_seconds = max(
                5,
                int(platform_settings.session_timeout_minutes),
            )

        for vs in watching_result.scalars().all():
            last = _viewer_heartbeats.get(vs.session_id)
            age = (now - (last or vs.connected_at)).total_seconds()
            if age > stale_seconds:
                vs.status = "timeout"
                vs.disconnected_at = now
                session.add(
                    ViewerEvent(
                        session_id=vs.id,
                        event_type="stale_timeout",
                        created_at=now,
                    )
                )
                session.add(
                    SecurityLog(
                        event="viewer_timeout",
                        actor=f"VIEWER #{vs.id}",
                        ip_address=vs.ip_address,
                        detail=(
                            f"Viewer session {vs.session_id} "
                            "ended (stale / tab closed)"
                        ),
                    )
                )
                _viewer_heartbeats.pop(vs.session_id, None)

        await session.commit()

        result = await session.execute(
            select(ViewerSession)
            .order_by(ViewerSession.connected_at.desc())
        )

        viewer_records = result.scalars().all()

        sessions = []

        for viewer in viewer_records:

            connected = viewer.connected_at

            if viewer.disconnected_at:
                disconnected = viewer.disconnected_at
            else:
                disconnected = datetime.now(timezone.utc)

            duration_seconds = max(
                0,
                int(
                    (
                        disconnected - connected
                    ).total_seconds()
                ),
            )

            sessions.append({
                "session_id": viewer.session_id,
                "stream_id": (
                    await get_stream_public_id(
                        session,
                        viewer.stream_id,
                    )
                ),
                "status": viewer.status,
                "connected_at": connected.isoformat(),
                "disconnected_at": (
                    viewer.disconnected_at.isoformat()
                    if viewer.disconnected_at
                    else None
                ),
                "duration_seconds": duration_seconds,
                "ip_address": viewer.ip_address,
                "user_agent": viewer.user_agent,
                "referrer": viewer.referrer,
                "country": getattr(viewer, "country", None),
                "region": getattr(viewer, "region", None),
                "city": getattr(viewer, "city", None),
            })

        # Determine active viewer count across the current stream.
        latest_stream_result = await session.execute(
            select(Stream)
            .order_by(Stream.created_at.desc())
            .limit(1)
        )

        latest_stream = (
            latest_stream_result.scalar_one_or_none()
        )

        viewer_count = 0

        if latest_stream:
            viewer_count = await update_viewer_count(
                session,
                latest_stream,
            )

            await session.commit()

        return {
            "success": True,
            "viewer_count": viewer_count,
            "sessions": sessions,
        }


async def get_stream_public_id(session, database_stream_id: int):
    """
    Convert the internal database stream primary key
    into the public stream ID used by the application.
    """

    result = await session.execute(
        select(Stream.stream_id).where(
            Stream.id == database_stream_id
        )
    )

    stream_id = result.scalar_one_or_none()

    return stream_id

# ------------------------------------------------------------------
# VIEWER SCREENSHOT
# ------------------------------------------------------------------

@router.post("/session/{session_id}/screenshot")
async def viewer_capture_screenshot(
    session_id: str,
):
    """
    Allow a viewer to capture a screenshot only when
    the administrator has granted screenshot permission
    to that viewer session.
    """

    async with AsyncSessionLocal() as session:

        # ---------------------------------------------------------
        # 1. Find the viewer session.
        # ---------------------------------------------------------

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = (
            result.scalar_one_or_none()
        )

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        # ---------------------------------------------------------
        # 2. Make sure the viewer is still connected.
        # ---------------------------------------------------------

        if viewer_session.status != "watching":
            return {
                "success": False,
                "message": "Viewer session is no longer active.",
            }

        # ---------------------------------------------------------
        # 3. Check screenshot permission.
        # ---------------------------------------------------------

        permission_result = await session.execute(
            select(ScreenshotPermission).where(
                ScreenshotPermission.viewer_session_id
                == viewer_session.id
            )
        )

        permission = (
            permission_result.scalar_one_or_none()
        )

        if (
            permission is None
            or not permission.allowed
        ):
            return {
                "success": False,
                "message": (
                    "Screenshot permission has not "
                    "been granted by the administrator."
                ),
            }

        # ---------------------------------------------------------
        # 4. Find the viewer's stream.
        # ---------------------------------------------------------

        result = await session.execute(
            select(Stream).where(
                Stream.id == viewer_session.stream_id
            )
        )

        stream = result.scalar_one_or_none()

        if stream is None:
            return {
                "success": False,
                "message": "No stream exists.",
            }

        if stream.status != "live":
            return {
                "success": False,
                "message": "The stream is not live.",
            }

        # ---------------------------------------------------------
        # 5. Make sure the stream source is running.
        # ---------------------------------------------------------

        stream_key = str(stream.id)
        if not stream_manager.has_stream_source(stream_key):
            return {
                "success": False,
                "message": "The stream source is not running.",
            }

        # ---------------------------------------------------------
        # 6. Capture one frame.
        # ---------------------------------------------------------

        screenshot_subscription = None

        try:

            screenshot_subscription = stream_manager.subscribe_stream_source(
                stream_key,
                buffered=False,
            )

            screenshot = (
                await screenshot_service.capture(
                    source_track=(
                        screenshot_subscription
                    ),
                    stream_id=stream.id,
                    admin_id=None, 
                )               
            )

            try:
                from backend.app.services.watermark import (
                    apply_screenshot_watermark,
                )
                apply_screenshot_watermark(
                    screenshot["file_path"]
                )
            except Exception as wm_err:
                print(
                    "DroneStream: viewer screenshot watermark:",
                    wm_err,
                )

            # -----------------------------------------------------
            # 7. Save screenshot information in the database.
            # -----------------------------------------------------

            screenshot_record = Screenshot(
                stream_id=stream.id,
                file_path=screenshot["file_path"],
                file_name=screenshot["file_name"],
                file_size_bytes=screenshot[
                    "file_size_bytes"
                ],
                captured_at=screenshot[
                    "captured_at"
                ],
                created_by_admin_id=None,
                created_by_viewer_session_id=(
                    viewer_session.id
                ),
            )

            session.add(screenshot_record)

            await session.commit()

            await session.refresh(
                screenshot_record
            )

            session.add(
                SecurityLog(
                    event="screenshot",
                    actor=f"VIEWER #{viewer_session.id}",
                    ip_address=viewer_session.ip_address,
                    detail=(
                        f"Viewer captured screenshot "
                        f"{screenshot['file_name']}"
                    ),
                )
            )
            await session.commit()

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Unable to capture screenshot: "
                    f"{error}"
                ),
            }

        finally:

            if screenshot_subscription is not None:

                try:
                    screenshot_subscription.stop()
                except Exception:
                    pass

        # ---------------------------------------------------------
        # 8. Return screenshot information.
        # ---------------------------------------------------------

        return {
            "success": True,
            "message": "Screenshot captured.",
            "screenshot": {
                "id": screenshot_record.id,
                "stream_id": stream.stream_id,
                "file_name": screenshot["file_name"],
                "file_path": screenshot["file_path"],
                "file_size_bytes": (
                    screenshot["file_size_bytes"]
                ),
                "captured_at": (
                    screenshot["captured_at"].isoformat()
                ),
                "width": screenshot["width"],
                "height": screenshot["height"],
                "created_by_viewer_session_id": (
                    screenshot_record.created_by_viewer_session_id
                ),
            },
        }
        
# ------------------------------------------------------------------
# VIEWER RECORDING START
# ------------------------------------------------------------------

@router.post("/session/{session_id}/recording/start")
async def viewer_start_recording(
    session_id: str,
):
    """
    Allow a viewer to start a recording only when
    the administrator has granted recording permission
    to that viewer session.
    """

    async with AsyncSessionLocal() as session:

        # ---------------------------------------------------------
        # 1. Find the viewer session.
        # ---------------------------------------------------------

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = (
            result.scalar_one_or_none()
        )

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        # ---------------------------------------------------------
        # 2. Make sure the viewer is still connected.
        # ---------------------------------------------------------

        if viewer_session.status != "watching":
            return {
                "success": False,
                "message": "Viewer session is no longer active.",
            }

        # ---------------------------------------------------------
        # 3. Check recording permission.
        # ---------------------------------------------------------

        permission_result = await session.execute(
            select(RecordingPermission).where(
                RecordingPermission.viewer_session_id
                == viewer_session.id
            )
        )

        permission = (
            permission_result.scalar_one_or_none()
        )

        if (
            permission is None
            or not permission.allowed
        ):
            return {
                "success": False,
                "message": (
                    "Recording permission has not "
                    "been granted by the administrator."
                ),
            }

        # ---------------------------------------------------------
        # 4. Find the viewer's stream.
        # ---------------------------------------------------------

        result = await session.execute(
            select(Stream).where(
                Stream.id == viewer_session.stream_id
            )
        )

        stream = result.scalar_one_or_none()

        if stream is None:
            return {
                "success": False,
                "message": "No stream exists.",
            }

        if stream.status != "live":
            return {
                "success": False,
                "message": "The stream is not live.",
            }

        # ---------------------------------------------------------
        # 5. Make sure the stream source is running, and no
        #    other recording is already active.
        # ---------------------------------------------------------

        stream_key = str(stream.id)
        if not stream_manager.has_stream_source(stream_key):
            return {
                "success": False,
                "message": "The stream source is not running.",
            }

        active_recorder = (
            get_stream_recording_service(stream.id)
            if stream_manager.uses_browser_publisher(stream_key)
            else recording_service
        )
        if active_recorder.is_recording:
            return {
                "success": False,
                "message": "A recording is already in progress.",
            }

        # ---------------------------------------------------------
        # 6. Start the recording.
        # ---------------------------------------------------------

        try:

            source_track = stream_manager.subscribe_recording(stream_key)

            recording = active_recorder.start(
                stream_id=stream.id,
                source_track=source_track,
                viewer_session_id=viewer_session.id,
            )

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Unable to start recording: {error}"
                ),
            }

        try:
            async with AsyncSessionLocal() as log_session:
                log_session.add(
                    SecurityLog(
                        event="recording",
                        actor=f"VIEWER #{viewer_session.id}",
                        ip_address=viewer_session.ip_address,
                        detail=(
                            f"Viewer started recording "
                            f"{recording['file_name']}"
                        ),
                    )
                )
                await log_session.commit()
        except Exception:
            pass

        return {
            "success": True,
            "message": "Recording started.",
            "recording": {
                "stream_id": stream.stream_id,
                "file_name": recording["file_name"],
                "started_at": (
                    recording["started_at"].isoformat()
                ),
            },
        }


# ------------------------------------------------------------------
# VIEWER RECORDING STOP
# ------------------------------------------------------------------

@router.post("/session/{session_id}/recording/stop")
async def viewer_stop_recording(
    session_id: str,
):
    """
    Allow a viewer to stop the recording they started,
    saving it with viewer creator attribution.
    """

    async with AsyncSessionLocal() as session:

        # ---------------------------------------------------------
        # 1. Find the viewer session.
        # ---------------------------------------------------------

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = (
            result.scalar_one_or_none()
        )

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        # ---------------------------------------------------------
        # 2. Make sure a recording is active.
        # ---------------------------------------------------------

        active_recorder = (
            get_stream_recording_service(viewer_session.stream_id)
            if stream_manager.uses_browser_publisher(
                str(viewer_session.stream_id)
            )
            else recording_service
        )
        if not active_recorder.is_recording:
            return {
                "success": False,
                "message": "No recording is currently active.",
            }

        # ---------------------------------------------------------
        # 3. Only the viewer who started the recording
        #    may stop it.
        # ---------------------------------------------------------

        active = active_recorder.active_recording

        if (
            active is None
            or active.get("viewer_session_id")
            != viewer_session.id
        ):
            return {
                "success": False,
                "message": (
                    "This recording was not started "
                    "by your session."
                ),
            }

        # ---------------------------------------------------------
        # 4. Stop the recording.
        # ---------------------------------------------------------

        try:

            recording = await active_recorder.stop()

        except Exception as error:

            return {
                "success": False,
                "message": (
                    f"Unable to stop recording: {error}"
                ),
            }

        # ---------------------------------------------------------
        # 5. Save the recording with viewer attribution.
        # ---------------------------------------------------------

        recording_record = Recording(
            stream_id=recording["stream_id"],
            started_at=recording["started_at"],
            ended_at=recording["ended_at"],
            duration_seconds=recording["duration_seconds"],
            file_path=recording["file_path"],
            file_name=recording["file_name"],
            file_size_bytes=recording["file_size_bytes"],
            status="completed",
            created_by_viewer_session_id=recording[
                "viewer_session_id"
            ],
        )

        session.add(recording_record)

        session.add(
            SecurityLog(
                event="recording",
                actor=f"VIEWER #{viewer_session.id}",
                ip_address=viewer_session.ip_address,
                detail=(
                    f"Viewer stopped recording "
                    f"{recording['file_name']}"
                ),
            )
        )

        await session.commit()
        await session.refresh(recording_record)

        return {
            "success": True,
            "message": "Recording stopped.",
            "recording": {
                "id": recording_record.id,
                "stream_id": recording["stream_id"],
                "file_name": recording["file_name"],
                "file_path": recording["file_path"],
                "started_at": (
                    recording["started_at"].isoformat()
                ),
                "ended_at": (
                    recording["ended_at"].isoformat()
                ),
                "duration_seconds": (
                    recording["duration_seconds"]
                ),
                "file_size_bytes": (
                    recording["file_size_bytes"]
                ),
                "status": recording_record.status,
                "created_by_viewer_session_id": (
                    recording_record.created_by_viewer_session_id
                ),
            },
        }  
        
# ------------------------------------------------------------------
# VIEWER RECORDING PLAYBACK
# ------------------------------------------------------------------

@router.get("/session/{session_id}/recordings/{recording_id}/stream")
async def stream_viewer_recording(
    session_id: str,
    recording_id: int,
):
    """
    Stream a recording for playback, only if it was
    created by this exact viewer session.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = result.scalar_one_or_none()

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        recording_result = await session.execute(
            select(Recording).where(
                Recording.id == recording_id
            )
        )

        recording = recording_result.scalar_one_or_none()

        if (
            recording is None
            or recording.created_by_viewer_session_id
            != viewer_session.id
        ):
            return {
                "success": False,
                "message": (
                    "Recording not found for this "
                    "viewer session."
                ),
            }

    file_path = Path(recording.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Recording file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
    )


# ------------------------------------------------------------------
# VIEWER RECORDING DOWNLOAD
# ------------------------------------------------------------------

@router.get("/session/{session_id}/recordings/{recording_id}/download")
async def download_viewer_recording(
    session_id: str,
    recording_id: int,
):
    """
    Download a recording, only if it was created
    by this exact viewer session.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = result.scalar_one_or_none()

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        recording_result = await session.execute(
            select(Recording).where(
                Recording.id == recording_id
            )
        )

        recording = recording_result.scalar_one_or_none()

        if (
            recording is None
            or recording.created_by_viewer_session_id
            != viewer_session.id
        ):
            return {
                "success": False,
                "message": (
                    "Recording not found for this "
                    "viewer session."
                ),
            }

    file_path = Path(recording.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Recording file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=recording.file_name,
    )     
    
# ------------------------------------------------------------------
# VIEWER SCREENSHOT VIEW
# ------------------------------------------------------------------

@router.get("/session/{session_id}/screenshots/{screenshot_id}/view")
async def view_viewer_screenshot(
    session_id: str,
    screenshot_id: int,
):
    """
    View a screenshot, only if it was captured
    by this exact viewer session.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = result.scalar_one_or_none()

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        screenshot_result = await session.execute(
            select(Screenshot).where(
                Screenshot.id == screenshot_id
            )
        )

        screenshot = screenshot_result.scalar_one_or_none()

        if (
            screenshot is None
            or screenshot.created_by_viewer_session_id
            != viewer_session.id
        ):
            return {
                "success": False,
                "message": (
                    "Screenshot not found for this "
                    "viewer session."
                ),
            }

    file_path = Path(screenshot.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Screenshot file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="image/png",
    )


# ------------------------------------------------------------------
# VIEWER SCREENSHOT DOWNLOAD
# ------------------------------------------------------------------

@router.get("/session/{session_id}/screenshots/{screenshot_id}/download")
async def download_viewer_screenshot(
    session_id: str,
    screenshot_id: int,
):
    """
    Download a screenshot, only if it was captured
    by this exact viewer session.
    """

    async with AsyncSessionLocal() as session:

        result = await session.execute(
            select(ViewerSession).where(
                ViewerSession.session_id == session_id
            )
        )

        viewer_session = result.scalar_one_or_none()

        if viewer_session is None:
            return {
                "success": False,
                "message": "Viewer session not found.",
            }

        screenshot_result = await session.execute(
            select(Screenshot).where(
                Screenshot.id == screenshot_id
            )
        )

        screenshot = screenshot_result.scalar_one_or_none()

        if (
            screenshot is None
            or screenshot.created_by_viewer_session_id
            != viewer_session.id
        ):
            return {
                "success": False,
                "message": (
                    "Screenshot not found for this "
                    "viewer session."
                ),
            }

    file_path = Path(screenshot.file_path)

    if not file_path.exists():
        return {
            "success": False,
            "message": "Screenshot file is missing on disk.",
        }

    return FileResponse(
        path=file_path,
        media_type="image/png",
        filename=screenshot.file_name,
    ) 