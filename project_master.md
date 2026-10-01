# DroneStream — Project Master Document

## 1. Project Overview

DroneStream is a secure web-based live streaming platform designed to broadcast live video and images captured from a drone.

The initial video path is:

Drone
    ↓
Drone Controller
    ↓
HDMI / Video Output
    ↓
Capture Card
    ↓
Admin PC
    ↓
FFmpeg / Streaming Pipeline
    ↓
DroneStream Server
    ↓
Internet
    ↓
Authorized Viewers

The capture card is not available during initial development. Development will therefore use a local test video source until the capture card is connected.

---

# 2. Main Objectives

DroneStream must allow an authorized administrator to:

- Start and stop a live stream.
- Generate secure viewing links.
- Share viewing links with people anywhere.
- See the live video feed.
- Monitor connected viewers.
- See when viewers open the stream.
- Track viewing duration.
- Identify viewer device type.
- Identify browser.
- Determine approximate viewer location where legally/technically possible.
- View viewer activity.
- Record the live stream when permitted.
- Capture still images when permitted.
- Project the stream on a large display.
- Control viewer permissions.
- Revoke stream links.
- Terminate a live stream immediately.
- Review security and audit logs.

---

# 3. Important Privacy Rules

Viewer location must be handled carefully.

IP-based location is approximate and may identify a country, region, or city.

Exact GPS coordinates must NOT be collected without explicit browser permission and a legitimate reason.

The system must not secretly access device GPS.

Viewer information must be collected according to applicable privacy laws and the platform's privacy policy.

---

# 4. Core Architecture

## Backend

Technology:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Pydantic

Responsibilities:

- Authentication
- Authorization
- Stream management
- Secure stream links
- Viewer sessions
- Viewer analytics
- Permissions
- Recording management
- Screenshot management
- Audit logging
- Security events
- API endpoints

---

# 5. Frontend

Initial technology:

- React
- Vite
- JavaScript/TypeScript

Frontend areas:

## Admin

- Login
- Dashboard
- Stream control
- Live preview
- Viewer monitoring
- Viewer analytics
- Recording controls
- Screenshot controls
- Stream-link management
- Permission management
- Security logs
- Audit logs
- Settings

## Viewer

- Secure stream page
- Live video player
- Stream status
- Full-screen mode
- Connection status
- Optional permitted controls

---

# 6. Streaming Architecture

Initial development:

Test Video
    ↓
FFmpeg
    ↓
Streaming Server
    ↓
Browser

Production:

Drone
    ↓
Controller
    ↓
Capture Card
    ↓
Admin PC
    ↓
FFmpeg
    ↓
WebRTC / Streaming Infrastructure
    ↓
DroneStream
    ↓
Viewer

The system should prioritize low latency.

WebRTC is the preferred technology for interactive low-latency live video.

Other streaming technologies may be introduced where appropriate.

---

# 7. FFmpeg

FFmpeg is responsible for:

- Video input
- Video encoding
- Video transcoding
- Hardware acceleration where available
- Recording
- Screenshot extraction
- Stream processing

The installed development environment currently has FFmpeg 9.x available.

---

# 8. Authentication

Administrative accounts must use:

- Secure password hashing
- Strong passwords
- Secure sessions
- HTTP-only cookies where applicable
- CSRF protection where applicable
- Rate limiting
- Account lockout / throttling
- Optional MFA
- Audit logging

Passwords must never be stored in plaintext.

Preferred password hashing:

Argon2id

---

# 9. Stream Security

Every stream must have a unique secure identifier.

Viewer links must use cryptographically secure random tokens.

Stream links should support:

- Expiration
- Revocation
- Permission control
- Optional viewer limits
- Optional password protection
- Audit logging

Administrative controls must always remain server-side.

Never rely solely on frontend JavaScript for authorization.

---

# 10. Viewer Tracking

The system should record viewer sessions.

Possible information:

- Session ID
- Stream ID
- Connection time
- Disconnect time
- Watch duration
- IP address
- Approximate location
- Device type
- Operating system
- Browser
- User agent
- Referrer where appropriate
- Viewer events

Privacy requirements must always be considered.

---

# 11. Database

PostgreSQL will be the primary database.

Planned tables include:

- admins
- users
- streams
- stream_links
- viewer_sessions
- viewer_events
- devices
- locations
- permissions
- recordings
- screenshots
- audit_logs
- security_events
- stream_settings

Database design must support future scaling.

---

# 12. Recording

Authorized users may be allowed to record live streams.

Recording must support:

- Start recording
- Stop recording
- Recording status
- Recording metadata
- Secure storage
- Download authorization
- Audit logging

---

# 13. Screenshots

Authorized users may capture still images from the live stream.

Each screenshot should contain:

- Screenshot ID
- Stream ID
- Timestamp
- Creator
- Storage location
- Optional metadata

---

# 14. Projector Mode

DroneStream must provide a projector/display mode.

Requirements:

- Large video display
- Minimal interface
- Full-screen support
- Stream status
- Optional overlay
- Stable playback

This allows the live drone feed to be displayed on a projector, television, monitor, or large screen.

---

# 15. Security Requirements

Security is a primary requirement.

The application should use:

- HTTPS
- Secure cookies
- CSRF protection
- Content Security Policy
- Security headers
- Input validation
- Output encoding
- SQL injection protection
- Rate limiting
- Authentication
- Authorization
- Secure password hashing
- Secure random tokens
- Audit logs
- Security event logs
- Session expiration
- Stream-link expiration
- Stream revocation
- File access controls
- Server-side permission checks

Secrets must never be committed to Git.

Environment variables should be used for:

- Database credentials
- Secret keys
- API keys
- Encryption keys
- Deployment credentials

---

# 16. Folder Structure

DroneStream/

backend/
    app/
        api/
        auth/
        database/
        models/
        services/
        streaming/
        viewers/
        recordings/
        security/
        main.py
    tests/

frontend/
    src/
        components/
        pages/
        admin/
        viewer/
        services/
        utils/

streaming/
    config/
    scripts/
    recordings/

database/
    migrations/
    schema/

docs/
    architecture/
    security/
    api/

tests/

project_master.md

---

# 17. Development Phases

## Phase 1 — Foundation

- Project structure
- Backend
- Database connection
- Configuration
- Environment variables
- Basic API

## Phase 2 — Authentication

- Admin registration
- Login
- Logout
- Password hashing
- Sessions
- Authorization

## Phase 3 — Test Streaming

- Local video source
- FFmpeg
- Streaming server
- Browser playback

## Phase 4 — Stream Management

- Create stream
- Start stream
- Stop stream
- Stream status
- Secure stream IDs

## Phase 5 — Secure Viewer Links

- Generate links
- Expiration
- Revocation
- Viewer permissions

## Phase 6 — Viewer Analytics

- Viewer sessions
- Connection/disconnection
- Watch duration
- Device
- Browser
- Approximate location

## Phase 7 — Recording

- Start recording
- Stop recording
- Recording storage
- Recording permissions

## Phase 8 — Screenshots

- Capture image
- Image storage
- Permissions
- Metadata

## Phase 9 — Projector Mode

- Full-screen viewing
- Display mode
- Minimal interface

## Phase 10 — Capture Card

Replace the test video source with:

Capture Card → FFmpeg → DroneStream

## Phase 11 — Security Hardening

- HTTPS
- Security headers
- Rate limits
- CSRF
- CSP
- Audit logging
- Security testing
- Penetration testing
- Secure deployment

## Phase 12 — Production Deployment

- Production server
- Domain
- HTTPS
- Database backups
- Monitoring
- Logging
- Recovery procedures

---

# 18. Development Rules

1. Do not remove existing functionality without explicit approval.
2. Do not change architecture unnecessarily.
3. Do not guess when a technical detail can be verified.
4. Test every major feature.
5. Keep secrets out of source code.
6. Use environment variables for sensitive configuration.
7. Server-side authorization is mandatory.
8. Security must be considered before production deployment.
9. Maintain backward compatibility where practical.
10. Update this document when major architecture decisions change.

---

# 19. Current Development Status

Environment:

- Windows 11
- Python 3.13 / FastAPI / PostgreSQL / React (Vite)
- FFmpeg available on PATH
- WebRTC via aiortc + MediaRelay shared source
- Test video: `streaming/recordings/test-drone.mp4` (or path used by `VIDEO_FILE`)
- Capture card: optional via Settings (`use_capture_card` + `capture_device_name`)

## Implemented (MVP+)

Admin

- Login / logout (HTTP-only session cookie) + security log
- Dashboard: create / start / stop stream
- Live WebRTC preview on dashboard
- Record / stop record / screenshot under live card
- Secure viewer links: generate, optional expiry hours, **optional password**, revoke
- Viewer monitoring: status (Watching, Kicked, Disconnected, Timed out, Link revoked, Stream ended), kick
- Recordings & screenshots lists (play/view/download)
- Settings: default screenshot/record, max viewers, auto-record, capture-card toggle + device name
- Security logs + event filter dropdown
- Projector mode (`/admin/projector`)

Viewer (`/watch/{token}`)

- Password gate when link is password-protected
- Live WebRTC video
- Permissioned screenshot / recording
- Fullscreen / PiP
- Session status poll (kick / revoke / stop stream ends access)
- Media panel for last capture (download / close)

Backend / security

- PostgreSQL source of truth for streams, links, sessions, media, settings, security_logs
- SecurityLog for: login/logout, stream start/stop, link generate/revoke, password fail, viewer connect/disconnect/kick/timeout, recording, screenshot, permissions, settings
- Heartbeat + stale timeout (~20s) for closed tabs
- `stream_state` kept for WebRTC token/status compatibility

WebRTC / ICE

- Local default: `DRONESTREAM_FORCE_LOOPBACK=1` (127.0.0.1 candidates)
- Production: set `DRONESTREAM_FORCE_LOOPBACK=0` and use Google STUN on server + browser
- Frontend uses STUN only when hostname is not localhost / 127.0.0.1

## Not required for local MVP (optional later)

- IP → country/region geolocation columns UI
- Watermark on screenshots/recordings
- TURN server for strict NAT
- MFA, full CSRF/CSP hardening, penetration test report
- Production deploy (domain, HTTPS, backups, systemd)

## How to run (dev)

```powershell
# API
cd C:\Users\ABDUL MALIK\Desktop\DroneStream
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload

# Frontend (separate terminal)
cd frontend   # or project root if Vite is there
npm run dev