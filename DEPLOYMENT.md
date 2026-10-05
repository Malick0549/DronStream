# DroneStream Staging Deployment

This stack is intended for a single Linux VPS running one DroneStream API process. The app keeps live peer connections and legacy admin sessions in process memory, so do not increase the API worker count or run multiple API replicas.

## Prerequisites

- Ubuntu 24.04 or another supported Linux VPS with Docker Engine and the Docker Compose plugin.
- A domain name with an `A` record pointing to the VPS public IPv4 address.
- Firewall access for TCP 80 and 443, UDP 443, TCP/UDP 3478, and UDP 49160-49260. These are used by HTTPS, HTTP/3, TURN, and TURN relay allocations.
- A browser on the broadcaster device that supports WebRTC and `getUserMedia`. Device capture requires HTTPS except on localhost.

Use a VPS for staging rather than a generic PaaS: the deployment needs control of UDP ports for WebRTC/TURN and enough CPU for media encoding. The capture card is selected in the broadcaster's browser on the device physically connected to it; the card is not passed through to the server container.

## Configure

1. Point the staging domain at the VPS and allow DNS to propagate.
2. Copy `.env.example` to `.env` on the VPS. Replace every `CHANGE_ME` value with a unique random secret. For example, generate values with `openssl rand -hex 32`; do not reuse a password across admin, database, and TURN settings.
3. Set `DOMAIN` to the exact public hostname. Set `CORS_ORIGINS` to a JSON array containing only `https://<hostname>`. Set `TURN_URLS` to the same hostname on port 3478 for UDP and TCP.
4. Keep `ENVIRONMENT=production` and `FORCE_LOOPBACK=false`. The latter is required so signaling does not rewrite ICE candidates to localhost.
5. Keep `.env` on the server only. Do not commit or send it through chat.

## Start Staging

From the repository root on the VPS:

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 api caddy turn
```

Caddy obtains and renews the HTTPS certificate after DNS and ports 80/443 are reachable. The API creates missing tables at startup; `create_all` is additive and does not alter or delete existing rows. For staging, use a fresh database or a restored database copy, not the production database.

## First-Run Checks

1. Open `https://<hostname>/health` and confirm `{"status":"healthy"}`.
2. Sign into the administrator UI using `ADMIN_USERNAME` and `ADMIN_PASSWORD` from the server `.env`.
3. Open **Broadcasters**, create a short-lived invite, and use it at `/broadcast?invite=...` on the broadcaster device.
4. Sign in at `/broadcast`, select the capture device, create a stream, and start the broadcast. Accept the browser's camera/capture permission prompt.
5. Open the generated `/watch/<token>` link in a separate browser and verify video, viewer counts, permission controls, recording, screenshots, and link revocation.
6. Test from a network outside the VPS LAN. Confirm both peers obtain relay candidates and that media works through TURN.
7. Restart the stack and verify database rows and saved media remain present. A VPS/container restart intentionally ends live WebRTC sessions; broadcasters must start again.

## Persistent Data and Recovery

PostgreSQL uses the `postgres_data` named volume. Recordings and screenshots are stored under `backend/recordings/saved` and `backend/screenshots/saved` and mounted from the VPS filesystem. Back up the database and both media directories before upgrades. To restore or migrate an existing database, test a backup copy first; do not point staging at the active local database.

## Limits Before Production

- One API process is required because active peer connections, stream relays, heartbeat maps, and legacy admin sessions are in memory.
- A process restart stops active broadcasts and invalidates legacy admin sessions, though database-backed broadcaster sessions and persistent records remain.
- The API currently relies on SQLAlchemy `create_all`, not versioned schema migrations. Review schema changes and take tested backups before production upgrades.
- The media path uses aiortc/libvpx software encoding. Load-test the target resolution and expected simultaneous broadcasters/viewers on the chosen VPS before advertising capacity.
- Configure VPS firewall rules as well as Docker ports; TURN relay UDP ports must be reachable from viewer networks.
- The staging stack has not been executed in this workspace because Docker is not installed here. Validate `docker compose config`, image builds, TLS issuance, and cross-network WebRTC on the VPS before calling the deployment production-ready.
