DroneStream

Secure Live Aerial Streaming Platform

DroneStream is a web platform for securely broadcasting a live drone/controller video feed to authorized remote viewers. It provides administrator stream control, secure viewer links, viewer monitoring, WebRTC delivery, recording permissions, recording management, and operational telemetry.

Deployment status: The repository is suitable for GitHub and cloud deployment testing. The current development media source uses a local test video/FFmpeg pipeline. Production use requires the planned capture-card/video-ingest path, production WebRTC networking (including ICE/TURN where required), persistent media storage, and final security hardening.

Architecture

Drone → Drone Controller → HDMI/Video Output → Capture Card
                                             ↓
                                      Streaming Computer
                                             ↓
                                    Production Media Ingest
                                             ↓
                                      DroneStream Backend
                                             ↓
                                            WebRTC
                                             ↓
                                        Remote Viewers

During development, a looping test video is used instead of the production capture card.

Core Features

Administrator

Secure administrator login/session management

Create, start, and stop streams

Generate and revoke secure viewer links

Monitor active viewer sessions and duration

View connection/device information collected by the application

View stream health and WebRTC telemetry

Control recording permission per viewer session

Review recording history where recording storage is enabled

Administrative logout

Viewer

Secure token-based stream access

WebRTC live video playback

Viewer session tracking

Recording/screenshot controls only when authorized by the backend

Technology Stack

Backend: Python, FastAPI, SQLAlchemy, PostgreSQL, asyncpg, Pydantic, aiortc, FFmpeg/PyAV

Frontend: React, Vite, JavaScript, browser WebRTC APIs

Database: PostgreSQL

Streaming Pipeline

Media Input
    ↓
FFmpeg / Media Source
    ↓
StreamManager
    ↓
MediaRelay
    ↓
aiortc WebRTC
    ↓
Viewer Browsers

A shared media source is used so multiple viewers receive the same stream rather than starting a separate media process for every viewer.

Database

The application uses PostgreSQL. Core tables include:

admins
streams
stream_links
viewer_sessions
viewer_events
recording_permissions

Additional recording/screenshot tables are used as those features are enabled.

The application reads the database connection from DATABASE_URL.

DATABASE_URL=postgresql+asyncpg://USERNAME:PASSWORD@HOST:5432/DATABASE

Never commit a real database password or other production secrets to GitHub.

Local Development

Backend

Activate the virtual environment:

.venv\Scripts\Activate.ps1

Start FastAPI:

python -m uvicorn backend.app.main:app --reload

Useful development URLs:

http://127.0.0.1:8000
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health
http://127.0.0.1:8000/health/database

Frontend

From the frontend directory:

npm install
npm run dev

The Vite development server normally runs at:

http://localhost:5173

Database initialization

python -m backend.app.init_db
python -m backend.check_db

API Areas

/api/auth
/api/streams
/api/viewer
/api/admin
/api/webrtc

Examples:

POST /api/streams/create
POST /api/streams/start
POST /api/streams/stop
GET  /api/streams/status
POST /api/streams/viewer-link

The running FastAPI OpenAPI documentation is the authoritative API contract.

Security

DroneStream uses backend authorization as the security boundary.

Viewer tokens are generated securely and can be revoked/expired.

Administrator routes require a valid administrator session.

The administrator session is stored in an HTTP-only cookie.

Recording permission is associated with an individual ViewerSession.

Frontend controls are not treated as security controls.

IP-based location is approximate; exact GPS requires explicit browser permission.

For production, use HTTPS, secure cookies, strong secret management, password hashing, rate limiting, security headers, CSRF protection where applicable, audit/security logging, and protected media storage.

Production Deployment

DroneStream is more demanding than a normal CRUD application because it contains a real-time WebRTC media path and a physical video-ingest requirement.

Recommended final architecture

Admin/Drone Controller + Capture Card
                ↓
        Production Ingest Server
                ↓
       FastAPI + aiortc/WebRTC
          ↙              ↘
     PostgreSQL       Media Storage
                ↓
          Remote Viewers

The production streaming server should provide control over the networking and media processes required by WebRTC/FFmpeg.

Render

Render is suitable for the FastAPI web service, React frontend, and managed PostgreSQL. It supports Python/FastAPI services, HTTPS, WebSockets, Git-based deployment, environment variables, and managed PostgreSQL.

For DroneStream, however, do not treat a Render-only deployment as the final media architecture yet. The current development source is local FFmpeg/test-video based, and the production WebRTC media path needs to be validated with the final networking and ingest design.

A cloud VM/VPS with suitable networking control is the better final target for the actual streaming/media server. Render can still be used for application/database staging or for components that do not require the production media path.

Environment Variables

Production secrets must be configured through the hosting provider rather than committed to Git.

Typical production configuration includes:

DATABASE_URL=
CORS_ORIGINS=
ADMIN_USERNAME=
ADMIN_PASSWORD=
SESSION_SECRET=
FFMPEG_PATH=
MEDIA_STORAGE_PATH=

Do not put passwords, session secrets, or database credentials in frontend code or README files.

Production Checklist

Remove development credentials and hardcoded secrets

Use HTTPS everywhere

Enable secure administrator cookies

Use password hashing for persistent administrator accounts

Configure production CORS origins

Add rate limiting

Add security headers

Add audit/security logging

Protect recording and screenshot files

Configure persistent media storage

Configure database backups

Replace test-video input with production capture-card/media ingest

Configure and test ICE/TURN for remote WebRTC connectivity where required

Test multiple remote viewers

Test revoked and expired viewer links

Test unauthorized recording attempts

Test administrator session expiry

Test recovery after server restart

Test deployment from a clean environment

Project Structure

DroneStream/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── database/
│   │   ├── models/
│   │   ├── recordings/
│   │   ├── security/
│   │   ├── services/
│   │   ├── streaming/
│   │   ├── viewers/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── src/
├── streaming/
├── database/
├── docs/
├── tests/
├── project_master.md
└── README.md

Development Media Source

The development environment uses a test video so the WebRTC pipeline can be tested without the production capture card. This source is not the final drone input.

The production implementation should replace it with the actual capture-card/video-ingest path without changing the viewer authorization model.

Deployment Workflow

Remove secrets and machine-specific production configuration.

Add/update .gitignore and .env.example.

Push the project to a private GitHub repository.

Deploy the application/database components to a cloud environment.

Verify authentication, database connectivity, stream creation, viewer links, viewer sessions, and telemetry.

Deploy and validate the production media ingest/WebRTC infrastructure.

Complete security, storage, backup, and recovery testing.

Only then expose the system to real drone viewers.

Project Status

DroneStream is an active development project. The core application foundation includes FastAPI, PostgreSQL/SQLAlchemy, React/Vite, administrator authentication, stream management, secure viewer links, viewer monitoring, aiortc WebRTC delivery, shared media streaming, telemetry, and recording-permission controls.

Production launch additionally requires validation of the real capture-card ingest, production WebRTC networking, persistent media storage, and final security hardening.

License

Add the project's chosen license before making the repository public.