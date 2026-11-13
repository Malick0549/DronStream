"""
WebSocket media relay.

The broadcaster page sends video segments (binary WebSocket messages)
to the server. The server forwards each segment to every viewer that
is connected to the same stream. The server never decodes the video.

Because this uses WebSockets, it travels through the Cloudflare tunnel
like any web page. No TURN server, UDP or open router ports are needed.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.app.auth.dependencies import get_current_broadcaster
from backend.app.database import AsyncSessionLocal
from backend.app.models.account import StreamOwnership
from backend.app.models.stream import Stream
from backend.app.models.viewer import StreamLink, ViewerSession


router = APIRouter(prefix="/api/relay", tags=["Relay"])

# A viewer is re-checked this often so kicked, revoked or stopped
# viewers are disconnected even though they keep the socket open.
VIEWER_RECHECK_SECONDS = 5


class StreamHub:
    """Everything the relay remembers about one live stream."""

    def __init__(self):
        self.mime = None          # e.g. 'video/webm;codecs=vp8'
        self.last_segment = None  # newest segment, sent to new viewers
        self.viewers = set()      # connected viewer WebSockets
        self.publisher = None     # the broadcaster WebSocket


hubs: dict[str, StreamHub] = {}


def get_hub(stream_key: str) -> StreamHub:
    hub = hubs.get(stream_key)
    if hub is None:
        hub = StreamHub()
        hubs[stream_key] = hub
    return hub


async def _authorize_viewer(token: str, session_id: str):
    """Same rules as POST /api/webrtc/offer for a viewer session.

    Returns the stream key (database id as text) or None.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ViewerSession, Stream, StreamLink)
            .join(Stream, Stream.id == ViewerSession.stream_id)
            .join(StreamLink, StreamLink.id == ViewerSession.stream_link_id)
            .where(
                ViewerSession.session_id == session_id,
                ViewerSession.status == "watching",
                StreamLink.token == token,
                StreamLink.revoked_at.is_(None),
                Stream.status == "live",
            )
        )
        row = result.first()
    if row is None:
        return None
    _, stream, link = row
    if link.expires_at is not None and now >= link.expires_at:
        return None
    return str(stream.id)


async def _authorize_publisher(websocket: WebSocket, stream_id: str):
    """The broadcaster must be signed in and own the stream.

    Returns the stream key (database id as text) or None.
    """
    try:
        account = await get_current_broadcaster(websocket)
    except Exception:
        return None
    if not (account.can_start_streams and account.can_publish_browser):
        return None

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stream)
            .join(StreamOwnership, StreamOwnership.stream_id == Stream.id)
            .where(
                Stream.stream_id == stream_id,
                StreamOwnership.account_id == account.id,
            )
        )
        stream = result.scalar_one_or_none()
    if stream is None or stream.status not in {"starting", "live"}:
        return None
    return str(stream.id)


@router.websocket("/publish/{stream_id}")
async def relay_publish(websocket: WebSocket, stream_id: str):
    stream_key = await _authorize_publisher(websocket, stream_id)
    if stream_key is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    hub = get_hub(stream_key)
    if hub.publisher is not None:
        # Only one broadcaster per stream.
        await websocket.close(code=4409)
        return
    hub.publisher = websocket
    hub.last_segment = None
    print(f"DroneStream relay: publisher connected for stream {stream_key}")

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("text") is not None:
                # The first text message is the codec, for example
                # 'video/webm;codecs=vp8'. Viewers need it for playback.
                hub.mime = message["text"]
                for viewer in list(hub.viewers):
                    try:
                        await viewer.send_text(hub.mime)
                    except Exception:
                        hub.viewers.discard(viewer)
                continue

            data = message.get("bytes")
            if not data:
                continue

            hub.last_segment = data
            for viewer in list(hub.viewers):
                try:
                    await viewer.send_bytes(data)
                except Exception:
                    hub.viewers.discard(viewer)
    except WebSocketDisconnect:
        pass
    finally:
        print(f"DroneStream relay: publisher left stream {stream_key}")
        hub.publisher = None
        hub.last_segment = None
        for viewer in list(hub.viewers):
            try:
                await viewer.close(code=4410)  # stream ended
            except Exception:
                pass
        hub.viewers.clear()
        hubs.pop(stream_key, None)


@router.websocket("/watch")
async def relay_watch(websocket: WebSocket, token: str, session_id: str):
    stream_key = await _authorize_viewer(token, session_id)
    if stream_key is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    hub = get_hub(stream_key)
    hub.viewers.add(websocket)
    print(f"DroneStream relay: viewer joined stream {stream_key}")

    try:
        # Catch the new viewer up: codec first, then the newest segment.
        if hub.mime:
            await websocket.send_text(hub.mime)
        if hub.last_segment:
            await websocket.send_bytes(hub.last_segment)

        while True:
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=VIEWER_RECHECK_SECONDS,
                )
            except asyncio.TimeoutError:
                still_allowed = await _authorize_viewer(token, session_id)
                if still_allowed != stream_key:
                    await websocket.close(code=4403)
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.viewers.discard(websocket)
        print(f"DroneStream relay: viewer left stream {stream_key}")
