# Home Hosting From Windows

This is an optional no-VPS route. The Windows PC stays on as the host; remote broadcasters use its HTTPS site from their own browsers. The capture card remains attached to the broadcaster's device, not to the Ubuntu VM.

## Recommended Layout

- Windows PC runs Oracle VirtualBox.
- An Ubuntu Server VM runs the Docker Compose stack from this project.
- The VM network adapter is bridged to the home LAN so it gets its own LAN IP.
- A free dynamic DNS hostname points to the home's public IP.
- The router forwards HTTPS and TURN traffic to the VM.

Use Ubuntu Server, not Kali. Kali is a security-testing distribution and does not provide a benefit for this web/media server.

## Important ISP Check

Before setting this up, compare the router's WAN IPv4 address with the public IPv4 shown by a reputable IP-check site. If they differ, or the router WAN address is in `100.64.0.0/10`, the ISP may be using CGNAT. Standard home router port forwarding will not work through CGNAT; ask the ISP for a public IPv4 or use a relay/hosting provider that supports UDP.

Also confirm that the ISP allows inbound connections. Streaming uses upload bandwidth from the host's internet connection, so each viewer consumes additional upstream capacity.

## Install and Transfer

1. Install VirtualBox and create an Ubuntu Server VM. Give it at least 2 CPU cores, 4 GB RAM, and 50 GB disk for a small test. Increase resources for concurrent streams, recordings, or higher resolutions.
2. Set the VM network adapter to **Bridged Adapter** and note the VM's stable LAN IPv4 address. Reserve that address in the router's DHCP settings.
3. On the current Windows project folder, double-click `Prepare-DroneStream-Transfer.ps1` or run it from PowerShell. It creates `Desktop\DroneStream-source.zip`, including current workspace edits but excluding `.env`, caches, and saved media.
4. Copy and extract the ZIP inside Ubuntu. Install Docker Engine and the Docker Compose plugin using Docker's official Ubuntu instructions.
5. In the Ubuntu project folder, copy `.env.example` to `.env` and replace every placeholder. Keep all secrets on the VM; do not put them in the source ZIP or chat.
6. Set `DOMAIN` and `CORS_ORIGINS` to the public hostname. Set `TURN_URLS` to that hostname on port 3478. Set `TURN_EXTERNAL_IP` to `PUBLIC_IPV4/VM_LAN_IPV4` (for example, `198.51.100.20/192.168.1.50`). Keep `FORCE_LOOPBACK=false`.

## DNS, Router, and Firewall

1. Use a free dynamic DNS provider that supports a hostname you control. Configure its updater on Windows or the VM to keep the hostname's `A` record pointed at the home public IPv4.
2. In the router, forward **TCP 80 and 443** to the VM LAN IPv4.
3. Forward **UDP and TCP 3478** and **UDP 49160-49260** to the VM. The UDP relay range is necessary for TURN media.
4. Allow the same ports through Ubuntu's firewall. Do not expose PostgreSQL port 5432 or the API's internal port 8000 publicly.
5. Check that the VM's OCI/Docker host firewall and router rules agree. Run `docker compose config --quiet`, then `docker compose build` and `docker compose up -d`.

Caddy obtains HTTPS certificates automatically when the public DNS name resolves to the home IP and TCP ports 80/443 are reachable. HTTPS is required for browsers to grant capture-device access on remote devices.

## What Has to Stay On

The Windows host and Ubuntu VM must stay powered on and connected. Set Windows sleep to **Never while plugged in**. Docker services use `restart: unless-stopped`, so they restart after a VM reboot, but an active stream ends during a reboot and the broadcaster must reconnect.

## Existing Accounts and Files

The transfer ZIP contains source, not the live PostgreSQL database or saved media. The source code keeps all application features; existing admin/broadcaster accounts, streams, links, recordings, and screenshots remain on the old machine until separately migrated.

Back up PostgreSQL with `pg_dump` and restore it into the VM's PostgreSQL service. Copy `backend/recordings/saved` and `backend/screenshots/saved` separately if you need those files. Keep database dumps and `.env` private. Test a backup copy before replacing any database.

## Reliability Limits

Home hosting is free of a VPS bill, but depends on the home's power, router, ISP upload speed, and public IPv4. Free dynamic DNS can change hostnames briefly during IP updates. CGNAT or blocked inbound UDP prevents direct public WebRTC unless an external TURN/media relay is used.