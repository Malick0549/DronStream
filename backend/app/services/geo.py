"""Approximate country/region from IP (no GPS)."""

from __future__ import annotations

import ipaddress
import urllib.request
import json


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.strip())
        return addr.is_global
    except Exception:
        return False


def lookup_ip_location(ip: str | None) -> dict:
    """
    Returns {country, region, city} or empty strings.
    Uses free ip-api.com (no key). Skips private/local IPs.
    """
    empty = {"country": None, "region": None, "city": None}
    if not ip or ip in ("unknown", "127.0.0.1", "::1"):
        return empty
    if not _is_public_ip(ip):
        return empty

    url = (
        f"http://ip-api.com/json/{ip}"
        "?fields=status,country,regionName,city"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DroneStream/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "success":
            return empty
        return {
            "country": data.get("country") or None,
            "region": data.get("regionName") or None,
            "city": data.get("city") or None,
        }
    except Exception as err:
        print("DroneStream: geo lookup skip:", repr(err))
        return empty