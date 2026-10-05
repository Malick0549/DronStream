import base64
import hashlib
import hmac
import time

from aiortc import RTCIceServer

from backend.app.config import settings


def _turn_credentials() -> tuple[str, str] | None:
    if not settings.turn_urls or not settings.turn_shared_secret:
        return None

    expires_at = int(time.time()) + settings.turn_credential_ttl_seconds
    username = f"{expires_at}:dronestream"
    digest = hmac.new(
        settings.turn_shared_secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    credential = base64.b64encode(digest).decode("ascii")
    return username, credential


def create_ice_servers() -> list[RTCIceServer]:
    if settings.environment.lower() in {"development", "dev"} and settings.force_loopback:
        return []

    servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
    ]
    credentials = _turn_credentials()
    if credentials is not None:
        username, credential = credentials
        servers.append(
            RTCIceServer(
                urls=settings.turn_urls,
                username=username,
                credential=credential,
            )
        )
    return servers


def public_ice_config() -> dict:
    servers = create_ice_servers()
    return {
        "iceServers": [
            {
                "urls": server.urls,
                **({"username": server.username} if server.username else {}),
                **({"credential": server.credential} if server.credential else {}),
            }
            for server in servers
        ]
    }
